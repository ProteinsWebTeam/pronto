from flask import render_template

from pronto import app


@app.route("/prediction/<accession>/")
def view_prediction(accession):
    return render_template("prediction.html")
