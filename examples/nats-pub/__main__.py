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

import argparse, sys
import tornado.ioloop
import tornado.gen
import time

from nats.io.client import Client as NATS


def show_usage():
    print("nats-pub SUBJECT [-d DATA] [-s SERVER]")
    print("")
    print("Example:")
    print("")
    print(
        "nats-pub hello -d world -s nats://127.0.0.1:4222 -s nats://127.0.0.1:4223"
    )


def show_usage_and_die():
    show_usage()
    sys.exit(1)


@tornado.gen.coroutine
def main():
    parser = argparse.ArgumentParser()

    # e.g. nats-pub hello -d "world" -s nats://127.0.0.1:4222 -s nats://127.0.0.1:4223
    parser.add_argument('subject', default='hello', nargs='?')
    parser.add_argument('-d', '--data', default="hello world")
    parser.add_argument('-s', '--servers', default=[], action='append')

    args = parser.parse_args()

    nc = NATS()
    try:
        servers = args.servers
        if len(args.servers) < 1:
            servers = ["nats://127.0.0.1:4222"]

        opts = {"servers": servers}
        yield nc.connect(**opts)
        yield nc.publish(args.subject, args.data)
        yield nc.flush()
        print("Published to '{0}'".format(args.subject))
    except Exception, e:
        print(e)
        show_usage_and_die()


if __name__ == '__main__':
    tornado.ioloop.IOLoop.current().run_sync(main)
