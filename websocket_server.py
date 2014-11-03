from gevent.monkey import patch_all
patch_all()
from gevent import Greenlet, sleep
from multiprocessing import Process, Queue
from multiprocessing.queues import Empty
import os
from geventwebsocket import WebSocketServer, WebSocketApplication, Resource
import json
import logging
from salt.client.api import APIClient
from salt.exceptions import EauthAuthenticationError


class InvalidMessage(Exception):
    def __init__(self, message, errors):
        super(InvalidMessage, self).__init__(message)
        self.errors = errors


def __virtual__():
    mod_opts = __opts__.get(__virtualname__, {})

    if 'port' in mod_opts:
        return __virtualname__

    return False


def get_opts():
    '''Return the salt master config.'''
    import salt.config

    return salt.config.client_config(
        os.environ.get('SALT_MASTER_CONFIG', '/etc/salt/master'))


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
                except UnicodeDecodeError:
                    log.error("Non UTF-8 data in event.")

__virtualname__ = 'websocket'
log = logging.getLogger(__virtualname__)
if '__opts__' not in globals():
        __opts__ = get_opts()


class SocketApplication(WebSocketApplication):

    event_listeners = []
    job_listeners = []
    event_queue = Queue()

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
        retval = self.SaltClient.run(cdict)
        return retval

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

    # Message and Connection Handling.
    def broadcast_event(self, e):
        for client in self.event_listeners:
            client.ws.send(e)

    def on_open(self):
        print "Connection opened"

    def auth_message(self, message):
        e = []
        if 'password' not in message:
            e.append("password field missing")
        if 'username' not in message:
            e.append("username field missing")
        if len(e) != 0:
            raise InvalidMessage("Missing fields", e)
        t = self.auth(message['username'], message['password'], message.get('eauth', 'pam'))
        self.ws.send(json.dumps(t))

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
        resp = self.cmd(message)
        self.ws.send(json.dumps(resp))

    def subscribe_message(self, message):
        '''This subscribes the socket to all events.'''
        e = []
        if 'subscription' not in message:
            e.append('subscription field missing')
        if len(e) != 0:
            raise InvalidMessage("Missing fields", e)
        if message['subscription'] == 'event':
            self.event_listeners.append(self.ws.handler.active_client)
        elif message['subscription'] == 'job':
            self.susbscribed_jobs = True
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
                self.event_listeners.remove(self.ws.handler.active_client)
        elif message['subscription'] == 'job':
            if self.job_greenlet:
                self.job_greenlet.kill()
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
        e = []
        if 'jid' not in message:
            e.append('jid field missing')
        if len(e) != 0:
            raise InvalidMessage("Missing fields", e)
        resp = self.get_job(message['jid'])
        self.ws.send(json.dumps({'acknowleged': resp}))

    def event_message(self, message):
        e = []
        if 'body' not in message:
            e.append('no event body')
        if len(e) != 0:
            raise InvalidMessage("Missing fields", e)
        retval = self.SaltClient.event.fire_event(message['body'], message.get('tag', ''))
        self.ws.send(json.dumps(retval))

    def on_message(self, message):
        print repr(self.ws.handler.active_client.address)
        if message is None:
            # Empty message, probably a disconnect.
            return
        try:
            deser = json.loads(message)
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
        print reason

if __name__ == '__main__':
    start()
