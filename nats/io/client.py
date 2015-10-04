import socket
import json
import tornado.iostream
import tornado.concurrent
import tornado.gen

from urlparse import urlparse
from datetime import timedelta
from nats.io.errors import *
from nats.io.utils  import *
from nats.protocol.parser import *

__version__   = b'0.0.1'
__lang__      = b'python2'
_CRLF_        = b'\r\n'
_SPC_         = b' '
_EMPTY_       = b''

class Client(object):

  def __init__(self):
    self.options = {}

    # INFO that we get upon connect from the server.
    self._server_info = {}

    # Storage and monotonically increasing index for subscription callbacks.
    self._subs = {}
    self._ssid = 0

    # Parser with state for processing the wire protocol.
    self._ps = Parser(self)
    self._err = None

  @tornado.gen.coroutine
  def connect(self, opts={}):
    """
    Establishes an async connection to a NATS servers.
    The connection can be customized via an optional dictionary:

         # NATS cluster usage
         nc = nats.io.client.Client()
         yield nc.connect({'servers': ['nats://192.168.1.10:4222', 'nats://192.168.2.10:4222'] })

         # If using a secure conn, user and pass are to be passed on the uri
         yield nc.connect({'servers': ['nats://hello:world@192.168.1.10:4222' })

    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    self.io = tornado.iostream.IOStream(sock)

    # Default options
    self.options["servers"]  = opts["servers"]  if "servers"  in opts else []
    self.options["verbose"]  = opts["verbose"]  if "verbose"  in opts else False
    self.options["pedantic"] = opts["pedantic"] if "pedantic" in opts else False

    # Bind to the first server available in options or default
    if "servers" not in opts:
      self.options["host"] = '127.0.0.1'
      self.options["port"] = 4222
    else:
      # TODO: Randomize servers option
      server = self.options["servers"][0]
      uri = urlparse(server)
      self.options["host"] = uri.hostname
      self.options["port"] = uri.port

      if uri.username is not None:
        self.options["user"] = uri.username
      if uri.password is not None:
        self.options["pass"] = uri.password

    try:
      yield self.io.connect((self.options["host"], self.options["port"]))
    except Exception, e:
      raise ErrServerConnect(e)

    # INFO {...}
    # TODO: Check for errors here.
    line = yield self.io.read_until(_CRLF_)
    _, args = line.split(INFO_OP + _SPC_, 1)
    self._server_info = json.loads(args)

    # CONNECT {...}
    yield self.send_command(self.connect_command())

    # Wait for ack or not depending on verbose setting.
    if self.options["verbose"]:
      result = yield self.io.read_until(_CRLF_)
      if result != OK:
        raise ErrProtocol("'{0}' expected".format(OK_OP))

    # Parser reads directly from the same IO as the client.
    self._ps.read()

    # Send initial PING. PONG should be parsed by the parsing loop already.
    yield self.send_command("{0}{1}".format(PING_OP, _CRLF_))

  def connect_command(self):
    """
    Generates a JSON string with the params to be used
    when sending CONNECT to the server.

      ->> CONNECT {"verbose": false, "pedantic": false, "lang": "python" }

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
    self.io.write(bytes(cmd))

  @tornado.gen.coroutine
  def _publish(self, subject, reply, payload):
    """
    Sends a PUB command to the server.
    """
    size = len(payload)
    pub_cmd = "{0} {1} {2} {3} {4}".format(PUB_OP, subject, reply, size, _CRLF_)
    yield self.send_command(pub_cmd)
    yield self.send_command(payload)
    yield self.send_command(_CRLF_)

  @tornado.gen.coroutine
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
    Sends a SUB command to the server.  It takes a queue
    parameter which can be used in case of distributed queues
    or left empty if it is not the case, and a callback that
    will be dispatched message for processing them.
    """
    self._ssid += 1
    sid = self._ssid
    sub = Subscription(subject=subject, queue=queue, callback=callback, future=future)
    self._subs[sid] = sub

    sub_cmd = "{0} {1} {2}{3}{4}".format(SUB_OP, subject, queue, sid, _CRLF_)
    self.send_command(sub_cmd)
    return sid

  @tornado.gen.coroutine
  def auto_unsubscribe(self, sid, limit):
    """
    Sends an UNSUB command to the server.  Unsubscribe is one of the basic building
    blocks in order to be able to define request/response semantics via pub/sub
    by announcing the server limited interest a priori.
    """
    unsub_cmd = "{0} {1} {2}{3}".format(UNSUB_OP, sid, limit, _CRLF_)
    self.send_command(unsub_cmd)

  def _process_pong(self):
    """
    Sends PING to the server.  This happens soon after CONNECT,
    and later on periodically by the client.  If the
    """
    # TODO: ping outstanding logic
    # self.send_command(PING)
    pass

  def _process_ping(self):
    """
    Sends a PONG reply to the server.  The server will be periodically
    sending a PING, and if the the client does not reply a number of times,
    it will close the connection sending an `-ERR 'Stale Connection'` error.
    """
    self.send_command(PONG)

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
