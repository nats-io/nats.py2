from setuptools import setup
from nats.io.client import __version__

setup(
  name='nats',
  version=__version__,
  description='NATS client for Python 2',
  long_description='Python 2 client for NATS, a lightweight, high-performance cloud native messaging system',
  url='https://github.com/nats-io/python-nats',
  author='Waldemar Quevedo',
  author_email='wally@apcera.com',
  license='MIT License',
  packages=['nats'],
  install_requires=[
    'tornado',
  ],
  zip_safe=True,
)
