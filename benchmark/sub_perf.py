import argparse, sys
import tornado.ioloop
import tornado.gen
import time
from random import randint
from nats.io.client import Client as NATS

DEFAULT_NUM_MSGS = 100000
DEFAULT_MSG_SIZE = 16
DEFAULT_BATCH_SIZE = 100
HASH_MODULO = 1000


def show_usage():
    message = """
Usage: sub_perf [options]

options:
    -n COUNT                         Messages to wait (default: 100000}
    -S SUBJECT                       Send subject (default: (test)
    -b BATCH                         Batch size (default: (100)
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
    parser.add_argument('-n', '--count', default=DEFAULT_NUM_MSGS, type=int)
    parser.add_argument('-S', '--subject', default='test')
    parser.add_argument('-t', '--subtype', default='sync')
    parser.add_argument('--servers', default=[], action='append')
    args = parser.parse_args()

    servers = args.servers
    if len(args.servers) < 1:
        servers = ["nats://127.0.0.1:4222"]
    opts = {"servers": servers}

    # Make sure we're connected to a server first...
    nc = NATS()
    try:
        yield nc.connect(**opts)
    except Exception, e:
        sys.stderr.write("ERROR: {0}".format(e))
        show_usage_and_die()

    @tornado.gen.coroutine
    def handler(msg):
        global received
        received += 1
        # Measure time from when we get the first message.
        if received == 1:
            start = time.time()
        if (received % HASH_MODULO) == 0:
            sys.stdout.write("*")
            sys.stdout.flush()

    if args.subtype == 'sync':
        yield nc.subscribe(args.subject, cb=handler)
    elif args.subtype == 'async':
        yield nc.subscribe_async(args.subject, cb=handler)
    else:
        sys.stderr.write(
            "ERROR: Unsupported type of subscription {0}".format(e))
        show_usage_and_die()

    # Start the benchmark
    start = time.time()
    to_send = args.count

    print("Waiting for {0} messages on [{1}]...".format(
        args.count, args.subject))
    while received < args.count:
        # Minimal pause in between batches sent to server
        yield tornado.gen.sleep(0.1)

    # Ensure that all commands have been processed by server already.
    yield nc.flush()

    elapsed = time.time() - start
    print("\nTest completed : {0} msgs/sec sent \n".format(
        args.count / elapsed))
    print("Received {0} messages ({1} msgs/sec)".format(
        received, received / elapsed))
    yield nc.close()


if __name__ == '__main__':
    tornado.ioloop.IOLoop.current().run_sync(main)
