#!/bin/bash

export PYTHONPATH=$(pwd)

pip install --upgrade pip
pip install unittest2
pip install -r requirements.txt

python tests/client_test.py
python tests/protocol_test.py
