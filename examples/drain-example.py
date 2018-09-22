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

import tornado.gen
import tornado.concurrent

from nats.io import Client as NATS
from nats.io.errors import ErrNoServers
from tornado.ioloop import IOLoop as loop

@tornado.gen.coroutine
def main():
    nc = NATS()

    conn_closed = tornado.concurrent.Future()

    def closed_cb():
        conn_closed.set_result(True)

    # Set pool servers in the cluster and give a name to the client.
    yield nc.connect("127.0.0.1:4222", closed_cb=closed_cb)

    @tornado.gen.coroutine
    def handler(msg):
        # Can check whether client is in draining state
        if nc.is_draining:
            print("[Status  ] Draining, will disconnect soon...")
        
        print("[Received] {}".format(msg.data))
        yield nc.publish(msg.reply, b'I can help')

    yield nc.subscribe("help", "workers", cb=handler)

    responses = []

    @tornado.gen.coroutine
    def send_requests():
        # Send 100 async requests and wait for all the responses.
        for i in range(0, 1000):
            try:
                response = yield nc.request("help", '[{}] help!'.format(i), timeout=0.1)
                responses.append(response)
            except:
                break

    loop.current().spawn_callback(send_requests)
    yield tornado.gen.sleep(1)

    # Gracefully close the connection and wait for closed callback to be signaled.
    yield nc.drain()
    yield conn_closed

    print("Received {} responses".format(len(responses)))

if __name__ == '__main__':
    loop.current().run_sync(main)
