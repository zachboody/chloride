**WARNING**
This is a massively rough, super-in progress project that is bound to be flaky, sketchy and otherwise unsuable. On top of that, it's developed against the experimental and non-public Salt APIClient.

A websocket-based API for Salt, designed primarily for server-to-server and lightweight application transport.

A salt master is set up with Vagrant added to PAM auth for easy testing, default username/password is vagrant/vagrant. The virtual machine is also running the minion, so there is at least one machine to manage.

For testing:

salt -T -a pam '*' test.ping

In a python shell:
from websocket import create_connection
ws = create_connection("ws://127.0.0.1:8000/")
# ws.send()
# ws.recv()