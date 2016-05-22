# Copyright 2015-2016 Apcera Inc. All rights reserved.

import socket
import json
import time
import io
import tornado.iostream
import tornado.concurrent
import tornado.escape
import tornado.gen
import tornado.ioloop
import tornado.queues

from random import shuffle
from urlparse import urlparse
from datetime import timedelta
from nats import __lang__, __version__
from nats.io.errors import *
from nats.io.utils  import *
from nats.protocol.parser import *

CONNECT_PROTO = b'{0} {1}{2}'
PUB_PROTO     = b'{0} {1} {2} {3} {4}{5}{6}'
SUB_PROTO     = b'{0} {1} {2} {3}{4}'
UNSUB_PROTO   = b'{0} {1} {2}{3}'

INFO_OP       = b'INFO'
CONNECT_OP    = b'CONNECT'
PUB_OP        = b'PUB'
MSG_OP        = b'MSG'
SUB_OP        = b'SUB'
UNSUB_OP      = b'UNSUB'
PING_OP       = b'PING'
PONG_OP       = b'PONG'
OK_OP         = b'+OK'
ERR_OP        = b'-ERR'
_CRLF_        = b'\r\n'
_SPC_         = b' '
_EMPTY_       = b''

PING_PROTO    = b'{0}{1}'.format(PING_OP, _CRLF_)
PONG_PROTO    = b'{0}{1}'.format(PONG_OP, _CRLF_)

# Defaults
DEFAULT_PING_INTERVAL     = 120 # seconds
MAX_OUTSTANDING_PINGS     = 2
MAX_RECONNECT_ATTEMPTS    = 60
RECONNECT_TIME_WAIT       = 2   # seconds
DEFAULT_CONNECT_TIMEOUT   = 2   # seconds

DEFAULT_READ_BUFFER_SIZE  = 1024 * 1024 * 100
DEFAULT_WRITE_BUFFER_SIZE = None
DEFAULT_READ_CHUNK_SIZE   = 32768 * 2
DEFAULT_PENDING_SIZE      = 1024 * 1024
DEFAULT_MAX_PAYLOAD_SIZE  = 1048576

