import sys

if sys.version_info >= (2, 7):
     import unittest
else:
    import unittest2 as unittest

import tornado.httpclient
import tornado.testing
import tornado.gen
import tornado.ioloop
import subprocess
import multiprocessing
import time
import json

from nats.io.errors import *
from nats.io.client import Client, __version__
from nats.io.utils  import new_inbox, INBOX_PREFIX
from nats.protocol.parser import *

class Server(object):

     def __init__(self,
                  port=4222,
                  user="",
                  password="",
                  timeout=1,
                  http_port=8222
               ):
          self.port = port
          self.user = user
          self.password = password
          self.timeout = timeout
          self.http_port = http_port
          self.proc = None

     def run(self):
          cmd = ["gnatsd", "-p", "%d" % self.port, "-DV", "-m", "%d" % self.http_port] # , "-l", "gnatsd.log"]

          if self.user != "":
               cmd.append("--user")
               cmd.append(self.user)
          if self.password != "":
               cmd.append("--pass")
               cmd.append(self.password)

          self.proc = subprocess.Popen(cmd)
          time.sleep(self.timeout)
          print("done!!!", self.port)
          self.proc.terminate()

# class ClientUtilsTest(unittest.TestCase):

#     def test_default_connect_command(self):
#         nc = Client()
#         nc.options["verbose"] = False
#         nc.options["pedantic"] = False
#         nc.options["auth_required"] = False
#         got = nc.connect_command()
#         expected = 'CONNECT {"lang": "python2", "pedantic": false, "verbose": false, "version": "%s"}\r\n' % __version__
#         self.assertEqual(expected, got)

#     def tests_generate_new_inbox(self):
#          inbox = new_inbox()
#          self.assertTrue(inbox.startswith(INBOX_PREFIX))
#          min_expected_len = len(INBOX_PREFIX)
#          self.assertTrue(len(inbox) > min_expected_len)

# class ClientTest(tornado.testing.AsyncTestCase):

#      def setUp(self):
#           self.server = Server(port=4222)
#           self.proc = multiprocessing.Process(target=self.server.run)
#           self.proc.start()
#           time.sleep(0.5)
#           super(ClientTest, self).setUp()

#      def tearDown(self):
#           self.proc.join(1)
#           self.proc.terminate()
#           super(ClientTest, self).tearDown()

#      @tornado.testing.gen_test
#      def test_parse_info(self):
#           nc = Client()
#           yield nc.connect()

#           info_keys = nc._server_info.keys()
#           self.assertTrue(len(info_keys) > 0)
#           self.assertIn("server_id", info_keys)
#           self.assertIn("version", info_keys)
#           self.assertIn("go", info_keys)
#           self.assertIn("host", info_keys)
#           self.assertIn("port", info_keys)
#           self.assertIn("auth_required", info_keys)
#           self.assertIn("ssl_required", info_keys)
#           self.assertIn("max_payload", info_keys)

#      @tornado.testing.gen_test
#      def test_connect_verbose(self):
#           nc = Client()
#           yield nc.connect({"verbose": True})

#           info_keys = nc._server_info.keys()
#           self.assertTrue(len(info_keys) > 0)

#      @tornado.testing.gen_test
#      def test_connect_pedantic(self):
#           nc = Client()
#           yield nc.connect({"pedantic": True})

#           info_keys = nc._server_info.keys()
#           self.assertTrue(len(info_keys) > 0)

#      @tornado.testing.gen_test
#      def test_connect_missing_server(self):
#           nc = Client()
#           with self.assertRaises(Exception):
#                yield nc.connect({"servers": ["nats://127.0.0.1:4223"]})

#      @tornado.testing.gen_test
#      def test_publish(self):
#           nc = Client()
#           yield nc.connect({"pedantic": True})
#           self.assertEqual(Client.CONNECTED, nc._status)
#           info_keys = nc._server_info.keys()
#           self.assertTrue(len(info_keys) > 0)
#           yield nc.publish("one", "hello")
#           yield nc.publish("two", "world")

class ClientAuthTest(tornado.testing.AsyncTestCase):

     def setUp(self):
          self.server = Server(port=4223, user="foo", password="bar", timeout=1, http_port=8223)
          self.proc = multiprocessing.Process(target=self.server.run)
          self.proc.start()

          self.server2 = Server(port=4224, user="foo2", password="bar2", timeout=4, http_port=8224)
          self.proc2 = multiprocessing.Process(target=self.server2.run)
          self.proc2.start()
          time.sleep(0.5)
          super(ClientAuthTest, self).setUp()

     def tearDown(self):
          self.proc.join(10)
          self.proc.terminate()
          self.proc2.join(10)
          self.proc2.terminate()
          super(ClientAuthTest, self).tearDown()

     @tornado.testing.gen_test
     def test_auth_connect(self):
          nc = Client()
          options = {
               "dont_randomize": True,
               "servers": [
                    "nats://foo:bar@127.0.0.1:4223",
                    "nats://foo2:bar2@127.0.0.1:4224"
                    ]
               }
          yield nc.connect(options)
          self.assertEqual(True, nc._server_info["auth_required"])

          sid_1 = yield nc.subscribe("foo", "",  lambda msg: nc.publish(msg.reply, msg.data))
          self.assertEqual(sid_1, 1)
          sid_2 = yield nc.subscribe("bar", "",  lambda msg: nc.publish(msg.reply, msg.data))
          self.assertEqual(sid_2, 2)
          sid_3 = yield nc.subscribe("quux", "", lambda msg: nc.publish(msg.reply, msg.data))
          self.assertEqual(sid_3, 3)

          yield nc.publish("foo", "hello")

          http = tornado.httpclient.AsyncHTTPClient()
          response = yield http.fetch('http://127.0.0.1:8223/connz')
          result = json.loads(response.body)
          connz = result['connections'][0]
          self.assertEqual(3, connz['subscriptions'])
          self.assertEqual(1, connz['in_msgs'])
          self.assertEqual(5, connz['in_bytes'])

          yield nc.publish("foo", "world")
          response = yield http.fetch('http://127.0.0.1:8223/connz')
          result = json.loads(response.body)
          connz = result['connections'][0]
          self.assertEqual(3, connz['subscriptions'])
          self.assertEqual(2, connz['in_msgs'])
          self.assertEqual(10, connz['in_bytes'])

          # Force disconnect...
          # nc.io.close()
          # nc._unbind()
          # http.close()

          # TODO: Test reconnect with another server
          try:
               a = nc._current_server
               yield tornado.gen.sleep(2)
          finally:
               b = nc._current_server
               self.assertNotEqual(a.uri, b.uri)

if __name__ == '__main__':
    runner = unittest.TextTestRunner(stream=sys.stdout)
    unittest.main(verbosity=1, exit=False, testRunner=runner)
