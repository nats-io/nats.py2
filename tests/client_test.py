import sys

if sys.version_info >= (2, 7):
     import unittest
else:
    import unittest2 as unittest

import tornado.testing
import tornado.gen
import subprocess
import multiprocessing
import time
import socket

from nats.io.errors import *
from nats.io.client import Client, __version__
from nats.io.utils  import new_inbox, INBOX_PREFIX
from nats.protocol.parser import *

class Server(object):

     def __init__(self,
                  port=4222,
                  user="",
                  password="",
                  timeout=1
               ):
          self.port = port
          self.user = user
          self.password = password
          self.timeout = timeout
          self.proc = None

     def run(self):
          cmd = ["gnatsd", "-p", "%d" % self.port, "-DV"] # , "-l", "gnatsd.log"]

          if self.user != "":
               cmd.append("--user")
               cmd.append(self.user)
          if self.password != "":
               cmd.append("--pass")
               cmd.append(self.password)

          print(cmd)
          self.proc = subprocess.Popen(cmd)
          # For now wait for a bit then stop abruptly
          time.sleep(self.timeout)
          self.proc.terminate()

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

     def setUp(self):
          self.server = Server(port=4222)
          self.proc = multiprocessing.Process(target=self.server.run)
          self.proc.start()
          # Dumb wait for the server to start
          time.sleep(0.5)
          super(ClientTest, self).setUp()

     def tearDown(self):
          self.proc.join(3)
          self.proc.terminate()
          super(ClientTest, self).tearDown()

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

     # @tornado.testing.gen_test
     # def test_connect_missing_server(self):
     #      nc = Client()
     #      with self.assertRaises(Exception):
     #           yield nc.connect({"servers": ["nats://127.0.0.1:4226"]})

     @tornado.testing.gen_test
     def test_publish(self):
          nc = Client()
          yield nc.connect({"pedantic": True})
          self.assertEqual(Client.CONNECTED, nc._status)
          info_keys = nc._server_info.keys()
          self.assertTrue(len(info_keys) > 0)
          yield nc.publish("hello", "world")
          # TODO: Confirm from the monitoring endpoint?

class ClientAuthorizationTest(tornado.testing.AsyncTestCase):

     def setUp(self):
          self.server = Server(port=4223, user="foo", password="bar")
          self.proc = multiprocessing.Process(target=self.server.run)
          self.proc.start()
          # Dumb wait for the server to start
          time.sleep(0.5)
          super(ClientAuthorizationTest, self).setUp()

     def tearDown(self):
          self.proc.join(3)
          self.proc.terminate()
          super(ClientAuthorizationTest, self).tearDown()

     @tornado.testing.gen_test
     def test_auth_connect(self):
          nc = Client()
          options = {"servers": ["nats://foo:bar@127.0.0.1:4223"]}
          yield nc.connect(options)
          self.assertEqual(True, nc._server_info["auth_required"])
          yield nc.publish("hello", "world")

if __name__ == '__main__':
    runner = unittest.TextTestRunner(stream=sys.stdout)
    unittest.main(verbosity=1, exit=False, testRunner=runner)
