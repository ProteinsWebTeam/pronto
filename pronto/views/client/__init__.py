from flask import render_template

from pronto import app
from . import databases


@app.route("/")
def index():
    return render_template("index.html")
