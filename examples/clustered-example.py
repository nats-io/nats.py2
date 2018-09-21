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
from datetime import timedelta
from nats.io.client import Client as NATS
from nats.io.errors import ErrConnectionClosed


@tornado.gen.coroutine
def main():
    nc = NATS()

    # Set pool servers in the cluster and give a name to the client
    # each with its own auth credentials.
    options = {
        "servers": [
            "nats://secret1:pass1@127.0.0.1:4222",
            "nats://secret2:pass2@127.0.0.1:4223",
            "nats://secret3:pass3@127.0.0.1:4224"
        ]
    }

    # Error callback takes the error type as param.
    def error_cb(e):
        print("Error! ", e)

    def close_cb():
        print("Connection was closed!")

    def disconnected_cb():
        print("Disconnected!")

    def reconnected_cb():
        print("Reconnected!")

    # Set callback to be dispatched whenever we get
    # protocol error message from the server.
    options["error_cb"] = error_cb

    # Called when we are not connected anymore to the NATS cluster.
    options["closed_cb"] = close_cb

    # Called whenever we become disconnected from a NATS server.
    options["disconnected_cb"] = disconnected_cb

    # Called when we connect to a node in the NATS cluster again.
    options["reconnected_cb"] = reconnected_cb

    yield nc.connect(**options)

    @tornado.gen.coroutine
    def subscriber(msg):
        yield nc.publish("pong", "pong:{0}".format(msg.data))

    yield nc.subscribe("ping", "", subscriber)

    for i in range(0, 100):
        yield nc.publish("ping", "ping:{0}".format(i))
        yield tornado.gen.sleep(0.1)

    yield nc.close()

    try:
        yield nc.publish("ping", "ping")
    except ErrConnectionClosed:
        print("No longer connected to NATS cluster.")


if __name__ == '__main__':
    tornado.ioloop.IOLoop.current().run_sync(main)
