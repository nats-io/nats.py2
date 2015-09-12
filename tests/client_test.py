import sys

if sys.version_info >= (2, 7):
     import unittest
else:
    import unittest2 as unittest

from nats.io.client import Client, __version__
from nats.protocol.parser import *

class ClientTest(unittest.TestCase):

    def test_default_connect_command(self):
        nc = Client()
        nc.options["verbose"] = False
        nc.options["pedantic"] = False
        nc.options["auth_required"] = False
        got = nc.connect_command()
        expected = 'CONNECT {"lang": "python2", "pedantic": false, "verbose": false, "version": "%s"}\r\n' % __version__
        self.assertEqual(expected, got)

    @unittest.skip("Implement as an async test")
    def test_parse_info(self):
        data = b'INFO {"server_id":"eec6c3","version":"0.6.6","go":"go1.4.2","host":"0.0.0.0","port":4222,"auth_required":false,"ssl_required":false,"max_payload":1048576}\r\n'

if __name__ == '__main__':
    runner = unittest.TextTestRunner(stream=sys.stdout)
    unittest.main(verbosity=1, exit=False, testRunner=runner)
