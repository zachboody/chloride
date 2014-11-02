from salt.client.api import APIClient


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

    def get_event(tag):
        pass

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
