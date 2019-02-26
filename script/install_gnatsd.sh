#!/bin/bash

set -e

export DEFAULT_NATS_SERVER_VERSION=v1.4.1
export NATS_SERVER_VERSION="${NATS_SERVER_VERSION:=$DEFAULT_NATS_SERVER_VERSION}"

# check to see if gnatsd folder is empty
if [ ! "$(ls -A $HOME/gnatsd)" ]; then
    (
	mkdir -p $HOME/gnatsd
	cd $HOME/gnatsd
	wget https://github.com/nats-io/gnatsd/releases/download/$NATS_SERVER_VERSION/gnatsd-$NATS_SERVER_VERSION-linux-amd64.zip -O gnatsd.zip
	unzip gnatsd.zip
	mv gnatsd-$NATS_SERVER_VERSION-linux-amd64/gnatsd .
    )
else
  echo 'Using cached directory.';
fi
