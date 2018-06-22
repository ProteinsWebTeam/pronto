#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import re
import urllib.parse
import urllib.request
from datetime import timedelta

import cx_Oracle
from flask import Flask, g, jsonify, request, session, redirect, render_template, url_for

import xref

app = Flask(__name__)
app.config.from_envvar('PRONTO_CONFIG')
app.permanent_session_lifetime = timedelta(days=7)


# TODO: do not hardcode INTERPRO schema, but use synonyms (e.g. MV_ENTRY2PROTEIN is not a synonym yet)
# todo: refactoring: do not use functions if only called once


def get_latest_entries(n):
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT E.ENTRY_AC, MIN(E.ENTRY_TYPE), MIN(E.SHORT_NAME), MIN(U.NAME), MIN(CREATED), COUNT(PROTEIN_AC)
        FROM (
          SELECT ENTRY_AC, ENTRY_TYPE, SHORT_NAME, USERSTAMP, CREATED
          FROM INTERPRO.ENTRY
          WHERE ROWNUM <= :1
          ORDER BY ENTRY_AC DESC
        ) E
        INNER JOIN INTERPRO.USER_PRONTO U ON E.USERSTAMP = U.DB_USER
        LEFT OUTER JOIN INTERPRO.MV_ENTRY2PROTEIN E2P ON E.ENTRY_AC = E2P.ENTRY_AC
        GROUP BY E.ENTRY_AC
        """,
        (n,)
    )

    entries = []
    for row in cur:
        entries.append({
            'id': row[0],
            'type': row[1],
            'shortName': row[2],
            'user': row[3].split()[0],
            'timestamp': row[4].timestamp(),
            'count': row[5]
        })

    cur.close()

    return entries



def get_topics():
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT TOPIC_ID, TOPIC
        FROM {}.CV_COMMENT_TOPIC
        ORDER BY TOPIC
        """.format(app.config['DB_SCHEMA'])
    )

    topics = [dict(zip(('id', 'value'), row)) for row in cur]
    cur.close()

    return topics








def get_db():
    """
    Opens a new database connection if there is none yet for the current application context.
    """

    if not hasattr(g, 'oracle_db'):
        user = get_user()
        try:
            credentials = user['dbuser'] + '/' + user['password']
        except (TypeError, KeyError):
            credentials = app.config['DATABASE_USER']
        finally:
            uri = credentials + '@' + app.config['DATABASE_HOST']

        g.oracle_db = cx_Oracle.connect(uri, encoding='utf-8', nencoding='utf-8')
    return g.oracle_db


@app.teardown_appcontext
def close_db(error):
    """
    Closes the database at the end of the request.
    """

    if hasattr(g, 'oracle_db'):
        g.oracle_db.close()


def get_user():
    """
    Get the user for the current request.
    """

    if not hasattr(g, 'user'):
        g.user = session.get('user')
    return g.user


def verify_user(username, password):
    """
    Authenticates a user with the provided credentials.
    """

    # Check the user account exists and is active
    con1 = get_db()
    cur = con1.cursor()
    cur.execute(
        """
        SELECT USERNAME, NAME, DB_USER, IS_ACTIVE FROM INTERPRO.USER_PRONTO WHERE LOWER(USERNAME) = :1
        """,
        (username.lower(), )
    )

    row = cur.fetchone()

    if not row:
        user = None
    else:
        username, name, db_user, is_active = row
        is_active = is_active == 'Y'

        user = {
            'username': username,
            'name': name,
            'dbuser': db_user,
            'active': is_active,
            'password': password,
            'status': False
        }

        if is_active:
            try:
                con2 = cx_Oracle.connect(
                    user=db_user,
                    password=password,
                    dsn=app.config['DATABASE_HOST']
                )
            except cx_Oracle.DatabaseError:
                pass
            else:
                con2.close()
                user['status'] = True

                # Update user activity
                cur.execute(
                    """
                    UPDATE INTERPRO.USER_PRONTO
                    SET LAST_ACTIVITY = SYSDATE
                    WHERE USERNAME = :1
                    """,
                    (username,)
                )

                con1.commit()

    cur.close()

    return user


def login_required(f):
    """
    Decorator for endpoints that require users to be logged in
    """
    def wrap(*args, **kwargs):
        if get_user():
            return f(*args, **kwargs)
        return redirect(url_for('log_in', next=request.url))

    return wrap


@app.route('/')
def index():
    """Home page."""
    return render_template('main.html', user=get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/login', methods=['GET', 'POST'])
def log_in():
    """Login page. Display a form on GET, and test the credentials on POST."""
    if get_user():
        return redirect(url_for('index'))
    elif request.method == 'GET':
        return render_template('login.html', referrer=request.referrer)
    else:
        username = request.form['username'].strip().lower()
        password = request.form['password'].strip()
        user = verify_user(username, password)

        if user and user['active'] and user['status']:
            session.permanent = True
            session['user'] = user
            return redirect(request.args.get('next', url_for('index')))
        else:
            msg = 'Wrong username or password.'
            return render_template(
                'login.html',
                username=username,
                error=msg,
                referrer=request.args.get('next', url_for('index'))
            )


@app.route('/logout/')
def log_out():
    """Clear the cookie, which logs the user out."""
    session.clear()
    return redirect(request.referrer)


@app.route('/db/<dbshort>/')
def view_db(dbshort):
    return render_template('main.html', user=get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/entry/<entry_ac>/')
def view_entry(entry_ac):
    return render_template('main.html', user=get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/protein/<protein_ac>/')
def view_protein(protein_ac):
    return render_template('main.html', user=get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/method/<method_ac>/')
def view_method(method_ac):
    return render_template('main.html', user=get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/methods/<path:methods>/matches/')
@app.route('/methods/<path:methods>/taxonomy/')
@app.route('/methods/<path:methods>/descriptions/')
@app.route('/methods/<path:methods>/comments/')
@app.route('/methods/<path:methods>/go/')
@app.route('/methods/<path:methods>/matrices/')
@app.route('/methods/<path:methods>/enzymes/')
def view_compare(methods):
    return render_template('main.html', user=get_user(), topics=get_topics(), schema=app.config['DB_SCHEMA'])


@app.route('/search/')
def view_search():
    return render_template('main.html', user=get_user(), schema=app.config['DB_SCHEMA'])

















def has_overlaping_matches(matches1, matches2, min_overlap=0.5):
    for m1 in matches1:
        l1 = m1[1] - m1[0]
        for m2 in matches2:
            l2 = m2[1] - m2[0]
            overlap = min(m1[1], m2[1]) - max(m1[0], m2[0])

            if overlap >= l1 * min_overlap or overlap >= l2 * min_overlap:
                return True

    return False











if __name__ == '__main__':
    app.run()

