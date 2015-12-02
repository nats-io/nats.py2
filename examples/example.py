import tornado.ioloop
import tornado.gen
import time
from nats.io.client import Client as NATS

@tornado.gen.coroutine
def main():
    nc = NATS()

    # Establish connection to the server.
    yield nc.connect({ "verbose": True, "servers": ["nats://127.0.0.1:4225"] })

    def discover(msg):
        print("[Received]: %s" % msg.data)

    sid = yield nc.subscribe("discover", "", discover)
    yield nc.auto_unsubscribe(sid, 2)

    loop = tornado.ioloop.IOLoop.instance()
    yield tornado.gen.Task(loop.add_timeout, time.time() + 1)

    yield nc.publish("discover", "A")
    yield nc.publish("discover", "B")
    
    # Following two messages won't be received.
    yield nc.publish("discover", "C")
    yield nc.publish("discover", "D")    

    def help_request_handler(msg):
        print("[Received]: %s" % msg.data)
        nc.publish(msg.reply, "OK, I can help!")

    yield nc.subscribe("help", "workers", help_request_handler)
    response = yield nc.timed_request("help", "Hi, need help!")
    print("[Response]: %s" % response.data)
    
    yield tornado.gen.Task(loop.add_timeout, time.time() + 1)

if __name__ == '__main__':
    tornado.ioloop.IOLoop.instance().run_sync(main)
