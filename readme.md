# WARNING #
This is a massively rough, super-in progress project that is bound to be flaky, sketchy and otherwise unusable. On top of that, it's developed against the experimental and non-public Salt APIClient.

A websocket-based API for Salt, designed primarily for server-to-server and lightweight application transport.

A salt master is set up with Vagrant added to PAM auth for easy testing, default username/password is vagrant/vagrant. The virtual machine is also running the minion, so there is at least one machine to manage.

# Testing #

salt -T -a pam '*' test.ping

In a python shell:
```
import json
from websocket import create_connection
ws = create_connection("ws://127.0.0.1:8000/")
m = {'type': 'auth', 'username': 'vagrant', 'password': 'vagrant'}
ws.send(json.dumps(m))
ws.recv()
```


# Message Types #
Most of the API is a pretty standard message-> response pattern. It's async with no guaranteed message order, so callbacks are your friend.

The exception is the 'subscribe' message type, which sets your socket up to recieve a message stream, either from the event bus or the jobs stream.

The messages and responses are (for now) JSON. I'll eventually look at some form of more efficent serializaton format. (msgpack, for instance.)

### auth ###
This is used to generate a token for the further message types.

Example message:
```
{ 
	'type': 'auth',
	'username': 'vagrant',
	'password': 'vagrant'
}
```
You can optionally include an 'eauth' parameter to set the auth type.
It defaults to pam if left out.

Example response:
```
{
	"username": "vagrant",
	"name": "vagrant",
	"perms": [".*", "@runner", "@wheel"],
	"start": 1414873954.974579,
	"token": "de7f428a61a8ab799d44e764067b0efd",
	"expire": 1414917154.974582,
	"user": "vagrant",
	"eauth": "pam"
}
```

### cmd ###
This runs a command, given a command, target pattern, and token.

Example message:
```
{
	'type': 'cmd',
	'method': 'test.ping',
	'pattern': '*',
	'pattern_type': 'glob',
	'token': 'a2822c3247c15755c7e17fa5686d40c7'
}
```
There are a few moving pieces to this format.
For example, if you leave pattern_type out, it defaults to glob.

args is either a list for positional arguments.
kwargs is an object for keyword arguments.
Both can be left out for no arguments.

This returns a jid immediately.

### subscribe ###
This subscribes you to the events stream.
```
{
	"type": "subscribe",
	"subscription": "event"
}
```
This puts you on the broadcast list for the events stream, which tends to be a fair amount of useful traffic.

### get_job ###
This returns a job by jid.
```
{
	"type": "get_job",
	"jid": "20141103073312975821"
}
```
Pretty straightforward, just like salt-run jobs.lookup_jid $(jid)

### signature ###
Returns the method siganture for a module method. This should be targeted at your fastest-responding relevent minion.
```
{
	"type": "signature",
	"tgt": "vagrant",
	"token": "9d15eef4b4465bd352a32fc8eed22444",
	"module": "test.ping"
}
```

### event ###
Fires an event on the event bus. This will eventually require a token!
{
	"type": "event",
	"body": {"test": true},
	"tag": "/test/noise"
}
