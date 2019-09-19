#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages
from .pronto import __version__


setup(
    name="pronto",
    version=__version__,
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "cx_Oracle>=7.0",
        "Flask>=1.0.2",
        "mysqlclient>=1.3.10"
    ],
)
