#!/bin/sh
#
# Simple script to generate table with benchmarks.
#
# Requires running NATS server with `gnatsd -m 8225 -p 4225`
#
#
echo "*** PUB using NATS client."
echo
echo "| messages | bytes | duration | msgs/sec | max written | errors | varz in msgs| varz in bytes|"
for nbytes in 1 10 100 1000; do 
  for messages in 100 1000 10000 100000 ; do
    python examples/bench/pub.py $messages $nbytes;  2> /dev/null
  done;
done
echo
echo

echo "*** PUB using NATS client (unicode)."
echo
echo "| messages | bytes | duration | msgs/sec | max written | errors | varz in msgs| varz in bytes|"
for nbytes in 1 10 100 1000; do 
  for messages in 100 1000 10000 100000; do
    python examples/bench/pub-unicode.py $messages $nbytes;  2> /dev/null
  done;
done
echo
echo

echo "*** PUB using NATS (larger messages)."
echo
echo "| messages | bytes | duration | msgs/sec | max written | errors | varz in msgs| varz in bytes|"
for nbytes in 10000 100000 1000000; do
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

echo "*** PUB request."
echo
echo "| messages | bytes | duration | msgs/sec | max written | errors | varz in msgs| varz in bytes|"
for nbytes in 1 10 100 1000; do 
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

echo "*** Request/Response."
echo
echo "| messages | bytes |  duration | msgs/sec | max written | timeouts | errors | varz in msgs| varz in bytes|"
for nbytes in 1 10 100 1000 5000 ; do 
  for messages in 100 1000 10000 ; do
    python examples/bench/request-response.py $messages $nbytes;  2> /dev/null
  done;
done
echo
echo

echo "*** Request/Response (larger messages)"
echo
echo "| messages | bytes |  duration | msgs/sec | max written | timeouts | errors | varz in msgs| varz in bytes|"
for nbytes in 10000 20000 30000; do
  for messages in 100 200 300; do
    python examples/bench/request-response.py $messages $nbytes;  2> /dev/null
  done;
done
echo
echo

echo "*** Slow Consumer"
echo
echo "| messages | bytes |  duration | msgs/sec | max written | timeouts | errors | varz in msgs| varz in bytes|"
for nbytes in 100000; do
  for messages in 100 500 1000; do
    python examples/bench/request-response.py $messages $nbytes;  2> /dev/null
  done;
done
echo
echo

# echo "** Reference benchmarks"
# echo 
# echo "*** PUB using raw python sockets."
# echo
# echo "| messages | bytes | duration | msgs/sec | max written | broken pipe | resource unavailable | connection reset |"
# for nbytes in 1 10 100 1000 10000; do 
#   for messages in 1000 10000 100000 200000; do
#     python examples/bench/pub-raw-socket.py $messages $nbytes; 2> /dev/null
#   done;
# done
# echo
# echo

# echo "*** PUB using tornado IO."
# echo
# echo "| messages | bytes |         duration |      msgs/sec | max written | connection reset |"
# for nbytes in 1 10 100 1000 10000; do 
#   for messages in 1000 10000 100000; do
#     python examples/bench/pub-tornado-write.py $messages $nbytes;  2> /dev/null
#   done;
# done
# echo
# echo
