# WARNING #
This is a massively rough, super-in progress project that is bound to be flaky, sketchy and otherwise unusable. On top of that, it's developed against the experimental and non-public Salt APIClient.

A zerorpc-based API for Salt, designed primarily for server-to-server and lightweight application transport.

A salt master is set up with Vagrant added to PAM auth for easy testing, default username/password is vagrant/vagrant. The virtual machine is also running the minion, so there is at least one machine to manage.

# Testing #

salt -T -a pam '*' test.ping

In a python shell:
```
import zerorpc
c = zerorpc.Client()
c.connect("tcp://127.0.0.1:8000/")
c.auth('vagrant', 'vagrant', 'pam')
```


# Message Types #
Most of the API is a pretty standard RPC pattern.

The exception is the 'event_stream' call, which yields events from the Salt event stream.

The messages and responses are python dicts. ZeroRPC uses msgpack internally, so it's fairly efficient.

### auth ###
This is used to generate a token for the further message types.

Example call:
`c.auth('vagrant', 'vagrant')`

Successful Response:
```
{
	'eauth': 'pam',
	'expire': 1415287682.240218,
	'name': 'vagrant',
	'perms': ['.*', '@runner', '@wheel'],
	'start': 1415244482.240218,
	'token': 'bd935538733fba062d022f0f01f332e3',
	'user': 'vagrant',
	'username': 'vagrant'
}
```

Failed Response:
```
{
	'details': 'Authentication failed with provided credentials.',
	'error': 'Invalid credentials'
}
```

You can optionally include an 'eauth' parameter to set the auth type.
It defaults to pam if left out.


### cmd ###
This runs a command, given a command, target pattern, and token.

Example call:
```
cmd = {
	'fun': 'test.ping',
	'tgt': '*',
	'mode': 'async',
	'expr_form': 'glob',
	'kwarg': {},
	'arg': [],
	'token': 'fe4640ee430cf86331aad9671841bdec'
}
c.cmd(cmd)
```
There are a few moving pieces to this format.

args is either a list for positional arguments.
kwargs is an object for keyword arguments.
Both can be left out for no arguments.
expr_form defaults to glob and can be left out.

Mode determines the return value you get. Async responds with a JID immediately, where "sync" waits and replies with the results.
Both echo the properties passed into it, with the exception of token, which is replaced by the username of the executing user.

Example Async response:
```
{
	'arg': [],
	'expr_form': 'glob',
	'fun': 'test.ping',
	'jid': '20141106034644575012',
	'kwarg': {},
	'minions': ['vagrant'],
	'mode': 'async',
	'tgt': '*',
	'username': 'vagrant'
}
```

Example Sync response:
```
{
	'arg': [],
	'expr_form': 'glob',
	'fun': 'test.ping',
	'kwarg': {},
	'mode': 'sync',
	'result': {},
	'tgt': '*',
	'username': 'vagrant'
}
```

### event_stream ###
This streams events from the salt event stream.
```
c.event_stream(token)
```
This puts you on the broadcast list for the events stream, which tends to be a fair amount of useful traffic.

### get_job ###
This returns a job by jid.
```
c.get_job(jid)
```
Pretty straightforward, just like salt-run jobs.lookup_jid $(jid)

### signature ###
Returns the method siganture for a module method. This should be targeted at your fastest-responding relevent minion. (I run a minion on the master for this very reason.)
```
# minion pattern, method/module, token
c.signature('vagrant', 'cmd.run', 'fe4640ee430cf86331aad9671841bdec')
```


### event ###
Fires an event on the event bus. This will eventually require a token!
```
{
	"type": "event",
	"body": {"test": true},
	"tag": "/test/noise"
}
```

### validate ###
Validates a token and returns the username and info around it.
```
c.validate(token)
```

Returns:
```
{
	"name": "vagrant",
	"start": 1415149293.733322,
	"token": "9f1fc7bd0e3c9ebbd1f80e67fa1147da",
	"expire": 1415192493.733323,
	"eauth": "pam",
	"valid": true
}
```