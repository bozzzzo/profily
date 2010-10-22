#!/usr/bin/env python

MODULE_NAME = "profily"
VERSION     = open("VERSION", 'r').read().strip()

try:
    from setuptools import setup, Extension
except ImportError:
    from distutils.core import setup, Extension

setup(
    name=MODULE_NAME,
    version=VERSION,
    description="a hacked profiler that shows time flow graph",
    maintainer="bozzo",
    license="Internal use only?",
    packages=[
        "profily",
    ],
    classifiers=[
        "Development Status :: 4 - Alpha",
        "Intended Audience :: bozzo",
        "Programming Language :: Python",
    ],
)
