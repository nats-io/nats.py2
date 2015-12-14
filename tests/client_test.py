import sys

if sys.version_info >= (2, 7):
     import unittest
else:
    import unittest2 as unittest

import tornado.httpclient
import tornado.concurrent
import tornado.testing
import tornado.gen
import tornado.ioloop
import subprocess
import threading
import time
import json
import socket
import os

from datetime import timedelta
from collections import defaultdict as Hash
from nats.io.errors import *
from nats.io.client import Client, __version__
from nats.io.utils  import new_inbox, INBOX_PREFIX
from nats.protocol.parser import *

class Gnatsd(object):

     def __init__(self,
                  port=4222,
                  user="",
                  password="",
                  timeout=0,
                  http_port=8222,
                  debug=False
               ):
          self.port = port
          self.user = user
          self.password = password
          self.timeout = timeout
          self.http_port = http_port
          self.proc = None
          self.debug = debug

          env_debug_flag = os.environ.get("DEBUG_NATS_TEST")
          if env_debug_flag == "true":
               self.debug = True

     def start(self):
          cmd = ["gnatsd", "-p", "%d" % self.port, "-m", "%d" % self.http_port]

          if self.user != "":
               cmd.append("--user")
               cmd.append(self.user)
          if self.password != "":
               cmd.append("--pass")
               cmd.append(self.password)

          if self.debug:
               cmd.append("-DV")

          if self.debug:
               self.proc = subprocess.Popen(cmd)
          else:
               # Redirect to dev null all server output
               devnull = open(os.devnull, 'w')
               self.proc = subprocess.Popen(cmd, stdout=devnull, stderr=subprocess.STDOUT)

          if self.debug:
               if self.proc is None:
                    print("[\031[0;33mDEBUG\033[0;0m] Failed to start server listening on port %d started." % self.port)
               else:
                    print("[\033[0;33mDEBUG\033[0;0m] Server listening on port %d started." % self.port)

     def finish(self):
          if self.debug:
               print("[\033[0;33mDEBUG\033[0;0m] Server listening on %d will stop." % self.port)

          if self.debug and self.proc is None:
               print("[\033[0;31mDEBUG\033[0;0m] Failed terminating server listening on port %d" % self.port)
          else:
               self.proc.terminate()
               self.proc.wait()
               if self.debug:
                    print("[\033[0;33mDEBUG\033[0;0m] Server listening on %d was stopped." % self.port)

class Log():
     def __init__(self, debug=False):
          self.records = Hash(list)
          self.debug = debug

     def persist(self, msg):
          if self.debug:
               print("[\033[0;33mDEBUG\033[0;0m] Message received: [{0} {1} {2}].".format(msg.subject, msg.reply, msg.data))
          self.records[msg.subject].append(msg)

class ClientUtilsTest(unittest.TestCase):

     def setUp(self):
          print("\n=== RUN {0}.{1}".format(self.__class__.__name__, self._testMethodName))

     def test_default_connect_command(self):
          nc = Client()
          nc.options["verbose"] = False
          nc.options["pedantic"] = False
          nc.options["auth_required"] = False
          nc.options["name"] = None
          got = nc.connect_command()
          expected = 'CONNECT {"lang": "python2", "pedantic": false, "verbose": false, "version": "%s"}\r\n' % __version__
          self.assertEqual(expected, got)

     def test_default_connect_command_with_name(self):
          nc = Client()
          nc.options["verbose"] = False
          nc.options["pedantic"] = False
          nc.options["auth_required"] = False
          nc.options["name"] = "secret"
          got = nc.connect_command()
          expected = 'CONNECT {"lang": "python2", "name": "secret", "pedantic": false, "verbose": false, "version": "%s"}\r\n' % __version__
          self.assertEqual(expected, got)

     def tests_generate_new_inbox(self):
          inbox = new_inbox()
          self.assertTrue(inbox.startswith(INBOX_PREFIX))
          min_expected_len = len(INBOX_PREFIX)
          self.assertTrue(len(inbox) > min_expected_len)

