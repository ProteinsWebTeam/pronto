from cx_Oracle import DatabaseError, IntegrityError
from flask import jsonify

from pronto import app, db, get_user


@app.route("/api/entry/<parent_acc>/child/<child_acc>/", methods=["PUT"])
def add_child_relationship(parent_acc, child_acc):
    user = get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": 'Please <a href="/login/">log in</a> '
                           'to perform this operation.'
            }
        }), 401

    con = db.get_oracle()
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
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid entry",
                "message": "{} is not "
                           "a valid InterPro accession.".format(parent_acc)
            }
        }), 400
    elif child_acc not in entries:
        cur.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid entry",
                "message": "{} is not "
                           "a valid InterPro accession.".format(child_acc)
            }
        }), 400
    elif entries[parent_acc] != entries[child_acc]:
        cur.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Invalid relationship",
                "message": "{} and {} do not have the same type.".format(
                    parent_acc, child_acc
                )
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
        return jsonify({
            "status": True
        }), 200

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.ENTRY2ENTRY (ENTRY_AC, PARENT_AC, RELATION)
            VALUES (:1, :2, :3)
            """, (child_acc, parent_acc, "TY")
        )
    except (DatabaseError, IntegrityError):
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": "Could not link {} to {}.".format(parent_acc, child_acc)
            }
        }), 500
    else:
        con.commit()
        return jsonify({
            "status": True
        }), 200
    finally:
        cur.close()


@app.route("/api/entry/<acc1>/relationship/<acc2>/", methods=['DELETE'])
def delete_relationship(acc1, acc2):
    user = get_user()

    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": 'Please <a href="/login/">log in</a> '
                           'to perform this operation.'
            }
        }), 401

    con = db.get_oracle()
    cur = con.cursor()
    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.ENTRY2ENTRY
            WHERE (PARENT_AC = :acc1 AND ENTRY_AC = :acc2)
            OR (PARENT_AC = :acc2 AND ENTRY_AC = :acc1)
            """,
            dict(acc1=acc1, acc2=acc2)
        )
    except IntegrityError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": "Could not delete unlink {} and {}".format(acc1, acc2)
            }
        }), 500
    else:
        # row_count = cur.rowcount  # TODO: check that row_count == 1?
        con.commit()
        return jsonify({"status": True}), 200
    finally:
        cur.close()


@app.route("/api/entry/<accession>/relationships/")
def get_entry_relationships(accession):
    cur = db.get_oracle().cursor()

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
    return jsonify(hierarchy), 200
