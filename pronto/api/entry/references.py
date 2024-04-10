# -*- coding: utf-8 -*-

from flask import jsonify
from oracledb import DatabaseError

from pronto import auth, utils
from ..annotation import get_citations, insert_citations
from . import bp


@bp.route("/<accession>/references/")
def get_suppl_references(accession):
    con = utils.connect_oracle()
    cur = con.cursor()
    cur.execute(
        """
        SELECT 
          S.PUB_ID, C.TITLE, C.YEAR, C.VOLUME, C.ISSUE, C.RAWPAGES, C.DOI_URL,
          C.PUBMED_ID, C.ISO_JOURNAL, C.MEDLINE_JOURNAL, C.AUTHORS
        FROM INTERPRO.SUPPLEMENTARY_REF S
        INNER JOIN INTERPRO.CITATION C
        ON S.PUB_ID = C.PUB_ID
        WHERE S.ENTRY_AC = :1      
        """, (accession,)
    )
    references = []
    for row in cur:
        references.append({
            "id": row[0],
            "title": row[1],
            "year": row[2],
            "volume": row[3],
            "issue": row[4],
            "pages": row[5],
            "doi": row[6],
            "pmid": row[7],
            "journal": row[8] if row[8] else row[9],
            "authors": row[10]
        })
    cur.close()
    con.close()
    return jsonify(references)


@bp.route("/<accession>/reference/<int:pmid>/", methods=["PUT"])
def link_reference(accession, pmid):
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
        SELECT PUB_ID
        FROM INTERPRO.CITATION
        WHERE PUBMED_ID = :1
        """, (pmid,)
    )
    row = cur.fetchone()
    if row:
        pub_id, = row
    else:
        citations = get_citations(cur, [pmid])
        if pmid not in citations:
            cur.close()
            con.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Invalid reference",
                    "message": f"{pmid} is not a valid PubMed ID."
                }
            }), 400

        err_pmid = insert_citations(cur, citations)
        if err_pmid is not None:
            cur.close()
            con.close()
            return jsonify({
                "status": False,
                "error": {
                    "title": "Database error",
                    "message": f"Could not insert citation "
                               f"for PubMed ID {err_pmid}"
                }
            }), 500

        pub_id = citations[pmid]

    cur.execute(
        """
        SELECT COUNT(*) 
        FROM INTERPRO.SUPPLEMENTARY_REF
        WHERE ENTRY_AC = :1 AND PUB_ID = :2
        """, (accession, pub_id)
    )

    if cur.fetchone()[0]:
        # Already inserted: ignore
        cur.close()
        con.close()
        return jsonify({"status": True}), 200

    cur.execute(
        """
        SELECT COUNT(*)
        FROM INTERPRO.ENTRY2PUB
        WHERE ENTRY_AC = :1 AND PUB_ID = :2
        """, (accession, pub_id)
    )
    if cur.fetchone()[0]:
        cur.close()
        con.close()
        return jsonify({
            "status": False,
            "error": {
                "title": "Existing reference",
                "message": f"{pmid} cannot be a supplementary reference "
                           f"because it is already in the main references."
            }
        }), 400

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.SUPPLEMENTARY_REF (ENTRY_AC, PUB_ID) 
            VALUES (:1, :2)
            """, (accession, pub_id)
        )
    except DatabaseError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": f"Could not add {pmid} to {accession}."
            }
        }), 500
    else:
        con.commit()
        return jsonify({"status": True}), 200
    finally:
        cur.close()
        con.close()


