import sys

if sys.version_info >= (2, 7):
     import unittest
else:
    import unittest2 as unittest

# For async tests
import tornado.testing
import tornado.tcpserver

from nats.io.errors import *
from nats.io.client import Client, __version__
from nats.io.utils  import new_inbox, INBOX_PREFIX
from nats.protocol.parser import *

# NOTE: Some tests require a running gnatsd server

class ClientUtilsTest(unittest.TestCase):

    def test_default_connect_command(self):
        nc = Client()
        nc.options["verbose"] = False
        nc.options["pedantic"] = False
        nc.options["auth_required"] = False
        got = nc.connect_command()
        expected = 'CONNECT {"lang": "python2", "pedantic": false, "verbose": false, "version": "%s"}\r\n' % __version__
        self.assertEqual(expected, got)

    def tests_generate_new_inbox(self):
         inbox = new_inbox()
         self.assertTrue(inbox.startswith(INBOX_PREFIX))
         min_expected_len = len(INBOX_PREFIX)
         self.assertTrue(len(inbox) > min_expected_len)

class ClientTest(tornado.testing.AsyncTestCase):

     @tornado.testing.gen_test
     def test_parse_info(self):
          nc = Client()
          yield nc.connect()

          info_keys = nc._server_info.keys()
          self.assertTrue(len(info_keys) > 0)
          self.assertIn("server_id", info_keys)
          self.assertIn("version", info_keys)
          self.assertIn("go", info_keys)
          self.assertIn("host", info_keys)
          self.assertIn("port", info_keys)
          self.assertIn("auth_required", info_keys)
          self.assertIn("ssl_required", info_keys)
          self.assertIn("max_payload", info_keys)

     @tornado.testing.gen_test
     def test_connect_verbose(self):
          nc = Client()
          yield nc.connect({"verbose": True})

          info_keys = nc._server_info.keys()
          self.assertTrue(len(info_keys) > 0)

     @tornado.testing.gen_test
     def test_connect_pedantic(self):
          nc = Client()
          yield nc.connect({"pedantic": True})

          info_keys = nc._server_info.keys()
          self.assertTrue(len(info_keys) > 0)

     @tornado.testing.gen_test
     def test_auth_connect(self):
          nc = Client()
          # TODO: gnatsd -DV --user foo --pass bar -p 4223
          # TODO: with self.assertRaises(ErrAuthorization):
          options = {"servers": ["nats://foo:bar@127.0.0.1:4225"]}
          yield nc.connect(options)
          self.assertEqual(True, nc._server_info["auth_required"])

     @tornado.testing.gen_test
     def test_connect_missing_server(self):
          nc = Client()
          with self.assertRaises(ErrServerConnect):
               yield nc.connect({"servers": ["nats://127.0.0.1:4226"]})

if __name__ == '__main__':
    runner = unittest.TextTestRunner(stream=sys.stdout)
    unittest.main(verbosity=1, exit=False, testRunner=runner)
