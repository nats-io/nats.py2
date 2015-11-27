import socket
import time
import sys

class Client(object):

    def __init__(self):
        self.total_written = 0
        self.socket = None
        self.io = None
        self.start_time = None
        self.end_time = None
        self.max_messages = 0

    def disconnected(self):
        print("Disconnected after writing: ", self.total_written)

def go():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setblocking(0)
    s.settimeout(10.0)

    nc = Client()
    nc.socket = s
    nc.socket.connect(("127.0.0.1", 4225))
    nc.socket.sendall("CONNECT {\"lang\":\"raw-python\"}\r\n")

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
            nc.socket.sendall("PUB help  {0}\r\n{1}\r\n".format(bytesize, line))
    finally:
        nc.end_time = time.time()

    duration = nc.end_time - nc.start_time
    rate = nc.max_messages / duration

    # print("Finished sending {0} messages in {1}".format(nc.max_messages, duration))
    # print("Publishing rate: {0} msgs/sec".format(rate))
    print("|{0}|{1}|{2}|{3}|{4}|".format(max_messages, bytesize, duration, rate, nc.total_written))

if __name__ == '__main__':
    go()
