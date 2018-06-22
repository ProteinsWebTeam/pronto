#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import timedelta

from flask import Flask

app = Flask(__name__)
app.config.from_envvar('PRONTO_CONFIG')
app.permanent_session_lifetime = timedelta(days=7)

from . import views
