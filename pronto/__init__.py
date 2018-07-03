#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import timedelta

from flask import Flask

from pronto import filters

app = Flask(__name__)
app.config.from_envvar('PRONTO_CONFIG')
app.permanent_session_lifetime = timedelta(days=7)
app.jinja_env.filters['wordat'] = filters.word_at
app.jinja_env.filters['numentries'] = filters.count_entries
app.jinja_env.filters['nummethods'] = filters.count_methods

from . import views
