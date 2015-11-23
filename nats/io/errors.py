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
    pass

class ErrStaleConnection(Exception):
    pass

class ErrMaxPayload(Exception):
    pass

class ErrNoServers(Exception):
    pass

class ErrServerConnect(socket.error):
    pass
