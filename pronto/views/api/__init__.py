from flask import jsonify

from pronto import app, get_user
from . import databases, interpro, uniprot


@app.route("/api/user/")
def user():
    return jsonify({"user": get_user()})
