import argparse, sys
import tornado.ioloop
import tornado.gen
import time
from random import randint
from nats.io.client import Client as NATS

DEFAULT_ITERATIONS = 10000
HASH_MODULO = 1000

def show_usage():
  message = """
Usage: latency_perf [options]

options:
  -n ITERATIONS                    Iterations to spec (default: 1000)
  -S SUBJECT                       Send subject (default: (test)
  """
  print(message)

def show_usage_and_die():
  show_usage()
  sys.exit(1)

global received
received = 0

@tornado.gen.coroutine
def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('-n', '--iterations', default=DEFAULT_ITERATIONS, type=int)
  parser.add_argument('-S', '--subject', default='test')
  parser.add_argument('--servers', default=[], action='append')
  args = parser.parse_args()

  servers = args.servers
  if len(args.servers) < 1:
    servers = ["nats://127.0.0.1:4222"]
  opts = { "servers": servers }

  # Make sure we're connected to a server first...
  nc = NATS()
  try:
    yield nc.connect(**opts)
  except Exception, e:
    sys.stderr.write("ERROR: {0}".format(e))
    show_usage_and_die()

  @tornado.gen.coroutine
  def handler(msg):
    yield nc.publish(msg.reply, "")
  yield nc.subscribe(args.subject, cb=handler)

  # Start the benchmark
  start = time.time()
  to_send = args.iterations

  print("Sending {0} request/responses on [{1}]".format(
      args.iterations, args.subject))
  while to_send > 0:
    to_send -= 1
    if to_send == 0:
      break

    yield nc.timed_request(args.subject, "")
    if (to_send % HASH_MODULO) == 0:
      sys.stdout.write("+")
      sys.stdout.flush()

  duration = time.time() - start
  ms = "%.3f" % ((duration/args.iterations) * 1000)
  print("\nTest completed : {0} ms avg request/response latency".format(ms))
  yield nc.close()

if __name__ == '__main__':
  tornado.ioloop.IOLoop.instance().run_sync(main)
