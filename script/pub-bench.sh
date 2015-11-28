#!/bin/sh

# Simple utility to generate table with benchmarks.

echo "*** PUB using raw python sockets, no buffered writer."
echo
echo "| messages | bytes |         duration |      msgs/sec | max written |"
for nbytes in 1 10 100 1000; do 
  for messages in 1000 10000 100000 200000; do
    python examples/bench/pub-raw-socket.py $messages $nbytes; 2> /dev/null
  done;
done
echo
echo

echo "*** PUB using tornado IO, no buffered writer."
echo
echo "| messages | bytes |         duration |      msgs/sec | max written |"
for nbytes in 1 10 100 1000; do 
  for messages in 1000 10000 100000; do
    python examples/bench/pub-tornado-write.py $messages $nbytes;  2> /dev/null
  done;
done
echo
echo

echo "*** PUB using NATS client."
echo
echo "| messages | bytes | duration | msgs/sec | max written | broken pipe | resource unavailable | connection reset | stream closed |"
for nbytes in 1 10 100 1000 10000; do 
  for messages in 100 1000 10000 100000 ; do
    python examples/bench/pub.py $messages $nbytes;  2> /dev/null
  done;
done
echo
echo

echo "*** PUB using NATS client, unicode"
echo
echo "| messages | bytes | duration | msgs/sec | max written | broken pipe | resource unavailable | connection reset | stream closed |"
for nbytes in 1 10 100 1000 10000; do 
  for messages in 100 1000 10000 100000; do
    python examples/bench/pub-unicode.py $messages $nbytes;  2> /dev/null
  done;
done
echo
echo

echo "*** PUB using NATS client with buffered writer (larger messages)."
echo
echo "| messages | bytes | duration | msgs/sec | max written | broken pipe | resource unavailable | connection reset |"
for nbytes in 100000 1000000; do
  for messages in 100 1000 10000; do
    python examples/bench/pub.py $messages $nbytes;  2> /dev/null
  done;
done

for nbytes in 5000000; do 
  for messages in 2 ; do
    python examples/bench/pub.py $messages $nbytes;  2> /dev/null
  done;
done
echo
echo

echo "*** PUB using NATS client with buffered writer and coroutine."
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
for nbytes in 1 10 100 1000 5000 ; do 
  for messages in 100 1000 10000 ; do
    python examples/bench/request-response.py $messages $nbytes;  2> /dev/null
  done;
done
echo
echo
