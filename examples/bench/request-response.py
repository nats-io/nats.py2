import socket
import time
import sys
import tornado.gen
import tornado.ioloop
from nats.io.client import Client as Nats

class Client(object):

    def __init__(self, nc):
        self.total_written = 0
        self.timeouts = 0
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
        options = {"servers": ["nats://127.0.0.1:4225"]}
        yield nc.nc.connect(options)
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

    @tornado.gen.coroutine
    def response_handler(msg):
        yield nc.nc.publish(msg.reply, "A")

    yield nc.nc.subscribe("help", "workers", response_handler)

    nc.start_time = time.time()
    nc.max_messages = int(max_messages)
    line = "A" * int(bytesize)

    for i in range(nc.max_messages):
        try:
            # a = time.time()
            result = yield nc.nc.timed_request("help", line)            
            # b = time.time()
            # print("result: ", result, b - a)
            nc.total_written += 1
        except tornado.gen.TimeoutError, e:
            nc.timeouts += 1
            continue
        finally:
            nc.end_time = time.time()

    duration = nc.end_time - nc.start_time
    rate = nc.total_written / duration
    tornado.ioloop.IOLoop.instance().stop()
    print("|{0}|{1}|{2}|{3}|{4}|{5}|".format(max_messages, bytesize, duration, rate, nc.total_written, nc.timeouts))

if __name__ == '__main__':
    go()
    tornado.ioloop.IOLoop.instance().start()
