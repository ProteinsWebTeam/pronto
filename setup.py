#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from setuptools import setup, find_packages


def get_requires():
    path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    with open(path, "rt") as fh:
        return list(map(str.strip, fh.readlines()))


setup(
    name="pronto",
    version="2.10.0",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=get_requires(),
)
