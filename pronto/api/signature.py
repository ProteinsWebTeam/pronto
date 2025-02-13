# -*- coding: utf-8 -*-

from oracledb import DatabaseError
from flask import Blueprint, jsonify, request

from pronto import auth, utils


bp = Blueprint("api_signature", __name__, url_prefix="/api/signature")


@bp.route("/<accession>/")
def get_signature(accession):
    con = utils.connect_pg()
    cur = con.cursor()
    # description becomes short name on the front end
    # abstract becomes description on the front end
    cur.execute(
        """
        SELECT
          s.accession,
          s.name,
          s.llm_name,
          s.description,
          s.llm_description,
          s.type,
          s.abstract,
          s.llm_abstract,
          s.num_sequences,
          s.num_complete_sequences,
          s.num_reviewed_sequences,
          s.num_complete_reviewed_sequences,
          s.num_residues,
          d.name,
          d.name_long,
          d.version
        FROM signature s
        INNER JOIN database d ON s.database_id = d.id
        WHERE UPPER(s.accession) = %(str)s
          OR UPPER(s.name) = %(str)s
        """, {"str": accession.upper()}
    )
    row = cur.fetchone()
    cur.close()
    con.close()
    
    if not row:
        return jsonify({
            "error": {
                "title": "Signature not found",
                "message": f"{accession} does not match any member database signature accession or name."
            }
        }), 404
    
    if check_if_ncbifam_amr(accession):
        return jsonify(ncbifam_amr_err_msg(accession)), 400

    # data populates signature table to new entry window
    db = utils.get_database_obj(row[13])
    result = {
        "accession": row[0],
        "name": row[1],  # --> short name
        "llm_name": row[2],
        "description": row[3],
        "llm_description": row[4],  # --> name on front end
        "type": row[5],
        "abstract": row[6],
        "llm_abstract": row[7],  # --> description on front end
        "proteins": {
            "total": row[8],
            "complete": row[9],
            "reviewed": {
                "total": row[10],
                "complete": row[11]
            }
        },
        "residues": {
            "total": row[12]
        },
        "database": {
            "name": row[14],
            "home": db.home,
            "link": db.gen_link(accession),
            "color": db.color,
            "version": row[15]
        },
        "entry": None,
    }

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT E.ENTRY_AC, E.NAME, E.ENTRY_TYPE, E.CHECKED, E.LLM
        FROM INTERPRO.ENTRY2METHOD EM
        LEFT OUTER JOIN INTERPRO.ENTRY E
          ON EM.ENTRY_AC = E.ENTRY_AC
        WHERE EM.METHOD_AC = :1
        """,
        [result["accession"]]
    )
    row = cur.fetchone()

    if row:
        entry_acc = row[0]

        entry = result["entry"] = {
            "accession": entry_acc,
            "name": row[1],
            "type": row[2],
            "checked": row[3] == "Y",
            "llm": row[4] == "Y",
            "hierarchy": []
        }

        cur.execute(
            """
            SELECT E.ENTRY_AC, E.NAME, E.LLM
            FROM (
                SELECT PARENT_AC, ROWNUM RN
                FROM INTERPRO.ENTRY2ENTRY
                START WITH ENTRY_AC = :1
                CONNECT BY PRIOR PARENT_AC = ENTRY_AC
            ) H
            INNER JOIN INTERPRO.ENTRY E ON H.PARENT_AC = E.ENTRY_AC
            ORDER BY H.RN DESC
            """,
            [entry_acc]
        )

        for row in cur.fetchall():
            entry["hierarchy"].append({
                "accession": row[0],
                "name": row[1],
                "llm": row[2] == "Y"
            })

    cur.close()
    con.close()

    return jsonify(result)


@bp.route("/<accession>/comments/")
def get_signature_comments(accession):
    try:
        n = int(request.args["max"])
    except (KeyError, ValueError):
        n = 0

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT C.ID, C.VALUE, C.CREATED_ON, C.STATUS, U.NAME
        FROM INTERPRO.METHOD_COMMENT C
        INNER JOIN INTERPRO.PRONTO_USER U 
          ON C.USERNAME = U.USERNAME
        WHERE C.METHOD_AC = :1
        ORDER BY C.CREATED_ON DESC
        """,
        [accession]
    )
    comments = [
        {
            "id": row[0],
            "text": row[1],
            "date": row[2].strftime("%d %b %Y at %H:%M"),
            "status": row[3] == "Y",
            "author": row[4],
            "accession": accession,
        } for row in cur
    ]
    cur.close()
    con.close()

    return jsonify({
        "count": len(comments),
        "results": comments[:n] if n else comments
    })


