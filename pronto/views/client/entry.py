from flask import render_template

from pronto import app


@app.route("/entry/<accession>/")
def view_entry(accession):
    return render_template("entry.html")
