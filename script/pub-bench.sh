#!/bin/sh

# Simple utility to generate table with benchmarks.

echo "*** PUB using raw python sockets"
echo
echo "| messages | bytes |         duration |      msgs/sec | max written |"
for nbytes in 1 10 100 1000; do 
  for messages in 1000 10000 100000 200000; do
    python examples/bench/pub-raw-socket.py $messages $nbytes; 2> /dev/null
  done;
done
echo
echo

echo "*** PUB using tornado IO"
echo
echo "| messages | bytes |         duration |      msgs/sec | max written |"
for nbytes in 1 10 100 1000; do 
  for messages in 1000 10000 100000 200000; do
    python examples/bench/pub-tornado-write.py $messages $nbytes;  2> /dev/null
  done;
done
echo
echo

echo "*** PUB using NATS client writing to socket."
echo
echo "| messages | bytes |         duration |      msgs/sec | max written |"
for nbytes in 1 10 100 1000 10000; do 
  for messages in 100 1000 10000 100000 ; do
    python examples/bench/pub.py $messages $nbytes;  2> /dev/null
  done;
done

echo "*** PUB using NATS client writing to socket (larger messages)."
echo
echo "| messages | bytes |         duration |      msgs/sec | max written |"
for nbytes in 100000 1000000 2000000; do 
  for messages in 100 1000 10000; do
    python examples/bench/pub.py $messages $nbytes;  2> /dev/null
  done;
done

for nbytes in 5000000; do 
  for messages in 100 ; do
    python examples/bench/pub.py $messages $nbytes;  2> /dev/null
  done;
done
echo
echo

echo "*** PUB using NATS client writing to socket using coroutine."
echo
echo "| messages | bytes |         duration |      msgs/sec | max written |"
for nbytes in 1 10 100 1000 10000; do 
  for messages in 100 1000 10000 ; do
    python examples/bench/pub-request.py $messages $nbytes;  2> /dev/null
  done;
done

for nbytes in 5000000; do 
  for messages in 2 ; do
    python examples/bench/pub-request.py $messages $nbytes;  2> /dev/null
  done;
done
echo
echo

echo "*** Request/Response"
echo
echo "| messages | bytes |         duration |      msgs/sec | max written | timeouts |"
for nbytes in 1 10 100 1000; do 
  for messages in 100 1000; do
    python examples/bench/request-response.py $messages $nbytes;  2> /dev/null
  done;
done
echo
echo