class Client(object):
  """
  Tornado based client for NATS.
  """

  DISCONNECTED = 0
  CONNECTED    = 1
  CLOSED       = 2
  RECONNECTING = 3
  CONNECTING   = 4

  def __repr__(self):
    return "<nats client v{}>".format(__version__)

  def __init__(self):
    self.options = {}

    # INFO that we get upon connect from the server.
    self._server_info = {}
    self._max_payload_size = DEFAULT_MAX_PAYLOAD_SIZE

    # Client connection state and clustering.
    self.io = None
    self._socket = None
    self._status = Client.DISCONNECTED
    self._server_pool = []
    self._current_server = None
    self._pending = []
    self._pending_size = 0
    self._loop = None
    self.stats = {
      'in_msgs':    0,
      'out_msgs':   0,
      'in_bytes':   0,
      'out_bytes':  0,
      'reconnects': 0,
      'errors_received': 0
    }

    # Storage and monotonically increasing index for subscription callbacks.
    self._subs = {}
    self._ssid = 0

    # Parser with state for processing the wire protocol.
    self._ps = Parser(self)
    self._err = None
    self._flush_queue = None
    self._flusher_task = None

    # Ping interval to disconnect from unhealthy servers.
    self._ping_timer = None
    self._pings_outstanding = 0
    self._pongs_received = 0
    self._pongs = []

    self._error_cb = None
    self._close_cb = None
    self._disconnected_cb = None
    self._reconnected_cb = None

  @tornado.gen.coroutine
  def connect(self,
              servers=[],
              verbose=False,
              pedantic=False,
              name=None,
              ping_interval=DEFAULT_PING_INTERVAL,
              max_outstanding_pings=MAX_OUTSTANDING_PINGS,
              dont_randomize=False,
              allow_reconnect=True,
              close_cb=None,
              error_cb=None,
              disconnected_cb=None,
              reconnected_cb=None,
              io_loop=tornado.ioloop.IOLoop.instance(),
              max_read_buffer_size=DEFAULT_READ_BUFFER_SIZE,
              max_write_buffer_size=DEFAULT_WRITE_BUFFER_SIZE,
              read_chunk_size=DEFAULT_READ_CHUNK_SIZE,
              tcp_nodelay=False,
              connect_timeout=DEFAULT_CONNECT_TIMEOUT,
              ):
    """
    Establishes a connection to a NATS server.

    Examples:

      # Configure pool of NATS servers.
      nc = nats.io.client.Client()
      yield nc.connect({ 'servers': ['nats://192.168.1.10:4222', 'nats://192.168.2.10:4222'] })

      # User and pass are to be passed on the uri to authenticate.
      yield nc.connect({ 'servers': ['nats://hello:world@192.168.1.10:4222'] })

    """
    self.options["servers"]  = servers
    self.options["verbose"]  = verbose
    self.options["pedantic"] = pedantic
    self.options["name"] = name
    self.options["max_outstanding_pings"] = max_outstanding_pings
    self.options["dont_randomize"] = dont_randomize
    self.options["allow_reconnect"] = allow_reconnect
    self.options["tcp_nodelay"] = tcp_nodelay

    # In seconds
    self.options["connect_timeout"] = connect_timeout
    self.options["ping_interval"] = ping_interval

    self._close_cb = close_cb
    self._error_cb = error_cb
    self._disconnected_cb = disconnected_cb
    self._reconnected_cb = reconnected_cb
    self._loop = io_loop
    self._max_read_buffer_size = max_read_buffer_size
    self._max_write_buffer_size = max_write_buffer_size
    self._read_chunk_size = read_chunk_size

    if len(self.options["servers"]) < 1:
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
      self._current_server = s
      self.io.set_close_callback(self._unbind)
    except socket.error as e:
      self._err = e
      if self._error_cb is not None:
        self._error_cb(ErrServerConnect(e))
      if not self.options["allow_reconnect"]:
        raise ErrNoServers
      yield self._schedule_primary_and_connect()

    self._status = Client.CONNECTING
    yield self._process_connect_init()

    # Flush pending data before continuing in connected status.
    # FIXME: Could use future here and wait for an error result
    # to bail earlier in case there are errors in the connection.
    yield self._flush_pending()

    # First time connecting to NATS so if there were no errors,
    # we can consider to be connected at this point.
    self._status = Client.CONNECTED

    # Prepare the ping pong interval.
    self._ping_timer = tornado.ioloop.PeriodicCallback(
      self._send_ping,
      self.options["ping_interval"] * 1000
      )
    self._ping_timer.start()

  @tornado.gen.coroutine
  def _server_connect(self, s):
    """
    Sets up a TCP connection to the server.
    """
    self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self._socket.setblocking(0)
    self._socket.settimeout(1.0)

    if self.options["tcp_nodelay"]:
      self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    self.io = tornado.iostream.IOStream(
      self._socket,
      max_buffer_size=self._max_read_buffer_size,
      max_write_buffer_size=self._max_write_buffer_size,
      read_chunk_size=self._read_chunk_size)

    future = self.io.connect((s.uri.hostname, s.uri.port))
    yield tornado.gen.with_timeout(
      timedelta(seconds=self.options["connect_timeout"]),
      future)

  @tornado.gen.coroutine
  def _send_ping(self, future=None):
    if self._pings_outstanding > self.options["max_outstanding_pings"]:
      yield self._unbind()
    else:
      yield self.io.write(PING_PROTO)
      yield self._flush_pending()
      if future is None:
        future = tornado.concurrent.Future()
      self._pings_outstanding += 1
      self._pongs.append(future)

  def connect_command(self):
    '''
    Generates a JSON string with the params to be used
    when sending CONNECT to the server.

      ->> CONNECT {"verbose": false, "pedantic": false, "lang": "python2" }

    '''
    options = {
      "verbose":  self.options["verbose"],
      "pedantic": self.options["pedantic"],
      "lang":     __lang__,
      "version":  __version__
    }
    if "auth_required" in self._server_info:
      if self._server_info["auth_required"] == True:
        options["user"] = self._current_server.uri.username
        options["pass"] = self._current_server.uri.password
    if self.options["name"] is not None:
      options["name"] = self.options["name"]

    args = json.dumps(options, sort_keys=True)
    return CONNECT_PROTO.format(CONNECT_OP, args, _CRLF_)

  @tornado.gen.coroutine
  def send_command(self, cmd, priority=False):
    """
    Flushes a command to the server as a bytes payload.
    """
    if priority:
      self._pending.insert(0, cmd)
    else:
      self._pending.append(cmd)
    self._pending_size += len(cmd)

    if len(self._pending) > DEFAULT_PENDING_SIZE:
      yield self._flush_pending()

  @tornado.gen.coroutine
  def _publish(self, subject, reply, payload, payload_size):
    payload_size_bytes = ("%d" % payload_size).encode()
    pub_cmd = b''.join([PUB_OP, _SPC_, subject.encode(), _SPC_, reply, _SPC_, payload_size_bytes, _CRLF_, payload, _CRLF_])
    self.stats['out_msgs']  += 1
    self.stats['out_bytes'] += payload_size
    yield self.send_command(pub_cmd)

  @tornado.gen.coroutine
  def _flush_pending(self):
    if not self.is_connected:
      return
    yield self._flush_queue.put(None)

  @tornado.gen.coroutine
  def publish(self, subject, payload):
    """
    Sends a PUB command to the server on the specified subject.

      ->> PUB hello 5
      ->> MSG_PAYLOAD: world
      <<- MSG hello 2 5

    """
    payload_size = len(payload)
    if payload_size > self._max_payload_size:
      raise ErrMaxPayload
    if self.is_closed:
      raise ErrConnectionClosed
    yield self._publish(subject, _EMPTY_, payload, payload_size)
    if self._flush_queue.empty():
      yield self._flush_pending()

  @tornado.gen.coroutine
  def publish_request(self, subject, reply, payload):
    """
    Publishes a message tagging it with a reply subscription
    which can be used by those receiving the message to respond:

      ->> PUB hello   _INBOX.2007314fe0fcb2cdc2a2914c1 5
      ->> MSG_PAYLOAD: world
      <<- MSG hello 2 _INBOX.2007314fe0fcb2cdc2a2914c1 5

    """
    payload_size = len(payload)
    if payload_size > self._max_payload_size:
      raise ErrMaxPayload
    if self.is_closed:
      raise ErrConnectionClosed
    yield self._publish(subject, reply, payload, payload_size)

  @tornado.gen.coroutine
  def flush(self, timeout=60):
    """
    Flush will perform a round trip to the server and return True
    when it receives the internal reply or raise a Timeout error.
    """
    if self.is_closed:
      raise ErrConnectionClosed
    yield self._flush_timeout(timeout)

  @tornado.gen.coroutine
  def _flush_timeout(self, timeout):
    """
    Takes a timeout and sets up a future which will return True
    once the server responds back otherwise raise a TimeoutError.
    """
    future = tornado.concurrent.Future()
    yield self._send_ping(future)
    result = yield tornado.gen.with_timeout(timedelta(seconds=timeout), future)
    raise tornado.gen.Return(result)

  @tornado.gen.coroutine
  def request(self, subject, payload, expected=1, cb=None):
    """
    Implements the request/response pattern via pub/sub
    using an ephemeral subscription which will be published
    with customizable limited interest.

      ->> SUB _INBOX.2007314fe0fcb2cdc2a2914c1 90
      ->> UNSUB 90 1
      ->> PUB hello _INBOX.2007314fe0fcb2cdc2a2914c1 5
      ->> MSG_PAYLOAD: world
      <<- MSG hello 2 _INBOX.2007314fe0fcb2cdc2a2914c1 5

    """
    inbox = new_inbox()
    sid = yield self.subscribe(inbox, _EMPTY_, cb)
    yield self.auto_unsubscribe(sid, expected)
    yield self.publish_request(subject, inbox, payload)
    raise tornado.gen.Return(sid)

  @tornado.gen.coroutine
  def timed_request(self, subject, payload, timeout=0.5):
    """
    Implements the request/response pattern via pub/sub
    using an ephemeral subscription which will be published
    with a limited interest of 1 reply returning the response
    or raising a Timeout error.

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
  def subscribe(self, subject="", queue="", cb=None, future=None, max_msgs=0, is_async=False):
    """
    Sends a SUB command to the server. Takes a queue parameter which can be used
    in case of distributed queues or left empty if it is not the case, and a callback
    that will be dispatched message for processing them.
    """
    if self.is_closed:
      raise ErrConnectionClosed

    self._ssid += 1
    sid = self._ssid
    sub = Subscription(
      subject=subject,
      queue=queue,
      cb=cb,
      future=future,
      max_msgs=max_msgs,
      is_async=is_async,
      )
    self._subs[sid] = sub
    yield self._subscribe(sub, sid)
    raise tornado.gen.Return(sid)

  @tornado.gen.coroutine
  def subscribe_async(self, subject, **kwargs):
    """
    Schedules callback from subscription to be processed asynchronously
    in the next iteration of the loop.
    """
    kwargs["is_async"] = True
    sid = yield self.subscribe(subject, **kwargs)
    raise tornado.gen.Return(sid)

  @tornado.gen.coroutine
  def unsubscribe(self, ssid, max_msgs=0):
    """
    Takes a subscription sequence id and removes the subscription
    from the client, optionally after receiving more than max_msgs,
    and unsubscribes immediatedly.
    """
    if self.is_closed:
      raise ErrConnectionClosed

    sub = None
    try:
      sub = self._subs[ssid]
    except KeyError:
      # Already unsubscribed.
      return

    # In case subscription has already received enough messages
    # then announce to the server that we are unsubscribing and
    # remove the callback locally too.
    if max_msgs == 0 or sub.received >= max_msgs:
      self._subs.pop(ssid, None)

    # We will send these for all subs when we reconnect anyway,
    # so that we can suppress here.
    if not self.is_reconnecting:
      yield self.auto_unsubscribe(ssid, max_msgs)

  @tornado.gen.coroutine
  def _subscribe(self, sub, ssid):
    """
    Generates a SUB command given a Subscription and the subject sequence id.
    """
    sub_cmd = b''.join([SUB_OP, _SPC_, sub.subject.encode(), _SPC_, sub.queue.encode(), _SPC_, ("%d" % ssid).encode(), _CRLF_])
    yield self.send_command(sub_cmd)
    yield self._flush_pending()

  @tornado.gen.coroutine
  def auto_unsubscribe(self, sid, limit=1):
    """
    Sends an UNSUB command to the server.  Unsubscribe is one of the basic building
    blocks in order to be able to define request/response semantics via pub/sub
    by announcing the server limited interest a priori.
    """
    b_limit = b''
    if limit > 0:
      b_limit = ("%d" % limit).encode()
    b_sid = ("%d" % sid).encode()
    unsub_cmd = b''.join([UNSUB_OP, _SPC_, b_sid, _SPC_, b_limit, _CRLF_])
    yield self.send_command(unsub_cmd)
    yield self._flush_pending()

  @tornado.gen.coroutine
  def _process_ping(self):
    """
    The server will be periodically sending a PING, and if the the client
    does not reply a PONG back a number of times, it will close the connection
    sending an `-ERR 'Stale Connection'` error.
    """
    yield self.send_command(PONG_PROTO)

  @tornado.gen.coroutine
  def _process_pong(self):
    """
    The client will send a PING soon after CONNECT and then periodically
    to the server as a failure detector to close connections to unhealthy servers.
    For each PING the client sends, we will add a respective PONG future.
    """
    if len(self._pongs) > 0:
      future = self._pongs.pop(0)
      future.set_result(True)
      self._pongs_received += 1
      self._pings_outstanding -= 1

  @tornado.gen.coroutine
  def _process_msg(self, sid, subject, reply, data):
    """
    Dispatches the received message to the stored subscription.
    It first tries to detect whether the message should be
    dispatched to a passed callback.  In case there was not
    a callback, then it tries to set the message into a future.
    """
    self.stats['in_msgs']  += 1
    self.stats['in_bytes'] += len(data)

    msg = Msg(subject=subject.decode(), reply=reply.decode(), data=data)
    sub = self._subs[sid]
    sub.received += 1
    if sub.cb is not None:
      if sub.is_async:
        self._loop.spawn_callback(sub.cb, msg)
      else:
        # Call it and take the possible future in the loop.
        maybe_future = sub.cb(msg)
        if maybe_future is not None and type(maybe_future) is tornado.concurrent.Future:
          yield maybe_future
    elif sub.future is not None:
      sub.future.set_result(msg)

  @tornado.gen.coroutine
  def _process_connect_init(self):
    """
    Handles the initial part of the NATS protocol, moving from
    the (RE)CONNECTING to CONNECTED states when establishing
    a connection with the server.
    """
    # INFO {...}
    line = yield self.io.read_until(_CRLF_, max_bytes=MAX_CONTROL_LINE_SIZE)
    _, args = line.split(INFO_OP + _SPC_, 1)
    self._server_info = tornado.escape.json_decode((args))
    self._max_payload_size = self._server_info["max_payload"]

    # CONNECT {...}
    cmd = self.connect_command()
    yield self.io.write(cmd)

    # Refresh state of the parser upon reconnect.
    if self.is_reconnecting:
      self._ps.reset()

    # Send a PING expecting a PONG to make a roundtrip to the server
    # and assert that sent messages sent this far have been processed.
    yield self.io.write(PING_PROTO)

    # FIXME: Add readline timeout for these.
    next_op = yield self.io.read_until(_CRLF_, max_bytes=MAX_CONTROL_LINE_SIZE)
    if self.options["verbose"] and OK_OP in next_op:
      next_op = yield self.io.read_until(_CRLF_, max_bytes=MAX_CONTROL_LINE_SIZE)
    if ERR_OP in next_op:
      err_line = next_op.decode()
      _, err_msg = err_line.split(_SPC_, 1)
      # FIXME: Maybe handling could be more special here,
      # checking for ErrAuthorization for example.
      # yield from self._process_err(err_msg)
      raise NatsError("nats: "+err_msg.rstrip('\r\n'))

    if PONG_PROTO in next_op:
      self._status = Client.CONNECTED

    # Parser reads directly from the same IO as the client.
    self._loop.spawn_callback(self._read_loop)

    # Queue and flusher for coalescing writes to the server.
    self._flush_queue = tornado.queues.Queue(maxsize=1024)
    self._loop.spawn_callback(self._flusher_loop)

  def _next_server(self):
    """
    Chooses next available server to connect.
    """
    if self.options["dont_randomize"]:
      server = self._server_pool.pop(0)
      self._server_pool.append(server)
    else:
      shuffle(self._server_pool)

    s = None
    for server in self._server_pool:
      if server.reconnects > MAX_RECONNECT_ATTEMPTS:
        continue
      s = server
    return s

  @property
  def is_closed(self):
    return self._status == Client.CLOSED

  @property
  def is_reconnecting(self):
    return self._status == Client.RECONNECTING

  @property
  def is_connected(self):
    return self._status == Client.CONNECTED

  @property
  def is_connecting(self):
    return self._status == Client.CONNECTING

  @tornado.gen.coroutine
  def _unbind(self):
    """
    Unbind handles the disconnection from the server then
    attempts to reconnect if `allow_reconnect' is enabled.
    """
    if self.is_connecting or self.is_closed or self.is_reconnecting:
      return

    if self._disconnected_cb is not None:
      self._disconnected_cb()

    if not self.options["allow_reconnect"]:
      self._process_disconnect()
      return
    if self.is_connected:
      self._status = Client.RECONNECTING

      if self._ping_timer.is_running:
        self._ping_timer.stop()

      while True:
        try:
          yield self._schedule_primary_and_connect()
        except ErrNoServers:
          self._process_disconnect()
          break

        try:
          yield self._process_connect_init()
          break
        except Exception as e:
          self._err = e
          yield self._close(Client.DISCONNECTED)

      # Replay all the subscriptions in case there were some.
      for ssid, sub in self._subs.items():
        sub_cmd = SUB_PROTO.format(SUB_OP, sub.subject, sub.queue, ssid, _CRLF_)
        yield self.io.write(sub_cmd)

      # Restart the ping pong interval callback.
      self._ping_timer = tornado.ioloop.PeriodicCallback(
        self._send_ping,
        self.options["ping_interval"] * 1000)
      self._ping_timer.start()
      self._err = None
      self._pings_outstanding = 0
      self._pongs = []

      # Flush any pending bytes from reconnect
      if len(self._pending) > 0:
        yield self._flush_pending()

      # Reconnected at this point
      self._status = Client.CONNECTED

      # Roundtrip to the server to ensure connection
      # is healthy at this point.
      yield self.flush()

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
      self.stats['reconnects'] += 1

      # For the reconnection logic, we need to consider
      # sleeping for a bit before trying to reconnect
      # too soon to a server which has failed previously.
      yield tornado.gen.Task(
        self._loop.add_timeout,
        timedelta(seconds=RECONNECT_TIME_WAIT))
      try:
        yield self._server_connect(s)
        self._current_server = s
        # Reset number of reconnects upon successful connection.
        s.reconnects = 0
        self.io.set_close_callback(self._unbind)

        if self.is_reconnecting and self._reconnected_cb is not None:
          self._reconnected_cb()

        return
      except socket.error as e:
        if self._error_cb is not None:
          self._error_cb(ErrServerConnect(e))

        # Continue trying to connect until there is an available server
        # or bail in case there are no more available servers.
        self._status = Client.RECONNECTING
        continue

  @tornado.gen.coroutine
  def _process_disconnect(self):
    """
    Does cleanup of the client state and tears down the connection.
    """
    self._status = Client.DISCONNECTED
    yield self.close()

  @tornado.gen.coroutine
  def close(self):
    """
    Wraps up connection to the NATS cluster and stops reconnecting.
    """
    yield self._close(Client.CLOSED)

  @tornado.gen.coroutine
  def _close(self, status, do_callbacks=True):
    """
    Takes the status on which it should leave the connection
    and an optional boolean parameter to dispatch the disconnected
    and close callbacks if there are any.
    """
    if self.is_closed:
      # If connection already closed, then just set status explicitly.
      self._status = status
      return

    self._status = Client.CLOSED
    if self._ping_timer.is_running():
      self._ping_timer.stop()

    if not self.io.closed():
      self.io.close()

    if do_callbacks:
      if self._disconnected_cb is not None:
        self._disconnected_cb()
      if self._close_cb is not None:
        self._close_cb()

  @tornado.gen.coroutine
  def _process_err(self, err=None):
    """
    Stores the last received error from the server and dispatches the error callback.
    """
    self.stats['errors_received'] += 1

    if err == "'Authorization Violation'":
      self._err = ErrAuthorization
    elif err == "'Slow Consumer'":
      self._err = ErrSlowConsumer
    elif err == "'Stale Connection'":
      self._err = ErrStaleConnection
    else:
      self._err = Exception(err)

    if self._error_cb is not None:
      self._error_cb(err)

  def last_error(self):
    return self._err

  @tornado.gen.coroutine
  def _read_loop(self, data=''):
    """
    Read loop for gathering bytes from the server in a buffer
    of maximum MAX_CONTROL_LINE_SIZE, then received bytes are streamed
    to the parsing callback for processing.
    """
    if not self.io.closed():
      self.io.read_bytes(MAX_CONTROL_LINE_SIZE, callback=self._read_loop, streaming_callback=self._ps.parse, partial=True)

  @tornado.gen.coroutine
  def _flusher_loop(self):
    """
    Coroutine which continuously tries to consume pending commands
    and then flushes them to the socket.
    """
    while True:
      if self.io.closed():
        break
      try:
        yield self._flush_queue.get()
        yield self.io.write(b''.join(self._pending))
        self._pending = []
        self._pending_size = 0
      except tornado.iostream.StreamBufferFullError:
        # Acumulate as pending data size and flush when possible.
        pass
      except tornado.iostream.StreamClosedError as e:
        self._err = e
        if self._error_cb is not None and not self.is_reconnecting:
          self._error_cb(e)
        yield self._unbind()

class Subscription():

  def __init__(self,
               subject='',
               queue='',
               cb=None,
               is_async=False,
               future=None,
               max_msgs=0,
               ):
    self.subject   = subject
    self.queue     = queue
    self.cb        = cb
    self.future    = future
    self.max_msgs  = max_msgs
    self.is_async  = is_async
    self.received = 0

class Msg(object):

  def __init__(self,
               subject='',
               reply='',
               data=b'',
               sid=0,
               ):
    self.subject = subject
    self.reply   = reply
    self.data    = data
    self.sid     = sid

class Srv(object):
  """
  Srv is a helper data structure to hold state of a server.
  """
  def __init__(self, uri):
    self.uri = uri
    self.reconnects = 0
    self.last_attempt = None
