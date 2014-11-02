from gevent.monkey import patch_all
patch_all()
from gevent import Greenlet, sleep
import os
from geventwebsocket import WebSocketServer, WebSocketApplication, Resource
import json
import logging
from salt.client.api import APIClient


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


def greenlet_events(wss):
        stream = wss.SaltClient.event.iter_events(full=True)
        while True:
            data = stream.next()
            if data:
                try:
                    wss.broadcast_event(data)
                except UnicodeDecodeError:
                    log.error("Non UTF-8 data in event.")
            sleep(0.1)

__virtualname__ = 'websocket'
log = logging.getLogger(__virtualname__)
if '__opts__' not in globals():
        __opts__ = get_opts()


class SocketApplication(WebSocketApplication):

    event_listeners = []
    job_listeners = []

    def __init__(self, *args, **kwargs):
        self.SaltClient = APIClient()
        Greenlet.spawn(greenlet_events, self)
        super(SocketApplication, self).__init__(*args, **kwargs)

    def broadcast_event(self, e):
        for client in self.event_listeners:
            client.ws.send(json.dumps(e))

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
        cdict = {
            'mode': 'async'
        }
        # TODO: async?
        cdict['fun'] = cmdmesg['method']
        cdict['tgt'] = cmdmesg['pattern']
        cdict['expr_form'] = cmdmesg.get('pattern_type', 'glob')
        cdict['kwarg'] = cmdmesg.get('kwargs', {})
        cdict['arg'] = cmdmesg.get('args', [])
        cdict['token'] = cmdmesg['token']
        retval = self.SaltClient.run(cdict)
        return retval

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
        pass

    def on_message(self, message):
        print repr(self.ws.handler.active_client.address)
        print message
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
            elif deser['type'] == 'signature':
                self.signature_message(deser)
            elif deser['type'] == 'runner':
                self.runner_message(deser)
        except Exception as e:
            emsg = {
                'error': 'Invalid Message.',
                'details': e.message
            }
            self.ws.send(json.dumps(emsg))

    def on_close(self, reason):
        print reason

if __name__ == '__main__':
    start()
