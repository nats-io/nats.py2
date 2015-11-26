#!/bin/sh

# Simple utility to generate table with benchmarks

echo "*** PUB using raw python sockets"
echo
echo "| messages | bytes |         duration |      msgs/sec | max written |"
for nbytes in 1 10 100 1000 10000; do 
  for messages in 1000 10000 100000 200000; do
    python examples/bench/pub-raw-socket.py $messages $nbytes; 2> /dev/null
  done;
done
echo
echo

echo "*** PUB using tornado IO"
echo
echo "| messages | bytes |         duration |      msgs/sec | max written |"
for nbytes in 1 10 100 1000 10000; do 
  for messages in 1000 10000 100000 200000; do
    python examples/bench/pub-tornado-write.py $messages $nbytes;  2> /dev/null
  done;
done

echo "*** PUB using NATS client"
echo
echo "| messages | bytes |         duration |      msgs/sec | max written |"
for nbytes in 1 10 100 1000 10000; do 
  for messages in 1000 10000 100000 200000; do
    python examples/bench/pub.py $messages $nbytes;  2> /dev/null
  done;
done