@bp.route("/<accession>/comment/", methods=["PUT"])
def add_signature_comment(accession):
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401

    content = request.get_json()
    text = content.get("text", "")
    if len(text) < 3:
        return jsonify({
            "status": False,
            "error": {
                "title": "Bad request",
                "message": "Comment too short (must be at least "
                           "three characters long)."
            }
        }), 400

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    cur.execute(
        """
        SELECT MAX(ID)
        FROM INTERPRO.METHOD_COMMENT
        """
    )
    max_id = cur.fetchone()[0]
    next_id = max_id + 1 if max_id else 1

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.METHOD_COMMENT (
              ID, METHOD_AC, USERNAME, VALUE
            )
            VALUES (:1, :2, :3, :4)
            """,
            (next_id, accession, user["username"], text)
        )
    except DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": str(exc)
            }
        }), 500
    else:
        con.commit()
        return jsonify({"status": True}), 200
    finally:
        cur.close()
        con.close()


@bp.route("/<accession>/comment/<commentid>/", methods=["DELETE"])
def delete_signature_comment(accession, commentid):
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    try:
        cur.execute(
            """
            UPDATE INTERPRO.METHOD_COMMENT 
            SET STATUS = 'N' 
            WHERE METHOD_AC = :1 AND ID = :2
            """,
            (accession, commentid)
        )
    except DatabaseError as e:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": str(e)
            }
        }), 500
    else:
        con.commit()
        return jsonify({"status": True}), 200
    finally:
        cur.close()
        con.close()


@bp.route("/<accession>/go/<term_id>/")
def get_term_citations(accession, term_id):
    con = utils.connect_pg()
    with con.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, published
            FROM publication
            WHERE id IN (
                SELECT DISTINCT ref_db_id
                FROM protein2go
                WHERE term_id = %s
                AND protein_acc IN (
                    SELECT DISTINCT protein_acc
                    FROM signature2protein
                    WHERE signature_acc = %s
                )
                AND ref_db_code = 'PMID'
            )
            ORDER BY published
            """, [term_id, accession]
        )

        results = []
        for row in cur:
            results.append({
                "id": row[0],
                "title": row[1],
                "date": row[2].strftime("%d %b %Y")
            })

    con.close()

    return jsonify({
        "count": len(results),
        "results": results
    })


@bp.route("/<accession>/go/<term_id>/subfam")
def get_signature_go_info(accession, term_id):
    if accession.startswith("PTHR"):
        return get_panther_go_subfam(accession, term_id)
    elif accession.startswith("G3DSA"):
        return get_funfam_go(accession, term_id)
    else:
        return jsonify({
            "error": {
                "title": "Invalid signature",
                "message": "Only CATH-Gene3D and PANTHER signatures "
                           "have subfamilies."
            }
        }), 400


def get_panther_go_subfam(accession: str, term_id: str):

    pg_con = utils.connect_pg()
    with pg_con.cursor() as pg_cur:

        sql = """
            SELECT DISTINCT model_acc, protein_acc
            FROM interpro.signature2protein
            WHERE signature_acc = %s
        """
        pg_cur.execute(sql, (accession,))
        matches = {}
        count_prot = 0
        for row in pg_cur.fetchall():
            count_prot += 1
            try:
                matches[row[0]] += 1
            except KeyError:
                matches[row[0]] = 1

    pg_con.close()

    con = utils.connect_oracle()
    cur = con.cursor()
    binds = [":" + str(i+1) for i in range(len(matches))]
    params = list(matches.keys()) + [term_id]
    cur.execute(
        f""" 
        SELECT DISTINCT SUBFAMILY_AC
        FROM INTERPRO.PANTHER2GO
        WHERE SUBFAMILY_AC IS NOT NULL
          AND SUBFAMILY_AC IN ({','.join(binds)}) 
          AND GO_ID = :go_id
        """,
        params
    )

    results = {acc: matches[acc] for acc, in cur.fetchall()}
    cur.close()
    con.close()

    return jsonify({
        "count": count_prot,
        "results": results
    })


