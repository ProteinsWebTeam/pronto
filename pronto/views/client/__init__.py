import cx_Oracle
from flask import redirect, render_template, request, session, url_for

from pronto import app, db, get_user
from . import database, prediction, protein


@app.route("/")
def index():
    return render_template("index.html")


def connect_as_user(username, password):
    try:
        con = cx_Oracle.connect(user=username,
                                password=password,
                                dsn=app.config["ORACLE_DB"]["dsn"])
    except cx_Oracle.DatabaseError:
        return False
    else:
        con.close()
        return True


def check_user(username, password):
    con = db.get_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT USERNAME, NAME, DB_USER, IS_ACTIVE
        FROM INTERPRO.USER_PRONTO
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
            "password": password,
            "status": False
        }

        if user["active"] and connect_as_user(user["dbuser"], password):
            user["status"] = True
            cur.execute(
                """
                UPDATE INTERPRO.USER_PRONTO
                SET LAST_ACTIVITY = SYSDATE
                WHERE USERNAME = :1
                """,
                (user["username"],)
            )
            con.commit()
    else:
        user = None

    cur.close()
    return user


@app.route("/login/", methods=["GET", "POST"])
def login():
    if get_user():
        return redirect(url_for("index"))
    elif request.method == "GET":
        print(request.referrer)
        return render_template("login.html", referrer=request.referrer or "/")
    else:
        username = request.form['username'].strip().lower()
        password = request.form['password'].strip()
        user = check_user(username, password)

        if user and user["active"] and user["status"]:
            session.permanent = True
            session["user"] = user
            return redirect(request.args.get("next", url_for("index")))
        else:
            print(request.args.get("next", url_for("index")))
            return render_template(
                "login.html",
                username=username,
                error="Wrong username or password.",
                referrer=request.args.get("next", url_for("index"))
            )


@app.route("/logout/")
def logout():
    """Clear the cookie, which logs the user out."""
    session.clear()
    return redirect(request.referrer)


@app.route("/search/")
def view_search():
    return render_template("search.html")
