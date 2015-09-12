import argparse, sys
import tornado.ioloop
import tornado.gen
import time

from nats.io.client import Client as NatsClient

def show_usage():
  print("nats-pub SUBJECT [-d DATA] [-s SERVER]")

def show_usage_and_die():
  show_usage()
  sys.exit(1)

@tornado.gen.coroutine
def main():
    parser = argparse.ArgumentParser()

    # e.g. nats-pub hello -s nats://127.0.0.1:4222
    parser.add_argument('subject', default='', nargs='?')
    parser.add_argument('-d', '--data', default="hello world")
    parser.add_argument('-s', '--servers', default=["nats://127.0.0.1:4222"], action='append')

    # Parse!
    args = parser.parse_args()

    # Create client and connect to server
    nc = NatsClient()
    yield nc.connect({ "servers": args.servers })
    yield nc.publish(args.subject, args.data)
    print("Published to '{0}'".format(args.subject))
    tornado.ioloop.IOLoop.instance().stop()

if __name__ == '__main__':
    main()
    tornado.ioloop.IOLoop.instance().start()
