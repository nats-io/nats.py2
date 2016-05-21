#!/bin/bash

export PYTHONPATH=$(pwd)

pip install --upgrade pip
pip install unittest2
pip install -r requirements.txt

python tests/test.py
