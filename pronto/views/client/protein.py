from flask import render_template

from pronto import app


@app.route("/protein/<accession>/")
def view_protein(accession):
    return render_template("protein.html")
