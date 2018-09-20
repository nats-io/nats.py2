import cProfile as prof
import tornado.gen
from nats.protocol.parser import *


class DummyNatsClient:
    def __init__(self):
        self._subs = {}
        self._pongs = []
        self._pings_outstanding = 0
        self._pongs_received = 0
        self._server_info = {"max_payload": 1048576, "auth_required": False}
        self.stats = {
            'in_msgs': 0,
            'out_msgs': 0,
            'in_bytes': 0,
            'out_bytes': 0,
            'reconnects': 0,
            'errors_received': 0
        }

    @tornado.gen.coroutine
    def _send_command(self, cmd):
        pass

    @tornado.gen.coroutine
    def _process_pong(self):
        pass

    @tornado.gen.coroutine
    def _process_ping(self):
        pass

    @tornado.gen.coroutine
    def _process_msg(self, sid, subject, reply, data):
        self.stats['in_msgs'] += 1
        self.stats['in_bytes'] += len(data)

    @tornado.gen.coroutine
    def _process_err(self, err=None):
        pass


def generate_msg(subject, nbytes, reply=""):
    msg = []
    protocol_line = "MSG {subject} 1 {reply} {nbytes}\r\n".format(
        subject=subject, reply=reply, nbytes=nbytes).encode()
    msg.append(protocol_line)
    msg.append(b'A' * nbytes)
    msg.append(b'r\n')
    return b''.join(msg)


def parse_msgs(max_msgs=1, nbytes=1):
    buf = bytearray()
    buf.extend(b''.join(
        [generate_msg("foo", nbytes) for i in range(0, max_msgs)]))
    print("--- buffer size: {0}".format(len(buf)))
    loop = tornado.ioloop.IOLoop.current()
    ps = Parser(DummyNatsClient())
    ps.buf = buf
    loop.run_sync(ps.parse)
    print("--- stats: ", ps.nc.stats)


if __name__ == '__main__':

    benchs = [
        "parse_msgs(max_msgs=10000,   nbytes=1)",
        "parse_msgs(max_msgs=100000,  nbytes=1)",
        "parse_msgs(max_msgs=10000,   nbytes=64)",
        "parse_msgs(max_msgs=100000,  nbytes=64)",
        "parse_msgs(max_msgs=10000,   nbytes=256)",
        "parse_msgs(max_msgs=100000,  nbytes=256)",
        "parse_msgs(max_msgs=10000,   nbytes=1024)",
        "parse_msgs(max_msgs=100000,  nbytes=1024)",
        "parse_msgs(max_msgs=10000,   nbytes=8192)",
        "parse_msgs(max_msgs=100000,  nbytes=8192)",
        "parse_msgs(max_msgs=10000,   nbytes=16384)",
        "parse_msgs(max_msgs=100000,  nbytes=16384)",
    ]

    for bench in benchs:
        print("=== {0}".format(bench))
        prof.run(bench)
