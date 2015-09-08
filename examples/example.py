import tornado.ioloop
import tornado.gen
import time
from nats.io.client import Client as NatsClient

@tornado.gen.coroutine
def main():
    nc = NatsClient()

    # establish connection to the server
    yield nc.connect({ "verbose": True, "servers": ["nats://127.0.0.1:4222"] })

    def help_request(msg):
        print("[Received]: %s" % msg.data)
        nc.publish("help.announce", "OK, I can help!")

    future = nc.subscribe("help.request", "", help_request)
    sid = future.result()
    # yield nc.unsubscribe(sid)

    loop = tornado.ioloop.IOLoop.instance()
    yield tornado.gen.Task(loop.add_timeout, time.time() + 1)
    yield nc.publish("help.request", "Need help!")
    yield tornado.gen.Task(loop.add_timeout, time.time() + 1)
    tornado.ioloop.IOLoop.instance().stop()

if __name__ == '__main__':
    tornado.ioloop.IOLoop.instance().run_sync(main)
