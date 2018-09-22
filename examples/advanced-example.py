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
from nats.io import Client as NATS
from nats.io.errors import ErrNoServers

@tornado.gen.coroutine
def main():
    nc = NATS()

    try:
        # Setting explicit list of servers in a cluster and
        # max reconnect retries.
        servers = [
            "nats://127.0.0.1:4222",
            "nats://127.0.0.1:4223",
            "nats://127.0.0.1:4224"
            ]
        yield nc.connect(max_reconnect_attempts=2, servers=servers)
    except ErrNoServers:
        print("No servers available!")
        return

    @tornado.gen.coroutine
    def message_handler(msg):
        subject = msg.subject
        reply = msg.reply
        data = msg.data.decode()
        for i in range(0, 20):
            yield nc.publish(reply, "i={i}".format(i=i).encode())

    yield nc.subscribe("help.>", cb=message_handler)

    @tornado.gen.coroutine
    def request_handler(msg):
        subject = msg.subject
        reply = msg.reply
        data = msg.data.decode()
        print("Received a message on '{subject} {reply}': {data}".format(
            subject=subject, reply=reply, data=data))

    # Signal the server to stop sending messages after we got 10 already.
    yield nc.request(
        "help.please", b'help', expected=10, cb=request_handler)

    # Flush connection to server, returns when all messages have been processed.
    # It raises a timeout if roundtrip takes longer than 1 second.
    yield nc.flush()

    # Drain gracefully closes the connection, allowing all subscribers to
    # handle any pending messages inflight that the server may have sent.
    yield nc.drain()

    # Drain works async in the background.
    yield tornado.gen.sleep(1)

if __name__ == '__main__':
    tornado.ioloop.IOLoop.instance().run_sync(main)
