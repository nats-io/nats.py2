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
import tornado.iostream
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
from nats import __lang__, __version__

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

          http = tornado.httpclient.HTTPClient()
          while True:
               try:
                    response = http.fetch('http://127.0.0.1:8222/varz')
                    if response.code == 200:
                         break
                    continue
               except:
                    time.sleep(0.1)
                    continue
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
     def test_connect_custom_connect_timeout(self):
          nc = Client()
          yield nc.connect(io_loop=self.io_loop, connect_timeout=1)
          self.assertEqual(1, nc.options["connect_timeout"])

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
          yield tornado.gen.sleep(0.5)

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
          yield tornado.gen.sleep(1.0)

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
     def test_request(self):
          nc = Client()
          yield nc.connect(io_loop=self.io_loop)

          class Component:
               def __init__(self, nc):
                    self.nc = nc
                    self.replies = []

               def receive_responses(self, msg=None):
                    self.replies.append(msg)

               @tornado.gen.coroutine
               def respond(self, msg=None):
                    yield self.nc.publish(msg.reply, "ok:1")
                    yield self.nc.publish(msg.reply, "ok:2")
                    yield self.nc.publish(msg.reply, "ok:3")

          log = Log()
          c = Component(nc)
          yield nc.subscribe(">", "", log.persist)
          yield nc.subscribe("help", "", c.respond)
          yield nc.request("help", "please", expected=2, cb=c.receive_responses)
          yield tornado.gen.sleep(0.5)

          http = tornado.httpclient.AsyncHTTPClient()
          response = yield http.fetch('http://127.0.0.1:%d/varz' % self.server_pool[0].http_port)
          varz = json.loads(response.body)
          self.assertEqual(18, varz['in_bytes'])
          self.assertEqual(32, varz['out_bytes'])
          self.assertEqual(4, varz['in_msgs'])
          self.assertEqual(7, varz['out_msgs'])
          self.assertEqual(2, len(log.records.keys()))
          self.assertEqual("please", log.records['help'][0].data)
          self.assertEqual(2, len(c.replies))
          self.assertEqual(32, nc.stats['in_bytes'])
          self.assertEqual(18, nc.stats['out_bytes'])
          self.assertEqual(7, nc.stats['in_msgs'])
          self.assertEqual(4, nc.stats['out_msgs'])

          full_msg = ''
          for msg in log.records['help']:
               full_msg += msg.data

          self.assertEqual('please', full_msg)
          self.assertEqual("ok:1", c.replies[0].data)
          self.assertEqual("ok:2", c.replies[1].data)

     @tornado.testing.gen_test
     def test_timed_request(self):
          nc = Client()
          yield nc.connect(io_loop=self.io_loop)

          class Component:
               def __init__(self, nc):
                    self.nc = nc

               @tornado.gen.coroutine
               def respond(self, msg=None):
                    yield self.nc.publish(msg.reply, "ok:1")
                    yield self.nc.publish(msg.reply, "ok:2")
                    yield self.nc.publish(msg.reply, "ok:3")

          log = Log()
          c = Component(nc)
          yield nc.subscribe(">", "", log.persist)
          yield nc.subscribe("help", "", c.respond)

          reply = yield nc.timed_request("help", "please")
          self.assertEqual("ok:1", reply.data)

          http = tornado.httpclient.AsyncHTTPClient()
          response = yield http.fetch('http://127.0.0.1:%d/varz' % self.server_pool[0].http_port)
          varz = json.loads(response.body)
          self.assertEqual(18, varz['in_bytes'])
          self.assertEqual(28, varz['out_bytes'])
          self.assertEqual(4, varz['in_msgs'])
          self.assertEqual(6, varz['out_msgs'])
          self.assertEqual(2, len(log.records.keys()))
          self.assertEqual("please", log.records['help'][0].data)
          self.assertEqual(28, nc.stats['in_bytes'])
          self.assertEqual(18, nc.stats['out_bytes'])
          self.assertEqual(6, nc.stats['in_msgs'])
          self.assertEqual(4, nc.stats['out_msgs'])

          full_msg = ''
          for msg in log.records['help']:
               full_msg += msg.data
          self.assertEqual('please', full_msg)

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
          yield tornado.gen.sleep(1.0)

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

     @tornado.testing.gen_test
     def test_customize_io_buffers(self):
          class Component():
               def __init__(self):
                    self.nc = Client()
                    self.errors = []
                    self.disconnected_cb_called = 0
                    self.closed_cb_called = 0

               def error_cb(self, e):
                    self.errors.append(e)

               def close_cb(self):
                    self.closed_cb_called += 1

               def disconnected_cb(self):
                    self.disconnected_cb_called += 1

          c = Component()
          options = {
               "io_loop": self.io_loop,
               "max_read_buffer_size": 1024,
               "max_write_buffer_size": 50,
               "read_chunk_size": 10,
               "error_cb": c.error_cb,
               "close_cb": c.close_cb,
               "disconnected_cb": c.disconnected_cb
               }
          with self.assertRaises(tornado.iostream.StreamBufferFullError):
               yield c.nc.connect(**options)
          self.assertFalse(c.nc.is_connected())
          self.assertEqual(1024, c.nc._max_read_buffer_size)
          self.assertEqual(50, c.nc._max_write_buffer_size)
          self.assertEqual(10, c.nc._read_chunk_size)

     @tornado.testing.gen_test
     def test_default_ping_interval(self):

          class Parser():

               def __init__(self, nc, t):
                    self.nc = nc
                    self.t = t

               def read(self, data=''):
                    self.t.assertEqual(1, len(self.nc._pongs))
                    self.nc._process_pong()
                    self.t.assertEqual(0, len(self.nc._pongs))

          nc = Client()
          nc._ps = Parser(nc, self)
          yield nc.connect(io_loop=self.io_loop)
          yield tornado.gen.sleep(1)
          self.assertEqual(0, nc._pings_outstanding)
          self.assertTrue(nc.is_connected())

     @tornado.testing.gen_test
     def test_custom_ping_interval(self):

          class Parser():
               def __init__(self, nc, t):
                    self.nc = nc
                    self.t = t

               def read(self, data=''):
                    self.t.assertEqual(1, len(self.nc._pongs))
                    self.nc._process_pong()
                    self.t.assertEqual(0, len(self.nc._pongs))

          nc = Client()
          nc._ps = Parser(nc, self)
          yield nc.connect(io_loop=self.io_loop, ping_interval=0.01)
          yield tornado.gen.sleep(1)
          self.assertEqual(3, nc._pings_outstanding)
          self.assertFalse(nc.is_connected())
          self.assertTrue(nc.is_reconnecting())

     @tornado.testing.gen_test
     def test_flush_timeout(self):

          class Parser():
               def __init__(self, nc, t):
                    self.nc = nc
                    self.t = t

               def read(self, data=''):
                    self.t.assertEqual(1, self.nc._pings_outstanding)
                    self.t.assertEqual(1, len(self.nc._pongs))
                    self.nc._process_pong()
                    self.t.assertEqual(0, len(self.nc._pongs))

          nc = Client()
          nc._ps = Parser(nc, self)
          yield nc.connect(io_loop=self.io_loop)
          with self.assertRaises(tornado.gen.TimeoutError):
               yield nc.flush(1)
          self.assertEqual(1, len(nc._pongs))
          nc.flush(1)
          self.assertEqual(2, nc._pings_outstanding)
          self.assertEqual(2, len(nc._pongs))

     @tornado.testing.gen_test
     def test_timed_request_timeout(self):

          class Parser():
               def __init__(self, nc, t):
                    self.nc = nc
                    self.t = t

               def read(self, data=''):
                    self.nc._process_pong()

          nc = Client()
          nc._ps = Parser(nc, self)
          yield nc.connect(io_loop=self.io_loop)
          with self.assertRaises(tornado.gen.TimeoutError):
               yield nc.timed_request("hello", "world", 500)

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

          http = tornado.httpclient.HTTPClient()
          while True:
               try:
                    response1 = http.fetch('http://127.0.0.1:8223/varz')
                    response2 = http.fetch('http://127.0.0.1:8224/varz')
                    if response1.code == 200 and response2.code == 200:
                         break
                    continue
               except:
                    time.sleep(0.1)
                    continue
          super(ClientAuthTest, self).setUp()

     def tearDown(self):
          super(ClientAuthTest, self).tearDown()
          for gnatsd in self.server_pool:
               gnatsd.finish()

          for t in self.threads:
               t.join()

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
          yield tornado.gen.sleep(1.0)

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
          # self.assertTrue(component.error_cb_called)
          self.assertTrue(component.disconnected_cb_called)
          self.assertTrue(component.reconnected_cb_called)

     @tornado.testing.gen_test(timeout=15)
     def test_auth_pending_bytes_handling(self):
          nc = Client()

          class Component:

               def __init__(self, nc):
                    self.nc = nc
                    self.errors = []
                    self.written = 0
                    self.max_messages = 2000
                    self.disconnected_at = 0
                    self.pending_bytes_when_closed = 0
                    self.pending_bytes_when_reconnected = 0

               def error_cb(self, err):
                    self.errors.append(err)

               def disconnected_cb(self):
                    self.disconnected_at = self.written
                    self.pending_bytes_when_closed = len(self.nc._pending)

               def reconnected_cb(self):
                    self.pending_bytes_when_reconnected = len(self.nc._pending)

               @tornado.gen.coroutine
               def publisher(self):
                    for i in range(0, self.max_messages):
                         yield self.nc.publish("foo", "{0},".format(i))
                         # yield self.nc.flush()
                         self.written += 1
                         yield tornado.gen.sleep(0.0001)

          c = Component(nc)

          options = {
               "dont_randomize": True,
               "servers": [
                    "nats://foo:bar@127.0.0.1:4223",
                    "nats://hoge:fuga@127.0.0.1:4224"
                    ],
               "io_loop": self.io_loop,
               "reconnected_cb": c.reconnected_cb,
               "disconnected_cb": c.disconnected_cb,
               "error_cb": c.error_cb,
               }
          yield c.nc.connect(**options)
          self.assertEqual(True, nc._server_info["auth_required"])

          log = Log()
          yield c.nc.subscribe("foo",  "", log.persist)
          self.io_loop.spawn_callback(c.publisher)

          yield tornado.gen.sleep(0.5)
          orig_gnatsd = self.server_pool.pop(0)
          orig_gnatsd.finish()

          try:
               a = nc._current_server
               # Wait for reconnect logic kick in...
               yield tornado.gen.sleep(5)
          finally:
               b = nc._current_server
               self.assertNotEqual(a.uri, b.uri)

          # Should have reconnected already
          self.assertTrue(nc.is_connected())
          self.assertFalse(nc.is_reconnecting())

          # Wait a bit until it flushes all...
          yield tornado.gen.sleep(1)

          http = tornado.httpclient.AsyncHTTPClient()
          response = yield http.fetch('http://127.0.0.1:8224/connz')
          result = json.loads(response.body)
          connz = result['connections'][0]
          self.assertEqual(c.max_messages - c.disconnected_at, connz['in_msgs'])
          self.assertTrue(c.pending_bytes_when_reconnected > c.pending_bytes_when_closed)

          # FIXME: Race with subscription not present by the time
          # we flush the buffer again so can't receive messages
          # if sending to our own subscription.
          #
          # full_msg = ''
          # for msg in log.records['foo']:
          #      full_msg += msg.data
          #
          # expected_full_msg = ''
          # for i in range(0, c.max_messages):
          #      expected_full_msg += "%d," % i
          #
          # a = set(full_msg.split(','))
          # b = set(expected_full_msg.split(','))
          # print(sorted(list(b - a)))
          # self.assertEqual(len(expected_full_msg), len(full_msg))

     @tornado.testing.gen_test(timeout=10)
     def test_close_connection(self):
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

          # Done
          yield nc.close()

          orig_gnatsd = self.server_pool.pop(0)
          orig_gnatsd.finish()

          try:
               a = nc._current_server
               # Wait and assert that we don't reconnect.
               yield tornado.gen.sleep(3)
          finally:
               b = nc._current_server
               self.assertEqual(a.uri, b.uri)

          self.assertFalse(nc.is_connected())
          self.assertFalse(nc.is_reconnecting())
          self.assertTrue(nc.is_closed())

          with(self.assertRaises(ErrConnectionClosed)):
               yield nc.publish("hello", "world")

          with(self.assertRaises(ErrConnectionClosed)):
               yield nc.flush()

          with(self.assertRaises(ErrConnectionClosed)):
               yield nc.subscribe("hello", "worker")

          with(self.assertRaises(ErrConnectionClosed)):
               yield nc.publish_request("hello", "inbox", "world")

          with(self.assertRaises(ErrConnectionClosed)):
               yield nc.request("hello", "world")

          with(self.assertRaises(ErrConnectionClosed)):
               yield nc.timed_request("hello", "world")

if __name__ == '__main__':
    runner = unittest.TextTestRunner(stream=sys.stdout)
    unittest.main(verbosity=2, exit=False, testRunner=runner)
