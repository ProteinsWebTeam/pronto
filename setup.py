#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup

setup(
    name='pronto',
    version='1.2.1',
    packages=['pronto'],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'cx_Oracle>=5.3',
        'Flask>=0.12.2',
        'Jinja2>=2.10'
    ],
)
