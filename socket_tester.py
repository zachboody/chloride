import json
from websocket import create_connection

ws = create_connection("ws://127.0.0.1:8000/")
m = {"type": "auth", "username": "vagrant", "password": "vagrant"}
ws.send(json.dumps(m))
amesg = ws.recv()
print amesg
sm = {"type": "subscribe", "subscription": "event"}
ws.send(json.dumps(sm))
while True:
    print ws.recv()
