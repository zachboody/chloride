from gevent.monkey import patch_all
patch_all()
from gevent import Greenlet, sleep
from gevent.queue import Queue as GQueue
from multiprocessing import Process, Queue
from multiprocessing.queues import Empty
import os
import zerorpc
import json
import logging
from copy import deepcopy
from salt.client.api import APIClient
from salt.exceptions import EauthAuthenticationError


def get_opts():
    '''Return the salt master config.'''
    import salt.config

    return salt.config.client_config(
        os.environ.get('SALT_MASTER_CONFIG', '/etc/salt/master'))


__virtualname__ = 'zerorpc'
log = logging.getLogger(__virtualname__)
if '__opts__' not in globals():
        __opts__ = get_opts()


class InvalidMessage(Exception):
    def __init__(self, message, errors=[]):
        super(InvalidMessage, self).__init__(message)
        self.errors = errors


def __virtual__():
    mod_opts = __opts__.get(__virtualname__, {})

    if 'port' in mod_opts:
        return __virtualname__

    return False


def start():
    '''Start up the server.'''
    # When started outside of salt-api __opts__ won't get injected
    if '__opts__' not in globals():
        globals()['__opts__'] = get_opts()

    if __virtual__ is False:
        raise SystemExit(1)

    mod_opts = __opts__.get(__virtualname__, {})

    s = zerorpc.Server(ZeroServer())
    s.bind("tcp://0.0.0.0:{0}".format(mod_opts['port']))
    print "Starting RPC server on port: {0}".format(mod_opts['port'])
    s.run()


def subprocess_read_events(q):
    from salt.client.api import APIClient
    import json
    from time import sleep

    client = APIClient()
    stream = client.event.iter_events(full=True)
    while True:
        data = stream.next()
        if data:
            data['type'] = 'event'
            try:
                q.put(json.dumps(data))
            except UnicodeDecodeError:
                pass
        sleep(0.1)


def process_events(wss):
        while True:
            try:
                d = wss.event_queue.get_nowait()
            except Empty:
                sleep(0.2)
                continue
            if d:
                try:
                    wss.broadcast_event(d)
                except Exception as e:
                    print e.message


class ZeroServer(object):

    event_listeners = set()
    event_queue = Queue()

    def __init__(self, *args, **kwargs):
        self.SaltClient = APIClient()
        self.event_listener_proc = Process(target=subprocess_read_events, args=(self.event_queue,))
        self.event_listener_proc.start()
        self.event_processor = Greenlet.spawn(process_events, self)
        super(ZeroServer, self).__init__(*args, **kwargs)

    def __del__(self, *args, **kwargs):
        self.event_listener_proc.kill()
        self.event_processor.kill()
        super(ZeroServer, self).__del__(*args, **kwargs)

    def validate_token(self, token):
        r = self.SaltClient.verify_token(token)
        if not r:
            r = {"start": '', "token": token, "expire": '', "name": '', "eauth": '', "valid": False}
        else:
            r['valid'] = True
        return r

    @zerorpc.stream
    def event_stream(self, token):
        v = self.validate_token(token)
        if v.get('valid', False):
            try:
                q = GQueue()
                self.event_listeners.add(q)
                for msg in q:
                    yield msg
            finally:
                self.event_listeners.remove(q)

    def auth(self, username, password, eauth='pam'):
        '''Authenticates a user against external auth and returns a token.'''
        try:
            token = self.SaltClient.create_token({
                'username': username,
                'password': password,
                'eauth': eauth
            })
        except:
            token = {
                'error': 'Invalid credentials',
                'details': 'Authentication failed with provided credentials.'
            }

        return token

    def cmd(self, cmdmesg):
        u = self.validate_token(cmdmesg['token'])
        if not u['valid']:
            raise EauthAuthenticationError("Invalid token")
        retval = self.SaltClient.run(cmdmesg)
        echodict = deepcopy(cmdmesg)
        echodict.pop('token')
        if cmdmesg.get('mode', 'async') == 'async':
            echodict['minions'] = retval['minions']
            echodict['jid'] = retval['jid']
        else:
            echodict['result'] = retval
        echodict['username'] = u['name']
        return echodict

    def runner_sync(self, cmdmesg):
        u = self.validate_token(cmdmesg['token'])
        if not u['valid']:
            raise EauthAuthenticationError("Invalid token")
        # elif '@runner' not in u['perms']:
            # raise EauthAuthenticationError("Insufficient permissions")
        resp = self.SaltClient.runnerClient.cmd(cmdmesg['fun'], cmdmesg['arg'])
        return resp

    def signature(self, tgt, module, token):
        cdict = {}
        cdict['tgt'] = tgt
        cdict['module'] = module
        cdict['token'] = token
        j = self.SaltClient.signature(cdict)
        resp = self.get_job(j['jid'])
        while len(resp) == 0:
            sleep(1)
            resp = self.get_job(j['jid'])
        return resp

    def get_job(self, jid):
        resp = self.SaltClient.runnerClient.cmd('jobs.lookup_jid', [jid])
        return resp

    def get_active(self):
        resp = self.SaltClient.runnerClient.cmd('jobs.active', [])
        return resp

    def broadcast_event(self, e):
        for q in self.event_listeners:
            q.put_nowait(json.loads(e))


if __name__ == '__main__':
    start()
