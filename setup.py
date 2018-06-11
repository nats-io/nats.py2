import os
from setuptools import setup, find_packages
from nats import __version__

this_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(this_dir, 'requirements.txt')) as f:
    requirements = f.read().splitlines()

setup(
    name='nats-client',
    version=__version__,
    description='NATS client for Python 2',
    long_description=
    'Tornado based Python client for NATS, a lightweight, high-performance cloud native messaging system',
    url='https://github.com/nats-io/python-nats',
    author='Waldemar Quevedo',
    author_email='wally@synadia.com',
    license='Apache 2.0 License',
    packages=['nats', 'nats.io', 'nats.protocol'],
    install_requires=requirements,
    zip_safe=True,
    classifiers=[
        'Intended Audience :: Developers',
        'Programming Language :: Python',
    ])
