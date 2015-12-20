import socket
import time
import sys
import json
import tornado.gen
import tornado.ioloop
import tornado.httpclient
from nats.io.client import Client as Nats

class Client(object):

    def __init__(self, nc):
        self.total_written = 0
        self.errors = 0
        self.start_time = None
        self.end_time = None
        self.max_messages = 0
        self.nc = nc

    def error(self, error):
        print("ERROR: {0}".format(error))

    def disconnected(self):
        print("DISCONNECTED: wrote {0}".format(self.total_written))

@tornado.gen.coroutine
def go():
    nc = Client(Nats())

    try:
        options = {
            "servers": ["nats://127.0.0.1:4225"],
            "disconnected_cb": nc.disconnected,
            "error_cb": nc.error,
            }
        yield nc.nc.connect(**options)
    except Exception as e:
        print("ERROR: could not establish connection to server", e)
        return

    try:
        max_messages = sys.argv[1]
    except:
        max_messages = 100000

    try:
        bytesize = sys.argv[2]
    except:
        bytesize = 1

    # Confirm original stats in the server
    http = tornado.httpclient.AsyncHTTPClient()
    response = yield http.fetch('http://127.0.0.1:8225/varz')
    start_varz = json.loads(response.body)

    nc.start_time = time.time()
    nc.max_messages = int(max_messages)
    line = "A" * int(bytesize)

    for i in range(nc.max_messages):
        try:
            yield nc.nc.publish("help.socket.{0}".format(i), line)
            nc.total_written += 1
        except Exception as e:
            nc.errors += 1

    yield nc.nc.flush()
    nc.end_time = time.time()
    duration = nc.end_time - nc.start_time
    rate = nc.total_written / duration

    http = tornado.httpclient.AsyncHTTPClient()
    response = yield http.fetch('http://127.0.0.1:8225/varz')
    end_varz = json.loads(response.body)
    delta_varz_in_msgs = end_varz["in_msgs"] - start_varz["in_msgs"]
    delta_varz_in_bytes = end_varz["in_bytes"] - start_varz["in_bytes"]    
    
    print("|{0}|{1}|{2}|{3}|{4}|{5}|{6}|{7}|".format(
        max_messages,
        bytesize,
        duration,
        rate,
        nc.total_written,
        nc.errors,
        delta_varz_in_msgs,
        delta_varz_in_bytes,
        ))

if __name__ == '__main__':
    tornado.ioloop.IOLoop.instance().run_sync(go)
