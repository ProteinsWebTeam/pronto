# -*- coding: utf-8 -*-

from flask import jsonify
from cx_Oracle import DatabaseError

from pronto import auth, utils
from . import bp


@bp.route("/<accession>/relationships/")
def get_relationships(accession):
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT 
          R.PARENT_AC, E1.NAME, E1.ENTRY_TYPE, 
          R.ENTRY_AC, E2.NAME, E2.ENTRY_TYPE
        FROM (
            SELECT PARENT_AC, ENTRY_AC
            FROM INTERPRO.ENTRY2ENTRY
            START WITH ENTRY_AC = :accession
            CONNECT BY PRIOR PARENT_AC = ENTRY_AC
            UNION ALL
            SELECT PARENT_AC, ENTRY_AC
            FROM INTERPRO.ENTRY2ENTRY
            START WITH PARENT_AC = :accession
            CONNECT BY PRIOR ENTRY_AC = PARENT_AC        
        ) R
        INNER JOIN INTERPRO.ENTRY E1 
          ON R.PARENT_AC = E1.ENTRY_AC
        INNER JOIN INTERPRO.ENTRY E2 
          ON R.ENTRY_AC = E2.ENTRY_AC
        """,
        dict(accession=accession)
    )

    parents = {}
    hierarchy = {}
    for row in cur:
        entry_acc = row[0]
        entry_name = row[1]
        entry_type = row[2]
        child_acc = row[3]
        child_name = row[4]
        child_type = row[5]

        parents[child_acc] = entry_acc

        if child_acc in hierarchy:
            child = hierarchy.pop(child_acc)
        else:
            child = {
                "accession": child_acc,
                "name": child_name,
                "type": child_type,
                "children": {},
                # can delete if query's child
                "deletable": entry_acc == accession
            }

        if entry_acc in parents:
            """
            entry_acc is itself a child of another entry: 
                find the root (oldest parent)
            """
            node_acc = entry_acc
            lineage = [node_acc]
            while node_acc in parents:
                node_acc = parents[node_acc]
                lineage.append(node_acc)

            node = None
            for node_acc in reversed(lineage):
                if node is None:
                    node = hierarchy[node_acc]
                else:
                    node = node["children"][node_acc]
        elif entry_acc in hierarchy:
            # entry_acc is root
            node = hierarchy[entry_acc]
        else:
            node = hierarchy[entry_acc] = {
                "accession": entry_acc,
                "name": entry_name,
                "type": entry_type,
                "children": {},
                # can delete if query's parent
                "deletable": child_acc == accession
            }

        node["children"][child_acc] = child

    cur.close()
    con.close()
    return jsonify(hierarchy), 200


@bp.route("/<parent_acc>/relationship/<child_acc>/", methods=["PUT"])
def add_relationship(parent_acc, child_acc):
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this operation."
            }
        }), 401

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    cur.execute(
        """
        SELECT ENTRY_AC, ENTRY_TYPE
        FROM INTERPRO.ENTRY 
        WHERE ENTRY_AC = :1 OR ENTRY_AC = :2
        """, (parent_acc, child_acc)
    )
    entries = dict(cur.fetchall())
    if parent_acc not in entries:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid entry",
                "message": f"{parent_acc} is not a valid InterPro accession."
            }
        }), 400
    elif child_acc not in entries:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid entry",
                "message": f"{child_acc} is not a valid InterPro accession."
            }
        }), 400
    elif entries[parent_acc] != entries[child_acc]:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid relationship",
                "message": f"{parent_acc} and {child_acc} do not have "
                           f"the same type."
            }
        }), 400

    cur.execute(
        """
        SELECT COUNT(*) 
        FROM INTERPRO.ENTRY2ENTRY
        WHERE PARENT_AC = :1 AND ENTRY_AC = :2
        """, (parent_acc, child_acc)
    )
    if cur.fetchone()[0]:
        cur.close()
        con.close()
        return jsonify({"status": True}), 200

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.ENTRY2ENTRY (ENTRY_AC, PARENT_AC, RELATION)
            VALUES (:1, :2, :3)
            """, (child_acc, parent_acc, "TY")
        )
    except DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": f"Could not link {parent_acc} to {child_acc}: "
                           f"{exc}."
            }
        }), 500
    else:
        con.commit()
        return jsonify({"status": True}), 200
    finally:
        cur.close()
        con.close()


@bp.route("/<accession1>/relationship/<accession2>/", methods=["DELETE"])
def delete_relationship(accession1, accession2):
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this operation."
            }
        }), 401

    con = utils.connect_oracle_auth(user)
    cur = con.cursor()
    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.ENTRY2ENTRY
            WHERE (PARENT_AC = :acc1 AND ENTRY_AC = :acc2)
            OR (PARENT_AC = :acc2 AND ENTRY_AC = :acc1)
            """,
            dict(acc1=accession1, acc2=accession2)
        )
    except DatabaseError as exc:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": f"Could not delete relationship between "
                           f"{accession1} and {accession2}: {exc}."
            }
        }), 500
    else:
        con.commit()
        return jsonify({"status": True}), 200
    finally:
        cur.close()
        con.close()
