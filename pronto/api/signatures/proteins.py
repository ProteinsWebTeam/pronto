# -*- coding: utf-8 -*-

import os
from tempfile import mkstemp
from flask import jsonify, request, send_file

from pronto import utils
from . import bp


@bp.route("/<path:accessions>/proteins/")
def get_proteins(accessions):
    accessions = set(utils.split_path(accessions))

    try:
        comment_id = int(request.args["comment"])
    except KeyError:
        comment_id = None
    except ValueError:
        return jsonify({
            "error": {
                "title": "Bad Request (invalid comment)",
                "message": f"{request.args['comment']} is not a number."
            }
        }), 400

    term_id = request.args.get("go")
    name_id = request.args.get("name")
    taxon_id = request.args.get("taxon")
    reviewed_only = "reviewed" in request.args
    dl_file = "file" in request.args

    try:
        exclude = set(request.args["exclude"].split(','))
    except KeyError:
        exclude = set()
    finally:
        accessions -= exclude

    try:
        page = int(request.args["page"])
    except (KeyError, ValueError):
        page = 1

    try:
        # if <= 0: all proteins are returned (with additional info)
        page_size = int(request.args["page_size"])
    except (KeyError, ValueError):
        page_size = 10

    con = utils.connect_pg()
    with con.cursor() as cur:
        taxon_name = left_num = right_num = None
        if taxon_id:
            cur.execute(
                """
                SELECT name, left_number, right_number
                FROM taxon
                WHERE id = %s
                """, (taxon_id,)
            )
            row = cur.fetchone()
            if row:
                taxon_name, left_num, right_num = row
            else:
                cur.close()
                con.close()
                return jsonify({
                    "error": {
                        "title": "Bad Request (invalid taxon)",
                        "message": f"No taxon with ID {taxon_id}."
                    }
                }), 400

        name_value = None
        if name_id is not None:
            cur.execute("SELECT text FROM protein_name WHERE name_id = %s",
                        (name_id,))
            row = cur.fetchone()
            if row:
                name_value, = row
            else:
                cur.close()
                con.close()
                return jsonify({
                    "error": {
                        "title": "Bad Request (invalid taxon)",
                        "message": f"No description with ID {name_id}."
                    }
                }), 400

        comment_value = None
        if comment_id is not None:
            cur.execute(
                """
                SELECT comment_text 
                FROM protein_similarity
                WHERE comment_id = %s
                LIMIT 1
                """, (comment_id,)
            )
            row = cur.fetchone()
            if row:
                comment_value, = row
            else:
                cur.close()
                con.close()
                return jsonify({
                    "error": {
                        "title": "Bad Request (invalid comment)",
                        "message": f"No comment with ID {comment_id}."
                    }
                }), 400

        term_name = None
        if term_id is not None:
            cur.execute("SELECT name FROM term WHERE ID = %s", (term_id,))
            row = cur.fetchone()
            if row:
                term_name, = row
            else:
                cur.close()
                con.close()
                return jsonify({
                    "error": {
                        "title": "Bad Request (invalid GO term)",
                        "message": f"No GO term with ID {term_id}."
                    }
                }), 400

        params = list(accessions)
        filters = []

        if reviewed_only:
            filters.append("is_reviewed")

        if left_num is not None:
            filters.append("taxon_left_num BETWEEN %s AND %s")
            params += [left_num, right_num]

        if name_id is not None:
            filters.append("name_id = %s")
            params.append(name_id)

        if comment_id is not None:
            filters.append("protein_acc IN (SELECT protein_acc "
                           "FROM protein_similarity "
                           "WHERE comment_id=%s)")
            params.append(comment_id)

        if term_id is not None:
            filters.append("protein_acc IN (SELECT protein_acc "
                           "FROM protein2go "
                           "WHERE term_id=%s)")
            params.append(term_id)

        base_sql = f"""
            SELECT protein_acc
            FROM (
                   SELECT protein_acc, COUNT(*) cnt
                   FROM signature2protein
                   WHERE signature_acc IN ({','.join("%s" for _ in accessions)})
                   {' AND ' + ' AND '.join(filters) if filters else ''}
                   GROUP BY protein_acc
                 ) t
            WHERE cnt = %s    
        """
        params.append(len(accessions))

        if exclude:
            base_sql += f"""
                EXCEPT
                SELECT DISTINCT protein_acc
                FROM signature2protein
                WHERE signature_acc IN ({','.join("%s" for _ in exclude)})
            """
            params += list(exclude)

        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                {base_sql}
            ) t
            """, params
        )
        cnt_proteins, = cur.fetchone()

        sql = f"""
            SELECT q.protein_acc, p.identifier, p.length, p.is_fragment, 
                   p.is_reviewed, t.name, pn.text
            FROM ({base_sql}) q
            INNER JOIN protein p ON q.protein_acc = p.accession
            INNER JOIN taxon t ON p.taxon_id = t.id
            INNER JOIN protein2name p2n ON p.accession = p2n.protein_acc
            INNER JOIN protein_name pn ON p2n.name_id = pn.name_id
            -- ORDER BY q.protein_acc
            -- ORDER BY (CASE WHEN p.is_reviewed THEN 1 ELSE 2 END), q.protein_acc
        """

        if page_size > 0:
            sql += "ORDER BY q.protein_acc LIMIT %s OFFSET %s"
            params += [page_size, (page-1)*page_size]

        cur.execute(sql, params)
        proteins = []
        for row in cur:
            proteins.append({
                "accession": row[0],
                "identifier": row[1],
                "length": row[2],
                "is_fragment": row[3],
                "is_reviewed": row[4],
                "organism": row[5],
                "name": row[6]
            })

    con.close()

    if dl_file:
        fd, filename = mkstemp()
        with os.fdopen(fd, "wt") as fp:
            fp.write("# Accession\tIdentifier\tName\tLength\tSource\t"
                     "Organism\n")

            for p in sorted(proteins, key=lambda p: p["accession"]):
                if p["is_reviewed"]:
                    src = "UniProtKB/Swiss-Prot"
                else:
                    src = "UniProtKB/TrEMBL"

                fp.write(f"{p['accession']}\t{p['identifier']}\t{p['name']}\t"
                         f"{p['length']}\t{src}\t{p['organism']}\n")

        try:
            return send_file(filename, mimetype="text/plain",
                             as_attachment=True,
                             attachment_filename="proteins.tsv")
        finally:
            os.remove(filename)

    else:
        return jsonify({
            "count": cnt_proteins,
            "results": proteins,
            "filters": {
                "comment": comment_value,
                "description": name_value,
                "exclude": list(exclude),
                "go": f"{term_id}: {term_name}" if term_name else None,
                "reviewed": reviewed_only,
                "taxon": taxon_name,
            },
            "page_info": {
                "page": page,
                "page_size": page_size
            }
        })

