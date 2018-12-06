from flask import render_template

from pronto import app


@app.route("/database/<dbcode>/")
def view_integrated_signatures(dbcode):
    return render_template("database_integrated.html")


@app.route("/database/<dbcode>/unintegrated/<mode>/")
def view_unintegrated_signatures(dbcode, mode):
    return render_template("database_unintegrated.html")
