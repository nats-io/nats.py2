# Copyright 2015 Apcera Inc. All rights reserved.

import socket
import json
import time
import tornado.iostream
import tornado.concurrent
import tornado.escape
import tornado.gen
import tornado.ioloop

from random import shuffle
from urlparse import urlparse
from datetime import timedelta, datetime
from nats.io.errors import *
from nats.io.utils  import *
from nats.protocol.parser import *

__version__  = b'0.0.1'
__lang__     = b'python2'
_CRLF_       = b'\r\n'
_SPC_        = b' '
_EMPTY_      = b''

# Ping interval.
DEFAULT_PING_INTERVAL = 120 * 1000 # in ms
MAX_OUTSTANDING_PINGS = 2
DEFAULT_TIMEOUT = 2 * 1000 # in ms

# Reconnection logic.
MAX_RECONNECT_ATTEMPTS = 10
RECONNECT_TIME_WAIT = 2 # in seconds

class Client(object):

  DISCONNECTED = 0
  CONNECTED    = 1
  CLOSED       = 2
  RECONNECTING = 3
  CONNECTING   = 4

  def __init__(self):
    self.options = {}

    # INFO that we get upon connect from the server.
    self._server_info = {}

    # Client connection state and clustering.
    self._socket = None
    self._status = Client.DISCONNECTED
    self._server_pool = []
    self._pending_bytes = ''

    # Storage and monotonically increasing index for subscription callbacks.
    self._subs = {}
    self._ssid = 0

    # Parser with state for processing the wire protocol.
    self._ps = Parser(self)
    self._err = None

    # Ping interval to disconnect from unhealthy servers.
    self._ping_timer = None
    self._pings_outstanding = 0
    self._pongs_received = 0
    self._pongs = []

  @tornado.gen.coroutine
  def connect(self, opts={}):
    """
    Establishes an async connection to a NATS servers, the connection can be
    customized via an optional dictionary.

       # NATS cluster usage
       nc = nats.io.client.Client()
       yield nc.connect({ 'servers': ['nats://192.168.1.10:4222', 'nats://192.168.2.10:4222'] })

       # If using a authentication, user and pass are to be passed on the uri.
       yield nc.connect({ 'servers': ['nats://hello:world@192.168.1.10:4222'] })

    """

    # Default options
    self.options["servers"]  = opts["servers"]  if "servers"  in opts else []
    self.options["verbose"]  = opts["verbose"]  if "verbose"  in opts else False
    self.options["pedantic"] = opts["pedantic"] if "pedantic" in opts else False
    self.options["ping_interval"] = opts["ping_interval"] if "ping_interval" in opts else DEFAULT_PING_INTERVAL
    self.options["max_outstanding_pings"] = opts["max_outstanding_pings"] if "max_outstanding_pings" in opts else MAX_OUTSTANDING_PINGS
    self.options["dont_randomize"] = opts["dont_randomize"] if "dont_randomize" in opts else False
    self.options["allow_reconnect"] = opts["allow_reconnect"] if "allow_reconnect" in opts else True

    if "servers" not in opts or len(self.options["servers"]) < 1:
      srv = Srv(urlparse("nats://127.0.0.1:4222"))
      self._server_pool.append(srv)
    else:
      for srv in self.options["servers"]:
        self._server_pool.append(Srv(urlparse(srv)))

    s = self._next_server()
    if s is None:
      raise ErrNoServers

    try:
      yield self._server_connect(s)
      s.last_attempt = datetime.now()
      self.io.set_close_callback(self._unbind)
    except Exception, e:
      yield self._schedule_primary_and_connect()
    yield self._process_connect_init()

    # First time connecting to NATS so if there were no errors,
    # we can consider to be connected at this point.
    self._status = Client.CONNECTED

  @tornado.gen.coroutine
  def _server_connect(self, s):
    """
    Sets up a TCP connection to the server.
    """
    self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self._socket.setblocking(0)
    self._socket.settimeout(5.0)
    self.io = tornado.iostream.IOStream(self._socket)
    yield self.io.connect((s.uri.hostname, s.uri.port))

  @tornado.gen.coroutine
  def send_ping(self):
    if self._pings_outstanding > self.options["max_outstanding_pings"]:
      self._unbind()
      # TODO: Closing state
      # TODO: Check if we are already reconnecting or should reconnect.
      # self._status = Client.RECONNECTING
      # TODO: Prepare to handle reconnect.
      # self.io.close()
      # TODO: Cancel pings interval.
      # TODO: Handle reconnect.
    else:
      self._pings_outstanding += 1
      self._pongs.append(self._process_pong)
      yield self.send_command("{0}{1}".format(PING_OP, _CRLF_))

  def connect_command(self):
    """
    Generates a JSON string with the params to be used
    when sending CONNECT to the server.

      ->> CONNECT {"verbose": false, "pedantic": false, "lang": "python2" }

    """
    options = {
      "verbose":  self.options["verbose"],
      "pedantic": self.options["pedantic"],
      "lang": __lang__,
      "version": __version__
    }
    if "auth_required" in self._server_info:
      if "user" in self.options:
         options["user"] = self.options["user"]
      if "pass" in self.options:
        options["pass"] = self.options["pass"]
    args = json.dumps(options, sort_keys=True)
    return b'{0} {1}{2}'.format(CONNECT_OP, args, _CRLF_)

  @tornado.gen.coroutine
  def send_command(self, cmd):
    """
    Flushes a command to the server as a bytes payload.
    """
    try:
      yield self.io.write(bytes(cmd))
    except tornado.iostream.StreamClosedError, e:
      # There should be a better mechanism but Write to the pending buffer
      # instead for now which will then be flushed once we reconnect.
      self._pending_bytes += bytes(cmd)
      if not self._status == Client.RECONNECTING:
        yield self._unbind()
        # TODO: Handle cleaning up state from a closed connection
        # so that we can try to connect once again.

  def is_closed(self):
    return self._status == Client.CLOSED

  def is_reconnecting(self):
    return self._status == Client.RECONNECTING

  def is_connected(self):
    return self._status == Client.CONNECTED

  def _publish(self, subject, reply, payload):
    """
    Sends a PUB command to the server.  We avoid using tornado for these
    writes in order to increase performance.
    """
    size = len(payload)
    pub_cmd = "{0} {1} {2} {3} {4}{5}{6}".format(PUB_OP, subject, reply, size, _CRLF_, payload, _CRLF_)
    self._socket.sendall(pub_cmd)

  def publish(self, subject, payload):
    """
    Publishes a message to the server on the specified subject.

      ->> PUB hello 5
      ->> MSG_PAYLOAD: world
      <<- MSG hello 2 5

    """
    self._publish(subject, _EMPTY_, payload)

  @tornado.gen.coroutine
  def publish_request(self, subject, reply, payload):
    """
    Publishes a message tagging it with a reply subscription
    which can be used by those receiving the message to respond:

       ->> PUB hello   _INBOX.2007314fe0fcb2cdc2a2914c1 5
       ->> MSG_PAYLOAD: world
       <<- MSG hello 2 _INBOX.2007314fe0fcb2cdc2a2914c1 5

    """
    self._publish(subject, reply, payload)

  @tornado.gen.coroutine
  def request(self, subject, payload, callback=None):
    """
    Implements the request/response via pub/sub and an ephemeral subscription
    which will be published with a limited interest of 1 reply.

       ->> SUB _INBOX.2007314fe0fcb2cdc2a2914c1 90
       ->> UNSUB 90 1
       ->> PUB hello _INBOX.2007314fe0fcb2cdc2a2914c1 5
       ->> MSG_PAYLOAD: world
       <<- MSG hello 2 _INBOX.2007314fe0fcb2cdc2a2914c1 5

    """
    inbox = new_inbox()
    sid = yield self.subscribe(inbox, _EMPTY_, callback)
    yield self.auto_unsubscribe(sid, 1)
    yield self.publish_request(subject, inbox, payload)
    raise tornado.gen.Return(sid)

  @tornado.gen.coroutine
  def timed_request(self, subject, payload, timeout=5):
    """
    Implements the request/response expecting a single response
    on an inbox with a timeout by using futures instead of callbacks.

       ->> SUB _INBOX.2007314fe0fcb2cdc2a2914c1 90
       ->> UNSUB 90 1
       ->> PUB hello _INBOX.2007314fe0fcb2cdc2a2914c1 5
       ->> MSG_PAYLOAD: world
       <<- MSG hello 2 _INBOX.2007314fe0fcb2cdc2a2914c1 5

    """
    inbox = new_inbox()
    future = tornado.concurrent.Future()
    sid = yield self.subscribe(inbox, _EMPTY_, None, future)
    yield self.auto_unsubscribe(sid, 1)
    yield self.publish_request(subject, inbox, payload)
    msg = yield tornado.gen.with_timeout(timedelta(seconds=timeout), future)
    raise tornado.gen.Return(msg)

  @tornado.gen.coroutine
  def subscribe(self, subject="", queue="", callback=None, future=None):
    """
    Sends a SUB command to the server. Takes a queue parameter which can be used
    in case of distributed queues or left empty if it is not the case, and a callback
    that will be dispatched message for processing them.
    """
    self._ssid += 1
    sid = self._ssid
    sub = Subscription(subject=subject, queue=queue, callback=callback, future=future)
    self._subs[sid] = sub
    yield self._subscribe(sub, sid)
    raise tornado.gen.Return(sid)

  @tornado.gen.coroutine
  def _subscribe(self, sub, ssid):
    """
    Generates a SUB command given a Subscription and the subject sequence id.
    """
    sub_cmd = "{0} {1} {2} {3}{4}".format(SUB_OP, sub.subject, sub.queue, ssid, _CRLF_)
    self.send_command(sub_cmd)

  @tornado.gen.coroutine
  def auto_unsubscribe(self, sid, limit):
    """
    Sends an UNSUB command to the server.  Unsubscribe is one of the basic building
    blocks in order to be able to define request/response semantics via pub/sub
    by announcing the server limited interest a priori.
    """
    unsub_cmd = "{0} {1} {2}{3}".format(UNSUB_OP, sid, limit, _CRLF_)
    self.send_command(unsub_cmd)

  def _process_ping(self):
    """
    The server will be periodically sending a PING, and if the the client
    does not reply a PONG back a number of times, it will close the connection
    sending an `-ERR 'Stale Connection'` error.
    """
    self.send_command(PONG)

  def _process_pong(self):
    """
    The client will be send a PING soon after CONNECT and then periodically
    to the the server as a failure detector to close connections to unhealthy servers.
    For each PING the client sends, we will add a respective PONG callback which
    will be dispatched by the parser upon receving it.
    """
    self._pongs_received += 1
    self._pings_outstanding -= 1

  def _process_msg(self, msg):
    """
    Dispatches the received message to the stored subscription.
    It first tries to detect whether the message should be dispatched
    to a passed callback.  In case there was not a callback,
    then it tries to set the message into a future.
    """
    sub = self._subs[msg.sid]

    if sub.callback is not None:
      sub.callback(msg)
    elif sub.future is not None:
      sub.future.set_result(msg)


  @tornado.gen.coroutine
  def _process_connect_init(self):
    """
    Handles the initial part of the NATS protocol, moving from
    the CONNECTING to CONNECTED states when establishing a connection
    with the server.
    """
    # TODO: Add readline timeout here upon connecting.
    self._status = Client.CONNECTING

    # INFO {...}
    # TODO: Check for errors here.
    line = yield self.io.read_until(_CRLF_)
    _, args = line.split(INFO_OP + _SPC_, 1)
    self._server_info = tornado.escape.json_decode((args))

    # CONNECT {...}
    yield self.send_command(self.connect_command())

    # Wait for ack or not depending on verbose setting.
    if self.options["verbose"]:
      result = yield self.io.read_until(_CRLF_)
      if result != OK:
        raise ErrProtocol("'{0}' expected".format(OK_OP))

    # Prepare the ping pong interval callback.
    self._ping_timer = tornado.ioloop.PeriodicCallback(self.send_ping, DEFAULT_PING_INTERVAL)
    self._ping_timer.start()

    # Parser reads directly from the same IO as the client.
    self._ps.read()

    # Send initial PING.  Reply from server should be handled
    # by the parsing loop already at this point.
    yield self.send_ping()
    # TODO: Flush timeout.

  def _next_server(self):
    """
    Chooses next available server to connect.
    """
    if self.options["dont_randomize"]:
      server = self.options['servers'].pop(0)
      self._server_pool.insert(-1, server)
    else:
      shuffle(self._server_pool)

    s = None
    for server in self._server_pool:
      # TODO: Reset max reconnects with a server after some time?
      if server.reconnects > MAX_RECONNECT_ATTEMPTS:
        continue
      s = server

    return s

  @tornado.gen.coroutine
  def _unbind(self):
    """
    Unbind handles the disconnection from the server then
    attempts to reconnect if `allow_reconnect' is enabled.
    """
    if not self.options["allow_reconnect"]:
      self._process_disconnect()
      return
    if self.is_connected():
      self._status = Client.RECONNECTING

      if self._ping_timer.is_running():
        self._ping_timer.stop()

      while True:
        try:
          self.io.close()
          yield self._schedule_primary_and_connect()
          break
        except ErrNoServers:
          self._process_disconnect()

      yield self._process_connect_init()

      # Replay all the subscriptions in case there were some.
      for ssid, sub in self._subs.items():
        yield self._subscribe(sub, ssid)

      # TODO: Flush all the pending bytes upon reconnect.
      self._status = Client.CONNECTED

  @tornado.gen.coroutine
  def _schedule_primary_and_connect(self):
    """
    Attempts to connect to an available server.
    """
    while True:
      s = self._next_server()
      if s is None:
        raise ErrNoServers
      s.reconnects += 1
      s.last_attempt = datetime.now()

      # For the reconnection logic, we need to consider
      # sleeping for a bit before trying to reconnect too soon to a
      # server which has failed previously.
      yield tornado.gen.Task(tornado.ioloop.IOLoop.instance().add_timeout, time.time() + RECONNECT_TIME_WAIT)
      try:
        yield self._server_connect(s)

        # Reset number of reconnects upon successful connection
        s.reconnects = 0
        self.io.set_close_callback(self._unbind)
        return
      except Exception, e:
        # Continue trying to connect until there is an available server
        # or bail in case there are no more available servers.
        self._status = Client.RECONNECTING
        continue

  def _process_disconnect(self):
    """
    Does cleanup of the client state and tears down the connection.
    """
    # TODO: Call disconnected callback
    # TODO: Remove ping interval timer
    # TODO: Close io
    # TODO: Set to close

  def _process_err(self, err=None):
    """
    Stores the last received error from the server.
    """
    self._err = err

  def last_error(self):
    """
    Returns the last processed error from the client.
    """
    return self._err

class Subscription(object):

  def __init__(self, **kwargs):
    self.subject  = kwargs["subject"]
    self.queue    = kwargs["queue"]
    self.callback = kwargs["callback"]
    self.future   = kwargs["future"]
    self.received = 0

class Srv(object):
  """
  Srv is a helper data structure to hold state on the
  """

  def __init__(self, uri):
    self.uri = uri
    self.reconnects = 0
    self.last_attempt = None
