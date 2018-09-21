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
Usage: pub_sub_perf [options]

options:
    -n COUNT                         Messages to send (default: 100000}
    -s SIZE                          Message size (default: 16)
    -S SUBJECT                       Send subject (default: (test)
    -b BATCH                         Batch size (default: (100)    
    """
    print(message)


def show_usage_and_die():
    show_usage()
    sys.exit(1)


global received
received = 0


def close_cb():
    print("Closed connection to NATS")


def disconnected_cb():
    print("Disconnected from NATS")


def reconnected_cb():
    print("Reconnected to NATS")


@tornado.gen.coroutine
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--count', default=DEFAULT_NUM_MSGS, type=int)
    parser.add_argument('-s', '--size', default=DEFAULT_MSG_SIZE, type=int)
    parser.add_argument('-S', '--subject', default='test')
    parser.add_argument('-b', '--batch', default=DEFAULT_BATCH_SIZE, type=int)
    parser.add_argument('--servers', default=[], action='append')
    args = parser.parse_args()

    data = []
    for i in range(0, args.size):
        data.append("W")
    payload = b''.join(data)

    servers = args.servers
    if len(args.servers) < 1:
        servers = ["nats://127.0.0.1:4222"]
    opts = {
        "servers": servers,
        "disconnected_cb": disconnected_cb,
        "close_cb": close_cb,
        "reconnected_cb": reconnected_cb,
        "allow_reconnect": False,
    }

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

    yield nc.subscribe(args.subject, cb=handler)

    # Start the benchmark
    start = time.time()
    to_send = args.count

    print("Sending {0} messages of size {1} bytes on [{2}]".format(
        args.count, args.size, args.subject))
    while to_send > 0:
        for i in range(0, args.batch):
            to_send -= 1
            yield nc.publish(args.subject, payload)
            if (to_send % HASH_MODULO) == 0:
                sys.stdout.write("#")
                sys.stdout.flush()
            if to_send == 0:
                break

        # Minimal pause in between batches sent to server
        yield tornado.gen.sleep(0.00001)

    # Ensure that all commands have been processed by server already.
    yield nc.flush()

    elapsed = time.time() - start
    mbytes = "%.1f" % (((args.size * args.count) / elapsed) / (1024 * 1024))
    print("\nTest completed : {0} msgs/sec sent ({1}) MB/sec\n".format(
        args.count / elapsed, mbytes))
    print("Received {0} messages ({1} msgs/sec)".format(
        received, received / elapsed))
    yield nc.close()


if __name__ == '__main__':
    tornado.ioloop.IOLoop.current().run_sync(main)