class ClientTest(tornado.testing.AsyncTestCase):

     def setUp(self):
          print("\n=== RUN {0}.{1}".format(self.__class__.__name__, self._testMethodName))
          self.threads = []
          self.server_pool = []

          server = Gnatsd(port=4222)
          self.server_pool.append(server)

          for gnatsd in self.server_pool:
               t = threading.Thread(target=gnatsd.start)
               self.threads.append(t)
               t.start()

          time.sleep(2)
          super(ClientTest, self).setUp()

     def tearDown(self):
          for gnatsd in self.server_pool:
               gnatsd.finish()

          for t in self.threads:
               t.join()

          super(ClientTest, self).tearDown()

     @tornado.testing.gen_test
     def test_connect_verbose(self):
          nc = Client()
          options = {
               "verbose": True,
               "io_loop": self.io_loop
               }
          yield nc.connect(**options)

          info_keys = nc._server_info.keys()
          self.assertTrue(len(info_keys) > 0)

          got = nc.connect_command()
          expected = 'CONNECT {"lang": "python2", "pedantic": false, "verbose": true, "version": "%s"}\r\n' % __version__
          self.assertEqual(expected, got)

     @tornado.testing.gen_test
     def test_connect_pedantic(self):
          nc = Client()
          yield nc.connect(io_loop=self.io_loop, pedantic=True)

          info_keys = nc._server_info.keys()
          self.assertTrue(len(info_keys) > 0)

          got = nc.connect_command()
          expected = 'CONNECT {"lang": "python2", "pedantic": true, "verbose": false, "version": "%s"}\r\n' % __version__
          self.assertEqual(expected, got)

     @tornado.testing.gen_test
     def test_parse_info(self):
          nc = Client()
          yield nc.connect(io_loop=self.io_loop)

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

     @tornado.testing.gen_test(timeout=5)
     def test_connect_error_callback(self):

          class SampleClient():
               def __init__(self):
                    self.nc = Client()
                    self.err = ""

               def err_cb(self, e):
                    self.err += str(e)

          client = SampleClient()
          with self.assertRaises(ErrNoServers):
               options = {
                    "servers": ["nats://127.0.0.1:4223"],
                    "error_cb": client.err_cb,
                    "allow_reconnect": False,
                    "io_loop": self.io_loop
                    }
               yield client.nc.connect(**options)

          self.assertEqual(socket.error, type(client.nc.last_error()))
          self.assertEqual('[Errno 61] Connection refused', client.err)

     @tornado.testing.gen_test
     def test_subscribe(self):
          nc = Client()
          options = {
               "io_loop": self.io_loop
               }
          yield nc.connect(**options)
          self.assertEqual(Client.CONNECTED, nc._status)
          info_keys = nc._server_info.keys()
          self.assertTrue(len(info_keys) > 0)

          inbox = new_inbox()
          yield nc.subscribe("help.1")
          yield nc.subscribe("help.2")

          http = tornado.httpclient.AsyncHTTPClient()
          response = yield http.fetch('http://127.0.0.1:%d/connz' % self.server_pool[0].http_port)
          result = json.loads(response.body)
          connz = result['connections'][0]
          self.assertEqual(2, connz['subscriptions'])

     @tornado.testing.gen_test
     def test_publish(self):
          nc = Client()
          yield nc.connect(io_loop=self.io_loop)
          self.assertEqual(Client.CONNECTED, nc._status)
          info_keys = nc._server_info.keys()
          self.assertTrue(len(info_keys) > 0)

          log = Log()
          yield nc.subscribe(">", "", log.persist)
          yield nc.publish("one", "hello")
          yield nc.publish("two", "world")

          http = tornado.httpclient.AsyncHTTPClient()
          response = yield http.fetch('http://127.0.0.1:%d/varz' % self.server_pool[0].http_port)
          varz = json.loads(response.body)
          self.assertEqual(10, varz['in_bytes'])
          self.assertEqual(10, varz['out_bytes'])
          self.assertEqual(2, varz['in_msgs'])
          self.assertEqual(2, varz['out_msgs'])
          self.assertEqual(2, len(log.records.keys()))
          self.assertEqual("hello", log.records['one'][0].data)
          self.assertEqual("world", log.records['two'][0].data)
          self.assertEqual(10, nc.stats['in_bytes'])
          self.assertEqual(10, nc.stats['out_bytes'])
          self.assertEqual(2, nc.stats['in_msgs'])
          self.assertEqual(2, nc.stats['out_msgs'])

     @tornado.testing.gen_test
     def test_publish_max_payload(self):
          nc = Client()
          yield nc.connect(io_loop=self.io_loop)
          self.assertEqual(Client.CONNECTED, nc._status)
          info_keys = nc._server_info.keys()
          self.assertTrue(len(info_keys) > 0)

          with self.assertRaises(ErrMaxPayload):
               yield nc.publish("large-message", "A" * (nc._server_info["max_payload"] * 2))

     @tornado.testing.gen_test
     def test_publish_request(self):
          nc = Client()

          yield nc.connect(io_loop=self.io_loop)
          self.assertEqual(Client.CONNECTED, nc._status)
          info_keys = nc._server_info.keys()
          self.assertTrue(len(info_keys) > 0)

          inbox = new_inbox()
          yield nc.publish_request("help.1", inbox, "hello")
          yield nc.publish_request("help.2", inbox, "world")

          http = tornado.httpclient.AsyncHTTPClient()
          response = yield http.fetch('http://127.0.0.1:%d/varz' % self.server_pool[0].http_port)
          varz = json.loads(response.body)

          self.assertEqual(10, varz['in_bytes'])
          self.assertEqual(0,  varz['out_bytes'])
          self.assertEqual(2,  varz['in_msgs'])
          self.assertEqual(0,  varz['out_msgs'])
          self.assertEqual(0,  nc.stats['in_bytes'])
          self.assertEqual(10, nc.stats['out_bytes'])
          self.assertEqual(0,  nc.stats['in_msgs'])
          self.assertEqual(2,  nc.stats['out_msgs'])

