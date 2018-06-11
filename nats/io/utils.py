# Copyright 2015-2018 The NATS Authors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import random

INBOX_PREFIX = "_INBOX."


def hex_rand(n):
    """
    Generates a hexadecimal string with `n` random bits.
    """
    return "%x" % random.SystemRandom().getrandbits(n)


def new_inbox():
    """
    Generates a unique _INBOX subject which can be used
    for publishing and receiving events.
    """
    return ''.join([
        INBOX_PREFIX,
        hex_rand(0x10),
        hex_rand(0x10),
        hex_rand(0x10),
        hex_rand(0x10),
        hex_rand(0x24)
    ])
