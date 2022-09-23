from datetime import timedelta

from flask import Flask, render_template

from . import api
from . import auth

__version__ = "2.4.0"


app = Flask(__name__)
app.config.from_envvar("PRONTO_CONFIG")
app.permanent_session_lifetime = timedelta(days=7)
app.url_map.strict_slashes = True


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/checks/")
def checks_settings():
    return render_template("checks.html")


@app.route("/database/<identifier>/")
def member_database(identifier):
    return render_template("database/signatures.html")


@app.route("/entry/<accession>/")
def entry(accession):
    return render_template("entry.html")


@app.route("/database/<identifier>/unintegrated/")
def member_database_unintegrated(identifier):
    return render_template("database/unintegrated.html")


@app.route("/protein/<accession>/")
def protein(accession):
    return render_template("protein.html")


@app.route("/search/")
def view_search():
    return render_template("search.html")


@app.route("/signature/<accession>/")
def signature(accession):
    return render_template("signature.html")


@app.route("/signatures/compare/")
def compare_signatures():
    return render_template("signatures/boilerplate.html", page="compare")


@app.route("/signatures/recommendations/")
def closest_signatures():
    return render_template("signatures/boilerplate.html",
                           page="recommendations")


@app.route("/signatures/<path:accessions>/comments/")
def comments(accessions):
    return render_template("signatures/comments.html")


@app.route("/signatures/<path:accessions>/descriptions/")
def descriptions(accessions):
    return render_template("signatures/descriptions.html")


@app.route("/signatures/<path:accessions>/go/")
def go(accessions):
    return render_template("signatures/go.html")


@app.route("/signatures/<path:accessions>/matrices/")
def matrices(accessions):
    return render_template("signatures/matrices.html")


@app.route("/signatures/<path:accessions>/proteins/")
def proteins(accessions):
    return render_template("signatures/proteins.html")


@app.route("/signatures/<path:accessions>/taxonomy/<rank>/")
def sig_taxonomy(accessions, rank):
    return render_template("signatures/taxonomy.html")


@app.route("/taxon/")
def taxon():
    return render_template("taxon.html")

@app.route("/proteome/")
def proteome():
    return render_template("proteome.html")

for bp in api.blueprints:
    app.register_blueprint(bp)

app.register_blueprint(auth.bp)
