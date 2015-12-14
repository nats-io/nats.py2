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
        options = {"verbose": False, "servers": ["nats://127.0.0.1:4225"]}
        yield nc.nc.connect(**options)
    except Exception, e:
        print("Error: could not establish connection to server", e)
        tornado.ioloop.IOLoop.instance().stop()
        return

    @tornado.gen.coroutine
    def response_handler(msg):
        nc.nc.publish(msg.reply, msg.data)

    yield nc.nc.subscribe("help", "workers", response_handler)
    print("Subscribed!")

if __name__ == '__main__':
    go()
    tornado.ioloop.IOLoop.instance().start()
