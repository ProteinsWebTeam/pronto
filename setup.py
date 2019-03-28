#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

setup(
    name="pronto",
    version="1.3.1",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "cx_Oracle>=6.0.2",
        "Flask>=0.12.2",
        "mysqlclient>=1.3.10"
    ],
)
