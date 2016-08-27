# coding: utf-8
import tornado.ioloop
import tornado.gen
import time
import ssl
from datetime import datetime
from nats.io.utils  import new_inbox
from nats.io.client import Client as NATS

@tornado.gen.coroutine
def main():
    nc = NATS()

    # Establish secure connection to the server, tls options parameterize
    # the wrap_socket available from ssl python package.
    options = {
        "verbose": True,
        "servers": ["nats://127.0.0.1:4444"],
        "tls": {
            "cert_reqs": ssl.CERT_REQUIRED,
            "ca_certs": "./tests/configs/certs/ca.pem",
            "keyfile":  "./tests/configs/certs/client-key.pem",
            "certfile": "./tests/configs/certs/client-cert.pem"
          }
        }
    yield nc.connect(**options)

    def discover(msg=None):
        print("[Received]: %s" % msg.data)

    sid = yield nc.subscribe("discover", "", discover)

    # Only interested in 2 messages.
    yield nc.auto_unsubscribe(sid, 2)
    yield nc.publish("discover", "A")
    yield nc.publish("discover", "B")

    # Following two messages won't be received.
    yield nc.publish("discover", "C")
    yield nc.publish("discover", "D")

    # Request/Response
    def help_request_handler(msg):
        print("[Received]: %s" % msg.data)
        nc.publish(msg.reply, "OK, I can help!")

    # Susbcription using distributed queue
    yield nc.subscribe("help", "workers", help_request_handler)

    try:
        # Expect a single request and timeout after 500 ms
        response = yield nc.timed_request("help", "Hi, need help!", timeout=0.500)
        print("[Response]: %s" % response.data)
    except tornado.gen.TimeoutError, e:
        print("Timeout! Need to retry...")

    # Customize number of responses to receive
    def many_responses(msg=None):
        print("[Response]: %s" % msg.data)

    yield nc.request("help", "please", expected=2, cb=many_responses)

    # Publish inbox
    my_inbox = new_inbox()
    yield nc.subscribe(my_inbox)
    yield nc.publish_request("help", my_inbox, "I can help too!")

    loop = tornado.ioloop.IOLoop.instance()
    yield tornado.gen.Task(loop.add_timeout, time.time() + 1)
    try:
        start = datetime.now()
        # Make roundtrip to the server and timeout after 1 second
        yield nc.flush(1)
        end = datetime.now()
        print("Latency: %d µs" % (end.microsecond - start.microsecond))
    except tornado.gen.TimeoutError, e:
        print("Timeout! Roundtrip too slow...")

if __name__ == '__main__':
    tornado.ioloop.IOLoop.instance().run_sync(main)
