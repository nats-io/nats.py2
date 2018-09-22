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
"""
Exported errors which can be thrown by the NATS client.
"""

import socket


class NatsError(Exception):
    pass


class ErrAuthorization(NatsError):
    pass


class ErrConnectionClosed(NatsError):
    pass


class ErrSecureConnRequired(NatsError):
    pass


class ErrJsonParse(NatsError):
    pass



class ErrSlowConsumer(NatsError):
    """
    The client becomes a slow consumer if the server ends up
    holding more than the allowed max limit of pending data size
    that was set in the server.
    """
    pass


class ErrStaleConnection(NatsError):
    """
    A connection becomes stale if there is a transgression
    in the number of maximum allowed pings not being responded.
    """
    pass


class ErrMaxPayload(NatsError):
    """
    Error raised upon publish in case the server ends up sending
    more bytes than the limit allowed by the server announces
    in its info message.
    """
    pass


class ErrNoServers(NatsError):
    """
    Raised when the number of reconnect attempts is exhausted
    when reconnecting to a server/set of servers, or if the
    allow reconnect option is was disabled.
    """
    pass


class ErrServerConnect(socket.error):
    """
    Raised when it could not establish a connection with server.
    """
    pass

class ErrBadSubscription(NatsError):
    def __str__(self):
        return "nats: Invalid Subscription"

class ErrDrainTimeout(NatsError):
    def __str__(self):
        return "nats: Draining Connection Timed Out"

class ErrConnectionDraining(NatsError):
     def __str__(self):
         return "nats: Connection Draining"

class ErrConnectionReconnecting(NatsError):
    def __str__(self):
        return "nats: Connection Reconnecting"