@bp.route("/<accession>/reference/<pub_id>/", methods=["DELETE"])
def unlink_reference(accession, pub_id):
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
            DELETE FROM INTERPRO.SUPPLEMENTARY_REF
            WHERE ENTRY_AC = :1 AND PUB_ID = :2
            """, (accession, pub_id)
        )
    except DatabaseError:
        return jsonify({
            "status": False,
            "error": {
                "title": "Database error",
                "message": "Could not unlink reference."
            }
        }), 500
    else:
        if cur.rowcount:
            con.commit()
        return jsonify({"status": True}), 200
    finally:
        cur.close()
        con.close()


@bp.route("/<accession>/references/swissprot/", methods=["PUT"])
def update_entry_citations(accession):
    """
    Retrieve signatures for interpro entry, and the matching proteins, to
    coordinating updating citations in the interpro oracle db for said proteins.

    :param accession: interpro entry accession
    """
    user = auth.get_user()
    if not user:
        return jsonify({
            "status": False,
            "error": {
                "title": "Access denied",
                "message": "Please log in to perform this action."
            }
        }), 401

    sig_query = """
        SELECT METHOD_AC
        FROM INTERPRO.ENTRY2METHOD
        WHERE ENTRY_AC = :1
    """

    con = utils.connect_oracle_auth(user)
    with con.cursor() as cur:
        cur.execute(sig_query, [accession])
        signature_accs = cur.fetchall()

    # process each signature in turn & batch process proteins for each signature
    signature_accs = [_[0] for _ in signature_accs]
    invalid_pmids, failed_pub_ids = update_signature_citations(
        signature_accs, accession, con
    )

    con.close()

    if len(invalid_pmids) == len(failed_pub_ids) == 0:
        return jsonify({
            "status": True,
        }), 200
    else:
        return jsonify({
            "status": False,
            "error": {
                "title": "Failed citation update",
                "message": f"Failed to update citations and/or relate citations to entry {accession}.",
                "invalid_pmids": invalid_pmids,
                "failed_pub_ids": failed_pub_ids,
            }
        }), 400


def update_signature_citations(
    sig_accs: list[str],
    entry_acc: str,
    orc_con
) -> tuple[list[str], list[str]]:
    """Coordinate inserting missing citations from PostGreSQL (e.g. INTTST) db 
    into the IPRO db (e.g. IPDEV), and relate the new citations to the InterPro entry

    :param sig_accs: list of signature accs associated with interpro entry
    :param entry_acc: str, IPPRO entry accession
    :param orc_con: open connection to IPPRO oracle db
    """
    invalid_pmids, failed_pub_ids = [], []
    pmid_query = f"""
        SELECT DISTINCT P.pubmed_id
        FROM protein2publication P
        INNER JOIN signature2protein S ON P.protein_acc = S.protein_acc
        WHERE S.signature_acc IN ({','.join(['%s'] * len(sig_accs))})
    """

    pg_con = utils.connect_pg(utils.get_pg_url())

    with pg_con.cursor() as pg_cur:
        pg_cur.execute(pmid_query, sig_accs)
        while pmid_batch := pg_cur.fetchmany(size=1000):
            citations, new_citations, pub_ids = {}, {}, []
            not_in_oracle, in_oracle = check_pmid_in_citations([_[0] for _ in pmid_batch], orc_con)

            if len(not_in_oracle) > 0:
                with orc_con.cursor() as new_cit_cur:
                    new_citations = get_citations(new_cit_cur, not_in_oracle)
                    error = insert_citations(new_cit_cur, new_citations)

                if error:
                    invalid_pmids.extend(list(new_citations.keys()))
                else:
                    pub_ids.extend([new_citations[pmid] for pmid in new_citations])

            with orc_con.cursor() as cit_cur:
                citations = get_citations(cit_cur, in_oracle)
                pub_ids.extend(get_unlinked_pub_ids(citations, cit_cur))

            for pub_id in pub_ids:
                error = relate_entry_to_pubs(entry_acc, pub_id[0], orc_con)
                if error:
                    failed_pub_ids.append(pub_id)

    pg_con.close()
    orc_con.commit()

    return invalid_pmids, failed_pub_ids


def check_pmid_in_citations(pmids: list[int], orc_con) -> tuple[list[int], list[int]]:
    """Check for pmid citations that are not listed in INTERPRO.CITATION

    :param pmids: list of pubmed ids from postgresql publication table
    :param orc_con: interpro oracle db connection
    """
    placeholder = ', '.join([':' + str(i) for i in range(1, len(pmids) + 1)])
    citation_query = f"""
    SELECT PUBMED_ID
    FROM INTERPRO.CITATION
    WHERE PUBMED_ID IN ({placeholder})
    """
    params = {str(i): pmid for i, pmid in enumerate(pmids, start=1)}

    with orc_con.cursor() as orc_cur:
        orc_cur.execute(citation_query, params)
        in_oracle = [row[0] for row in orc_cur]
        not_in_oracle = set(pmids).difference(set(in_oracle))

    return list(not_in_oracle), in_oracle


def get_unlinked_pub_ids(citations: dict, cur) -> list[str]:
    """Retrieve pub_ids for citations retrieved from api.annotation.get_citations()

    :param citations: dict from api.annotation.get_citations()
    :param cur: active oracle db cursor
    """
    placeholder = ', '.join([':' + str(i) for i in range(1, len(citations.keys()) + 1)])
    query = f"""
        SELECT C.PUB_ID
        FROM INTERPRO.CITATION C
        WHERE C.PUBMED_ID IN ({placeholder}) 
          AND C.PUB_ID NOT IN (SELECT PUB_ID FROM INTERPRO.SUPPLEMENTARY_REF)
    """

    cur.execute(query, tuple(citations.keys()))
    return [row for row in cur]


def relate_entry_to_pubs(entry_acc, pub_id, orc_con):
    """Link the entry record to the newly inserted publications

    :param entry_acc: str, interpro entry accession
    :param pub_id: int, pubmed id
    :param orc_con: open oracle db connection
    """
    insert_cur = orc_con.cursor()
    try:
        insert_cur.execute(
            """
            INSERT INTO INTERPRO.SUPPLEMENTARY_REF (ENTRY_AC, PUB_ID)
            VALUES (:acc, :pub)
            """, dict(acc=entry_acc, pub=pub_id)
        )
    except DatabaseError as exc:
        insert_cur.close()
        return exc
