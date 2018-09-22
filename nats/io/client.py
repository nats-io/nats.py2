# Copyright 2015-2018 The NATS Authors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import tornado.iostream
import tornado.concurrent
import tornado.escape
import tornado.gen
import tornado.ioloop
import tornado.queues
import socket
import json
import time
import io
import ssl

from random import shuffle
from urlparse import urlparse
from datetime import timedelta

from nats import __lang__, __version__
from nats.io.errors import *
from nats.io.nuid import NUID
from nats.protocol.parser import *

CONNECT_PROTO = b'{0} {1}{2}'
PUB_PROTO = b'{0} {1} {2} {3} {4}{5}{6}'
SUB_PROTO = b'{0} {1} {2} {3}{4}'
UNSUB_PROTO = b'{0} {1} {2}{3}'

INFO_OP = b'INFO'
CONNECT_OP = b'CONNECT'
PUB_OP = b'PUB'
MSG_OP = b'MSG'
SUB_OP = b'SUB'
UNSUB_OP = b'UNSUB'
PING_OP = b'PING'
PONG_OP = b'PONG'
OK_OP = b'+OK'
ERR_OP = b'-ERR'
_CRLF_ = b'\r\n'
_SPC_ = b' '
_EMPTY_ = b''

PING_PROTO = b'{0}{1}'.format(PING_OP, _CRLF_)
PONG_PROTO = b'{0}{1}'.format(PONG_OP, _CRLF_)

# Defaults
DEFAULT_PING_INTERVAL = 120  # seconds
MAX_OUTSTANDING_PINGS = 2
MAX_RECONNECT_ATTEMPTS = 60
RECONNECT_TIME_WAIT = 2  # seconds
DEFAULT_CONNECT_TIMEOUT = 2  # seconds
DEFAULT_DRAIN_TIMEOUT = 30 # seconds

DEFAULT_READ_BUFFER_SIZE = 1024 * 1024 * 10
DEFAULT_WRITE_BUFFER_SIZE = None
DEFAULT_READ_CHUNK_SIZE = 32768 * 2
DEFAULT_PENDING_SIZE = 1024 * 1024
DEFAULT_MAX_PAYLOAD_SIZE = 1048576

# Default Pending Limits of Subscriptions
DEFAULT_SUB_PENDING_MSGS_LIMIT = 65536
DEFAULT_SUB_PENDING_BYTES_LIMIT = 65536 * 1024

PROTOCOL = 1
INBOX_PREFIX = bytearray(b'_INBOX.')
INBOX_PREFIX_LEN = len(INBOX_PREFIX) + 22 + 1

class Subscription():
    def __init__(self, subject='', queue='', cb=None, is_async=False,
                 future=None, max_msgs=0, sid=None):
        self.subject = subject
        self.queue = queue
        self.cb = cb
        self.future = future
        self.max_msgs = max_msgs
        self.is_async = is_async
        self.received = 0
        self.sid = sid

        # Per subscription message processor
        self.pending_msgs_limit = None
        self.pending_bytes_limit = None
        self.pending_queue = None
        self.pending_size = 0
        self.closed = False


class Msg(object):
    __slots__ = 'subject', 'reply', 'data', 'sid'

    def __init__(
            self,
            subject='',
            reply='',
            data=b'',
            sid=0,
    ):
        self.subject = subject
        self.reply = reply
        self.data = data
        self.sid = sid

    def __repr__(self):
        return "<{}: subject='{}' reply='{}' data='{}...'>".format(
            self.__class__.__name__,
            self.subject,
            self.reply,
            self.data[:10].decode(),
        )

class Srv(object):
    """
    Srv is a helper data structure to hold state of a server.
    """

    def __repr__(self):
        return "<nats server uri={}, reconnects={}, discovered={}>".format(
            self.uri.netloc, self.reconnects, self.discovered)

    def __init__(self, uri):
        self.uri = uri
        self.reconnects = 0
        self.last_attempt = None
        self.did_connect = False
        self.discovered = False

