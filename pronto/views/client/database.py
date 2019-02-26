from flask import render_template

from pronto import app


@app.route("/database/<dbcode>/")
def view_db_signatures(dbcode):
    return render_template("member_database/all.html")


@app.route("/database/<dbcode>/unintegrated/<mode>/")
def view_db_unintegrated_signatures(dbcode, mode):
    return render_template("member_database/unintegrated.html")
