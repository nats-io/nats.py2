import argparse, sys
import tornado.ioloop
import tornado.gen
import time

from nats.io.client import Client as NatsClient

def show_usage():
  print("nats-sub SUBJECT [-s SERVER] [-q QUEUE]")

def show_usage_and_die():
  show_usage()
  sys.exit(1)

@tornado.gen.coroutine
def main():
    # Parse the command line arguments
    parser = argparse.ArgumentParser()

    # e.g. nats-sub hello -s nats://127.0.0.1:4222
    parser.add_argument('subject', default='', nargs='?')
    parser.add_argument('-s', '--servers', default=["nats://127.0.0.1:4222"], action='append')
    parser.add_argument('-q', '--queue', default="")

    # Parse!
    args = parser.parse_args()

    # Create client and connect to server
    nc = NatsClient()
    yield nc.connect({ "servers": args.servers })

    def handler(msg):
        print("[Received: {}] {}".format(msg.subject, msg.data))

    print("Subscribed to '{}'".format(args.subject))
    future = nc.subscribe(args.subject, args.queue, handler)
    sid = future.result()

if __name__ == '__main__':
    main()
    tornado.ioloop.IOLoop.instance().start()
