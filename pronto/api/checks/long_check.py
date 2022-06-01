# -*- coding: utf-8 -*-

from typing import Dict, List, Optional, Set, Tuple
import cx_Oracle

from cx_Oracle import Cursor

from pronto.utils import connect_pg

DoS = Dict[str, Set[str]]
LoS = List[str]
Err = List[Tuple[str, Optional[str]]]
LoT = List[Tuple[str, str, str]]

def ck_child_matches(cur: Cursor, pg_url: str) -> Err:

    cur.execute(
    """
        SELECT E2E.PARENT_AC, E2MP.METHOD_AC, E2E.ENTRY_AC, E2M.METHOD_AC
        FROM INTERPRO.ENTRY2ENTRY E2E
        JOIN INTERPRO.ENTRY2METHOD E2M ON E2E.ENTRY_AC = E2M.ENTRY_AC
        JOIN INTERPRO.ENTRY2METHOD E2MP ON E2E.PARENT_AC = E2MP.ENTRY_AC
        ORDER BY E2E.PARENT_AC
    """
    )

    entries = dict()
    for row in cur:
        parent_ac, p_sign, child_ac, c_sign = row
        try:
            entries[parent_ac]["p_sign"].add(p_sign)
            entries[parent_ac][child_ac].add(c_sign)
        except KeyError:
            if parent_ac in entries:
                entries[parent_ac][child_ac]=set()
            else:
                entries[parent_ac] = {"p_sign":set(), child_ac:set()}
            entries[parent_ac]["p_sign"].add(p_sign)
            entries[parent_ac][child_ac].add(c_sign)

    errors = []

    pg_con = connect_pg(pg_url)
    pg_cur = pg_con.cursor()

    for parent_ac, info in entries.items():
       
        all_sign = set()
        for item in info.values():
            all_sign = all_sign.union(item)

        sign_prot = get_proteins(pg_cur, all_sign)

        parent_list_prot = set()
        for sign in list(info["p_sign"]):
            parent_list_prot = parent_list_prot.union(sign_prot[sign])

        for child_ac, list_sign in info.items():
            if child_ac != "p_sign":
                list_prot = set()
                for sign in list_sign:
                    if sign in sign_prot:
                        list_prot = list_prot.union(sign_prot[sign])

                common_acc = parent_list_prot.intersection(list_prot)
                
                if len(common_acc) == 0 or len(common_acc) <= len(list_prot) / 2:
                    # print(f"{parent_ac} ({len(parent_list_prot)}) {child_ac} ({len(list_prot)}): {len(common_acc)}")
                    errors.append((parent_ac, child_ac))

    pg_cur.close()
    pg_con.close()

    return errors

def ck_skip_flag_no_match(cur: Cursor, sign_no_frag: set) -> Err:
    cur.execute(
    """
        SELECT E2M.ENTRY_AC, E2M.METHOD_AC
        FROM INTERPRO.ENTRY E
        JOIN INTERPRO.ENTRY2METHOD E2M ON (E.ENTRY_AC=E2M.ENTRY_AC)
        JOIN INTERPRO.METHOD M ON (E2M.METHOD_AC=M.METHOD_AC)
        WHERE M.SKIP_FLAG='N'
        AND M.DBCODE NOT IN ('V') 
        AND E.CHECKED = 'Y'
    """
    )

    errors = []
    for row in cur:
        entry_ac, sign = row
        if sign in sign_no_frag:
            continue
        else:
            errors.append((entry_ac, sign))

    return errors

def ck_fragments(cur: Cursor, sign_no_frag: set) -> Err:
    # Integrated ENTRIES that have METHODs that MATCH ONLY FRAGMENTS
    cur.execute(
    """
        SELECT E.ENTRY_AC, E2M.METHOD_AC
        FROM INTERPRO.ENTRY E
        JOIN INTERPRO.ENTRY2METHOD E2M ON E.ENTRY_AC=E2M.ENTRY_AC
        WHERE E.CHECKED='Y'
        GROUP BY E.ENTRY_AC, E2M.METHOD_AC
    """
    )

    errors = []
    for row in cur:
        entry_ac, sign = row
        if sign in sign_no_frag:
            continue
        else:
            errors.append((entry_ac, sign))

    return errors

def get_proteins(pg_cur: Cursor, sign_list: list) -> Err:

    sign_list_txt = "','".join(sign_list)

    pg_cur.execute(
        f"""
            SELECT DISTINCT SIGNATURE_ACC, PROTEIN_ACC 
            FROM SIGNATURE2PROTEIN S2P
            WHERE SIGNATURE_ACC in ('{sign_list_txt}')
        """
    )
    list_acc = dict()

    for row in pg_cur:
        try:
            list_acc[row[0]].add(row[1])
        except KeyError:
            list_acc[row[0]] = set()
            list_acc[row[0]].add(row[1])

    return list_acc

def get_signatures(pg_url: str) -> Err:
    pg_con = connect_pg(pg_url)
    pg_cur = pg_con.cursor()

    pg_cur.execute(
        f"""
            SELECT DISTINCT SIGNATURE_ACC
            FROM SIGNATURE2PROTEIN S2P
        """
    )
    list_acc = set()

    for row in pg_cur:
        list_acc.add(row[0])

    pg_cur.close()
    pg_con.close()

    return list_acc

def check(ora_url: str, pg_url: str):
    sign_no_frag = get_signatures(pg_url)

    con = cx_Oracle.connect(ora_url)
    cur = con.cursor()
    
    for item in ck_child_matches(cur, pg_url):
        yield "child_matches", item

    cur.close()
    con.close()

    con = cx_Oracle.connect(ora_url)
    cur = con.cursor()

    for item in ck_skip_flag_no_match(cur, sign_no_frag):
        yield "skip_no_matches", item

    for item in ck_fragments(cur, sign_no_frag):
        yield "fragment_matches", item
    
