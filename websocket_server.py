from gevent.monkey import patch_all
patch_all()
from gevent import Greenlet, sleep
from multiprocessing import Process, Queue
from multiprocessing.queues import Empty
import os
from geventwebsocket import WebSocketServer, WebSocketApplication, Resource
import json
import logging
from time import time
from salt.client.api import APIClient
from salt.exceptions import EauthAuthenticationError
import hashlib


def get_opts():
    '''Return the salt master config.'''
    import salt.config

    return salt.config.client_config(
        os.environ.get('SALT_MASTER_CONFIG', '/etc/salt/master'))


__virtualname__ = 'websocket'
log = logging.getLogger(__virtualname__)
if '__opts__' not in globals():
        __opts__ = get_opts()


class InvalidMessage(Exception):
    def __init__(self, message, errors):
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

    WebSocketServer(
        ('', mod_opts['port']),
        Resource({'/': SocketApplication})
    ).serve_forever()


def subprocess_read_events(q):
    from salt.client.api import APIClient
    import json
    from time import sleep

    client = APIClient()
    stream = client.event.iter_events(full=True)
    while True:
        data = stream.next()
        if data:
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


def cmd_sync_waiter(wsapp, cmdobj, sname):
    ret = wsapp.SaltClient.run(cmdobj)
    cli = wsapp.sockmap.get(sname, None)
    if cli is None:
        return
    try:
        cli.ws.send(json.dumps({'type': 'cmd', 'body': ret}))
    except:
        # Retry
        cli.ws.send(json.dumps({'type': 'cmd', 'body': ret}))


