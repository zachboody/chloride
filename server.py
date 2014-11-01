from geventwebsocket import WebSocketServer, WebSocketApplication, Resource
from salt.client.api import APIClient
import json


class InvalidMessage(Exception):
    def __init__(self, message, errors):
        super(InvalidMessage, self).__init__(message)
        self.errors = errors


class ClientWrapper():

    EventFeedListeners = []

    def __init__(self):
        self.SaltClient = APIClient()

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
            'mode': 'sync',
            'timeout': 30
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


class SocketApplication(WebSocketApplication):

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
    Client = ClientWrapper()
    WebSocketServer(
        ('', 8000),
        Resource({'/': SocketApplication})
    ).serve_forever()