class ClientAuthTest(tornado.testing.AsyncTestCase):

     def setUp(self):
          print("\n=== RUN {0}.{1}".format(self.__class__.__name__, self._testMethodName))
          self.threads = []
          self.server_pool = []

          server1 = Gnatsd(port=4223, user="foo", password="bar", http_port=8223)
          self.server_pool.append(server1)
          server2 = Gnatsd(port=4224, user="hoge", password="fuga", http_port=8224)
          self.server_pool.append(server2)

          for gnatsd in self.server_pool:
               t = threading.Thread(target=gnatsd.start)
               self.threads.append(t)
               t.start()

          time.sleep(1)
          super(ClientAuthTest, self).setUp()

     def tearDown(self):
          for gnatsd in self.server_pool:
               gnatsd.finish()

          for t in self.threads:
               t.join()

          super(ClientAuthTest, self).tearDown()

     @tornado.testing.gen_test(timeout=10)
     def test_auth_connect(self):
          nc = Client()
          options = {
               "dont_randomize": True,
               "servers": [
                    "nats://foo:bar@127.0.0.1:4223",
                    "nats://hoge:fuga@127.0.0.1:4224"
                    ],
               "io_loop": self.io_loop
               }
          yield nc.connect(**options)
          self.assertEqual(True, nc._server_info["auth_required"])

          log = Log()
          sid_1 = yield nc.subscribe("foo",  "", log.persist)
          self.assertEqual(sid_1, 1)
          sid_2 = yield nc.subscribe("bar",  "", log.persist)
          self.assertEqual(sid_2, 2)
          sid_3 = yield nc.subscribe("quux", "", log.persist)
          self.assertEqual(sid_3, 3)
          yield nc.publish("foo", "hello")
          yield tornado.gen.sleep(1.0)

          http = tornado.httpclient.AsyncHTTPClient()
          response = yield http.fetch('http://127.0.0.1:8223/connz')
          result = json.loads(response.body)
          connz = result['connections'][0]
          self.assertEqual(3, connz['subscriptions'])
          self.assertEqual(1, connz['in_msgs'])
          self.assertEqual(5, connz['in_bytes'])

          yield nc.publish("foo", "world")
          yield tornado.gen.sleep(0.5)
          response = yield http.fetch('http://127.0.0.1:8223/connz')
          result = json.loads(response.body)
          connz = result['connections'][0]
          self.assertEqual(3, connz['subscriptions'])
          self.assertEqual(2, connz['in_msgs'])
          self.assertEqual(10, connz['in_bytes'])

          orig_gnatsd = self.server_pool.pop(0)
          orig_gnatsd.finish()

          try:
               a = nc._current_server
               # Wait for reconnect logic kick in...
               yield tornado.gen.sleep(5)
          finally:
               b = nc._current_server
               self.assertNotEqual(a.uri, b.uri)

          self.assertTrue(nc.is_connected())
          self.assertFalse(nc.is_reconnecting())

          http = tornado.httpclient.AsyncHTTPClient()
          response = yield http.fetch('http://127.0.0.1:8224/connz')
          result = json.loads(response.body)
          connz = result['connections'][0]
          self.assertEqual(3, connz['subscriptions'])
          self.assertEqual(0, connz['in_msgs'])
          self.assertEqual(0, connz['in_bytes'])

          yield nc.publish("foo", "!!!")
          yield tornado.gen.sleep(0.5)
          response = yield http.fetch('http://127.0.0.1:8224/connz')
          result = json.loads(response.body)
          connz = result['connections'][0]
          self.assertEqual(3, connz['subscriptions'])
          self.assertEqual(1, connz['in_msgs'])
          self.assertEqual(3, connz['in_bytes'])

          full_msg = ''
          for msg in log.records['foo']:
               full_msg += msg.data

          self.assertEqual('helloworld!!!', full_msg)

     @tornado.testing.gen_test(timeout=10)
     def test_auth_connect_fails(self):

          class Component:
               def __init__(self, nc):
                    self.nc = nc
                    self.error = None
                    self.error_cb_called = False
                    self.close_cb_called = False
                    self.disconnected_cb_called = False
                    self.reconnected_cb_called = False

               def error_cb(self, err):
                    self.error = err
                    self.error_cb_called = True

               def close_cb(self):
                    self.close_cb_called = True

               def disconnected_cb(self):
                    self.disconnected_cb_called = True

               def reconnected_cb(self):
                    self.reconnected_cb_called = True

          nc = Client()
          component = Component(nc)
          options = {
               "dont_randomize": True,
               "servers": [
                    "nats://foo:bar@127.0.0.1:4223",
                    "nats://foo2:bar2@127.0.0.1:4224"
                    ],
               "io_loop": self.io_loop,
               "close_cb": component.close_cb,
               "error_cb": component.error_cb,
               "disconnected_cb": component.disconnected_cb,
               "reconnected_cb": component.reconnected_cb
               }
          yield component.nc.connect(**options)
          self.assertEqual(True, component.nc.is_connected())
          self.assertEqual(True, nc._server_info["auth_required"])

          log = Log(debug=True)
          sid_1 = yield component.nc.subscribe("foo",  "", log.persist)
          self.assertEqual(sid_1, 1)
          sid_2 = yield component.nc.subscribe("bar",  "", log.persist)
          self.assertEqual(sid_2, 2)
          sid_3 = yield component.nc.subscribe("quux", "", log.persist)
          self.assertEqual(sid_3, 3)
          yield nc.publish("foo", "hello")
          yield tornado.gen.sleep(1)
          self.assertEqual("hello", log.records['foo'][0].data)

          http = tornado.httpclient.AsyncHTTPClient()
          response = yield http.fetch('http://127.0.0.1:8223/connz')
          result = json.loads(response.body)
          connz = result['connections'][0]
          self.assertEqual(3, connz['subscriptions'])
          self.assertEqual(1, connz['in_msgs'])
          self.assertEqual(5, connz['in_bytes'])

          yield component.nc.publish("foo", "world")
          yield tornado.gen.sleep(0.5)
          response = yield http.fetch('http://127.0.0.1:8223/connz')
          result = json.loads(response.body)
          connz = result['connections'][0]
          self.assertEqual(3, connz['subscriptions'])
          self.assertEqual(2, connz['in_msgs'])
          self.assertEqual(10, connz['in_bytes'])

          orig_gnatsd = self.server_pool.pop(0)
          orig_gnatsd.finish()

          # Wait for reconnect logic kick in and fail due to authorization error.
          yield tornado.gen.sleep(5)
          self.assertFalse(component.nc.is_connected())
          self.assertTrue(component.nc.is_reconnecting())

          # No guarantee in getting the error before the connection is closed,
          # by the server though the behavior should be as below.
          # self.assertEqual(1, component.nc.stats['errors_received'])
          # self.assertEqual(ErrAuthorization, component.nc.last_error())
          self.assertTrue(component.error_cb_called)
          self.assertTrue(component.close_cb_called)
          self.assertFalse(component.disconnected_cb_called)
          self.assertTrue(component.reconnected_cb_called)

if __name__ == '__main__':
    runner = unittest.TextTestRunner(stream=sys.stdout)
    unittest.main(verbosity=2, exit=False, testRunner=runner)
