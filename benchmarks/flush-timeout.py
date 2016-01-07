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
        self.timeouts = 0
        self.errors = 0
        self.start_time = None
        self.end_time = None
        self.max_messages = 0
        self.nc = nc

    def error(self, error):
        self.errors += 1
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
        tornado.ioloop.IOLoop.instance().stop()
        return

    try:
        max_messages = int(sys.argv[1])
    except:
        max_messages = 1000

    try:
        max_latency = float(sys.argv[2]) * 1000
    except:
        max_latency = 500

    # Confirm original stats in the server
    http = tornado.httpclient.AsyncHTTPClient()
    response = yield http.fetch('http://127.0.0.1:8225/varz')
    start_varz = json.loads(response.body)

    nc.start_time = time.time()

    for i in range(max_messages):
        try:
            result = yield nc.nc.flush(max_latency)
            nc.total_written += 1
        except tornado.gen.TimeoutError:
            nc.timeouts += 1

    try:
        yield nc.nc.flush()
    except tornado.gen.TimeoutError:
        nc.timeouts += 1

    nc.end_time = time.time()    
    duration = nc.end_time - nc.start_time
    rate = nc.total_written / duration

    http = tornado.httpclient.AsyncHTTPClient()
    response = yield http.fetch('http://127.0.0.1:8225/varz')
    end_varz = json.loads(response.body)
    delta_varz_in_msgs = end_varz["in_msgs"] - start_varz["in_msgs"]
    delta_varz_in_bytes = end_varz["in_bytes"] - start_varz["in_bytes"]    

    print("|{0}|{1}|{2}|{3}|{4}|{5}|{6}|{7}|{8}|".format(
        max_messages,
        max_latency,
        duration,
        rate,
        nc.total_written,
        nc.timeouts,
        nc.errors,
        delta_varz_in_msgs,
        delta_varz_in_bytes,
        ))

if __name__ == '__main__':
    tornado.ioloop.IOLoop.instance().run_sync(go)
