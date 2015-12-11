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

from datetime import timedelta
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
                  debug=True
               ):
          self.port = port
          self.user = user
          self.password = password
          self.timeout = timeout
          self.http_port = http_port
          self.proc = None
          self.debug = debug

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

          self.proc = subprocess.Popen(cmd)

     def finish(self):
          print("[NOTICE] Server running at %d will stop." % self.port)
          if self.proc is None:
               print("[ WARN ] Failed at terminating server running at %d" % self.port)
          else:
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
          self.threads = []
          self.server_pool = []
          
          server = Gnatsd(port=4222)
          self.server_pool.append(server)

          for gnatsd in self.server_pool:
               t = threading.Thread(target=gnatsd.start)
               self.threads.append(t)
               t.start()

          time.sleep(0.5)
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
               yield client.nc.connect({
                    "servers": ["nats://127.0.0.1:4223"],
                    "error_cb": client.err_cb,
                    "allow_reconnect": False
                    })

          self.assertEqual(socket.error, type(client.nc.last_error()))
          self.assertEqual('[Errno 61] Connection refused', client.err)

     @tornado.testing.gen_test
     def test_subscribe(self):
          nc = Client()
          yield nc.connect()
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
          yield nc.connect()
          self.assertEqual(Client.CONNECTED, nc._status)
          info_keys = nc._server_info.keys()
          self.assertTrue(len(info_keys) > 0)

          # FIXME: Messages are not being passed in here
          # properly in the test, though works in examples,
          # might be a symptom something.
          class Transmission():
               def __init__(self):
                    self.called = False

               def persist(self, msg):
                    self.called = True

          tr = Transmission()
          yield nc.subscribe(">", "", callback=tr.persist)
          yield nc.publish("one", "hello")
          yield nc.publish("two", "world")

          http = tornado.httpclient.AsyncHTTPClient()
          response = yield http.fetch('http://127.0.0.1:%d/varz' % self.server_pool[0].http_port)
          varz = json.loads(response.body)
          self.assertEqual(10, varz['in_bytes'])
          self.assertEqual(2, varz['in_msgs'])
          self.assertEqual(True, tr.called)
          # self.assertEqual("hello", tr.subs['one'])
          # self.assertEqual("world", tr.subs['world'])

     @tornado.testing.gen_test
     def test_publish_request(self):
          nc = Client()
          yield nc.connect()
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
          self.assertEqual(2, varz['in_msgs'])

class ClientAuthTest(tornado.testing.AsyncTestCase):

     def setUp(self):
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

          time.sleep(0.1)
          super(ClientAuthTest, self).setUp()

     def tearDown(self):
          for gnatsd in self.server_pool:
               gnatsd.finish()

          for t in self.threads:
               t.join()

          super(ClientAuthTest, self).tearDown()

     @tornado.testing.gen_test(timeout=120)
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
          yield tornado.gen.sleep(0.5)

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
               
          # TODO: Test reconnect with another server.
          try:
               a = nc._current_server
               yield tornado.gen.sleep(5)
          finally:
               b = nc._current_server
               self.assertNotEqual(a.uri, b.uri)

if __name__ == '__main__':
    runner = unittest.TextTestRunner(stream=sys.stdout)
    unittest.main(verbosity=1, exit=False, testRunner=runner)
