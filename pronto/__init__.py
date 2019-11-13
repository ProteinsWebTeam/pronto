# -*- coding: utf-8 -*-

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from flask import Flask, g, session


__version__ = "1.6.1"


class Executor(object):
    def __init__(self):
        self.executor = ThreadPoolExecutor()
        self._tasks = {}

    def enqueue(self, name, fn, *args, **kwargs):
        self.update()
        if name in self._tasks and self._tasks[name]["status"] is None:
            # Running
            return False
        else:
            self._tasks[name] = {
                "name": name,
                "future": self.submit(fn, *args, **kwargs),
                "started": datetime.now(),
                "completed": None,
                "status": None
            }
            return True

    def submit(self, fn, *args, **kwargs):
        return self.executor.submit(fn, *args, **kwargs)

    def has(self, name):
        self.update()
        return name in self._tasks

    def update(self):
        names = list(self._tasks)
        for name in names:
            task = self._tasks[name]
            future = task["future"]
            if future.done():
                now = datetime.now()
                if future.exception() is not None:
                    # Call raised: error
                    print(future.exception())
                    task["status"] = False
                elif task["completed"] is None:
                    # First time we see the task as completed
                    task["completed"] = now
                    task["status"] = True
                elif (now - task["completed"]).total_seconds() > 3600:
                    # Finished more than one hour ago: clean
                    del self._tasks[name]

    @property
    def tasks(self):
        self.update()
        tasks = []
        for task in sorted(self._tasks.values(), key=lambda t: t["started"]):
            tasks.append({
                "name": task["name"],
                "status": task["status"]
            })

        return tasks


app = Flask(__name__)
app.config.from_envvar("PRONTO_CONFIG")
app.permanent_session_lifetime = timedelta(days=7)
executor = Executor()


def get_user():
    """
    Get the user for the current request.
    """
    if not hasattr(g, "user"):
        g.user = session.get("user")
    return g.user


@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(g, "mysql_db"):
        g.mysql_db.close()

    if hasattr(g, "oracle_db"):
        g.oracle_db.close()


from . import views
