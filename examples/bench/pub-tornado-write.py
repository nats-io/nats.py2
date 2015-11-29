import socket
import time
import sys
import tornado.gen
import tornado.ioloop
import tornado.iostream

class Client(object):

    def __init__(self):
        self.total_written = 0
        self.socket = None
        self.io = None
        self.start_time = None
        self.end_time = None
        self.max_messages = 0
        self.connection_reset = 0

    def disconnected(self):
        self.connection_reset += 1

@tornado.gen.coroutine
def go():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setblocking(0)
    s.settimeout(1.0)

    nc = Client()
    nc.socket = s
    nc.io = tornado.iostream.IOStream(s)
    yield nc.io.connect(("127.0.0.1", 4225))
    nc.io.set_close_callback(nc.disconnected)
    yield nc.io.write("CONNECT {\"lang\":\"tornado\"}\r\n")

    try:
        max_messages = sys.argv[1]
    except:
        max_messages = 100000

    try:
        bytesize = sys.argv[2]
    except:
        bytesize = 1

    nc.start_time = time.time()
    nc.max_messages = int(max_messages)
    line = "A" * int(bytesize)

    # print("Sending {0} messages of {1} bytes".format(nc.max_messages, bytesize))
    try:
        for i in range(nc.max_messages):
            nc.total_written += 1
            nc.io.write("PUB help  {0}\r\n{1}\r\n".format(bytesize, line))
    except Exception, e:
        pass
    finally:
        nc.end_time = time.time()

    nc.end_time = time.time()
    duration = nc.end_time - nc.start_time
    rate = nc.max_messages / duration
    print("|{0}|{1}|{2}|{3}|{4}|{5}|".format(max_messages, bytesize, duration, rate, nc.total_written, nc.connection_reset))

if __name__ == '__main__':
    tornado.ioloop.IOLoop.instance().run_sync(go)
