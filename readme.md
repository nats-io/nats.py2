# NATS - Python 2 Tornado based Client

A Python +2.6 async client for the [NATS messaging system](https://nats.io).

## Getting Started

Only dependency is Tornado so it must be installed first:

```bash
pip install tornado
```

Then:

```bash
git clone https://github.com/nats-io/python-nats
cd python-nats
python setup.py install
```

## Usage

```python
# coding: utf-8
import tornado.ioloop
import tornado.gen
import time
from datetime import datetime
from nats.io.utils  import new_inbox
from nats.io.client import Client as NATS

@tornado.gen.coroutine
def main():
    nc = NATS()

    # Establish connection to the server.
    yield nc.connect({ "verbose": True, "servers": ["nats://127.0.0.1:4222"] })

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
        response = yield nc.timed_request("help", "Hi, need help!", 500)
        print("[Response]: %s" % response.data)
    except tornado.gen.TimeoutError, e:
        print("Timeout! Need to retry...")

    # Publish inbox
    my_inbox = new_inbox()
    yield nc.subscribe(my_inbox)
    yield nc.publish_request("help", my_inbox, "I can help too!")

    loop = tornado.ioloop.IOLoop.instance()
    yield tornado.gen.Task(loop.add_timeout, time.time() + 1)
    try:
        start = datetime.now()
        # Make roundtrip to the server and timeout after 1000 ms
        yield nc.flush(1)
        end = datetime.now()
        print("Latency: %d µs" % (end.microsecond - start.microsecond))
    except tornado.gen.TimeoutError, e:
        print("Timeout! Flush too slow...")

if __name__ == '__main__':
    tornado.ioloop.IOLoop.instance().run_sync(main)

```

## Examples

In this repo there are also included a couple of simple utilities
for subscribing and publishing messages to NATS:

```sh
    # Make a subscription to 'hello'
    $ python examples/nats-sub hello

    Subscribed to 'hello'
    [Received: hello] world

    # Send a message to hello
    $ python examples/nats-pub hello -d "world"
```

## License

(The MIT License)

Copyright (c) 2015 Apcera Inc.<br/>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to
deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
IN THE SOFTWARE.
