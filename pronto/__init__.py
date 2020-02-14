# -*- coding: utf-8 -*-

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from flask import Flask, g, session

from pronto.db import get_oracle


__version__ = "1.6.2"


class Executor(object):
    def __init__(self):
        self.executor = ThreadPoolExecutor()
        self.running = []

    def enqueue(self, name, fn, *args, **kwargs):
        self.update()
        if self.has(name):
            return False
        else:
            con = get_oracle(require_auth=True)
            cur = con.cursor()
            cur.execute(
                """
                INSERT INTO INTERPRO.PRONTO_TASK (NAME, USERNAME, STARTED) 
                VALUES (:1, USER, SYSDATE)
                """, (name, )
            )
            con.commit()
            cur.close()
            self.running.append((name, self.submit(fn, *args, **kwargs)))
            return True

    def submit(self, fn, *args, **kwargs):
        return self.executor.submit(fn, *args, **kwargs)

    def has(self, name):
        self.update()
        cur = get_oracle().cursor()
        cur.execute(
            """
            SELECT COUNT(*)
            FROM INTERPRO.PRONTO_TASK
            WHERE NAME = :1 AND STATUS IS NULL
            """, (name,)
        )
        count, = cur.fetchone()
        cur.close()
        return count != 0

    def update(self):
        running = []
        finished = []
        for name, future in self.running:
            if future.done():
                if future.exception() is not None:
                    finished.append((name, 'N'))
                else:
                    finished.append((name, 'Y'))
            else:
                running.append((name, future))

        if finished:
            con = get_oracle(require_auth=True)
            cur = con.cursor()
            cur.executemany(
                """
                UPDATE INTERPRO.PRONTO_TASK
                SET FINISHED = SYSDATE, STATUS = :1
                WHERE NAME = :2 AND STATUS IS NULL
                """, finished
            )
            con.commit()
            cur.close()

        self.running = running

    @property
    def tasks(self):
        self.update()
        cur = get_oracle().cursor()
        cur.execute(
            """
            SELECT NAME, STATUS
            FROM INTERPRO.PRONTO_TASK
            WHERE FINISHED IS NULL 
            OR FINISHED >= SYSDATE - (1 / 24)
            ORDER BY STARTED
            """
        )
        tasks = []
        for name, status in cur:
            if status is None:
                tasks.append({"name": name, "status": None})
            else:
                tasks.append({"name": name, "status": status == 'Y'})
        cur.close()
        return tasks


app = Flask(__name__)
app.config.from_envvar("PRONTO_CONFIG")
app.permanent_session_lifetime = timedelta(days=7)
executor = Executor()


def get_user():
    """
    Get the user for the current request.
    """
    return session.get("user")


@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(g, "mysql_db"):
        g.mysql_db.close()

    if hasattr(g, "oracle_db"):
        g.oracle_db.close()


from . import views