class Client(object):
    """
    Tornado based client for NATS.
    """

    DISCONNECTED = 0
    CONNECTED = 1
    CLOSED = 2
    RECONNECTING = 3
    CONNECTING = 4
    DRAINING_SUBS = 5
    DRAINING_PUBS = 6

    def __repr__(self):
        return "<nats client v{}>".format(__version__)

    def __init__(self):
        self._loop = None
        self._current_server = None
        self._server_info = {}
        self._server_pool = []
        self.io = None
        self._socket = None

        # Ping Interval
        self._ping_timer = None
        self._pings_outstanding = 0
        self._pongs_received = 0
        self._pongs = []

        # Callbacks
        self._err = None
        self._error_cb = None
        self._disconnected_cb = None
        self._closed_cb = None
        self._reconnected_cb = None

        # Dispatcher
        self._max_payload_size = DEFAULT_MAX_PAYLOAD_SIZE
        self._subs = {}
        self._ssid = 0
        self._status = Client.DISCONNECTED
        self._ps = Parser(self)

        # Flusher
        self._pending = []
        self._pending_size = 0
        self._flush_queue = None

        # New style request/response
        self._resp_sub = None
        self._resp_map = None
        self._resp_sub_prefix = None
        self._nuid = NUID()

        # Custom options
        self.options = {}
        self.stats = {
            'in_msgs': 0,
            'out_msgs': 0,
            'in_bytes': 0,
            'out_bytes': 0,
            'reconnects': 0,
            'errors_received': 0
        }

    @tornado.gen.coroutine
    def connect(self,
                servers=["nats://127.0.0.1:4222"],
                loop=None,
                # 'io_loop' and 'loop' are the same, but we have
                # both params to be consistent with asyncio client.
                io_loop=None,

                # Event Callbacks
                error_cb=None,
                disconnected_cb=None,
                reconnected_cb=None,
                closed_cb=None,
                # 'close_cb' is the same as 'closed_cb' but we have
                # both params to be consistent with the asyncio client.
                close_cb=None,

                # CONNECT options
                name=None,
                pedantic=False,
                verbose=False,
                no_echo=False,
                user=None,
                password=None,
                token=None,

                # Reconnect logic
                allow_reconnect=True,
                connect_timeout=DEFAULT_CONNECT_TIMEOUT,
                reconnect_time_wait=RECONNECT_TIME_WAIT,
                max_reconnect_attempts=MAX_RECONNECT_ATTEMPTS,
                dont_randomize=False,

                # Ping Interval
                ping_interval=DEFAULT_PING_INTERVAL,
                max_outstanding_pings=MAX_OUTSTANDING_PINGS,
                tls=None,
                max_read_buffer_size=DEFAULT_READ_BUFFER_SIZE,
                max_write_buffer_size=DEFAULT_WRITE_BUFFER_SIZE,
                read_chunk_size=DEFAULT_READ_CHUNK_SIZE,
                tcp_nodelay=False,
                drain_timeout=DEFAULT_DRAIN_TIMEOUT,
                ):
        """
        Establishes a connection to a NATS server.

        Examples:

          # Configure pool of NATS servers.
          nc = nats.io.client.Client()
          yield nc.connect({ 'servers': ['nats://192.168.1.10:4222', 'nats://192.168.2.10:4222'] })

          # User and pass are to be passed on the uri to authenticate.
          yield nc.connect({ 'servers': ['nats://hello:world@192.168.1.10:4222'] })

          # Simple URL can be used as well.
          yield nc.connect('demo.nats.io:4222')

        """
        self._setup_server_pool(servers)
        self._loop = io_loop or loop or tornado.ioloop.IOLoop.current()
        self._error_cb = error_cb
        self._closed_cb = closed_cb or close_cb
        self._reconnected_cb = reconnected_cb
        self._disconnected_cb = disconnected_cb
        self._max_read_buffer_size = max_read_buffer_size
        self._max_write_buffer_size = max_write_buffer_size
        self._read_chunk_size = read_chunk_size

        self.options["verbose"] = verbose
        self.options["pedantic"] = pedantic
        self.options["name"] = name
        self.options["no_echo"] = no_echo
        self.options["user"] = user
        self.options["password"] = password
        self.options["token"] = token
        self.options["max_outstanding_pings"] = max_outstanding_pings
        self.options["max_reconnect_attempts"] = max_reconnect_attempts
        self.options["reconnect_time_wait"] = reconnect_time_wait
        self.options["dont_randomize"] = dont_randomize
        self.options["allow_reconnect"] = allow_reconnect
        self.options["tcp_nodelay"] = tcp_nodelay

        # In seconds
        self.options["connect_timeout"] = connect_timeout
        self.options["ping_interval"] = ping_interval
        self.options["drain_timeout"] = drain_timeout

        # TLS customizations
        if tls is not None:
            self.options["tls"] = tls

        while True:
            try:
                s = self._next_server()
                if s is None:
                    raise ErrNoServers

                # Check when was the last attempt and back off before reconnecting
                if s.last_attempt is not None:
                    now = time.time()
                    if (now - s.last_attempt
                        ) < self.options["reconnect_time_wait"]:
                        yield tornado.gen.sleep(
                            self.options["reconnect_time_wait"])

                # Mark that we have attempted to connect
                s.reconnects += 1
                s.last_attempt = time.time()
                yield self._server_connect(s)
                self._current_server = s

                # Mark that TCP connect worked against this server.
                s.did_connect = True

                # Established TCP connection at least and about
                # to send connect command, which might not succeed
                # in case TLS required and handshake failed.
                self._status = Client.CONNECTING
                yield self._process_connect_init()
                break
            except (socket.error, tornado.iostream.StreamClosedError) as e:
                self._status = Client.DISCONNECTED
                self._err = e
                if self._error_cb is not None:
                    self._error_cb(ErrServerConnect(e))
                if not self.options["allow_reconnect"]:
                    raise ErrNoServers

        # Flush pending data before continuing in connected status.
        # FIXME: Could use future here and wait for an error result
        # to bail earlier in case there are errors in the connection.
        yield self._flush_pending()

        # First time connecting to NATS so if there were no errors,
        # we can consider to be connected at this point.
        self._status = Client.CONNECTED

        # Prepare the ping pong interval.
        self._ping_timer = tornado.ioloop.PeriodicCallback(
            self._ping_interval, self.options["ping_interval"] * 1000)
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

        self.io = tornado.iostream.IOStream(self._socket,
            max_buffer_size=self._max_read_buffer_size,
            max_write_buffer_size=self._max_write_buffer_size,
            read_chunk_size=self._read_chunk_size)

        # Connect to server with a deadline
        future = self.io.connect((s.uri.hostname, s.uri.port))
        yield tornado.gen.with_timeout(
            timedelta(seconds=self.options["connect_timeout"]), future)

        # Called whenever disconnected from the server.
        self.io.set_close_callback(self._process_op_err)

    @tornado.gen.coroutine
    def _send_ping(self, future=None):
        if future is None:
            future = tornado.concurrent.Future()
        self._pongs.append(future)
        yield self.send_command(PING_PROTO)
        yield self._flush_pending()

    def connect_command(self):
        '''
        Generates a JSON string with the params to be used
        when sending CONNECT to the server.

          ->> CONNECT {"verbose": false, "pedantic": false, "lang": "python2" }

        '''
        options = {
            "verbose": self.options["verbose"],
            "pedantic": self.options["pedantic"],
            "lang": __lang__,
            "version": __version__,
            "protocol": PROTOCOL
        }
        if "auth_required" in self._server_info:
            if self._server_info["auth_required"] == True:
                # In case there is no password, then consider handle
                # sending a token instead.
                if self.options["user"] is not None and self.options["password"] is not None:
                    options["user"] = self.options["user"]
                    options["pass"] = self.options["password"]
                elif self.options["token"] is not None:
                    options["auth_token"] = self.options["token"]
                elif self._current_server.uri.password is None:
                    options["auth_token"] = self._current_server.uri.username
                else:
                    options["user"] = self._current_server.uri.username
                    options["pass"] = self._current_server.uri.password
        if self.options["name"] is not None:
            options["name"] = self.options["name"]
        if self.options["no_echo"] is not None:
            options["echo"] = not self.options["no_echo"]

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

        if self._pending_size > DEFAULT_PENDING_SIZE:
            yield self._flush_pending()

    @tornado.gen.coroutine
    def _publish(self, subject, reply, payload, payload_size):
        payload_size_bytes = ("%d" % payload_size).encode()
        pub_cmd = b''.join([
            PUB_OP, _SPC_,
            subject.encode(), _SPC_, reply, _SPC_, payload_size_bytes, _CRLF_,
            payload, _CRLF_
        ])
        self.stats['out_msgs'] += 1
        self.stats['out_bytes'] += payload_size
        yield self.send_command(pub_cmd)

    @tornado.gen.coroutine
    def _flush_pending(self, check_connected=True):
        if not self.is_connected and check_connected:
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
        yield self.publish_request(subject, _EMPTY_, payload)

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
        if self._flush_queue.empty():
            yield self._flush_pending()

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
        try:
            result = yield tornado.gen.with_timeout(
                timedelta(seconds=timeout), future)
        except tornado.gen.TimeoutError:
            # Set the future to False so it can be ignored in _process_pong,
            # and try to remove from the list of pending pongs.
            future.set_result(False)
            for i, pong_future in enumerate(self._pongs):
                if pong_future == future:
                    del self._pongs[i]
                    break
            raise
        raise tornado.gen.Return(result)

    @tornado.gen.coroutine
    def request(self, subject, payload, timeout=0.5, expected=1, cb=None):
        """
        Implements the request/response pattern via pub/sub using an
        unique reply subject and an async subscription.

        If cb is None, then it will wait and return a single message
        using the new request/response style that is less chatty over
        the network.

          ->> SUB _INBOX.BF6zPVxvScfXGd4VyUMJyo.* 1
          ->> PUB hello _INBOX.BF6zPVxvScfXGd4VyUMJyo.BF6zPVxvScfXCh4VyUMJyo 5
          ->> MSG_PAYLOAD: hello
          <<- MSG hello 2 _INBOX.BF6zPVxvScfXGd4VyUMJyo.BF6zPVxvScfXCh4VyUMJyo 5
          ->> PUB _INBOX.BF6zPVxvScfXGd4VyUMJyo.BF6zPVxvScfXCh4VyUMJyo  5
          ->> MSG_PAYLOAD: world
          <<- MSG _INBOX.BF6zPVxvScfXGd4VyUMJyo.BF6zPVxvScfXCh4VyUMJyo 1 5

        If a cb is passed, then it will use auto unsubscribe
        functionality and expect a limited number of messages which
        will be handled asynchronously in the callback.

          ->> SUB _INBOX.gnKUg9bmAHANjxIsDiQsWO 90
          ->> UNSUB 90 1
          ->> PUB hello _INBOX.gnKUg9bmAHANjxIsDiQsWO 5
          ->> MSG_PAYLOAD: world
          <<- MSG hello 2 _INBOX.gnKUg9bmAHANjxIsDiQsWO 5

        """
        if self.is_draining:
            raise ErrConnectionDraining

        # If callback given then continue to use old style.
        if cb is not None:
            next_inbox = INBOX_PREFIX[:]
            next_inbox.extend(self._nuid.next())
            inbox = str(next_inbox)
            sid = yield self.subscribe(
                inbox,
                queue=_EMPTY_,
                cb=cb,
                max_msgs=expected,
            )
            yield self.auto_unsubscribe(sid, expected)
            yield self.publish_request(subject, inbox, payload)
            raise tornado.gen.Return(sid)

        if self._resp_sub_prefix is None:
            self._resp_map = {}

            # Create a prefix and single wildcard subscription once.
            self._resp_sub_prefix = str(INBOX_PREFIX[:])
            self._resp_sub_prefix += self._nuid.next()
            self._resp_sub_prefix += b'.'
            resp_mux_subject = str(self._resp_sub_prefix[:])
            resp_mux_subject += b'*'
            sub = Subscription(subject=str(resp_mux_subject))

            # FIXME: Allow setting pending limits for responses mux subscription.
            sub.pending_msgs_limit = DEFAULT_SUB_PENDING_MSGS_LIMIT
            sub.pending_bytes_limit = DEFAULT_SUB_PENDING_BYTES_LIMIT
            sub.pending_queue = tornado.queues.Queue(
                maxsize=sub.pending_msgs_limit)

            # Single task for handling the requests
            @tornado.gen.coroutine
            def wait_for_msgs():
                while True:
                    sub = wait_for_msgs.sub
                    if sub.closed:
                        break

                    msg = yield sub.pending_queue.get()
                    if msg is None:
                        break

                    token = msg.subject[INBOX_PREFIX_LEN:]
                    try:
                        fut = self._resp_map[token]
                        fut.set_result(msg)
                        del self._resp_map[token]
                    except KeyError:
                        # Future already handled so drop any extra
                        # responses which may have made it.
                        continue

            wait_for_msgs.sub = sub
            self._loop.spawn_callback(wait_for_msgs)

            # Store the subscription in the subscriptions map,
            # then send the protocol commands to the server.
            self._ssid += 1
            sid = self._ssid
            sub.sid = sid
            self._subs[sid] = sub

            # Send SUB command...
            sub_cmd = b''.join([
                SUB_OP, _SPC_,
                sub.subject.encode(), _SPC_, ("%d" % sid).encode(), _CRLF_
            ])
            yield self.send_command(sub_cmd)
            yield self._flush_pending()

        # Use a new NUID for the token inbox and then use the future.
        token = self._nuid.next()
        inbox = self._resp_sub_prefix[:]
        inbox.extend(token)
        future = tornado.concurrent.Future()
        self._resp_map[token.decode()] = future
        yield self.publish_request(subject, str(inbox), payload)
        msg = yield tornado.gen.with_timeout(
            timedelta(seconds=timeout), future)
        raise tornado.gen.Return(msg)

    @tornado.gen.coroutine
    def timed_request(self, subject, payload, timeout=0.5):
        """
        Implements the request/response pattern via pub/sub
        using an ephemeral subscription which will be published
        with a limited interest of 1 reply returning the response
        or raising a Timeout error.

          ->> SUB _INBOX.E9jM2HTirMXDMXPROSQmSd 90
          ->> UNSUB 90 1
          ->> PUB hello _INBOX.E9jM2HTirMXDMXPROSQmSd 5
          ->> MSG_PAYLOAD: world
          <<- MSG hello 2 _INBOX.E9jM2HTirMXDMXPROSQmSd 5

        """
        next_inbox = INBOX_PREFIX[:]
        next_inbox.extend(self._nuid.next())
        inbox = str(next_inbox)
        future = tornado.concurrent.Future()
        sid = yield self.subscribe(
            subject=inbox, queue=_EMPTY_, cb=None, future=future, max_msgs=1)
        yield self.auto_unsubscribe(sid, 1)
        yield self.publish_request(subject, inbox, payload)
        msg = yield tornado.gen.with_timeout(
            timedelta(seconds=timeout), future)
        raise tornado.gen.Return(msg)

    @tornado.gen.coroutine
    def subscribe(
            self,
            subject="",
            queue="",
            cb=None,
            future=None,
            max_msgs=0,
            is_async=False,
            pending_msgs_limit=DEFAULT_SUB_PENDING_MSGS_LIMIT,
            pending_bytes_limit=DEFAULT_SUB_PENDING_BYTES_LIMIT,
    ):
        """
        Sends a SUB command to the server. Takes a queue parameter
        which can be used in case of distributed queues or left empty
        if it is not the case, and a callback that will be dispatched
        message for processing them.
        """
        if self.is_closed:
            raise ErrConnectionClosed

        if self.is_draining:
            raise ErrConnectionDraining

        self._ssid += 1
        sid = self._ssid
        sub = Subscription(
            subject=subject,
            queue=queue,
            cb=cb,
            future=future,
            max_msgs=max_msgs,
            is_async=is_async,
            sid=sid,
        )
        self._subs[sid] = sub

        if cb is not None:
            sub.pending_msgs_limit = pending_msgs_limit
            sub.pending_bytes_limit = pending_bytes_limit
            sub.pending_queue = tornado.queues.Queue(
                maxsize=pending_msgs_limit)

            @tornado.gen.coroutine
            def wait_for_msgs():
                while True:
                    sub = wait_for_msgs.sub
                    err_cb = wait_for_msgs.err_cb

                    try:
                        sub = wait_for_msgs.sub
                        if sub.closed:
                            break

                        msg = yield sub.pending_queue.get()
                        if msg is None:
                            break
                        sub.pending_size -= len(msg.data)

                        if sub.max_msgs > 0 and sub.received >= sub.max_msgs:
                            # If we have hit the max for delivered msgs, remove sub.
                            self._remove_subscription(sub)

                        # Invoke depending of type of handler.
                        if sub.is_async:
                            # NOTE: Deprecate this usage in a next release,
                            # the handler implementation ought to decide
                            # the concurrency level at which the messages
                            # should be processed.
                            self._loop.spawn_callback(sub.cb, msg)
                        else:
                            # Call it and take the possible future in the loop.
                            yield sub.cb(msg)
                    except Exception as e:
                        # All errors from calling an async subscriber
                        # handler are async errors.
                        if err_cb is not None:
                            yield err_cb(e)
                    finally:
                        if sub.max_msgs > 0 and sub.received >= sub.max_msgs:
                            # If we have hit the max for delivered msgs, remove sub.
                            self._remove_subscription(sub)
                            break

            # Bind the subscription and error cb if present
            wait_for_msgs.sub = sub
            wait_for_msgs.err_cb = self._error_cb
            self._loop.spawn_callback(wait_for_msgs)

        elif future is not None:
            # Used to handle the single response from a request
            # based on auto unsubscribe.
            sub.future = future

        # Send SUB command...
        sub_cmd = b''.join([
            SUB_OP, _SPC_,
            sub.subject.encode(), _SPC_,
            sub.queue.encode(), _SPC_, ("%d" % sid).encode(), _CRLF_
        ])
        yield self.send_command(sub_cmd)
        yield self._flush_pending()
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
            self._remove_subscription(sub)

        # We will send these for all subs when we reconnect anyway,
        # so that we can suppress here.
        if not self.is_reconnecting:
            yield self.auto_unsubscribe(ssid, max_msgs)

    def _remove_subscription(self, sub):
        # Mark as invalid
        sub.closed = True

        # Remove the pending queue
        if sub.pending_queue is not None:
            try:
                # Send empty msg to signal cancellation
                # and stop the msg processing loop.
                sub.pending_queue.put_nowait(None)
            except tornado.queues.QueueFull:
                # Skip error
                return

    @tornado.gen.coroutine
    def auto_unsubscribe(self, sid, limit=1):
        """
        Sends an UNSUB command to the server.  Unsubscribe is one of the basic building
        blocks in order to be able to define request/response semantics via pub/sub
        by announcing the server limited interest a priori.
        """
        if self.is_draining:
            raise ErrConnectionDraining
        yield self._unsubscribe(sid, limit)

    @tornado.gen.coroutine
    def _unsubscribe(self, sid, limit=1):
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
        if self._flush_queue.empty():
            yield self._flush_pending()

    @tornado.gen.coroutine
    def _process_pong(self):
        """
        The client will send a PING soon after CONNECT and then periodically
        to the server as a failure detector to close connections to unhealthy servers.
        For each PING the client sends, we will add a respective PONG future.
        Here we want to find the oldest PONG future that is still running.  If the
        flush PING-PONG already timed out, then just drop those old items.
        """
        if len(self._pongs) > 0:
            future = self._pongs.pop(0)
            self._pongs_received += 1
            if self._pings_outstanding > 0:
                self._pings_outstanding -= 1

            # Only exit loop if future still running (hasn't exceeded flush timeout).
            if future.running():
                future.set_result(True)

    @tornado.gen.coroutine
    def _process_msg(self, sid, subject, reply, data):
        """
        Dispatches the received message to the stored subscription.
        It first tries to detect whether the message should be
        dispatched to a passed callback.  In case there was not
        a callback, then it tries to set the message into a future.
        """
        payload_size = len(data)
        self.stats['in_msgs'] += 1
        self.stats['in_bytes'] += payload_size

        msg = Msg(subject=subject.decode(), reply=reply.decode(), data=data)

        # Don't process the message if the subscription has been removed
        sub = self._subs.get(sid)
        if sub is None:
            raise tornado.gen.Return()
        sub.received += 1

        if sub.max_msgs > 0 and sub.received >= sub.max_msgs:
            # Enough messages so can throwaway subscription now.
            self._subs.pop(sid, None)

        # Check if it is an old style request.
        if sub.future is not None:
            sub.future.set_result(msg)

            # Discard subscription since done
            self._remove_subscription(sub)
            raise tornado.gen.Return()

        # Let subscription wait_for_msgs coroutine process the messages,
        # but in case sending to the subscription task would block,
        # then consider it to be an slow consumer and drop the message.
        try:
            sub.pending_size += payload_size
            if sub.pending_size >= sub.pending_bytes_limit:
                # Substract again the bytes since throwing away
                # the message so would not be pending data.
                sub.pending_size -= payload_size

                if self._error_cb is not None:
                    yield self._error_cb(ErrSlowConsumer())
                raise tornado.gen.Return()

            yield sub.pending_queue.put_nowait(msg)
        except tornado.queues.QueueFull:
            if self._error_cb is not None:
                yield self._error_cb(ErrSlowConsumer())

    @tornado.gen.coroutine
    def _process_connect_init(self):
        """
        Handles the initial part of the NATS protocol, moving from
        the (RE)CONNECTING to CONNECTED states when establishing
        a connection with the server.
        """
        # INFO {...}
        line = yield self.io.read_until(_CRLF_, max_bytes=None)
        _, args = line.split(INFO_OP + _SPC_, 1)
        self._server_info = tornado.escape.json_decode((args))

        if 'max_payload' in self._server_info:
            self._max_payload_size = self._server_info["max_payload"]

        # Check whether we need to upgrade to TLS first of all
        if 'tls_required' in self._server_info and self._server_info['tls_required']:
            # Detach and prepare for upgrading the TLS connection.
            self._loop.remove_handler(self._socket.fileno())

            tls_opts = {}
            if "tls" in self.options:
                # Allow customizing the TLS version though default
                # to one that the server supports at least.
                tls_opts = self.options["tls"]

            # Rewrap using a TLS connection, can't do handshake on connect
            # as the socket is non blocking.
            self._socket = ssl.wrap_socket(
                self._socket, do_handshake_on_connect=False, **tls_opts)

            # Use the TLS stream instead from now
            self.io = tornado.iostream.SSLIOStream(self._socket)
            self.io.set_close_callback(self._process_op_err)
            self.io._do_ssl_handshake()

        # Refresh state of the parser upon reconnect.
        if self.is_reconnecting:
            self._ps.reset()

        # CONNECT then send a PING expecting a PONG to make a
        # roundtrip to the server and assert that sent commands sent
        # this far have been processed already.
        cmd = self.connect_command()
        yield self.io.write(cmd)
        yield self.io.write(PING_PROTO)

        # FIXME: Add readline timeout for these.
        next_op = yield self.io.read_until(
            _CRLF_, max_bytes=MAX_CONTROL_LINE_SIZE)
        if self.options["verbose"] and OK_OP in next_op:
            next_op = yield self.io.read_until(
                _CRLF_, max_bytes=MAX_CONTROL_LINE_SIZE)
        if ERR_OP in next_op:
            err_line = next_op.decode()
            _, err_msg = err_line.split(_SPC_, 1)
            # FIXME: Maybe handling could be more special here,
            # checking for ErrAuthorization for example.
            # yield from self._process_err(err_msg)
            raise NatsError("nats: " + err_msg.rstrip('\r\n'))

        if PONG_PROTO in next_op:
            self._status = Client.CONNECTED

        self._loop.spawn_callback(self._read_loop)
        self._pongs = []
        self._pings_outstanding = 0
        self._ping_timer = tornado.ioloop.PeriodicCallback(
            self._ping_interval, self.options["ping_interval"] * 1000)
        self._ping_timer.start()

        # Queue and flusher for coalescing writes to the server.
        self._flush_queue = tornado.queues.Queue(maxsize=1024)
        self._loop.spawn_callback(self._flusher_loop)

    def _process_info(self, info_line):
        """
        Process INFO lines sent by the server to reconfigure client
        with latest updates from cluster to enable server discovery.
        """
        info = tornado.escape.json_decode(info_line.decode())

        if 'connect_urls' in info:
            if info['connect_urls']:
                connect_urls = []
                for connect_url in info['connect_urls']:
                    uri = urlparse("nats://%s" % connect_url)
                    srv = Srv(uri)
                    srv.discovered = True

                    # Filter for any similar server in the server pool already.
                    should_add = True
                    for s in self._server_pool:
                        if uri.netloc == s.uri.netloc:
                            should_add = False
                    if should_add:
                        connect_urls.append(srv)

                if self.options["dont_randomize"] is not True:
                    shuffle(connect_urls)
                for srv in connect_urls:
                    self._server_pool.append(srv)

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
            if self.options["max_reconnect_attempts"] > 0 and (
                    server.reconnects >
                    self.options["max_reconnect_attempts"]):
                continue
            else:
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
        return self._status == Client.CONNECTED or self.is_draining

    @property
    def is_connecting(self):
        return self._status == Client.CONNECTING

    @property
    def is_draining(self):
        return (self._status == Client.DRAINING_SUBS or self._status == Client.DRAINING_PUBS)

    @property
    def is_draining_pubs(self):
        return self._status == Client.DRAINING_PUBS

    @tornado.gen.coroutine
    def _process_op_err(self, err=None):
        """
        Process errors which occured while reading/parsing the protocol.
        It attempts to reconnect if `allow_reconnect' is enabled.
        """
        if self.is_connecting or self.is_closed or self.is_reconnecting:
            return

        if self.options["allow_reconnect"] and self.is_connected:
            self._status = Client.RECONNECTING
            yield self._attempt_reconnect()
        else:
            # Transition into CLOSED state
            self._status = Client.DISCONNECTED
            self._err = err
            yield self._close(Client.CLOSED)

    @tornado.gen.coroutine
    def _attempt_reconnect(self):
        if self._ping_timer is not None and self._ping_timer.is_running():
            self._ping_timer.stop()

        if self.io and not self.io.closed():
            self.io.close()
        yield self._end_flusher_loop()

        self._err = None
        if self._disconnected_cb is not None:
            self._disconnected_cb()

        if self.is_closed:
            return

        if "dont_randomize" not in self.options or not self.options["dont_randomize"]:
            shuffle(self._server_pool)

        while True:
            try:
                # Try to establish a TCP connection to a server in
                # the cluster then send CONNECT command to it.
                yield self._select_next_server()
                yield self._process_connect_init()

                # Consider a reconnect to be done once CONNECT was
                # processed by the server successfully.
                self.stats["reconnects"] += 1

                # Reset number of reconnects upon successful connection.
                self._current_server.did_connect = True
                self._current_server.reconnects = 0

                # Replay all the subscriptions.
                for ssid, sub in self._subs.items():
                    sub_cmd = SUB_PROTO.format(
                        SUB_OP, sub.subject, sub.queue, ssid, _CRLF_,
                        )
                    yield self.io.write(sub_cmd)
                self._err = None

                # Flush any pending bytes from reconnect
                if len(self._pending) > 0:
                    yield self._flush_pending()
                self._status = Client.CONNECTED
                # Roundtrip to the server to ensure all previous commands
                # have been sent.
                yield self.flush()

                # Reconnected at this point successfully.
                if self._reconnected_cb is not None:
                    self._reconnected_cb()
                break
            except ErrNoServers as e:
                self._err = e
                self._status = Client.DISCONNECTED
                yield self.close()
                break
            except (socket.error, NatsError, tornado.iostream.StreamClosedError) as e:
                self._err = e
                if self._error_cb is not None:
                    self._error_cb(e)
                self._status = Client.RECONNECTING
                self._current_server.last_attempt = time.time()
                self._current_server.reconnects += 1

    def _setup_server_pool(self, connect_url):
        if type(connect_url) is str:
            try:
                if "nats://" in connect_url or "tls://" in connect_url:
                    # Closer to how the Go client handles this.
                    # e.g. nats://127.0.0.1:4222
                    uri = urlparse(connect_url)
                elif ":" in connect_url:
                    # Expand the scheme for the user
                    # e.g. 127.0.0.1:4222
                    uri = urlparse("nats://%s" % connect_url)
                else:
                    # Just use the endpoint with the default NATS port.
                    # e.g. demo.nats.io
                    uri = urlparse("nats://%s:4222" % connect_url)

                # In case only endpoint with scheme was set.
                # e.g. nats://demo.nats.io or localhost:
                if uri.port is None:
                    uri = urlparse("nats://%s:4222" % uri.hostname)
            except ValueError:
                raise NatsError("nats: invalid connect url option")

            if uri.hostname is None or len(uri.hostname) == 0 or uri.hostname == "none":
                raise NatsError("nats: invalid hostname in connect url")
            self._server_pool.append(Srv(uri))
        elif type(connect_url) is list:
            try:
                for server in connect_url:
                    uri = urlparse(server)
                    self._server_pool.append(Srv(uri))
            except ValueError:
                raise NatsError("nats: invalid connect url option")
        else:
            raise NatsError("nats: invalid connect url option")

    @tornado.gen.coroutine
    def _select_next_server(self):
        """
        Looks up in the server pool for an available server
        and attempts to connect.
        """

        # Continue trying to connect until there is an available server
        # or bail in case there are no more available servers.
        while True:
            if len(self._server_pool) == 0:
                self._current_server = None
                raise ErrNoServers

            now = time.time()
            s = self._server_pool.pop(0)
            if self.options["max_reconnect_attempts"] > 0:
                if s.reconnects > self.options["max_reconnect_attempts"]:
                    # Discard server since already tried to reconnect too many times.
                    continue

            # Not yet exceeded max_reconnect_attempts so can still use
            # this server in the future.
            self._server_pool.append(s)
            if s.last_attempt is not None and now < s.last_attempt + self.options["reconnect_time_wait"]:
                # Backoff connecting to server if we attempted recently.
                yield tornado.gen.sleep(self.options["reconnect_time_wait"])

            try:
                yield self._server_connect(s)
                self._current_server = s
                break
            except (socket.error, tornado.iostream.StreamClosedError) as e:
                s.last_attempt = time.time()
                s.reconnects += 1

                self._err = e
                if self._error_cb is not None:
                    self._error_cb(e)
                self._status = Client.RECONNECTING
                continue

    @tornado.gen.coroutine
    def close(self):
        """
        Wraps up connection to the NATS cluster and stops reconnecting.
        Does cleanup of the client state and tears down the connection.
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
            self._status = status
            return
        self._status = Client.CLOSED

        # Stop background tasks
        yield self._end_flusher_loop()

        if self._ping_timer is not None and self._ping_timer.is_running():
            self._ping_timer.stop()

        if not self.io.closed():
            self.io.close()

        # Cleanup subscriptions since not reconnecting so no need
        # to replay the subscriptions anymore.
        for ssid, sub in self._subs.items():
            self._subs.pop(ssid, None)
            self._remove_subscription(sub)

        if do_callbacks:
            if self._disconnected_cb is not None:
                self._disconnected_cb()
            if self._closed_cb is not None:
                self._closed_cb()

    @tornado.gen.coroutine
    def drain(self, sid=None):
        """
        Drain will put a connection into a drain state. All subscriptions will
        immediately be put into a drain state. Upon completion, the publishers
        will be drained and can not publish any additional messages. Upon draining
        of the publishers, the connection will be closed. Use the `closed_cb'
        option to know when the connection has moved from draining to closed.

        If a sid is passed, just the subscription with that sid will be drained
        without closing the connection.
        """
        if self.is_draining:
            return

        if self.is_closed:
            raise ErrConnectionClosed

        if self.is_connecting or self.is_reconnecting:
            raise ErrConnectionReconnecting

        # Drain a single subscription
        if sid is not None:
            raise tornado.gen.Return(self._drain_sub(sid))

        # Start draining the subscriptions
        self._status = Client.DRAINING_SUBS

        drain_tasks = []
        for ssid, sub in self._subs.items():
            task = self._drain_sub(ssid)
            drain_tasks.append(task)

        # Wait for subscriptions to stop handling messages.
        drain_is_done = tornado.gen.multi(drain_tasks)
        try:
            yield tornado.gen.with_timeout(
                timedelta(seconds=self.options["drain_timeout"]),
                drain_is_done,
                )
        except tornado.gen.TimeoutError:
            if self._error_cb is not None:
                yield self._error_cb(ErrDrainTimeout())
        finally:
            self._status = Client.DRAINING_PUBS
            yield self.flush()
            yield self.close()

    def _drain_sub(self, sid):
        sub = self._subs.get(sid)
        if sub is None:
            raise ErrBadSubscription

        drained = tornado.concurrent.Future()

        # Draining happens async under a task per sub which can be awaited.
        @tornado.gen.coroutine
        def drain_subscription():
            # Announce server that no longer want to receive more
            # messages in this sub and just process the ones remaining.
            yield self._unsubscribe(sid, limit=0)
            yield self.flush()

            # Wait until no more messages are left or enough received,
            # then cancel the subscription task.
            while sub.pending_queue.qsize() > 0 and not sub.closed:
                yield tornado.gen.sleep(0.1)

            # Subscription is done and won't be receiving further
            # messages so can throw it away now.
            self._subs.pop(sid, None)
            self._remove_subscription(sub)
            drained.set_result(True)
        self._loop.spawn_callback(drain_subscription)

        # Return future which can be used to await draining is done.
        return drained

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

    @property
    def connected_url(self):
        if self.is_connected:
            return self._current_server.uri
        else:
            return None

    @property
    def servers(self):
        servers = []
        for srv in self._server_pool:
            servers.append(srv)
        return servers

    @property
    def discovered_servers(self):
        servers = []
        for srv in self._server_pool:
            if srv.discovered:
                servers.append(srv)
        return servers

    @tornado.gen.coroutine
    def _ping_interval(self):
        if not self.is_connected:
            return
        self._pings_outstanding += 1
        if self._pings_outstanding > self.options["max_outstanding_pings"]:
            yield self._process_op_err(ErrStaleConnection)
        yield self._send_ping()

    @tornado.gen.coroutine
    def _read_loop(self, data=''):
        """
        Read loop for gathering bytes from the server in a buffer
        of maximum MAX_CONTROL_LINE_SIZE, then received bytes are streamed
        to the parsing callback for processing.
        """
        while True:
            if not self.is_connected or self.is_connecting or self.io.closed():
                break

            try:
                yield self.io.read_bytes(
                    DEFAULT_READ_CHUNK_SIZE,
                    streaming_callback=self._ps.parse,
                    partial=True)
            except tornado.iostream.StreamClosedError as e:
                self._err = e
                if self._error_cb is not None and not self.is_reconnecting and not self.is_closed:
                    self._error_cb(e)
                break

    @tornado.gen.coroutine
    def _flusher_loop(self):
        """
        Coroutine which continuously tries to consume pending commands
        and then flushes them to the socket.
        """
        while True:
            pending = []
            pending_size = 0
            try:
                # Block and wait for the flusher to be kicked
                yield self._flush_queue.get()

                # Check whether we should bail first
                if not self.is_connected or self.is_connecting or self.io.closed():
                    break

                # Flush only when we actually have something in buffer...
                if self._pending_size > 0:
                    cmds = b''.join(self._pending)

                    # Reset pending queue and store tmp in case write fails
                    self._pending, pending = [], self._pending
                    self._pending_size, pending_size = 0, self._pending_size
                    yield self.io.write(cmds)
            except tornado.iostream.StreamBufferFullError:
                # Acumulate as pending data size and flush when possible.
                self._pending = pending + self._pending
                self._pending_size += pending_size
            except tornado.iostream.StreamClosedError as e:
                self._pending = pending + self._pending
                self._pending_size += pending_size
                yield self._process_op_err(e)

    @tornado.gen.coroutine
    def _end_flusher_loop(self):
        """
        Let flusher_loop coroutine quit - useful when disconnecting.
        """
        if not self.is_connected or self.is_connecting or self.io.closed():
            if self._flush_queue is not None and self._flush_queue.empty():
                self._flush_pending(check_connected=False)
            yield tornado.gen.moment
