from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from flask import Flask, g, session


class Executor(object):
    def __init__(self):
        self.executor = ThreadPoolExecutor()
        self._tasks = {}

    def submit(self, name, fn, *args, **kwargs):
        self.update()
        if name not in self._tasks:
            self._tasks[name] = {
                "name": name,
                "future": self.executor.submit(fn, *args, **kwargs),
                "started": datetime.now(),
                "terminated": None,
                "status": None
            }

    def has(self, name):
        self.update()
        return name in self._tasks

    def update(self):
        names = list(self._tasks)
        for name in names:
            task = self._tasks[name]
            future = task["future"]
            if future.done():
                if future.exception() is not None:
                    # Call raised: error
                    task["status"] = False
                elif task["terminated"] is None:
                    # First time we see the task as terminated
                    task["terminated"] = datetime.now()
                    task["status"] = True
                elif (datetime.now() - task["terminated"]).total_seconds() > 3600:
                    # Finished more than one hour ago: clean
                    del self._tasks[name]


    @property
    def tasks(self):
        self.update()
        tasks = []
        for task in sorted(self._tasks.values(), key=lambda t: t["time"]):
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
