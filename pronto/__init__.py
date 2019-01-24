from datetime import timedelta

from flask import Flask, g, session


app = Flask(__name__)
app.config.from_envvar("PRONTO_CONFIG")
app.permanent_session_lifetime = timedelta(days=7)


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
