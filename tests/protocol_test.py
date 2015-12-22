import sys

if sys.version_info >= (2, 7):
     import unittest
else:
    import unittest2 as unittest

import tornado.testing
from nats.io.client import Subscription
from nats.protocol.parser import *

class MockNatsClient:

    def __init__(self):
        self._subs = {}
        self._pongs = []
        self._pings_outstanding = 0
        self._pongs_received = 0
        self._server_info = {"max_payload": 1048576, "auth_required": False }

    def send_command(self, cmd):
        pass

    def _process_pong(self):
        pass

    def _process_ping(self):
        pass

    def _process_msg(self, msg):
        pass

    def _process_err(self, err=None):
        pass

class ProtocolParserTest(unittest.TestCase):

    def test_parse_ping(self):
        ps = Parser(MockNatsClient())
        data = b'PING\r\n'
        ps.parse(data)
        self.assertEqual(len(ps.scratch), 0)
        self.assertEqual(ps.state, AWAITING_CONTROL_LINE)

    def test_parse_pong(self):
        ps = Parser(MockNatsClient())
        data = b'PONG\r\n'
        ps.parse(data)
        self.assertEqual(len(ps.scratch), 0)
        self.assertEqual(ps.state, AWAITING_CONTROL_LINE)

    def test_parse_ok(self):
        ps = Parser()
        data = b'+OK\r\n'
        ps.parse(data)
        self.assertEqual(len(ps.scratch), 0)
        self.assertEqual(ps.state, AWAITING_CONTROL_LINE)

    def test_parse_msg(self):
        nc = MockNatsClient()
        expected = b'hello world!'

        def payload_test(msg):
          self.assertEqual(msg["data"], expected)

        params = {
             "subject": "hello",
             "queue": None,
             "cb": payload_test,
             "future": None
             }
        sub = Subscription(**params)
        nc._subs[1] = sub
        ps = Parser(nc)
        data = b'MSG hello 1 world 12\r\n'
        ps.parse(data)
        self.assertEqual(len(ps.scratch), 0)
        self.assertEqual(len(ps.msg_arg.keys()), 3)
        self.assertEqual(ps.msg_arg["subject"], "hello")
        self.assertEqual(ps.msg_arg["reply"], "world")
        self.assertEqual(ps.msg_arg["sid"], 1)
        self.assertEqual(ps.needed, 12)
        self.assertEqual(ps.state, AWAITING_MSG_PAYLOAD)

        ps.parse(expected)
        self.assertEqual(len(ps.scratch), 0)
        self.assertEqual(ps.state, AWAITING_MSG_END)

        data = b'\r\n'
        ps.parse(data)
        self.assertEqual(len(ps.scratch), 0)
        self.assertEqual(ps.state, AWAITING_CONTROL_LINE)

    def test_parse_msg_op(self):
        ps = Parser()
        data = b'MSG hello'
        ps.parse(data)
        self.assertEqual(len(ps.scratch), 9)
        self.assertEqual(ps.state, AWAITING_MSG_ARG)

    def test_parse_split_msg_op(self):
        ps = Parser()
        data = b'MSG'
        ps.parse(data)
        self.assertEqual(len(ps.scratch), 3)
        self.assertEqual(ps.state, AWAITING_MSG_ARG)

    def test_parse_split_msg_op_space(self):
        ps = Parser()
        data = b'MSG '
        ps.parse(data)
        self.assertEqual(len(ps.scratch), 4)
        self.assertEqual(ps.state, AWAITING_MSG_ARG)

    def test_parse_split_msg_op_wrong_args(self):
        ps = Parser()
        data = b'MSG PONG\r\n'
        with self.assertRaises(ErrProtocol):
             ps.parse(data)
             # self.assertEqual(len(ps.scratch), 5)
             self.assertEqual(ps.state, AWAITING_MSG_ARG)

    def test_parse_err_op(self):
        ps = Parser()
        data = b"-ERR 'Slow..."
        ps.parse(data)
        self.assertEqual(len(ps.scratch), 13)
        self.assertEqual(ps.state, AWAITING_MINUS_ERR_ARG)

    def test_parse_err(self):
        ps = Parser(MockNatsClient())
        data = b"-ERR 'Slow Consumer'\r\n"
        ps.parse(data)
        self.assertEqual(len(ps.scratch), 0)
        self.assertEqual(ps.state, AWAITING_CONTROL_LINE)

if __name__ == '__main__':
    runner = unittest.TextTestRunner(stream=sys.stdout)
    unittest.main(verbosity=2, exit=False, testRunner=runner)
