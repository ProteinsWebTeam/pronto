from flask import render_template

from pronto import app


@app.route("/database/<dbcode>/")
def integrated_signatures(dbcode):
    return render_template("database_integrated.html")


@app.route("/database/<dbcode>/unintegrated/")
def unintegrated_signatures(dbcode):
    return render_template("database_unintegrated.html")
