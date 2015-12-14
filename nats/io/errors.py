# Copyright 2015 Apcera Inc. All rights reserved.

"""
Exported errors which can be thrown by the NATS client.
"""

import socket

class ErrAuthorization(Exception):
    pass

class ErrConnectionClosed(Exception):
    pass

class ErrSecureConnRequired(Exception):
    pass

class ErrJsonParse(Exception):
    pass

class ErrSlowConsumer(Exception):
    """
    The client becomes a slow consumer if the server ends up
    holding more than the allowed max limit of pending data size
    that was set in the server.
    """
    pass

class ErrStaleConnection(Exception):
    """
    A connection becomes stale if there is a transgression
    in the number of maximum allowed pings not being responded.
    """
    pass

class ErrMaxPayload(Exception):
    """
    Error raised upon publish in case the server ends up sending
    more bytes than the limit allowed by the server announces
    in its info message.
    """
    pass

class ErrNoServers(Exception):
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
