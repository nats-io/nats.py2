# Copyright 2015 Apcera Inc. All rights reserved.

"""
NATS network protocol parser.
"""

INFO_OP     = b'INFO'
CONNECT_OP  = b'CONNECT'
PUB_OP      = b'PUB'
MSG_OP      = b'MSG'
SUB_OP      = b'SUB'
UNSUB_OP    = b'UNSUB'
PING_OP     = b'PING'
PONG_OP     = b'PONG'
OK_OP       = b'+OK'
ERR_OP      = b'-ERR'
MSG_END     = b'\n'
_CRLF_      = b'\r\n'
_SPC_       = b' '

OK          = OK_OP + _CRLF_
PING        = PING_OP + _CRLF_
PONG        = PONG_OP + _CRLF_
CRLF_SIZE   = len(_CRLF_)
OK_SIZE     = len(OK)
PING_SIZE   = len(PING)
PONG_SIZE   = len(PONG)
MSG_OP_SIZE = len(MSG_OP)
ERR_OP_SIZE = len(ERR_OP)

# States
AWAITING_CONTROL_LINE   = 1
AWAITING_MSG_ARG        = 2
AWAITING_MSG_PAYLOAD    = 3
AWAITING_MINUS_ERR_ARG  = 4
MAX_CONTROL_LINE_SIZE   = 1024

class Msg(object):

  def __init__(self, **params):
    self.subject = params["subject"]
    self.reply   = params["reply"]
    self.data    = params["data"]
    self.sid     = params["sid"]

class Parser(object):

  def __init__(self, nc=None):
    self.nc = nc
    self.reset()

  def __repr__(self):
    return "<nats protocol parser state={0} buflen={1} needed={2}>".format(
        self.state, len(self.buf), self.needed)

  def reset(self):
    self.buf = b''
    self.state = AWAITING_CONTROL_LINE
    self.needed = 0
    self.msg_arg = {}

  def read(self, data=''):
    """
    Read loop for gathering bytes from the server in a buffer
    of maximum MAX_CONTROL_LINE_SIZE, then received bytes are streamed
    to the parsing callback for processing.
    """
    if not self.nc.io.closed():
      self.nc.io.read_bytes(MAX_CONTROL_LINE_SIZE, callback=self.read, streaming_callback=self.parse, partial=True)

  def parse(self, data=''):
    """
    Parses the wire protocol from NATS for the client
    and dispatches the subscription callbacks.
    """
    self.buf += data
    while self.buf:
      if self.state == AWAITING_CONTROL_LINE:
        scratch = self.buf[:MAX_CONTROL_LINE_SIZE]

        # MSG
        if scratch.startswith(MSG_OP):
          self.buf = self.buf[MSG_OP_SIZE:]
          self.state = AWAITING_MSG_ARG

        # OK
        elif scratch.startswith(OK):
          self.buf = self.buf[OK_SIZE:]
          self.state = AWAITING_CONTROL_LINE

        # -ERR
        elif scratch.startswith(ERR_OP):
          self.buf = self.buf[ERR_OP_SIZE:]
          self.state = AWAITING_MINUS_ERR_ARG

        # PONG
        elif scratch.startswith(PONG):
          self.buf = self.buf[PONG_SIZE:]
          self.state = AWAITING_CONTROL_LINE
          self.nc._process_pong()

        # PING
        elif scratch.startswith(PING):
          self.buf = self.buf[PING_SIZE:]
          self.state = AWAITING_CONTROL_LINE
          self.nc._process_ping()
        else:
          break

      # -ERR 'error'
      elif self.state == AWAITING_MINUS_ERR_ARG:
        scratch = self.buf[:MAX_CONTROL_LINE_SIZE]

        i = scratch.find(_CRLF_)
        if i > 0:
          line = scratch[:i]
          _, err = line.split(_SPC_, 1)
          self.buf = self.buf[i+CRLF_SIZE:]
          self.state = AWAITING_CONTROL_LINE
          self.nc._process_err(err)
        else:
          break

      elif self.state == AWAITING_MSG_ARG:
        scratch = self.buf[:MAX_CONTROL_LINE_SIZE]

        i = scratch.find(_CRLF_)
        if i > 0:
          line = scratch[:i]
          args = line.split(_SPC_)

          # Check in case of using a queue
          args_size = len(args)
          if args_size == 5:
            self.msg_arg["subject"] = args[1]
            self.msg_arg["sid"] = int(args[2])
            self.msg_arg["reply"] = args[3]
            self.needed = int(args[4])
          elif args_size == 4:
            self.msg_arg["subject"] = args[1]
            self.msg_arg["sid"] = int(args[2])
            self.msg_arg["reply"] = b''
            self.needed = int(args[3])
          else:
            raise ErrProtocol("nats: Wrong number of arguments in MSG")
          self.buf = self.buf[i+CRLF_SIZE:]
          self.state = AWAITING_MSG_PAYLOAD
        else:
          break

      elif self.state == AWAITING_MSG_PAYLOAD:
        if len(self.buf) >= self.needed+CRLF_SIZE:
          payload = self.buf[:self.needed]
          subject = self.msg_arg["subject"]
          sid     = self.msg_arg["sid"]
          reply   = self.msg_arg["reply"]

          # Set next stage already before dispatching to callback.
          self.buf = self.buf[self.needed:]
          i = self.buf.find(MSG_END)
          if i > 0:
            self.buf = self.buf[i+1:]
            self.state = AWAITING_CONTROL_LINE
          else:
            raise ErrProtocol("nats: Wrong termination sequence for MSG")
          msg = Msg(subject=subject, sid=sid, reply=reply, data=payload)
          self.nc._process_msg(msg)
        else:
          break

class ErrProtocol(Exception):
  def __str__(self):
    return "nats: Protocol Error"
