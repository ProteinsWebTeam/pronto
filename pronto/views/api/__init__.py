from flask import jsonify

from pronto import app, get_user
from . import databases, entry, interpro, signature, uniprot


@app.route("/api/user/")
def user():
    return jsonify({"user": get_user()})
