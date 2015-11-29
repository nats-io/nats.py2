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
  print("nats-pub hello -d world -s nats://127.0.0.1:4222 -s nats://127.0.0.1:4223")

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
      yield nc.connect({ "servers": servers })
      nc.publish(args.subject, args.data)
      yield nc.flush()
      print("Published to '{0}'".format(args.subject))
    except Exception, e:
      print(e)
      show_usage_and_die()

if __name__ == '__main__':
    tornado.ioloop.IOLoop.instance().run_sync(main)
