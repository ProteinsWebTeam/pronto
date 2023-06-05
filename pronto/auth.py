# -*- coding: utf-8 -*-

from oracledb import DatabaseError
from flask import redirect, render_template, request, session, url_for
from flask import Blueprint

from . import utils


bp = Blueprint("auth", __name__)


def get_user():
    """
    Get the user for the current request.
    """
    return session.get("user")


@bp.route("/login/", methods=["GET", "POST"])
def login():
    if get_user():
        return redirect(url_for("index"))
    elif request.method == "GET":
        return render_template("login.html", referrer=request.referrer)
    else:
        username = request.form["username"].strip().lower()
        password = request.form["password"].strip()
        user = check_user(username, password)

        if user and user["active"]:
            session["user"] = user
            return redirect(request.args.get("next", url_for("index")))
        else:
            return render_template(
                "login.html",
                username=username,
                error="Wrong username or password.",
                referrer=request.args.get("next", url_for("index"))
            )


@bp.route("/logout/")
def logout():
    """Clear the cookie, which logs the user out."""
    session.pop("user", None)
    return redirect(request.referrer)


def check_user(username, password):
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT USERNAME, NAME, DB_USER, IS_ACTIVE
        FROM INTERPRO.PRONTO_USER
        WHERE LOWER(USERNAME) = LOWER(:1)
        """,
        (username,)
    )

    row = cur.fetchone()
    if row:
        user = {
            "username": row[0],
            "name": row[1],
            "dbuser": row[2],
            "active": row[3] == 'Y',
            "password": password
        }

        try:
            con2 = utils.connect_oracle_auth(user)
        except DatabaseError:
            user = None
        else:
            con2.close()

            cur.execute(
                """
                UPDATE INTERPRO.PRONTO_USER
                SET LAST_ACTIVITY = SYSDATE
                WHERE USERNAME = :1
                """,
                (user["username"],)
            )
            con.commit()
    else:
        user = None

    cur.close()
    con.close()
    return user