class SocketApplication(WebSocketApplication):

    event_listeners = []
    job_listeners = []
    event_queue = Queue()
    sockmap = {}

    def __init__(self, *args, **kwargs):
        self.SaltClient = APIClient()
        self.event_listener_proc = Process(target=subprocess_read_events, args=(self.event_queue,))
        self.event_listener_proc.start()
        self.event_processor = Greenlet.spawn(process_events, self)
        super(SocketApplication, self).__init__(*args, **kwargs)

    def __del__(self, *args, **kwargs):
        self.event_listener_proc.kill()
        self.event_processor.kill()
        super(SocketApplication, self).__del__(*args, **kwargs)

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
        cdict = {}
        cdict['fun'] = cmdmesg['method']
        cdict['tgt'] = cmdmesg['pattern']
        cdict['mode'] = cmdmesg.get('mode', 'async')
        cdict['expr_form'] = cmdmesg.get('pattern_type', 'glob')
        cdict['kwarg'] = cmdmesg.get('kwargs', {})
        cdict['arg'] = cmdmesg.get('args', [])
        cdict['token'] = cmdmesg['token']
        if cdict['mode'] == 'async':
            # Async, so we can block and wait.
            retval = self.SaltClient.run(cdict)
            self.ws.send(json.dumps({'type': 'cmd', 'body': retval}))
        else:
            # Spawn a greenlet, then return.
            sname = cdict['fun'] + str(time())
            self.sockmap[sname] = self.ws.handler.active_client
            Greenlet.spawn(cmd_sync_waiter, self, cdict, sname)
            return

    def signature(self, cmdmesg):
        cdict = {}
        cdict['tgt'] = cmdmesg['tgt']
        cdict['module'] = cmdmesg['module']
        cdict['token'] = cmdmesg['token']
        j = self.SaltClient.signature(cdict)
        resp = self.get_job(j['jid'])
        return resp

    def get_job(self, jid):
        resp = self.SaltClient.runnerClient.cmd('jobs.lookup_jid', [jid])
        return resp

    def get_active(self):
        resp = self.SaltClient.runnerClient.cmd('jobs.active', [])
        return resp

    # Message and Connection Handling.
    def broadcast_event(self, e):
        for cm in self.event_listeners:
            client = self.sockmap[cm]
            client.ws.send(e)

    def hash_conn(self):
        m = hashlib.md5()
        m.update(str(self.ws.handler.active_client.address[0]))
        m.update(str(self.ws.handler.active_client.address[1]))
        return m.hexdigest()

    def on_open(self):
        h = self.hash_conn()
        print "Connection opened as {0}".format(h)
        self.sockmap[h] = self.ws.handler.active_client

    def auth_message(self, message):
        e = []
        if 'password' not in message:
            e.append("password field missing")
        if 'username' not in message:
            e.append("username field missing")
        if len(e) != 0:
            raise InvalidMessage("Missing fields", e)
        t = self.auth(message['username'], message['password'], message.get('eauth', 'pam'))
        self.ws.send(json.dumps({'type': 'auth', 'body': t}))

    def runner_message(self, message):
        pass

    def cmd_message(self, message):
        e = []
        if 'method' not in message:
            e.append('method field missing')
        if 'pattern' not in message:
            e.append('pattern field missing')
        if 'token' not in message:
            e.append('token missing')
        if len(e) != 0:
            raise InvalidMessage("Missing fields", e)
        self.cmd(message)

    def subscribe_message(self, message):
        '''This subscribes the socket to all events.'''
        e = []
        if 'subscription' not in message:
            e.append('subscription field missing')
        if len(e) != 0:
            raise InvalidMessage("Missing fields", e)
        if message['subscription'] == 'event':
            self.event_listeners.append(self.hash_conn())
        elif message['subscription'] == 'job':
            pass
        else:
            raise InvalidMessage("Unknown subscription type.")

    def unsubscribe_message(self, message):
        '''This unsubscribes the socket to all events.'''
        e = []
        if 'subscription' not in message:
            e.append('subscription field missing')
        if len(e) != 0:
            raise InvalidMessage("Missing fields", e)
        if message['subscription'] == 'event':
                self.event_listeners.pop(self.hash_conn(), None)
        elif message['subscription'] == 'job':
            pass
        else:
            raise InvalidMessage("Unknown subscription type.")

    def signature_message(self, message):
        e = []
        if 'tgt' not in message:
            e.append('tgt field missing')
        if 'module' not in message:
            e.append('module field missing')
        if 'token' not in message:
            e.append('token field missing')
        if len(e) != 0:
            raise InvalidMessage("Missing fields", e)
        resp = self.signature(message)
        self.ws.send(json.dumps(resp))

    def get_job_message(self, message):
        if 'jid' not in message:
            resp = self.get_active()
        else:
            resp = self.get_job(message['jid'])
        self.ws.send(json.dumps({'type': 'get_job', 'body': resp}))

    def event_message(self, message):
        e = []
        if 'body' not in message:
            e.append('no event body')
        if len(e) != 0:
            raise InvalidMessage("Missing fields", e)
        retval = self.SaltClient.event.fire_event(message['body'], message.get('tag', ''))
        self.ws.send(json.dumps({"type": "event", "acknowleged": retval}))

    def on_message(self, message):
        print repr(self.ws.handler.active_client.address)
        if message is None:
            # Empty message, probably a disconnect.
            return
        try:
            try:
                deser = json.loads(message)
            except:
                raise InvalidMessage("Could not deserialize message. Is it valid json?")
            if deser['type'] == 'auth':
                self.auth_message(deser)
            elif deser['type'] == 'cmd':
                self.cmd_message(deser)
            elif deser['type'] == 'subscribe':
                self.subscribe_message(deser)
            elif deser['type'] == 'unsubscribe':
                self.unsubscribe_message(deser)
            elif deser['type'] == 'event':
                self.event_message(deser)
            elif deser['type'] == 'signature':
                self.signature_message(deser)
            elif deser['type'] == 'runner':
                self.runner_message(deser)
            elif deser['type'] == 'get_job':
                self.get_job_message(deser)
        except InvalidMessage as e:
            emsg = {
                'error': str(e),
                'message': e.message,
                'details': e.errors
            }
            self.ws.send(json.dumps(emsg))
        except EauthAuthenticationError as e:
            emsg = {
                'error': str(e),
                'message': e.message,
            }
            self.ws.send(json.dumps(emsg))

    def on_close(self, reason):
        h = self.hash_conn()
        self.sockmap.pop(h, None)
        print "{0}: closed, {1}".format(h, reason)

if __name__ == '__main__':
    start()
