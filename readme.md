# NATS - Python 2.7 Asynchronous Client

A Python 2.7 asynchronous client for the [NATS messaging system](https://nats.io).

## Installation

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

Or via `pip install`:

```
pip install nats
```

## Basic Usage

```python
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

    loop = tornado.ioloop.IOLoop.instance()
    yield tornado.gen.Task(loop.add_timeout, time.time() + 1)
    yield nc.publish("help.request", "Need help!")
    yield tornado.gen.Task(loop.add_timeout, time.time() + 1)
    tornado.ioloop.IOLoop.instance().stop()

if __name__ == '__main__':
    tornado.ioloop.IOLoop.instance().run_sync(main)
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
