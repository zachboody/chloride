import os
from geventwebsocket import WebSocketServer, WebSocketApplication, Resource
from ClientWrapper import ClientWrapper
import json
import logging


class InvalidMessage(Exception):
    def __init__(self, message, errors):
        super(InvalidMessage, self).__init__(message)
        self.errors = errors

__virtualname__ = 'websocket'
log = logging.getLogger(__virtualname__)
Client = ClientWrapper()


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


class SocketApplication(WebSocketApplication):

    susbscribed_events = False
    susbscribed_jobs = False

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
        t = Client.auth(message['username'], message['password'], message.get('eauth', 'pam'))
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
        resp = Client.cmd(message)
        self.ws.send(json.dumps(resp))

    def subscribe_message(self, message):
        pass

    def _event_stream(self):
        pass

    def signature_message(self, message):
        pass

    def on_message(self, message):
        print message
        deser = json.loads(message)
        try:
            if deser['type'] == 'auth':
                self.auth_message(deser)
            elif deser['type'] == 'cmd':
                self.cmd_message(deser)
            elif deser['type'] == 'subscribe':
                self.subscribe_message(deser)
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
