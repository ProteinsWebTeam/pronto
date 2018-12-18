from flask import render_template

from pronto import app


@app.route("/signatures/<path:accessions>/proteins/")
def view_overlapping_proteins(accessions):
    return render_template("signatures/overlapping_proteins.html")


@app.route("/signatures/<path:accessions>/taxonomy/")
def view_taxonomic_origins(accessions):
    return render_template("signatures/taxonomy.html")


@app.route("/signatures/<path:accessions>/descriptions/")
def view_uniprot_descriptions(accessions):
    return render_template("signatures/descriptions.html")


@app.route("/signatures/<path:accessions>/similarity/")
def view_similarity_comments(accessions):
    return render_template("signatures/similarity.html")


@app.route("/signatures/<path:accessions>/go/")
def view_go_terms(accessions):
    return render_template("signatures/go.html")


@app.route("/signatures/<path:accessions>/matrices/")
def view_matrices(accessions):
    return render_template("signatures/matrices.html")


@app.route("/signatures/<path:accessions>/enzyme/")
def view_enzyme_entries(accessions):
    return render_template("signatures/enzyme.html")
