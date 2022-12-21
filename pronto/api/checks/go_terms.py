# -*- coding: utf-8 -*-

from typing import Dict, List, Optional, Set, Tuple

from cx_Oracle import Cursor
import cx_Oracle

from .utils import load_terms


DoS = Dict[str, Set[str]]
LoS = List[str]
Err = List[Tuple[str, Optional[str]]]
LoT = List[Tuple[str, str]]


def ck_forbidden_go(ip_cur: Cursor, terms : LoS) -> Err:
    # These terms are too general or root go and should not be used for annotation
    binds = [":" + str(i + 1) for i in range(len(terms))]
    ip_cur.execute(f"""
        SELECT ENTRY_AC, GO_ID
        FROM INTERPRO.INTERPRO2GO
        WHERE GO_ID IN ({",".join(binds)})
        """, terms)

    return ip_cur.fetchall()


def ck_secondary_go(ip_cur: Cursor, goa_cur: Cursor) -> Err:
    # SELECT GO ids which are now secondary
    goa_cur.execute(
        """
            SELECT SECONDARY_ID, GO_ID
            FROM GO.SECONDARIES
        """
    )
    list_old_goa = dict(goa_cur.fetchall())

    ip_cur.execute(
        """
            SELECT ENTRY_AC, GO_ID
            FROM INTERPRO.INTERPRO2GO
        """
    )
    replaced_go = []
    for row in ip_cur:
        entry = row[0]
        go = row[1]

        if go in list_old_goa:
            replaced_go.append((entry,f"old: {go}, new: {list_old_goa[go]}"))

    return replaced_go


def ck_obsolete_go(ip_cur: Cursor, goa_cur: Cursor) -> Err:
    # GO terms that are now obsolete
    ip_cur.execute(
        """
            SELECT I.ENTRY_AC, I.GO_ID
            FROM INTERPRO.INTERPRO2GO I
            ORDER BY I.GO_ID, I.ENTRY_AC
        """
    )
    entry_goa = ip_cur.fetchall()

    goa_cur.execute(
        """
            SELECT GO_ID
            FROM GO.OBSOLETE_GO_TERMS
        """
    )
    obs_goa = [row[0] for row in goa_cur]

    obsolete_go = []
    for entry, go in entry_goa:
        if go in obs_goa:
            obsolete_go.append((entry, go))

    obsolete = []
    replacement = ck_secondary_go(ip_cur, goa_cur)
    for entry, go in obsolete_go:
        count = 0
        for entry2, rep in replacement:
            old = rep.split(',')[0].split(': ')[1]
            if entry == entry2 and go == old:
                count +=1
        if count == 0: # no replacement found for obsolete GO term
            obsolete.append((entry,go))

    return obsolete


def ck_interpro2go(cur: Cursor) -> Err:
    # go term assigned to an InterPro entry without a method
    cur.execute(
        """
            SELECT ENTRY_AC
            FROM INTERPRO.INTERPRO2GO
            MINUS
            SELECT ENTRY_AC
            FROM INTERPRO.ENTRY2METHOD
    """
    )
    # JOIN INTERPRO.ENTRY E ON E2M.ENTRY_AC=E.ENTRY_AC
    #         AND E.CHECKED='Y'
    return [(acc, None) for acc, in cur]


def check(ora_cur: Cursor,  ora_goa_url: str):
    terms = load_terms(ora_cur, "generic_go")
    for item in ck_forbidden_go(ora_cur, terms):
        yield "generic_go", item

    con_goa = cx_Oracle.connect(ora_goa_url)
    goa_cur = con_goa.cursor()

    for item in ck_secondary_go(ora_cur, goa_cur):
        yield "secondary_go", item

    for item in ck_obsolete_go(ora_cur, goa_cur):
        yield "obsolete_go", item

    goa_cur.close()
    con_goa.close()

    for item in ck_interpro2go(ora_cur):
        yield "interpro2go", item
