from flask import render_template

from pronto import app


@app.route("/signatures/<path:accessions>/proteins/")
def view_overlapping_proteins(accessions):
    return render_template("signatures/overlapping_proteins.html")

