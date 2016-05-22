from setuptools import setup, find_packages
from nats import __version__

setup(
    name='nats-client',
    version=__version__,
    description='NATS client for Python 2',
    long_description='Tornado based Python client for NATS, a lightweight, high-performance cloud native messaging system',
    url='https://github.com/nats-io/python-nats',
    author='Waldemar Quevedo',
    author_email='wally@apcera.com',
    license='MIT License',
    packages=['nats', 'nats.io', 'nats.protocol'],
    install_requires=['tornado==4.2'],
    zip_safe=True,
    classifiers=[
        'Intended Audience :: Developers',
        'Programming Language :: Python',
    ]
)
