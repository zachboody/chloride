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

    def on_message(self, message):
        print message
        deser = json.loads(message)
        try:
            if deser['type'] == 'auth':
                self.auth_message(deser)

        except Exception as e:
            emsg = {
                'error': 'Invalid Message.',
                'details': e.message
            }
            self.ws.send(json.dumps(emsg))

    def on_close(self, reason):
        print reason

Client = ClientWrapper()
WebSocketServer(
    ('', 8000),
    Resource({'/': SocketApplication})
).serve_forever()
