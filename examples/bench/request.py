import socket
import time
import sys
import tornado.gen
import tornado.ioloop
from nats.io.client import Client as Nats

class Client(object):

    def __init__(self, nc):
        self.total_written = 0
        self.start_time = None
        self.end_time = None
        self.max_messages = 0
        self.nc = nc

    def disconnected(self):
        print("Disconnected after writing: ", self.total_written)

@tornado.gen.coroutine
def go():
    nc = Client(Nats())

    try:
        yield nc.nc.connect({"servers": ["nats://127.0.0.1:4225"]})
    except Exception, e:
        print("Error: could not establish connection to server", e)
        tornado.ioloop.IOLoop.instance().stop()
        return

    try:
        max_messages = sys.argv[1]
    except:
        max_messages = 100000

    try:
        bytesize = sys.argv[2]
    except:
        bytesize = 1

    nc.start_time = time.time()
    nc.max_messages = int(max_messages)
    line = "A" * int(bytesize)

    try:
        for i in range(nc.max_messages):
            nc.total_written += 1
            # a = time.time()
            yield nc.nc.timed_request("help", line, 500)
            # b = time.time()
            # duration = b - a
            # print("Latency: {0}".format(duration))
    finally:
        nc.end_time = time.time()

    duration = nc.end_time - nc.start_time
    rate = nc.total_written / duration
    print("|{0}|{1}|{2}|{3}|{4}|".format(max_messages, bytesize, duration, rate, nc.total_written))

if __name__ == '__main__':
    tornado.ioloop.IOLoop.instance().run_sync(go)