def get_funfam_go(accession, term_id):

    pg_con = utils.connect_pg()
    with pg_con.cursor() as pg_cur:

        sql = """
            SELECT count(protein_acc)
            FROM interpro.signature2protein
            WHERE signature_acc = %s
        """
        pg_cur.execute(sql, (accession,))
        count_prot = pg_cur.fetchone()[0]

    pg_con.close()

    con = utils.connect_oracle()
    cur = con.cursor()

    cur.execute(
        f""" 
        SELECT METHOD_AC, count(PROTEIN_AC)
        FROM INTERPRO.FUNFAM2GO
        WHERE METHOD_AC LIKE :gene3d
          AND GO_ID = :go_id
        GROUP BY METHOD_AC
        """,
        (f"{accession}%", term_id)
    )

    results = dict(cur.fetchall())
    cur.close()
    con.close()

    return jsonify({
        "count": count_prot,
        "results": results
    })


@bp.route("/<accession>/predictions/")
def get_signature_predictions(accession):
    all_collocations = "all" in request.args

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT EM.METHOD_AC, E.ENTRY_AC, E.ENTRY_TYPE, E.NAME, E.CHECKED, E.LLM
        FROM INTERPRO.ENTRY2METHOD EM
        INNER JOIN INTERPRO.ENTRY E ON EM.ENTRY_AC = E.ENTRY_AC
        """
    )
    integrated = {row[0]: row[1:] for row in cur}

    if accession in integrated:
        query_entry = integrated[accession][0]

        # Get ancestors
        cur.execute(
            """
            SELECT PARENT_AC
            FROM INTERPRO.ENTRY2ENTRY
            START WITH ENTRY_AC = :1
            CONNECT BY PRIOR PARENT_AC = ENTRY_AC
            """, [query_entry]
        )
        ancestors = {row[0] for row in cur}

        # Get descendants
        cur.execute(
            """
            SELECT ENTRY_AC
            FROM INTERPRO.ENTRY2ENTRY
            START WITH PARENT_AC = :1
            CONNECT BY PRIOR ENTRY_AC = PARENT_AC
            """, [query_entry]
        )
        descendants = {row[0] for row in cur}
    else:
        query_entry = None
        ancestors = set()
        descendants = set()

    # Get (child -> parent) and (parent -> children) relationships
    cur.execute("SELECT ENTRY_AC, PARENT_AC FROM INTERPRO.ENTRY2ENTRY")
    parent_of = {}
    children_of = {}
    for child_acc, parent_acc in cur:
        parent_of[child_acc] = parent_acc
        try:
            children_of[parent_acc].append(child_acc)
        except KeyError:
            children_of[parent_acc] = [child_acc]
    cur.close()
    con.close()

    con = utils.connect_pg()
    cur = con.cursor()
    cur.execute(
        """
        SELECT num_complete_sequences, num_residues
        FROM interpro.signature
        WHERE accession = %s
        """, [accession]
    )
    q_proteins, q_residues = cur.fetchone()

    if all_collocations:
        cur.execute(
            """
            SELECT
              c.signature_acc_2,
              s.num_complete_sequences,
              s.num_residues,
              d.name,
              d.name_long,
              c.num_collocations,
              c.num_overlaps,
              COALESCE(p.num_residue_overlaps, 0),
              c.num_reviewed_res_overlaps
            FROM interpro.comparison c
            INNER JOIN interpro.signature s
              ON c.signature_acc_2 = s.accession
            INNER JOIN interpro.database d
              ON s.database_id = d.id
            LEFT OUTER JOIN interpro.prediction p
              ON (c.signature_acc_1 = p.signature_acc_1
                  AND c.signature_acc_2 = p.signature_acc_2)
            WHERE c.signature_acc_1 = %s
            """, [accession]
        )
    else:
        cur.execute(
            """
            SELECT
              p.signature_acc_2,
              s.num_complete_sequences,
              s.num_residues,
              d.name,
              d.name_long,
              p.num_collocations,
              p.num_protein_overlaps,
              p.num_residue_overlaps,
              c.num_reviewed_res_overlaps
            FROM interpro.prediction p
            INNER JOIN interpro.signature s
              ON p.signature_acc_2 = s.accession
            INNER JOIN interpro.database d
              ON s.database_id = d.id
            INNER JOIN interpro.comparison c
              on (c.signature_acc_1 = p.signature_acc_1
                  AND c.signature_acc_2 = p.signature_acc_2)
            WHERE p.signature_acc_1 = %s
            """, [accession]
        )

    targets = {}
    for row in cur:
        t_acc = row[0]
        t_proteins = row[1]
        t_residues = row[2]
        db_key = row[3]
        db_name = row[4]
        collocations = row[5]
        protein_overlaps = row[6]
        residue_overlaps = row[7]
        reviewed_res_overlaps = row[8]

        p = utils.Prediction(q_proteins, t_proteins, protein_overlaps)
        if p.relationship is None and not all_collocations:
            continue

        pr = utils.Prediction(q_residues, t_residues, residue_overlaps)

        try:
            obj = integrated[t_acc]
        except KeyError:
            entry = None
        else:
            entry = {
                "accession": obj[0],
                "type": obj[1],
                "name": obj[2],
                "checked": obj[3] == "Y",
                "llm": obj[4] == "Y"
            }

        database = utils.get_database_obj(db_key)
        targets[t_acc] = {
            "accession": t_acc,
            "database": {
                "name": db_name,
                "color": database.color,
                "link": database.gen_link(t_acc)
            },
            "proteins": t_proteins,
            "collocations": collocations,
            "overlaps": protein_overlaps,
            "similarity": p.similarity,
            "containment": p.containment,
            "relationship": p.relationship,
            "entry": entry,
            "residues": {
                "similarity": pr.similarity,
                "containment": pr.containment,
                "relationship": pr.relationship,
                "overlaps": residue_overlaps,
                "reviewed_overlaps": reviewed_res_overlaps
            }
        }
    cur.close()
    con.close()

    """
    Sort to have in first position predictions integrated in entries
    related to entry containing the query signature
    """
    sort_obj = Sorter(query_entry, ancestors, descendants)
    results = []
    for s in sorted(targets.values(), key=sort_obj.digest):
        if s["entry"]:
            entry_acc = s["entry"]["accession"]
            hierarchy = []

            while entry_acc in parent_of:
                entry_acc = parent_of[entry_acc]
                hierarchy.append(entry_acc)

            # Transform child -> parent into parent -> child
            s["entry"]["hierarchy"] = hierarchy[::-1]

        results.append(s)

    return jsonify(results)


class Sorter(object):
    def __init__(self, query_entry: str, ancestors: set, descendants: set):
        self.entry = query_entry
        self.ancestors = ancestors
        self.descendants = descendants

    def digest(self, obj: dict):
        i = 3
        if obj["entry"]:
            entry_acc = obj["entry"]["accession"]
            if entry_acc in self.ancestors:
                i = 0
            elif entry_acc == self.entry:
                i = 1
            elif entry_acc in self.descendants:
                i = 2

        rel = obj["relationship"]
        if rel in ("similar", "related"):
            j = 0
            key = "similarity"
        elif rel == "parent":
            j = 1
            key = "containment"
        elif rel == "child":
            j = 2
            key = "containment"
        else:
            j = 3
            key = "similarity"

        return i, j, -obj["residues"][key], -obj[key]


def check_if_ncbifam_amr(accession: str) -> bool:

    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM INTERPRO.NCBIFAM_AMR
        WHERE METHOD_AC = :1
        """,
        [accession]
    )

    cnt, = cur.fetchone()
    return cnt > 0


def ncbifam_amr_err_msg(accession: str) -> dict:
    return {
        "status": False,
            "error": {
                "title": "Can't integrate signature",
                "message": f"{accession} is an NCBIfam AMR model."
            }
        }
