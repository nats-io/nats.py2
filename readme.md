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

## Basic Usage

```python
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
