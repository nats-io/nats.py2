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
        self.broken_pipe_errors = 0
        self.resource_unavailable = 0
        self.connection_reset = 0

    def disconnected(self):
        print("Disconnected after writing: ", self.total_written)

@tornado.gen.coroutine
def go():
    nc = Client(Nats())

    try:
        yield nc.nc.connect({"servers": ["nats://127.0.0.1:4225"]})
    except Exception, e:
        print("Error: could not establish connection to server", e)
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

    for i in range(nc.max_messages):
        try:
            yield nc.nc.publish_request("help.io.{0}".format(i), "", line)
            nc.total_written += 1
        except Exception, e:
            nc.connection_reset += 1

    yield nc.nc.flush()
    nc.end_time = time.time()
    duration = nc.end_time - nc.start_time
    rate = nc.total_written / duration
    print("|{0}|{1}|{2}|{3}|{4}|{5}|{6}|{7}|".format(max_messages, bytesize, duration, rate, nc.total_written, nc.broken_pipe_errors, nc.resource_unavailable,nc.connection_reset))

if __name__ == '__main__':
    tornado.ioloop.IOLoop.instance().run_sync(go)
