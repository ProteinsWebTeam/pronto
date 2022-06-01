# -*- coding: utf-8 -*-

from typing import Dict, List, Optional, Set, Tuple

from cx_Oracle import Cursor

from .utils import load_terms


DoS = Dict[str, Set[str]]
LoS = List[str]
Err = List[Tuple[str, Optional[str]]]
LoT = List[Tuple[str, str]]


def ck_general_go(ip_cur: Cursor, terms = LoS) -> Err: # TO DO: insert GO terms in DB
    # These terms are too general and should not be used for annotation

    prog3 = "','".join(terms) if terms else None
    print(prog3)
    ip_cur.execute(
        f"""
        SELECT ENTRY_AC, GO_ID
        FROM INTERPRO.INTERPRO2GO
        WHERE GO_ID IN ('{prog3}')
        """
    )
    # 'GO:0031572','GO:0016929','GO:0042710','GO:0044848',
    # 'GO:0000075','GO:0007049','GO:0071214','GO:0071229','GO:0071216',
    # 'GO:0070887','GO:0071495','GO:0071496','GO:0071411','GO:1905120',
    # 'GO:0051716','GO:0033554','GO:0099135','GO:0099136','GO:0099134',
    # 'GO:0097549','GO:0034401','GO:0001539','GO:0009790','GO:0098589',
    # 'GO:0008152','GO:0098798','GO:0071174','GO:0060089','GO:1901977',
    # 'GO:0002832','GO:0032102','GO:0048585','GO:0090233','GO:0051348',
    # 'GO:0097659','GO:0097285','GO:0098802','GO:0098590','GO:0002833',
    # 'GO:0032103','GO:0048584','GO:0090232','GO:0051347','GO:0098926',
    # 'GO:0098928','GO:1901976','GO:1903504','GO:0002831','GO:0032101',
    # 'GO:0048583','GO:0080134','GO:0090231','GO:0051338','GO:1902522',
    # 'GO:0036275','GO:0009628','GO:0001101','GO:0036277','GO:0036276',
    # 'GO:0009607','GO:0097366','GO:0042221','GO:1902518','GO:0036270',
    # 'GO:1902519','GO:1902520','GO:0009719','GO:1902521','GO:0009605',
    # 'GO:0014076','GO:0036272','GO:1905119','GO:0036287','GO:0036274',
    # 'GO:0036271','GO:1903491','GO:0036273','GO:0050896','GO:0006950',
    # 'GO:1990054','GO:0036288','GO:0071173','GO:0031577','GO:0110100',
    # 'GO:0000988','GO:0007610','GO:0005488','GO:0000910','GO:0006810'

    return ip_cur.fetchall()



def ck_root_go(ip_cur: Cursor, terms = LoS) -> Err:
    # InterPro entries with root GO terms
    # 'GO:0008150', 'GO:0003674', 'GO:0005575'
    prog3 = "','".join(terms) if terms else None
    ip_cur.execute(
        f"""
            SELECT ENTRY_AC, GO_ID
            FROM INTERPRO.INTERPRO2GO
            WHERE GO_ID IN ('{prog3}')
        """
    )
    return ip_cur.fetchall()


def ck_dead_entries(cur: Cursor) -> Err:
    # Absolutely dead InterPro accessions
    cur.execute(
        """
            SELECT ENTRY_AC, GO_ID
            FROM INTERPRO.INTERPRO2GO
            WHERE ENTRY_AC NOT IN (
            SELECT ENTRY_AC FROM INTERPRO.ENTRY
            UNION ALL
            SELECT SECONDARY_AC FROM INTERPRO.ENTRY_ACCPAIR)
            OR ENTRY_AC IN (
            SELECT ENTRY_AC FROM INTERPRO.ENTRY_DELETED)
            ORDER BY ENTRY_AC, GO_ID
        """
    )
    return cur.fetchall()


def ck_secondary_acc(cur: Cursor) -> Err: # I don't think this check is necessary anymore, ENTRY_ACCPAIR has last been updated in 2019 
    # InterPro accessions which are now secondary
    cur.execute(
        """
            SELECT G.ENTRY_AC AS OLD_ENTRY_AC,
            G.GO_ID AS GO_ID,
            NEW.ENTRY_AC AS NEW_ENTRY_AC,
            NEW.NAME AS NEW_NAME
            FROM INTERPRO.INTERPRO2GO G,
            INTERPRO.ENTRY_ACCPAIR OLD,
            INTERPRO.ENTRY NEW
            WHERE G.ENTRY_AC = OLD.SECONDARY_AC
            AND OLD.SECONDARY_AC NOT IN (SELECT ENTRY_AC FROM INTERPRO.ENTRY)
            AND OLD.ENTRY_AC = NEW.ENTRY_AC (+)
            ORDER BY G.ENTRY_AC, G.GO_ID, NEW.ENTRY_AC
        """
    )
    errors = []
    for row in cur:
        errors.append((row[0], row[1]))

    return errors

def ck_secondary_go(ip_cur: Cursor, goa_cur: Cursor) -> Err:
    # SELECT GO ids which are now secondary
    goa_cur.execute(
        """
            SELECT SECONDARY_ID, GO_ID
            FROM GO.SECONDARIES
        """
    )
    list_old_goa = {}
    for row in goa_cur:
        list_old_goa[row[0]] = row[1]

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
    return [(acc, None) for acc, in cur]


def check(ora_cur: Cursor,  goa_cur: Cursor):
    terms = load_terms(ora_cur, "generic_go")
    for item in ck_general_go(ora_cur, terms):
        yield "generic_go_term", item

    terms = load_terms(ora_cur, "root_go")
    for item in ck_root_go(ora_cur, terms):
        yield "root_go_term", item

    for item in ck_dead_entries(ora_cur):
        yield "dead_entry", item

    for item in ck_secondary_acc(ora_cur):
        yield "secondary_acc", item

    for item in ck_secondary_go(ora_cur, goa_cur):
        yield "secondary_go", item

    for item in ck_obsolete_go(ora_cur, goa_cur):
        yield "obsolete_go", item

    for item in ck_interpro2go(ora_cur):
        yield "interpro2go", item
