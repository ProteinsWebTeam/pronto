#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

setup(
    name="pronto",
    version="1.4.1",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "cx_Oracle>=7.0",
        "Flask>=1.0.2",
        "mysqlclient>=1.3.10"
    ],
)
