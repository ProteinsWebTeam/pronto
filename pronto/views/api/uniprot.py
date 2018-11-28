from flask import jsonify

from pronto import app
from pronto.db import get_oracle


@app.route("/api/uniprot/version/")
def uniprot_version():
    cur = get_oracle().cursor()
    cur.execute(
        """
        SELECT VERSION
        FROM {}.CV_DATABASE
        WHERE DBCODE = 'u'
        """.format(app.config["DB_SCHEMA"])
    )
    row = cur.fetchone()
    cur.close()
    return jsonify({"version": row[0]})
