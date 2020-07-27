#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from setuptools import setup, find_packages


def get_version():
    path = os.path.join(os.path.dirname(__file__), "pronto", "__init__.py")
    with open(path, "rt") as fh:
        for line in fh:
            if line.startswith("__version__"):
                return line.split('=', 1)[1].strip().replace('"', '')


def get_requires():
    path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    with open(path, "rt") as fh:
        return list(map(str.strip, fh.readlines()))


setup(
    name="pronto",
    version=get_version(),
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=get_requires(),
)
