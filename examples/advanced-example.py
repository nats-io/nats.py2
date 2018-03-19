# coding: utf-8
# Copyright 2015-2018 The NATS Authors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import tornado.ioloop
import tornado.gen
import time
from nats.io import Client as NATS

@tornado.gen.coroutine
def main():
    nc = NATS()

    # Set pool servers in the cluster and give a name to the client.
    options = {
        "name": "worker",
        "servers": [
            "nats://secret:pass@127.0.0.1:4222",
            "nats://secret:pass@127.0.0.1:4223",
            "nats://secret:pass@127.0.0.1:4224"
            ]
        }

    # Explicitly set loop to use for the reactor.
    options["io_loop"] = tornado.ioloop.IOLoop.instance()

    yield nc.connect(**options)

    @tornado.gen.coroutine
    def subscriber(msg):
        yield nc.publish("discover", "pong")

    yield nc.subscribe("discover", "", subscriber)

    @tornado.gen.coroutine
    def async_subscriber(msg):
        # First request takes longer, while others are still processed.
        if msg.subject == "requests.1":
            yield tornado.gen.sleep(0.5)
        print("Processed request [{0}]: {1}".format(msg.subject, msg))

    # Create asynchronous subscription and make roundtrip to server
    # to ensure that subscriptions have been processed.
    yield nc.subscribe_async("requests.*", cb=async_subscriber)
    yield nc.flush()
    for i in range(1, 10):
        yield nc.publish("requests.{0}".format(i), "example")
    yield tornado.gen.sleep(1)

    while True:
        # Confirm stats to implement basic throttling logic.
        sent = nc.stats["out_msgs"]
        received = nc.stats["in_msgs"]
        delta = sent - received

        if delta > 2000:
            print("Waiting... Sent: {0}, Received: {1}, Delta: {2}".format(sent, received, delta))
            yield tornado.gen.sleep(1)

        if nc.stats["reconnects"] > 10:
            print("[WARN] Reconnected over 10 times!")

        for i in range(1000):
            yield nc.publish("discover", "ping")

if __name__ == '__main__':
    tornado.ioloop.IOLoop.instance().run_sync(main)
