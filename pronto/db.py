#!/usr/bin/env python
# -*- coding: utf-8 -*-

import cx_Oracle
import MySQLdb
from flask import g

from pronto import app, get_user


def get_mysql_db():
    if not hasattr(g, "mysql_db"):
        g.mysql_db = MySQLdb.connect(**app.config["MYSQL_DB"])

    return g.mysql_db


def connect_oracle(user, dsn):
    if isinstance(user, dict):
        con_str = user["dbuser"] + "/" + user["password"]
    else:
        con_str = user
    url = con_str + '@' + dsn
    return cx_Oracle.connect(url, encoding="utf-8", nencoding="utf-8")


def get_oracle(require_auth=False):
    """
    Opens a new database connection if there is none yet
    for the current application context.
    """
    if not hasattr(g, "oracle_db"):
        user = get_user()
        if user:
            credentials = user["dbuser"] + "/" + user["password"]
        elif not require_auth:
            credentials = app.config["ORACLE_DB"]["credentials"]
        else:
            raise RuntimeError()

        url = credentials + "@" + app.config["ORACLE_DB"]["dsn"]
        g.oracle_db = cx_Oracle.connect(url, encoding="utf-8",
                                        nencoding="utf-8")

    return g.oracle_db
