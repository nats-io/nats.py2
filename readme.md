# NATS - Python 2 Tornado based Client

A Python +2.6 async client for the [NATS messaging system](https://nats.io).

## Getting 

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
import tornado.concurrent
from nats.io.client import Client as NATS
from nats.io.utils  import new_inbox

@tornado.gen.coroutine
def go():
  nats = NATS()
  yield nats.connect({"servers": ["nats://127.0.0.1:4222"]})

  @tornado.gen.coroutine
  def request_handler(msg):
    yield nats.publish(msg.reply, "I can help!")

  # Simple Async subscriber
  sid = yield nats.subscribe("help", "", request_handler)

  # Unsubscribing
  yield nats.auto_unsubscribe(sid, 1)

  try:
    # Requests
    response = yield nats.timed_request("help", "help me", timeout=1)
    print("Got:", response.data)
  except tornado.gen.TimeoutError, e:
    print("Timeout!", e)

  tornado.ioloop.IOLoop.instance().stop()

if __name__ == '__main__':
  tornado.ioloop.IOLoop.instance().run_sync(go)
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
