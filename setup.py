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


setup(
    name="pronto",
    version=get_version(),
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "cx_Oracle>=7.0",
        "Flask>=1.0.2",
        "mysqlclient>=1.3.10"
    ],
)
