#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import re
import urllib.parse
import urllib.request
from datetime import timedelta

import cx_Oracle
from flask import Flask, g, jsonify, request, session, redirect, render_template, url_for

import xref

app = Flask(__name__)
app.config.from_envvar('PRONTO_CONFIG')
app.permanent_session_lifetime = timedelta(days=7)


def get_db_stats():
    """
    Retrieves the number of signatures (all, integrated into InterPro, and unintegrated) for each member database.
    """

    # Previous SUM statements were:
    ## SUM(CASE WHEN E2M.ENTRY_AC IS NOT NULL  AND FS.FEATURE_ID IS NOT NULL THEN 1 ELSE 0 END),
    ## SUM(CASE WHEN M.CANDIDATE != 'N' AND E2M.ENTRY_AC IS NULL AND FS.FEATURE_ID IS NOT NULL THEN 1 ELSE 0 END)

    # Removed the join with FEATURE_SUMMARY:
    ## LEFT OUTER JOIN {}.FEATURE_SUMMARY FS ON M.METHOD_AC = FS.FEATURE_ID
    # that can be used to get the number of methods without matches:
    ## sum(case when m.method_ac is not null and feature_id is null then 1 else 0 end) nomatch,

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT
          M.DBCODE,
          MIN(C.DBNAME) DBNAME,
          MIN(C.DBSHORT),
          MIN(V.VERSION),
          COUNT(M.METHOD_AC),
          SUM(CASE WHEN E2M.ENTRY_AC IS NOT NULL THEN 1 ELSE 0 END),
          SUM(CASE WHEN E2M.ENTRY_AC IS NULL THEN 1 ELSE 0 END)
        FROM INTERPRO.METHOD M
        LEFT OUTER JOIN {0}.DB_VERSION V ON M.DBCODE = V.DBCODE
        LEFT OUTER JOIN {0}.CV_DATABASE C ON V.DBCODE = C.DBCODE
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD E2M ON E2M.METHOD_AC = M.METHOD_AC
        GROUP BY M.DBCODE
        ORDER BY DBNAME
        """.format(app.config['DB_SCHEMA'])
    )

    databases = []
    for row in cur:
        databases.append({
            'code': row[0],
            'name': row[1],
            'shortName': row[2].lower(),
            'version': row[3],
            'home': xref.find_ref(row[0]).home,
            'count': row[4],
            'countIntegrated': row[5],
            'countUnintegrated': row[6],
        })

    cur.close()

    return databases


def get_latest_entries(n):
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT E.ENTRY_AC, MIN(E.ENTRY_TYPE), MIN(E.SHORT_NAME), MIN(U.NAME), MIN(CREATED), COUNT(PROTEIN_AC)
        FROM (
          SELECT ENTRY_AC, ENTRY_TYPE, SHORT_NAME, USERSTAMP, CREATED
          FROM INTERPRO.ENTRY
          WHERE ROWNUM <= :1
          ORDER BY ENTRY_AC DESC
        ) E
        INNER JOIN INTERPRO.USER_PRONTO U ON E.USERSTAMP = U.DB_USER
        LEFT OUTER JOIN INTERPRO.MV_ENTRY2PROTEIN E2P ON E.ENTRY_AC = E2P.ENTRY_AC
        GROUP BY E.ENTRY_AC
        """,
        (n,)
    )

    entries = []
    for row in cur:
        entries.append({
            'id': row[0],
            'type': row[1],
            'shortName': row[2],
            'user': row[3].split()[0],
            'timestamp': row[4].timestamp(),
            'count': row[5]
        })

    cur.close()

    return entries


def get_topic(topic_id):
    """
    Retrieves a topic (category of comments) from its ID.
    """

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT TOPIC
        FROM {}.PROTEIN_COMMENT_TOPIC
        WHERE TOPIC_ID = :1
        """.format(app.config['DB_SCHEMA']),
        (topic_id,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def get_taxon(taxon_id):
    """
    Returns taxonomic information (name, phylogenetic left/right number) from a taxon ID.
    """

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT TAX_ID, FULL_NAME, LEFT_NUMBER, RIGHT_NUMBER, RANK
        FROM {}.ETAXI
        WHERE TAX_ID=:1
        """.format(app.config['DB_SCHEMA']),
        (taxon_id,))
    row = cur.fetchone()
    cur.close()
    return None if not row else dict(zip(('id', 'fullName', 'leftNumber', 'rightNumber', 'rank'), row))


def get_topics():
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT TOPIC_ID, TOPIC
        FROM {}.PROTEIN_COMMENT_TOPIC
        WHERE TOPIC_ID != 0
        ORDER BY TOPIC
        """.format(app.config['DB_SCHEMA'])
    )

    topics = [dict(zip(('id', 'value'), row)) for row in cur]
    cur.close()

    return topics


def build_method2protein_sql(methods, **kwargs):
    taxon = kwargs.get('taxon')
    db = kwargs.get('db')
    desc_id = kwargs.get('description')
    topic_id = kwargs.get('topic')
    comment_id = kwargs.get('comment')
    term_id = kwargs.get('term')
    search = kwargs.get('search')

    can = []
    must = []
    mustnt = []

    for method_ac, value in methods.items():
        if value is None:
            can.append(method_ac)
        elif value:
            must.append(method_ac)
        else:
            mustnt.append(method_ac)

    # Get the list of all proteins matched by the methods (and passing the filters)
    can_cond = ','.join([':can' + str(i) for i in range(len(can + must))])
    params = {'can' + str(i): method for i, method in enumerate(can + must)}

    # Retrieve proteins that MUST match a set of given signatures
    if must:
        must_join = """
            INNER JOIN (
                SELECT
                  SEQ_ID,
                  COUNT(DISTINCT FEATURE_ID) CT
                FROM {}.FEATURE2PROTEIN F2P
                WHERE FEATURE_ID IN ({})
                GROUP BY SEQ_ID
            ) FF ON FF.SEQ_ID = F2P.SEQ_ID
        """.format(
            app.config['DB_SCHEMA'],
            ','.join([':must' + str(i) for i in range(len(must))])
        )

        must_cond = 'AND FF.CT = :n_must'

        params.update({'must' + str(i): method for i, method in enumerate(must)})
        params['n_must'] = len(must)
    else:
        must_join = ''
        must_cond = ''

    # Exclude proteins matching a set of given signatures
    if mustnt:
        mustnt_join = """
            LEFT JOIN (
                SELECT
                    DISTINCT SEQ_ID
                FROM {}.FEATURE2PROTEIN F2P
                WHERE FEATURE_ID IN ({})
                GROUP BY SEQ_ID
            ) EF ON F2P.SEQ_ID = EF.SEQ_ID
        """.format(
            app.config['DB_SCHEMA'],
            ','.join([':mustnt' + str(i) for i in range(len(mustnt))])
        )

        mustnt_cond = 'AND EF.SEQ_ID IS NULL'

        params.update({'mustnt' + str(i): method for i, method in enumerate(mustnt)})
    else:
        mustnt_join = ''
        mustnt_cond = ''

    # Retrieve only proteins associated to a given Swiss-Prot topic/comment
    if topic_id and comment_id:
        comment_join = 'INNER JOIN {}.PROTEIN_COMMENT_CODE CC ON F2P.SEQ_ID = CC.PROTEIN_AC'.format(
            app.config['DB_SCHEMA']
        )
        comment_cond = 'AND CC.TOPIC_ID = :topic AND CC.COMMENT_ID = :comment_id'
        params.update({'topic': topic_id, 'comment_id': comment_id})
    else:
        comment_join = ''
        comment_cond = ''

    # Retrieve only proteins associated to a given UniProt description
    if desc_id:
        desc_cond = 'AND F2P.DESCRIPTION_ID = :descid'
        params['descid'] = desc_id
    else:
        desc_cond = ''

    # Retrieve only proteins from a given database (S: reviewed/SwissProt; T: unreviewed/TrEMBL)
    if db:
        db_cond = 'AND DB = :db'
        params['db'] = db
    else:
        db_cond = ''

    # Retrieve only proteins associated to a given GO term
    if term_id:
        term_join = """
        INNER JOIN (
            SELECT DISTINCT TERM_GROUP_ID
            FROM {}.TERM_GROUP2TERM WHERE GO_ID = :term
        ) GO ON F2P.TERM_GROUP_ID = GO.TERM_GROUP_ID
        """.format(app.config['DB_SCHEMA'])
        params['term'] = term_id
    else:
        term_join = ''

    if search:
        name_cond = 'AND F2P.SEQ_ID LIKE :search_like'
        params['search_like'] = search + '%'
    else:
        name_cond = ''

    if taxon:
        tax_cond = 'AND LEFT_NUMBER BETWEEN :ln AND :rn'
        params['ln'] = int(taxon['leftNumber'])
        params['rn'] = int(taxon['rightNumber'])
    else:
        tax_cond = ''

    sql = """
        SELECT
            MIN(LEFT_NUMBER) AS LEFT_NUMBER,
            MIN(GLOBAL) AS GLOBAL,
            MIN(LENGTH) AS LENGTH,
            MIN(DB) AS DB,
            MIN(F2P.DESCRIPTION_ID) AS DESCRIPTION_ID,
            MIN(F2P.TERM_GROUP_ID) AS TERM_GROUP_ID,
            F2P.SEQ_ID
        FROM {}.FEATURE2PROTEIN F2P
        {}
        {}
        {}
        {}
        WHERE FEATURE_ID IN ({})
        {}
        {}
        {}
        {}
        {}
        {}
        {}
        GROUP BY F2P.SEQ_ID
    """.format(
        app.config['DB_SCHEMA'],

        # Joins (above WHERE FEATURE_ID)
        must_join, mustnt_join, comment_join, term_join,

        # WHERE FEATURE_ID
        can_cond,

        # Other conditions
        must_cond,
        mustnt_cond,
        comment_cond,
        desc_cond,
        db_cond,
        name_cond,
        tax_cond
    )

    return sql, params


def get_overlapping_proteins(methods, **kwargs):
    """
    Returns the protein matched by one or more signatures.
    """
    page = kwargs.get('page', 1)
    page_size = kwargs.get('page_size', 10)

    sql, params = build_method2protein_sql(methods, **kwargs)

    cur = get_db().cursor()

    if kwargs.get('code'):
        params['code'] = kwargs['code']

        cur.execute(
            """
            SELECT
                SEQ_ID,
                GLOBAL
            FROM (
                {}
            )
            WHERE GLOBAL = :code
            ORDER BY SEQ_ID
            """.format(sql),
            params
        )

        proteins = [(row[0], row[1], 1) for row in cur]
    else:
        cur.execute(
            """
            SELECT
                SEQ_ID,
                CODE,
                SEQ_CT
            FROM (
                SELECT
                    SEQ_ID,
                    GLOBAL AS CODE,
                    COUNT(*) OVER (PARTITION BY GLOBAL) AS SEQ_CT,
                    ROW_NUMBER() OVER (PARTITION BY GLOBAL ORDER BY LENGTH) AS RN
                FROM (
                    {}
                )
            )
            WHERE RN = 1
            ORDER BY SEQ_CT DESC, SEQ_ID
            """.format(sql),
            params
        )
        proteins = [row for row in cur]

    count = len(proteins)

    if not count:
        return proteins, count, 0  # invalid method IDs, or no methods passing the filtering

    # Select requested page
    proteins = proteins[(page - 1) * page_size:page * page_size]

    # Creat list of protein accessions and a dictionary of info for condensed proteins
    protein_acs = [p[0] for p in proteins]
    protein_codes = {p_ac: {'code': p_code, 'count': int(p_ct)} for p_ac, p_code, p_ct in proteins}

    # Get info on proteins (description, taxon, etc.)
    proteins_cond = ','.join([':' + str(i+1) for i in range(len(protein_acs))])
    cur.execute(
        """
        SELECT P.PROTEIN_AC, P.DBCODE, P.LEN, PI.DESCRIPTION, E.FULL_NAME
        FROM {0}.PROTEIN P
        INNER JOIN {0}.PROTEIN_INFO PI ON P.PROTEIN_AC = PI.PROTEIN_AC
        INNER JOIN {0}.ETAXI E ON P.TAX_ID = E.TAX_ID
        WHERE P.PROTEIN_AC IN ({1})
        """.format(app.config['DB_SCHEMA'], proteins_cond),
        protein_acs
    )

    max_len = 0
    protein_info = {}
    for row in cur:
        p_ac = row[0]

        protein_info[p_ac] = {
            'id': p_ac,
            'isReviewed': row[1] == 'S',
            'length': row[2],
            'description': row[3],
            'organism': row[4],
            'link': ('http://sp.isb-sib.ch/uniprot/' if row[1] == 'S' else 'http://www.uniprot.org/uniprot/') + p_ac,
            'code': protein_codes[p_ac]['code'],
            'count': protein_codes[p_ac]['count']
        }

        if row[2] > max_len:
            max_len = row[2]

    proteins_cond = ','.join([':prot' + str(i) for i in range(len(protein_acs))])
    params = {'prot' + str(i): p_ac for i, p_ac in enumerate(protein_acs)}
    cur.execute(
        """
        SELECT F2P.SEQ_ID, F2P.FEATURE_ID, FS.NAME, M.DBCODE, M.CANDIDATE, E2M.ENTRY_AC
        FROM {0}.FEATURE2PROTEIN F2P
        INNER JOIN {0}.FEATURE_SUMMARY FS ON F2P.FEATURE_ID = FS.FEATURE_ID
        INNER JOIN (
            SELECT DISTINCT FEATURE_ID
            FROM {0}.MATCH_SUMMARY
            WHERE SEQ_ID IN ({1})
        ) M ON FS.FEATURE_ID = M.FEATURE_ID
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD E2M ON M.FEATURE_ID = E2M.METHOD_AC
        LEFT OUTER JOIN INTERPRO.METHOD M ON M.FEATURE_ID = M.METHOD_AC
        WHERE F2P.SEQ_ID IN ({1})
        ORDER BY E2M.ENTRY_AC, F2P.FEATURE_ID
        """.format(app.config['DB_SCHEMA'], proteins_cond),
        params
    )

    proteins2methods = {}
    for protein_ac, method_ac, method_name, method_db, is_candidate, entry_ac in cur:
        try:
            proteins2methods[protein_ac]
        except KeyError:
            proteins2methods[protein_ac] = []
        finally:
            if method_db is not None:
                m = xref.find_ref(method_db, method_ac)
                method_db = {
                    'link': m.gen_link(),
                    'color': m.color
                }

            proteins2methods[protein_ac].append({
                'id': method_ac,
                'name': method_name,
                'isCandidate': is_candidate == 'Y',
                'entryId': entry_ac,
                'isSelected': method_ac in methods,
                'db': method_db
            })

    proteins2matches = {}
    cur.execute(
        """
        SELECT PROTEIN_AC, METHOD_AC, POS_FROM, POS_TO
        FROM {}.MATCH
        WHERE PROTEIN_AC IN ({})
        """.format(app.config['DB_SCHEMA'], proteins_cond),
        params
    )
    for protein_ac, method_ac, pos_from, pos_to in cur:
        if protein_ac not in proteins2matches:
            proteins2matches[protein_ac] = {
                method_ac: [{'start': pos_from, 'end': pos_to}]
            }
        elif method_ac not in proteins2matches[protein_ac]:
            proteins2matches[protein_ac][method_ac] = [{'start': pos_from, 'end': pos_to}]
        else:
            proteins2matches[protein_ac][method_ac].append({'start': pos_from, 'end': pos_to})

    cur.close()

    # Merge proteins, methods, and matches info
    for p_ac in protein_info:
        methods = []
        for m in proteins2methods[p_ac]:
            try:
                m['matches'] = proteins2matches[p_ac][m['id']]
            except KeyError:
                pass
            else:
                methods.append(m)
        protein_info[p_ac]['methods'] = methods

    return [protein_info[p_ac] for p_ac in protein_acs], count, max_len


def get_overlapping_entries(method):
    """
     Returns the overlapping entries for a given signature.
    """
    cur = get_db().cursor()

    """
    Signature predictions

    Two following join were removed:
        LEFT JOIN INTERPRO_ANALYSIS.EXTRA_RELATIONS EXC ON EXC.FEATURE_ID1=FSC.FEATURE_ID AND EXC.FEATURE_ID2=FSQ.FEATURE_ID
        LEFT JOIN INTERPRO_ANALYSIS.EXTRA_RELATIONS EXQ ON EXQ.FEATURE_ID1=FSQ.FEATURE_ID AND EXQ.FEATURE_ID2=FSC.FEATURE_ID

        Which allowed to select:
            EXC.EXTRA1      number of signatures that the candidate has a relationship with, but the query does not have
            EXQ.EXTRA1      number of signatures that the query has a relationship with, but the candidate does not have

        LEFT OUTER JOIN INTERPRO_ANALYSIS.ADJACENT_RELATIONS ADJC ON ADJC.FEATURE_ID2=FSC.FEATURE_ID AND ADJC.FEATURE_ID1=FSQ.FEATURE_ID
        LEFT OUTER JOIN INTERPRO_ANALYSIS.ADJACENT_RELATIONS ADJQ ON ADJQ.FEATURE_ID2=FSQ.FEATURE_ID AND ADJQ.FEATURE_ID1=FSC.FEATURE_ID

        Which allowed to select:
            ADJC.ADJ2       number of signatures adjacent to the candidate which overlap with the query
            ADJQ.ADJ2       number of signatures adjacent to the query which overlap with the candidate
    """
    cur.execute(
        """
        SELECT
          F.FEATURE_ID1,
          F.DBCODE,
          CV.DBSHORT,

          E.ENTRY_AC,
          E.CHECKED,
          E.ENTRY_TYPE,
          E.NAME,

          FSC_CT_PROT,
          FSC_N_BLOB,

          OS_CT_OVER,
          OS_N_OVER,
          FSQ_CT_PROT,
          FSQ_N_BLOB,

          F.LEN1,
          F.LEN2,

          P.RELATION,
          R.RELATION CURATED_RELATION
        FROM (
            SELECT
                FSC.FEATURE_ID FEATURE_ID1,
                FSQ.FEATURE_ID FEATURE_ID2,
                FSC.DBCODE,
                FSC.CT_PROT FSC_CT_PROT,
                FSC.N_BLOB FSC_N_BLOB,
                OS.CT_OVER OS_CT_OVER,
                OS.N_OVER OS_N_OVER,
                FSQ.CT_PROT FSQ_CT_PROT,
                FSQ.N_BLOB FSQ_N_BLOB,
                OS.LEN1,
                OS.LEN2
            FROM (
                SELECT FEATURE_ID1, FEATURE_ID2, CT_OVER, N_OVER, LEN1, LEN2
                FROM {0}.OVERLAP_SUMMARY
                WHERE FEATURE_ID2 = :1
            ) OS
            INNER JOIN {0}.FEATURE_SUMMARY FSC ON OS.FEATURE_ID1 = FSC.FEATURE_ID
            INNER JOIN {0}.FEATURE_SUMMARY FSQ ON OS.FEATURE_ID2 = FSQ.FEATURE_ID
            WHERE ((OS.CT_OVER >= (0.3 * FSC.CT_PROT)) OR (OS.CT_OVER >= (0.3 * FSQ.CT_PROT)))
        ) F
        LEFT OUTER JOIN {0}.PREDICTION P ON F.FEATURE_ID1 = P.FEATURE_ID1 AND F.FEATURE_ID2 = P.FEATURE_ID2
        LEFT OUTER JOIN INTERPRO.CURATED_RELATIONS R ON F.FEATURE_ID1 = R.FEATURE_ID1 AND F.FEATURE_ID2 = R.FEATURE_ID2
        LEFT OUTER JOIN {0}.CV_DATABASE CV ON F.DBCODE = CV.DBCODE
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD E2M ON F.FEATURE_ID1 = E2M.METHOD_AC
        LEFT OUTER JOIN INTERPRO.ENTRY E ON E2M.ENTRY_AC = E.ENTRY_AC
        ORDER BY OS_CT_OVER DESC
        """.format(app.config['DB_SCHEMA']),
        (method,)
    )

    methods = []
    for row in cur:
        db = xref.find_ref(row[1], row[0])

        methods.append({
            # method and member database
            'id': row[0],
            'dbCode': row[1],
            'dbShort': row[2],
            'dbLink': db.gen_link() if db else None,

            # InterPro entry info
            'entryId': row[3],
            'entryHierarchy': [],
            'isChecked': row[4] == 'Y',
            'entryType': row[5],
            'entryName': row[6],

            'nProts': row[7],           # number of proteins where both query and candidate signatures overlap
            'nBlobs': row[8],           # number of overlapping blobs with query and candidate signature

            'nProtsCand': row[9],       # number of proteins for every candidate signature
            'nBlobsCand': row[10],
            'nProtsQuery': row[11],     # number of proteins in the query signature found
            'nBlobsQuery': row[12],

            'lenCand': row[13],         # average percentage of the overlap length as a fraction of the candidate blob length
            'lenQuery': row[14],        # average percentage of the overlap length as a fraction of the query blob length

            'relation': row[15],        # predicted relationship
            'curatedRelation': row[16]  # existing curated relationship
        })

    cur.execute(
        """
        SELECT ENTRY_AC, PARENT_AC
        FROM INTERPRO.ENTRY2ENTRY
        """,
    )

    parent_of = dict(cur.fetchall())
    cur.close()

    for m in methods:
        entry_ac = m['entryId']

        if entry_ac:
            hierarchy = []

            while entry_ac in parent_of:
                entry_ac = parent_of[entry_ac]
                hierarchy.append(entry_ac)

            m['entryHierarchy'] = hierarchy[::-1]

    return methods


def get_taxonomy(methods, taxon, rank):
    """
    Returns the taxonomic origins of one or more signatures.
    """

    cur = get_db().cursor()

    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}

    max_cnt = 0
    cur.execute(
        """
        SELECT MAX(CT_PROT)
        FROM {}.FEATURE_SUMMARY
        WHERE FEATURE_ID in ({})
        """.format(app.config['DB_SCHEMA'], fmt),
        params
    )
    row = cur.fetchone()
    if row:
        max_cnt = row[0]

    params['left_number'] = taxon['leftNumber']
    params['right_number'] = taxon['rightNumber']
    params['rank'] = rank

    cur.execute(
        """
        SELECT E.TAX_ID, MIN(E.FULL_NAME), F.FEATURE_ID, SUM(F.CNT)
        FROM (
          SELECT FEATURE_ID, LEFT_NUMBER, COUNT(SEQ_ID) CNT
          FROM {0}.FEATURE2PROTEIN
          WHERE FEATURE_ID IN ({1}) AND LEFT_NUMBER BETWEEN :left_number AND :right_number
          GROUP BY FEATURE_ID, LEFT_NUMBER
        ) F
        INNER JOIN (
          SELECT TAX_ID, LEFT_NUMBER
          FROM {0}.TAXONOMY_RANK
          WHERE LEFT_NUMBER BETWEEN :left_number AND :right_number
          AND RANK = :rank
        ) T
        ON F.LEFT_NUMBER = T.LEFT_NUMBER
        INNER JOIN {0}.ETAXI E ON T.TAX_ID = E.TAX_ID
        GROUP BY FEATURE_ID, E.TAX_ID
        """.format(app.config['DB_SCHEMA'], fmt),
        params
    )

    taxons = {}
    for tax_id, full_name, method_ac, count in cur:
        try:
            taxons[tax_id]
        except KeyError:
            taxons[tax_id] = {
                'id': tax_id,
                'fullName': full_name,
                'methods': {}
            }
        finally:
            taxons[tax_id]['methods'][method_ac] = count

    cur.close()

    return sorted(taxons.values(), key=lambda x: -sum(x['methods'].values())), max_cnt


def get_descriptions(methods, db=None):
    """
    Returns the descriptions associated to one or more signatures.
    """
    cur = get_db().cursor()

    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}
    params['db'] = db

    cur.execute(
        """
        SELECT F.DESCRIPTION_ID, D.DESCRIPTION, FEATURE_ID, CT, CTMAX
        FROM (
          SELECT
            FEATURE_ID,
            DESCRIPTION_ID,
            MAX(CT) CT,
            MAX(CTMAX) CTMAX
          FROM (
            SELECT
              FEATURE_ID,
              DESCRIPTION_ID,
              COUNT(*) OVER (PARTITION BY DESCRIPTION_ID, FEATURE_ID) CT ,
              COUNT(DISTINCT SEQ_ID) OVER (PARTITION BY DESCRIPTION_ID) CTMAX
            FROM {0}.FEATURE2PROTEIN
            WHERE FEATURE_ID IN ({1}) AND (DB = :db OR :db IS NULL)
          )
          GROUP BY DESCRIPTION_ID, FEATURE_ID
        ) F
        INNER JOIN {0}.PROTEIN_DESCRIPTION_VALUE D ON F.DESCRIPTION_ID = D.DESCRIPTION_ID
        """.format(app.config['DB_SCHEMA'], fmt),
        params
    )

    descriptions = {}
    for desc_id, desc, method_ac, count, count_max in cur:
        try:
            descriptions[desc_id]
        except KeyError:
            descriptions[desc_id] = {
                'id': desc_id,
                'value': desc,
                'methods': {},
                'max': count_max
            }
        finally:
            descriptions[desc_id]['methods'][method_ac] = count

    cur.close()

    return sorted(descriptions.values(), key=lambda x: -x['max'])


def get_description(desc_id):
    """
    Returns proteins associated to a given description.
    """

    cur = get_db().cursor()

    cur.execute(
        """
        SELECT P.PROTEIN_AC, P.NAME, P.DBCODE, E.FULL_NAME
        FROM {0}.PROTEIN_DESCRIPTION_CODE C
        INNER JOIN {0}.PROTEIN P ON C.PROTEIN_AC = P.PROTEIN_AC
        INNER JOIN {0}.ETAXI E ON P.TAX_ID = E.TAX_ID
        WHERE C.DESCRIPTION_ID = :desc_id
        ORDER BY P.PROTEIN_AC
        """.format(app.config['DB_SCHEMA']),
        (desc_id,)
    )

    proteins = []
    for row in cur:
        proteins.append({
            'id': row[0],
            'shortName': row[1],
            'isReviewed': row[2] == 'S',
            'organism': row[3]
        })

    cur.close()

    return proteins


def get_go_terms(methods, aspects=list()):
    """
    Return the GO terms associated to one or more signatures.
    """

    cur = get_db().cursor()

    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}

    sql = """
        SELECT
          T.GO_ID,
          T.NAME,
          T.CATEGORY,
          F.FEATURE_ID,
          F.SEQ_ID,
          P2G.REF_DB_ID
        FROM (
          SELECT DISTINCT FEATURE_ID, TERM_GROUP_ID, SEQ_ID
          FROM {0}.FEATURE2PROTEIN
          WHERE FEATURE_ID IN ({1})
        ) F
        INNER JOIN {0}.TERM_GROUP2TERM G2T ON F.TERM_GROUP_ID = G2T.TERM_GROUP_ID
        INNER JOIN {0}.TERMS T ON G2T.GO_ID = T.GO_ID
        LEFT OUTER JOIN (
          SELECT PROTEIN_AC, GO_ID, REF_DB_ID
          FROM {0}.PROTEIN2GO_MANUAL
          WHERE REF_DB_CODE = 'PMID'
        ) P2G ON F.SEQ_ID = P2G.PROTEIN_AC AND G2T.GO_ID = P2G.GO_ID
    """.format(app.config['DB_SCHEMA'], fmt)

    if aspects and isinstance(aspects,(list, tuple)):
        sql += "WHERE T.CATEGORY IN ({})".format(','.join([':aspect' + str(i) for i in range(len(aspects))]))
        params.update({'aspect' + str(i): aspect for i, aspect in enumerate(aspects)})

    cur.execute(sql, params)

    terms = {}
    methods = {}  # count the total number of proteins for each signature
    for go_id, term, aspect, method_ac, protein_ac, ref_id in cur:
        try:
            terms[go_id]
        except KeyError:
            terms[go_id] = {
                'id': go_id,
                'value': term,
                'methods': {},
                'aspect': aspect
            }
        finally:
            d = terms[go_id]['methods']

        try:
            d[method_ac]
        except KeyError:
            d[method_ac] = {
                'proteins': set(),
                'references': set()
            }
        finally:
            d[method_ac]['proteins'].add(protein_ac)
            if ref_id:
                d[method_ac]['references'].add(ref_id)

        try:
            methods[method_ac]
        except KeyError:
            methods[method_ac] = set()
        finally:
            methods[method_ac].add(protein_ac)

    for term in terms.values():
        for method in term['methods'].values():
            method['proteins'] = len(method['proteins'])
            method['references'] = len(method['references'])

    cur.close()

    return (
        sorted(terms.values(), key=lambda t: -sum(m['proteins'] for m in t['methods'].values())),
        {method_ac: len(proteins) for method_ac, proteins in methods.items()}
    )


def get_swissprot_comments(methods, topic_id):
    """
    Returns Swiss-Prot comments of a given topic associated to one or more signatures.
    """

    cur = get_db().cursor()

    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}
    params['topic_id'] = topic_id

    cur.execute(
        """
        SELECT
          F.FEATURE_ID,
          C.COMMENT_ID,
          C.TEXT,
          COUNT(F.SEQ_ID)
        FROM (
          SELECT FEATURE_ID, SEQ_ID
          FROM {0}.FEATURE2PROTEIN
          WHERE FEATURE_ID IN ({1})
        ) F
        INNER JOIN (
          SELECT C.PROTEIN_AC, C.COMMENT_ID, V.TEXT
          FROM {0}.PROTEIN_COMMENT_CODE C
          INNER JOIN {0}.PROTEIN_COMMENT_VALUE V ON C.COMMENT_ID = V.COMMENT_ID
          WHERE C.TOPIC_ID = :topic_id AND V.TOPIC_ID = :topic_id
        ) C ON F.SEQ_ID = C.PROTEIN_AC
        GROUP BY FEATURE_ID, COMMENT_ID, TEXT
        """.format(app.config['DB_SCHEMA'], fmt),
        params
    )

    comments = {}
    for method_ac, comment_id, comment, count in cur:
        try:
            comments[comment_id]
        except KeyError:
            comments[comment_id] = {
                'id': comment_id,
                'value': comment,
                'methods': {},
                'max': 0
            }
        finally:
            comments[comment_id]['methods'][method_ac] = count

            if count > comments[comment_id]['max']:
                comments[comment_id]['max'] = count

    cur.close()

    return sorted(comments.values(), key=lambda x: -x['max'])


def get_match_matrix(methods):
    """
    Returns the overlap match matrix, and the collocation match matrix for overlapping signatures.
    """

    cur = get_db().cursor()

    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}

    cur.execute(
        """
        SELECT F.FEATURE_ID, F.CT_PROT, OS.FEATURE_ID2, OS.CT_COLOC, OS.AVG_OVER, OS.CT_OVER
        FROM (
          SELECT FEATURE_ID, COUNT(DISTINCT SEQ_ID) CT_PROT
          FROM {0}.FEATURE2PROTEIN
          WHERE FEATURE_ID IN ({1})
          GROUP BY FEATURE_ID
        ) F
        INNER JOIN (
          SELECT FEATURE_ID1, FEATURE_ID2, CT_COLOC, AVG_OVER, CT_OVER
          FROM {0}.OVERLAP_SUMMARY
          WHERE FEATURE_ID1 IN ({1}) AND FEATURE_ID2 IN ({1})
        ) OS ON F.FEATURE_ID = OS.FEATURE_ID1
        """.format(app.config['DB_SCHEMA'], fmt),
        params
    )

    matrix = {}
    for method_ac_1, n_prot, method_ac_2, n_coloc, avg_over, n_overlap in cur:
        try:
            matrix[method_ac_1]
        except KeyError:
            matrix[method_ac_1] = {
                'prot': n_prot,
                'methods': {}
            }
        finally:
            matrix[method_ac_1]['methods'][method_ac_2] = {
                'coloc': n_coloc,
                'over': n_overlap,
                'avgOver': avg_over
            }

    cur.close()

    return matrix, max([m['prot'] for m in matrix.values()])


def get_db_info(dbshort):
    cur = get_db().cursor()

    cur.execute(
        """
        SELECT CV.DBNAME, CV.DBCODE, DB.VERSION
        FROM {}.CV_DATABASE CV
        INNER JOIN INTERPRO.DB_VERSION DB ON CV.DBCODE = DB.DBCODE
        WHERE LOWER(CV.DBSHORT) = :1
        """.format(app.config['DB_SCHEMA']),
        (dbshort.lower(),)
    )

    row = cur.fetchone()

    try:
        dbname, dbcode, dbversion = row
    except TypeError:
        dbname = dbcode = dbversion = None
    finally:
        cur.close()
        return dbname, dbcode, dbversion


def get_unintegrated(dbcode, mode='newint', search=None):
    # mode in ('newint', 'exist', 'norel')
    cur = get_db().cursor()

    if search is not None:
        search += '%'

    cur.execute(
        """
        SELECT DISTINCT
            FS.FEATURE_ID,
            P.FEATURE_ID2,
            M.CANDIDATE,
            P.RELATION,
            EM2.ENTRY_AC,
            E.ENTRY_TYPE
        FROM {0}.FEATURE_SUMMARY FS
        LEFT OUTER JOIN {0}.PREDICTION P ON (FS.FEATURE_ID = P.FEATURE_ID1 AND P.FEATURE_ID1 != P.FEATURE_ID2)
        LEFT OUTER JOIN {0}.METHOD M ON P.FEATURE_ID2 = M.METHOD_AC
        LEFT OUTER JOIN {0}.ENTRY2METHOD EM1 ON FS.FEATURE_ID = EM1.METHOD_AC
        LEFT OUTER JOIN {0}.ENTRY2METHOD EM2 ON P.FEATURE_ID2 = EM2.METHOD_AC
        LEFT OUTER JOIN {0}.ENTRY E ON EM2.ENTRY_AC = E.ENTRY_AC
        WHERE FS.DBCODE = :1 AND EM1.ENTRY_AC IS NULL AND (:2 IS NULL OR FS.FEATURE_ID LIKE :2)
        """.format(app.config['DB_SCHEMA']),
        (dbcode, search)
    )

    methods = {}
    for m1_ac, m2_ac, m2_is_candidate, rel, e_ac, e_type in cur:
        if m1_ac in methods:
            m = methods[m1_ac]
        else:
            m = methods[m1_ac] = {
                'id': m1_ac,
                'predictions': []
            }

        m['predictions'].append({
            'id': e_ac if e_ac is not None else m2_ac,
            'type': e_type if e_ac is not None else None,
            'isCandidate': m2_is_candidate == 'Y',
            'relation': rel
        })

    cur.close()

    # Filter methods
    if mode == 'norel':
        # Method mustn't have any non-null relation
        def test_method(m):
            return not len([p for p in m['predictions'] if p['relation'] is not None])
    elif mode == 'exist':
        # Method must have at least one InterPro prediction
        def test_method(m):
            return len([p for p in m['predictions'] if p['relation'] == 'ADDTO' and p['type'] is not None])
    elif mode == 'newint':
        # Method must have at least one prediction that is an unintegrated candidate signature
        def test_method(m):
            return len([p for p in m['predictions'] if p['relation'] == 'ADDTO' and p['type'] is None and p['isCandidate']])
    else:
        # Invalid mode
        def test_method(m):
            return False

    _methods = []
    for m in sorted([m for m in methods.values()], key=lambda x: x['id']):

        if test_method(m):
            add_to = {}
            parents = set()
            children = set()

            for p in m['predictions']:

                feature = p['id']
                e_type = p['type']

                if p['relation'] == 'ADDTO':
                    add_to[feature] = e_type
                elif p['relation'] == 'PARENT_OF':
                    parents.add(feature)
                elif p['relation'] == 'CHILD_OF':
                    children.add(feature)

            _methods.append({
                'id': m['id'],
                'addTo': [{'id': k, 'type': add_to[k]} for k in sorted(add_to)],
                'parents': list(sorted(parents)),
                'children': list(sorted(children))
            })

    return _methods


def get_methods(dbcode, search=None, integrated=None, checked=None, commented=None):
    """
    Get signatures from a given member database with their InterPro entry and the most recent comment (if any)
    """

    cur = get_db().cursor()

    sql = """
        SELECT
          M.METHOD_AC,
          EM.ENTRY_AC,
          E.CHECKED,
          MM_NOW.PROTEIN_COUNT,
          MM_THEN.PROTEIN_COUNT,
          C.VALUE,
          C.NAME,
          C.CREATED_ON
        FROM INTERPRO.METHOD M
        LEFT OUTER JOIN INTERPRO.MV_METHOD_MATCH MM_NOW ON M.METHOD_AC = MM_NOW.METHOD_AC
        LEFT OUTER JOIN INTERPRO.MV_METHOD_MATCH MM_THEN ON M.METHOD_AC = MM_THEN.METHOD_AC
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD EM ON M.METHOD_AC = EM.METHOD_AC
        LEFT OUTER JOIN INTERPRO.ENTRY E ON E.ENTRY_AC = EM.ENTRY_AC
        LEFT OUTER JOIN (
            SELECT
              C.METHOD_AC,
              C.VALUE,
              P.NAME,
              C.CREATED_ON,
              ROW_NUMBER() OVER (PARTITION BY METHOD_AC ORDER BY C.CREATED_ON DESC) R
            FROM INTERPRO.METHOD_COMMENT C
            INNER JOIN INTERPRO.USER_PRONTO P ON C.USERNAME = P.USERNAME
        ) C ON (M.METHOD_AC = C.METHOD_AC AND C.R = 1)
        WHERE M.DBCODE = :1
    """

    params = [dbcode]

    if search is not None:
        sql += " AND M.METHOD_AC LIKE :2"
        params.append(search + '%')

    if integrated:
        sql += " AND EM.ENTRY_AC IS NOT NULL"
    elif integrated is False:
        sql += " AND EM.ENTRY_AC IS NULL"

    if checked:
        sql += " AND E.CHECKED = 'Y'"
    elif checked is False:
        sql += " AND E.CHECKED = 'N'"

    if commented:
        sql += " AND C.VALUE IS NOT NULL"
    elif commented is False:
        sql += " AND C.VALUE IS NULL"

    cur.execute(sql, params)

    methods = []
    for row in cur:
        methods.append({
            'id': row[0],
            'entryId': row[1],
            'isChecked': row[2] == 'Y',
            'countNow': row[3],
            'countThen': row[4],
            'latestComment': {'text': row[5], 'author': row[6], 'date': row[7].strftime('%Y-%m-%d %H:%M:%S')} if row[5] is not None else None
        })

    cur.close()

    return methods


def get_method_comments(method_ac):
    """
    Get the curator comments associated to a given signature
    """
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT C.ID, C.VALUE, C.CREATED_ON, C.STATUS, U.NAME
        FROM INTERPRO.METHOD_COMMENT C
        INNER JOIN INTERPRO.USER_PRONTO U ON C.USERNAME = U.USERNAME
        WHERE C.METHOD_AC = :1
        ORDER BY C.CREATED_ON DESC
        """,
        (method_ac, )
    )

    comments = []
    for row in cur:
        comments.append({
            'id': row[0],
            'text': row[1],
            'date': row[2].strftime('%Y-%m-%d %H:%M:%S'),
            'status': row[3] == 'Y',
            'author': row[4],
        })

    cur.close()

    return comments


def get_entry_comments(entry_ac):
    """
    Get the curator comments associated to a given entry
    """
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT C.ID, C.VALUE, C.CREATED_ON, C.STATUS, U.NAME
        FROM INTERPRO.ENTRY_COMMENT C
        INNER JOIN INTERPRO.USER_PRONTO U ON C.USERNAME = U.USERNAME
        WHERE C.ENTRY_AC = :1
        ORDER BY C.CREATED_ON DESC
        """,
        (entry_ac, )
    )

    comments = []
    for row in cur:
        comments.append({
            'id': row[0],
            'text': row[1],
            'date': row[2].strftime('%Y-%m-%d %H:%M:%S'),
            'status': row[3] == 'Y',
            'author': row[4],
        })

    cur.close()

    return comments


def add_comment(entry_ac, author, comment, comment_type='entry'):
    if comment_type == 'entry':
        col_name = 'ENTRY_AC'
        table_name = 'ENTRY_COMMENT'
    elif comment_type == 'method':
        col_name = 'METHOD_AC'
        table_name = 'METHOD_COMMENT'
    else:
        return False

    con = get_db()
    cur = con.cursor()

    cur.execute('SELECT MAX(ID) FROM INTERPRO.{}'.format(table_name))
    max_id = cur.fetchone()[0]
    next_id = max_id + 1 if max_id else 1

    try:
        cur.execute(
            """
            INSERT INTO INTERPRO.{} (ID, {}, USERNAME, VALUE)
            VALUES (:1, :2, :3, :4)
            """.format(table_name, col_name),
            (next_id, entry_ac, author, comment)
        )
    except cx_Oracle.IntegrityError:
        status = False
    else:
        status = True
        con.commit()

    cur.close()
    return status


def get_entry(entry_ac):
    cur = get_db().cursor()

    cur.execute(
        """
        SELECT
          E.NAME,
          E.SHORT_NAME,
          E.ENTRY_TYPE,
          ET.ABBREV,
          E.CHECKED,
          (SELECT COUNT(*) FROM INTERPRO.MV_ENTRY2PROTEIN MVEP WHERE MVEP.ENTRY_AC = :1),
          E.CREATED,
          E.TIMESTAMP
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.CV_ENTRY_TYPE ET ON E.ENTRY_TYPE = ET.CODE
        LEFT OUTER JOIN INTERPRO.MV_ENTRY_MATCH EM ON E.ENTRY_AC = EM.ENTRY_AC
        WHERE E.ENTRY_AC = :1
        """,
        (entry_ac,)
    )

    row = cur.fetchone()

    if not row:
        # Might be a secondary accession
        cur.execute(
            """
            SELECT
              E.NAME,
              E.SHORT_NAME,
              E.ENTRY_TYPE,
              ET.ABBREV,
              E.CHECKED,
              (SELECT COUNT(*) FROM INTERPRO.MV_ENTRY2PROTEIN MVEP WHERE MVEP.ENTRY_AC = :1),
              E.CREATED,
              E.TIMESTAMP,
              E.ENTRY_AC
            FROM INTERPRO.ENTRY E
            INNER JOIN INTERPRO.CV_ENTRY_TYPE ET ON E.ENTRY_TYPE = ET.CODE
            LEFT OUTER JOIN INTERPRO.MV_ENTRY_MATCH EM ON E.ENTRY_AC = EM.ENTRY_AC
            INNER JOIN INTERPRO.MV_SECONDARY S ON E.ENTRY_AC = S.ENTRY_AC
            WHERE S.SECONDARY_AC = :1
            """,
            (entry_ac,)
        )

        row = cur.fetchone()
        if not row:
            cur.close()
            return None

        entry_ac = row[8]

    entry = {
        'id': entry_ac,
        'name': row[0],
        'shortName': row[1],
        'typeCode': row[2],
        'type': row[3],
        'isChecked': row[4] == 'Y',
        'proteinCount': row[5],
        'created': row[6].strftime('%Y-%m-%d %H:%M:%S'),
        'modified': row[7].strftime('%Y-%m-%d %H:%M:%S'),
        'methods': [],
        'relationships': {
            'count': 0,
            'types': {
                'parents': [],
                'children': [],
                'containers': [],
                'components': []
            }
        },
        'go': [],
        'description': None,
        'references': {},
        'missingXrefs': []
    }

    # Methods
    cur.execute(
        """
        SELECT
          M.DBCODE,
          M.METHOD_AC,
          M.NAME,
          NVL(MM.PROTEIN_COUNT, 0)
        FROM INTERPRO.METHOD M
        INNER JOIN INTERPRO.ENTRY2METHOD E2M ON M.METHOD_AC = E2M.METHOD_AC
        LEFT OUTER JOIN INTERPRO.MV_METHOD_MATCH MM ON M.METHOD_AC = MM.METHOD_AC
        WHERE E2M.ENTRY_AC = :1
        ORDER BY M.METHOD_AC
        """,
        (entry_ac, )
    )

    for row in cur:
        dbcode = row[0]
        method_ac = row[1]
        name = row[2]
        count = row[3]

        dbname = None
        home = None
        link = None

        db = xref.find_ref(dbcode, method_ac)
        if db:
            dbname = db.name
            home = db.home
            link = db.gen_link()

        entry['methods'].append({
            'dbname': dbname,
            'home': home,
            'link': link,
            'id': method_ac,
            'name': name,
            'count': count
        })

    # Relationships
    # Parents
    cur.execute(
        """
        SELECT
          E.ENTRY_AC,
          E.NAME,
          E.CHECKED,
          E.ENTRY_TYPE
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.ENTRY2ENTRY EE ON EE.PARENT_AC = E.ENTRY_AC
        WHERE EE.ENTRY_AC = :1
        """,
        (entry_ac,)
    )

    for row in cur:
        entry['relationships']['types']['parents'].append({
            'id': row[0],
            'name': row[1],
            'checked': row[2] == 'Y',
            'typeCode': row[3]
        })

    # Children
    cur.execute(
        """
        SELECT
          E.ENTRY_AC,
          E.NAME,
          E.CHECKED,
          E.ENTRY_TYPE
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.ENTRY2ENTRY EE ON EE.ENTRY_AC = E.ENTRY_AC
        WHERE EE.PARENT_AC = :1
        """,
        (entry_ac,)
    )

    for row in cur:
        entry['relationships']['types']['children'].append({
            'id': row[0],
            'name': row[1],
            'checked': row[2] == 'Y',
            'typeCode': row[3]
        })

    # Containers
    cur.execute(
        """
        SELECT
          E.ENTRY_AC,
          E.NAME,
          E.CHECKED,
          E.ENTRY_TYPE
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.ENTRY2COMP EC ON EC.ENTRY1_AC = E.ENTRY_AC
        WHERE EC.ENTRY2_AC = :1
        """,
        (entry_ac,)
    )

    for row in cur:
        entry['relationships']['types']['containers'].append({
            'id': row[0],
            'name': row[1],
            'checked': row[2] == 'Y',
            'typeCode': row[3]
        })

    # Components
    cur.execute(
        """
        SELECT
          E.ENTRY_AC,
          E.NAME,
          E.CHECKED,
          E.ENTRY_TYPE
        FROM INTERPRO.ENTRY E
        INNER JOIN INTERPRO.ENTRY2COMP EC ON EC.ENTRY2_AC = E.ENTRY_AC
        WHERE EC.ENTRY1_AC = :1
        """,
        (entry_ac,)
    )

    for row in cur:
        entry['relationships']['types']['components'].append({
            'id': row[0],
            'name': row[1],
            'checked': row[2] == 'Y',
            'typeCode': row[3]
        })

    entry['relationships']['count'] = sum([len(e) for e in entry['relationships']['types'].values()])

    # GO annotations
    cur.execute(
        """
        SELECT DISTINCT
          GT.GO_ID,
          GT.CATEGORY,
          GT.NAME
        FROM GO.TERMS@GOAPRO GT
        INNER JOIN (
          SELECT GS.GO_ID
          FROM INTERPRO.INTERPRO2GO I2G
          INNER JOIN GO.SECONDARIES@GOAPRO GS ON I2G.GO_ID = GS.SECONDARY_ID
          WHERE I2G.ENTRY_AC = :1
          UNION
          SELECT GT.GO_ID
          FROM INTERPRO.INTERPRO2GO I2G
          INNER JOIN GO.TERMS@GOAPRO GT ON I2G.GO_ID = GT.GO_ID
          WHERE I2G.ENTRY_AC = :1
        ) GS
        ON GS.GO_ID = GT.GO_ID
        """,
        (entry_ac,)
    )

    entry['go'] = [dict(zip(['id', 'category', 'name'], row)) for row in cur]

    # References
    cur.execute(
        """
        SELECT
          DISTINCT (C.PUB_ID),
          C.TITLE,
          C.YEAR,
          C.VOLUME,
          C.RAWPAGES,
          C.DOI_URL,
          C.PUBMED_ID,
          C.ISO_JOURNAL,
          C.AUTHORS
        FROM INTERPRO.CITATION C
        WHERE C.PUB_ID IN (
          SELECT PUB_ID
          FROM INTERPRO.ENTRY2PUB
          WHERE ENTRY_AC = :1
          UNION
          SELECT M.PUB_ID
          FROM INTERPRO.METHOD2PUB M
          INNER JOIN INTERPRO.ENTRY2METHOD E ON E.METHOD_AC = M.METHOD_AC
          WHERE ENTRY_AC = :1
          UNION
          SELECT PUB_ID
          FROM INTERPRO.PDB_PUB_ADDITIONAL
          WHERE ENTRY_AC = :1
          UNION
          SELECT SUPPLEMENTARY_REF.PUB_ID
          FROM INTERPRO.SUPPLEMENTARY_REF
          WHERE ENTRY_AC = :1
        )
        """,
        (entry_ac, )
    )

    columns = ('id', 'title', 'year', 'volume', 'pages', 'doi', 'pmid', 'journal', 'authors')
    references = {row[0]: dict(zip(columns, row)) for row in cur}

    # Description
    cur.execute(
        """
        SELECT A.TEXT
        FROM INTERPRO.COMMON_ANNOTATION A
        INNER JOIN INTERPRO.ENTRY2COMMON E ON A.ANN_ID = E.ANN_ID
        WHERE E.ENTRY_AC = :1
        ORDER BY E.ORDER_IN
        """,
        (entry_ac,)
    )

    missing_refs = []
    description = ''

    for row in cur:
        text = row[0]

        # # Disabled for not breaking the <pre> tags
        # text = re.sub(r'\s{2,}', ' ', text)

        # Wrap text in paragraph
        # (not that it's better, but some annotations already contain the <p> tag)
        if text[:3].lower() != '<p>':
            text = '<p>' + text
        if text[-4:].lower() != '</p>':
            text += '</p>'

        # Find references and replace <cite id="PUBXXXX"/> by #PUBXXXX
        for m in re.finditer(r'<cite\s+id="(PUB\d+)"\s*/>', text):
            ref = m.group(1)
            text = text.replace(m.group(0), '#' + ref)

            if ref not in references:
                missing_refs.append(ref)

        # Find cross-references
        for m in re.finditer(r'<dbxref\s+db\s*=\s*"(\w+)"\s+id\s*=\s*"([\w\.\-]+)"\s*\/>', text):
            match = m.group(0)
            dbcode = m.group(1).upper()
            xref_id = m.group(2)

            url = xref.find_xref(dbcode)
            if url:
                url = url.format(xref_id)
                text = text.replace(match, '<a href="{}">{}</a>'.format(url, xref_id))
            else:
                entry['missingXrefs'].append({
                    'db': dbcode,
                    'id': xref_id
                })

        for m in re.finditer(r'<taxon\s+tax_id="(\d+)">([^<]+)</taxon>', text):
            text = text.replace(
                m.group(0),
                '<a href="http://www.uniprot.org/taxonomy/{}">{}</a>'.format(m.group(1), m.group(2))
            )

        description += text

    if missing_refs:
        # For some entries, the association entry-citation is missing in the INTERPRO.ENTRY2PUB

        missing_refs = list(set(missing_refs))
        cur.execute(
            """
            SELECT
              DISTINCT (PUB_ID),
              TITLE,
              YEAR,
              VOLUME,
              RAWPAGES,
              DOI_URL,
              PUBMED_ID,
              ISO_JOURNAL,
              AUTHORS
            FROM INTERPRO.CITATION
            WHERE PUB_ID IN ({})
            """.format(','.join([':' + str(i+1) for i in range(len(missing_refs))])),
            missing_refs
        )

        columns = ('id', 'title', 'year', 'volume', 'pages', 'doi', 'pmid', 'journal', 'authors')
        references.update({row[0]: dict(zip(columns, row)) for row in cur})

    cur.close()

    for block in re.findall(r'\[\s*#PUB\d+(?:\s*,\s*#PUB\d+)*\s*\]', description):
        refs = re.findall(r'#(PUB\d+)', block)

        description = description.replace(block, '<cite id="{}"/>'.format(','.join(refs)))

    entry.update({
        'description': description,
        'references': {
            'values': references,
            'count': len(references)
        }
    })

    return entry


def get_protein(protein_ac):
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT
          P.NAME,
          P.LEN,
          P.DBCODE,
          P.TAX_ID,
          E.FULL_NAME,
          E.SCIENTIFIC_NAME
        FROM {0}.PROTEIN P
        LEFT OUTER JOIN {0}.ETAXI E ON P.TAX_ID = E.TAX_ID
        WHERE PROTEIN_AC = :1
        """.format(app.config['DB_SCHEMA']),
        (protein_ac, )
    )

    row = cur.fetchone()

    if not row:
        return None

    protein = {
        'id': protein_ac,
        'name': row[0],
        'length': row[1],
        'isReviewed': row[2] == 'S',
        'link': ('http://sp.isb-sib.ch/uniprot/' if row[2] == 'S' else 'http://www.uniprot.org/uniprot/') + protein_ac,
        'taxon': {
            'id': row[3],
            'fullName': row[4],
            'scientificName': row[5]
        }
    }

    cur.execute(
        """
        SELECT
          E.ENTRY_AC,
          E.NAME,
          E.ENTRY_TYPE,
          CET.ABBREV,
          E2E.PARENT_AC,
          MA.METHOD_AC,
          ME.NAME,
          MA.DBCODE,
          MA.POS_FROM,
          MA.POS_TO
        FROM {}.MATCH MA
        INNER JOIN INTERPRO.METHOD ME ON MA.METHOD_AC = ME.METHOD_AC
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD E2M ON MA.METHOD_AC = E2M.METHOD_AC
        LEFT OUTER JOIN INTERPRO.ENTRY E ON E2M.ENTRY_AC = E.ENTRY_AC
        LEFT OUTER JOIN INTERPRO.CV_ENTRY_TYPE CET ON CET.CODE = E.ENTRY_TYPE
        LEFT OUTER JOIN INTERPRO.ENTRY2ENTRY E2E ON E.ENTRY_AC = E2E.ENTRY_AC
        WHERE MA.PROTEIN_AC = :1
        """.format(app.config['DB_SCHEMA']),
        (protein_ac, )
    )

    entries = {}
    for row in cur:
        entry_ac = row[0]

        try:
            entries[entry_ac]
        except KeyError:
            entries[entry_ac] = {
                'id': entry_ac,
                'name': row[1],
                'typeCode': row[2],
                'type': row[3],
                'parent': row[4],
                'methods': {}
            }
        finally:
            methods = entries[entry_ac]['methods']

        method_ac = row[5]
        try:
            methods[method_ac]
        except KeyError:
            db = xref.find_ref(dbcode=row[7], ac=method_ac)

            methods[method_ac] = {
                'id': method_ac,
                'name': row[6],
                'db': {
                    'name': db.name,
                    'link': db.gen_link(),
                    'color': db.color
                },
                'matches': []
            }
        finally:
            methods[method_ac]['matches'].append({'start': row[8], 'end': row[9]})

    for entry_ac in entries:
        entries[entry_ac]['methods'] = list(entries[entry_ac]['methods'].values())

    # Structural features and predictions
    cur.execute(
        """
        SELECT
          MS.DBCODE,
          MS.DOMAIN_ID,
          SC.FAM_ID,
          MS.POS_FROM,
          MS.POS_TO
        FROM INTERPRO.MATCH_STRUCT MS
        INNER JOIN INTERPRO.STRUCT_CLASS SC ON MS.DOMAIN_ID = SC.DOMAIN_ID
        WHERE MS.PROTEIN_AC = :1
        """,
        (protein_ac, )
    )

    structs = {}
    for dbcode, domain_id, fam_id, start, end in cur:
        try:
            structs[fam_id]
        except KeyError:
            db = xref.find_ref(dbcode=dbcode, ac=fam_id)

            structs[fam_id] = {
                'id': fam_id,
                'db': {
                    'name': db.name,
                    'link': db.gen_link(),
                    'color': db.color
                },
                'matches': []
            }
        finally:
            structs[fam_id]['matches'].append({'start': start, 'end': end})

    cur.close()

    protein.update({
        'entries': list(entries.values()),
        'structures': list(structs.values())
    })

    return protein


def get_db():
    """
    Opens a new database connection if there is none yet for the current application context.
    """

    if not hasattr(g, 'oracle_db'):
        user = get_user()
        try:
            credentials = user['dbuser'] + '/' + user['password']
        except (TypeError, KeyError):
            credentials = app.config['DATABASE_USER']
        finally:
            uri = credentials + '@' + app.config['DATABASE_HOST']

        g.oracle_db = cx_Oracle.connect(uri)
    return g.oracle_db


@app.teardown_appcontext
def close_db(error):
    """
    Closes the database at the end of the request.
    """

    if hasattr(g, 'oracle_db'):
        g.oracle_db.close()


def get_user():
    """
    Get the user for the current request.
    """

    if not hasattr(g, 'user'):
        g.user = session.get('user')
    return g.user


def verify_user(username, password):
    """
    Authenticates a user with the provided credentials.
    """

    # Check the user account exists and is active
    con1 = get_db()
    cur = con1.cursor()
    cur.execute(
        """
        SELECT USERNAME, NAME, DB_USER, IS_ACTIVE FROM INTERPRO.USER_PRONTO WHERE LOWER(USERNAME) = :1
        """,
        (username.lower(), )
    )

    row = cur.fetchone()

    if not row:
        user = None
    else:
        username, name, db_user, is_active = row
        is_active = is_active == 'Y'

        user = {
            'username': username,
            'name': name,
            'dbuser': db_user,
            'active': is_active,
            'password': password,
            'status': False
        }

        if is_active:
            try:
                con2 = cx_Oracle.connect(
                    user=db_user,
                    password=password,
                    dsn=app.config['DATABASE_HOST']
                )
            except cx_Oracle.DatabaseError:
                pass
            else:
                con2.close()
                user['status'] = True

                # Update user activity
                cur.execute(
                    """
                    UPDATE INTERPRO.USER_PRONTO
                    SET LAST_ACTIVITY = SYSDATE
                    WHERE USERNAME = :1
                    """,
                    (username,)
                )

                con1.commit()

    cur.close()

    return user


def login_required(f):
    """
    Decorator for endpoints that require users to be logged in
    """
    def wrap(*args, **kwargs):
        if get_user():
            return f(*args, **kwargs)
        return redirect(url_for('log_in', next=request.url))

    return wrap


@app.route('/')
def index():
    """Home page."""
    return render_template('main.html', user=get_user())


@app.route('/login', methods=['GET', 'POST'])
def log_in():
    """Login page. Display a form on GET, and test the credentials on POST."""
    if get_user():
        return redirect(url_for('index'))
    elif request.method == 'GET':
        return render_template('login.html', referrer=request.referrer)
    else:
        username = request.form['username'].strip().lower()
        password = request.form['password'].strip()
        user = verify_user(username, password)

        if user and user['active'] and user['status']:
            session.permanent = True
            session['user'] = user
            return redirect(request.args.get('next', url_for('index')))
        else:
            msg = 'Wrong username or password.'
            return render_template(
                'login.html',
                username=username,
                error=msg,
                referrer=request.args.get('next', url_for('index'))
            )


@app.route('/logout/')
def log_out():
    """Clear the cookie, which logs the user out."""
    session.clear()
    return redirect(request.referrer)


@app.route('/db/<dbshort>/')
def view_db(dbshort):
    return render_template('main.html', user=get_user())


@app.route('/entry/<entry_ac>/')
def view_entry(entry_ac):
    return render_template('main.html', user=get_user())


@app.route('/protein/<protein_ac>/')
def view_protein(protein_ac):
    return render_template('main.html', user=get_user())


@app.route('/method/<method_ac>/')
def view_method(method_ac):
    return render_template('main.html', user=get_user())


@app.route('/methods/<path:methods>/matches/')
@app.route('/methods/<path:methods>/taxonomy/')
@app.route('/methods/<path:methods>/descriptions/')
@app.route('/methods/<path:methods>/comments/')
@app.route('/methods/<path:methods>/go/')
@app.route('/methods/<path:methods>/matrices/')
def view_compare(methods):
    return render_template('main.html', user=get_user(), topics=get_topics())


@app.route('/search/')
def view_search():
    return render_template('main.html', user=get_user())


@app.route('/api/search/')
def api_search():
    """
    Search a given string.
    Can be an InterPro accession ("IPR" is optional), a signature accession, or a protein accession.
    Example:
    ---
    /search?query=IPR000001
    """
    search = request.args.get('query', '')

    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1

    entry_accs = []
    methods_accs = []
    proteins_accs = []
    cur = get_db().cursor()

    for term in search.split():
        try:
            term = int(term)
        except ValueError:
            pass
        else:
            term = 'IPR{:06d}'.format(term)

        cur.execute('SELECT ENTRY_AC FROM INTERPRO.ENTRY WHERE ENTRY_AC = :1', (term.upper(),))
        row = cur.fetchone()
        if row:
            entry_accs.append(row[0])
            continue

        cur.execute('SELECT METHOD_AC from INTERPRO.METHOD WHERE UPPER(METHOD_AC) = :1', (term.upper(),))
        row = cur.fetchone()
        if row:
            methods_accs.append(row[0])
            continue

        cur.execute(
            'SELECT PROTEIN_AC from {}.PROTEIN WHERE PROTEIN_AC = :1'.format(app.config['DB_SCHEMA']),
            (term.upper(),)
        )
        row = cur.fetchone()
        if row:
            proteins_accs.append(row[0])
            continue

    page_size = 20
    params = urllib.parse.urlencode({
        'query': search,
        'format': 'json',
        'size': page_size,
        'start': (page - 1) * page_size
    })

    try:
        req = urllib.request.urlopen('http://www.ebi.ac.uk/ebisearch/ws/rest/interpro?{}'.format(params))
        res = json.loads(req.read().decode())
    except (urllib.error.HTTPError, json.JSONDecodeError):
        hits = []
        hit_count = 0
    else:
        hit_count = res['hitCount']
        hits = [e['id'] for e in res['entries']]

    if hits:
        cur.execute(
            """
            SELECT ENTRY_AC, ENTRY_TYPE, NAME
            FROM INTERPRO.ENTRY
            WHERE ENTRY_AC IN ({})
            """.format(','.join([':' + str(i+1) for i in range(len(hits))])),
            hits
        )

        names = {entry_ac: (name, entry_type) for entry_ac, entry_type, name in cur}
        hits = [{'id': entry_ac, 'name': names[entry_ac][0], 'type': names[entry_ac][1]} for entry_ac in hits]

    cur.close()

    return jsonify({
        'entries': list(sorted(set(entry_accs))),
        'methods': list(sorted(set(methods_accs))),
        'proteins': proteins_accs,

        'ebiSearch': {
            'hits': hits,
            'hitCount': hit_count,
            'page': page,
            'pageSize': page_size
        }
    })

    if s == 0:
        # No matches
        r['error'] = 'Your search returned no matches.'
    elif s > 1:
        # Ambiguous
        r['error'] = 'Your search returned no matches.'
    elif len(entries) == 1:
        # InterPro entry
        r.update({
            'status': True,
            'url': '/entry/{}'.format(entries[0]),
        })
    elif len(proteins) == 1:
        r.update({
            'status': True,
            'url': '/protein/{}'.format(proteins[0]),
        })
    elif len(methods) > 1:
        r.update({
            'status': True,
            'url': '/methods/{}'.format('/'.join(methods)),
        })
    elif len(methods) == 1:
        r.update({
            'status': True,
            'url': '/method/{}'.format(methods[0]),
        })
    else:
        # Ambiguous again (e.g. multiple InterPro entries)
        r['error'] = 'Your search returned no matches.'

    return jsonify(r)


@app.route('/api/comment/<comment_type>/<comment_id>/',  strict_slashes=False, methods=['POST'])
def api_flag_comment(comment_type, comment_id):
    user = get_user()

    if not user:
        return jsonify({
            'status': False,
            'message': 'Please log in to perform this action.'
        }), 401

    if comment_type == 'entry':
        table_name = 'ENTRY_COMMENT'
    elif comment_type == 'method':
        table_name = 'METHOD_COMMENT'
    else:
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    try:
        comment_id = int(comment_id)
        status = 'Y' if bool(int(request.form['status'])) else 'N'
    except (KeyError, ValueError):
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    con = get_db()
    cur = con.cursor()
    try:
        cur.execute(
            'UPDATE INTERPRO.{} SET STATUS = :1 WHERE ID = :2'.format(table_name),
            (status, comment_id)
        )
    except cx_Oracle.DatabaseError as e:
        cur.close()
        return jsonify({
            'status': False,
            'message': 'Could not {}flag: {}.'.format(
                'un' if status else '',
                e
            )
        }), 400
    else:
        con.commit()
        cur.close()
        return jsonify({
            'status': True,
            'message': None
        })


@app.route('/api/protein/<protein_ac>/')
def api_protein(protein_ac):
    r = {
        'status': False,
        'result': None,
        'error': None
    }

    protein = get_protein(protein_ac)

    if protein:
        r.update({
            'status': True,
            'result': protein
        })
    else:
        r['error'] = 'The protein <strong>{}</strong> does not exist.'.format(protein_ac)

    return jsonify(r)


@app.route('/api/entry/<entry_ac>/')
def api_entry(entry_ac):
    r = {
        'status': False,
        'result': None,
        'error': None
    }

    try:
        entry = get_entry(entry_ac)
    except:
        r['error'] = 'An error occurred while searching for <strong>{}</strong>.'.format(entry_ac)
    else:
        if entry:
            r.update({
                'status': True,
                'result': entry
            })
        else:
            r['error'] = 'The entry <strong>{}</strong> does not exist.'.format(entry_ac)
    finally:
        return jsonify(r)


@app.route('/api/entry/<entry_ac>/check/', strict_slashes=False, methods=['POST'])
def api_check_entry(entry_ac):
    user = get_user()

    if not user:
        return jsonify({
            'status': False,
            'message': 'Please log in to perform this action.'
        }), 401

    try:
        is_checked = 'Y' if bool(int(request.form['checked'])) else 'N'
    except (KeyError, ValueError):
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    con = get_db()
    cur = con.cursor()
    try:
        cur.execute(
            'UPDATE INTERPRO.ENTRY SET CHECKED = :1 WHERE ENTRY_AC = :2',
            (is_checked, entry_ac)
        )
    except cx_Oracle.DatabaseError as e:
        cur.close()
        return jsonify({
            'status': False,
            'message': 'Could not {}check entry {}: {}.'.format(
                '' if is_checked else 'un',
                entry_ac,
                e
            )
        }), 400
    else:
        con.commit()
        cur.close()
        return jsonify({
            'status': True,
            'message': None
        })


@app.route('/api/entry/<entry_ac>/comments/')
def api_entry_comments(entry_ac):
    comments = get_entry_comments(entry_ac)
    count = len(comments)

    try:
        size = int(request.args['size'])
    except (KeyError, ValueError):
        pass
    else:
        comments = comments[:size]

    for c in comments:
        c['text'] = re.sub(
            r'#(\d+)',
            r'<a href="https://github.com/geneontology/go-annotation/issues/\1">#\1</a>',
            c['text']
        )

    return jsonify({
        'count': count,
        'results': comments
    })


@app.route('/api/entry/<entry_ac>/comment/', strict_slashes=False, methods=['POST'])
def api_entry_comment(entry_ac):
    user = get_user()

    if not user:
        return jsonify({
            'status': False,
            'message': 'Please log in to perform this action.'
        }), 401

    try:
        comment = request.form['comment'].strip()
    except (AttributeError, KeyError):
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    if len(comment) < 3:
        return jsonify({
            'status': False,
            'message': 'Comment too short (must be at least three characters long).'
        }), 400
    elif not add_comment(entry_ac, user['username'], comment, comment_type='entry'):
        return jsonify({
            'status': False,
            'message': 'Could not add comment for signature "{}".'.format(entry_ac)
        }), 400

    return jsonify({
        'status': True,
        'message': None
    })


@app.route('/api/method/<method_ac>/prediction/')
def api_prediction(method_ac):
    """
    Signature prediction
    Example:
    ---
    /method/prediction/PF00051
    """
    methods = get_overlapping_entries(method_ac)
    return jsonify({
        'results': methods,
        'count': len(methods)
    })


@app.route('/api/method/<method_ac>/comment/', strict_slashes=False, methods=['POST'])
def api_method_comment(method_ac):
    """

    Example:
    ---

    """
    user = get_user()

    if not user:
        return jsonify({
            'status': False,
            'message': 'Please log in to perform this action.'
        }), 401

    try:
        comment = request.form['comment'].strip()
    except (AttributeError, KeyError):
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    if len(comment) < 3:
        return jsonify({
            'status': False,
            'message': 'Comment too short (must be at least three characters long).'
        }), 400
    elif not add_comment(method_ac, user['username'], comment, comment_type='method'):
        return jsonify({
            'status': False,
            'message': 'Could not add comment for signature "{}".'.format(method_ac)
        }), 400

    return jsonify({
        'status': True,
        'message': None
    })


@app.route('/api/method/<method_ac>/comments/')
def api_method_comments(method_ac):
    comments = get_method_comments(method_ac)
    count = len(comments)

    try:
        size = int(request.args['size'])
    except (KeyError, ValueError):
        pass
    else:
        comments = comments[:size]

    return jsonify({
        'count': count,
        'results': comments
    })


@app.route('/api/method/<method_ac>/references/<go_id>')
def api_method_references(method_ac, go_id):
    references = []

    cur = get_db().cursor()

    # cur.execute(
    #     """
    #     SELECT DISTINCT P2G.REF_DB_ID
    #     FROM (
    #       SELECT DISTINCT TERM_GROUP_ID, SEQ_ID
    #       FROM INTERPRO_ANALYSIS.FEATURE2PROTEIN
    #       WHERE FEATURE_ID = :1
    #     ) F2P
    #     INNER JOIN INTERPRO_ANALYSIS.TERM_GROUP2TERM G2T ON F2P.TERM_GROUP_ID = G2T.TERM_GROUP_ID
    #     INNER JOIN INTERPRO_ANALYSIS.PROTEIN2GO_MANUAL P2G ON G2T.GO_ID = P2G.GO_ID AND F2P.SEQ_ID = P2G.PROTEIN_AC
    #     WHERE P2G.GO_ID = :2 AND P2G.REF_DB_CODE = 'PMID'
    #     ORDER BY P2G.REF_DB_ID
    #     """,
    #     (method_ac, go_id)
    # )
    #
    # references = [{'id': row[0]} for row in cur]

    cur.execute(
        """
        SELECT DISTINCT PUB.ID, PUB.TITLE, PUB.FIRST_PUBLISH_DATE
        FROM (
          SELECT DISTINCT TERM_GROUP_ID, SEQ_ID
          FROM {0}.FEATURE2PROTEIN
          WHERE FEATURE_ID = :1
        ) F2P
        INNER JOIN {0}.TERM_GROUP2TERM G2T ON F2P.TERM_GROUP_ID = G2T.TERM_GROUP_ID
        INNER JOIN {0}.PROTEIN2GO_MANUAL P2G ON G2T.GO_ID = P2G.GO_ID AND F2P.SEQ_ID = P2G.PROTEIN_AC
        INNER JOIN GO.PUBLICATIONS@GOAPRO PUB ON PUB.ID = P2G.REF_DB_ID
        WHERE P2G.GO_ID = :2 AND P2G.REF_DB_CODE = 'PMID'
        ORDER BY PUB.FIRST_PUBLISH_DATE
        """.format(app.config['DB_SCHEMA']),
        (method_ac, go_id)
    )

    references = []
    for row in cur:
        references.append({
            'id': row[0],
            'title': row[1],
            'date': row[2].strftime('%d %b %Y')
        })

    cur.close()

    return jsonify({
        'count': len(references),
        'results': references
    })


@app.route('/api/method/<method_ac>/proteins/all/')
def get_method_proteins(method_ac):
    try:
        db = request.args['db'].upper()
    except KeyError:
        db = None

    if db in ('S', 'T'):
        params = (method_ac, db)
        db_cond = 'AND DB = :2'
    else:
        params = (method_ac,)
        db_cond = ''

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT
          F.SEQ_ID,
          P.DBCODE,
          P.LEN,
          P.NAME,
          PI.DESCRIPTION,
          E.TAX_ID,
          E.FULL_NAME
        FROM (
          SELECT SEQ_ID
          FROM {0}.FEATURE2PROTEIN
          WHERE FEATURE_ID = :1
          {1}
        ) F
        INNER JOIN {0}.PROTEIN P ON F.SEQ_ID = P.PROTEIN_AC
        INNER JOIN {0}.PROTEIN_INFO PI ON F.SEQ_ID = PI.PROTEIN_AC
        INNER JOIN {0}.ETAXI E ON P.TAX_ID = E.TAX_ID
        ORDER BY F.SEQ_ID
        """.format(app.config['DB_SCHEMA'], db_cond),
        params
    )

    proteins = []
    for row in cur:
        if row[1] == 'S':
            url = 'http://sp.isb-sib.ch/uniprot/'
        else:
            url = 'http://www.uniprot.org/uniprot/'

        proteins.append({
            'id': row[0],
            'link': url + row[0],
            'isReviewed': row[1] == 'S',
            'length': row[2],
            'shortName': row[3],
            'name': row[4],
            'taxon': {'id': row[5], 'fullName': row[6]},
            'matches': None
        })

    cur.close()
    return jsonify({
        'list': [p['id'] for p in proteins],
        'results': proteins,
        'maxLength': 0,
        'count': len(proteins),
        'pageInfo': {
            'page': 1,
            'pageSize': len(proteins)
        }
    })


@app.route('/api/method/<method_ac>/proteins/')
def api_method_proteins(method_ac):
    try:
        taxon_id = int(request.args['taxon'])
    except (KeyError, ValueError):
        taxon_id = 1
    finally:
        taxon = get_taxon(taxon_id)

    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1
    else:
        if page < 1:
            page = 1

    try:
        page_size = int(request.args['pageSize'])
    except (KeyError, ValueError):
        page_size = 25
    else:
        if page_size < 1:
            page_size = 25

    try:
        desc_id = int(request.args['description'])
    except (KeyError, ValueError):
        desc_id = None

    try:
        topic_id = int(request.args['topic'])
        comment_id = int(request.args['comment'])
    except (KeyError, ValueError):
        topic_id = None
        comment_id = None

    try:
        go_id = request.args['term']
    except KeyError:
        go_id = None

    try:
        db = request.args['db'].upper()
    except KeyError:
        db = None
    else:
        db = db if db in ('S', 'T') else None

    search = request.args.get('search', '').strip()
    if not search:
        search = None

    sql, params = build_method2protein_sql(
        methods={method_ac: None},
        taxon=taxon,
        description=desc_id,
        topic=topic_id,
        comment=comment_id,
        term=go_id,
        db=db,
        search=search
    )

    cur = get_db().cursor()
    # cur.execute('SELECT COUNT(*) FROM ({})'.format(sql), params)
    # count = cur.fetchone()[0]
    # proteins_all = []

    cur.execute('SELECT SEQ_ID FROM ({})'.format(sql), params)
    proteins_all = [row[0] for row in cur]
    count = len(proteins_all)

    params['i_start'] = 1 + (page - 1) * page_size
    params['i_end'] = page * page_size
    params['method_ac'] = method_ac

    cur.execute(
        """
        SELECT P.PROTEIN_AC, P.DBCODE, P.LEN, P.NAME, PI.DESCRIPTION, E.TAX_ID, E.FULL_NAME, MS.POS_FROM, MS.POS_TO
        FROM {0}.PROTEIN P
        INNER JOIN (
            SELECT *
            FROM (
                SELECT F.*, ROWNUM RN
                FROM (
                    {1}
                    ORDER BY F2P.SEQ_ID
                  ) F
                WHERE ROWNUM <= :i_end
            ) WHERE RN >= :i_start

        ) F ON P.PROTEIN_AC = F.SEQ_ID
        INNER JOIN {0}.PROTEIN_INFO PI ON P.PROTEIN_AC = PI.PROTEIN_AC
        INNER JOIN {0}.ETAXI E ON P.TAX_ID = E.TAX_ID
        INNER JOIN {0}.MATCH_SUMMARY MS ON PI.PROTEIN_AC = MS.SEQ_ID
        WHERE MS.FEATURE_ID = :method_ac
        ORDER BY P.PROTEIN_AC
        """.format(app.config['DB_SCHEMA'], sql),
        params
    )

    proteins = {}
    max_length = 0
    for row in cur:
        protein_ac = row[0]

        if protein_ac not in proteins:
            if row[1] == 'S':
                url = 'http://sp.isb-sib.ch/uniprot/'
            else:
                url = 'http://www.uniprot.org/uniprot/'

            proteins[protein_ac] = {
                'id': protein_ac,
                'link': url + protein_ac,
                'isReviewed': row[1] == 'S',
                'length': row[2],
                'shortName': row[3],
                'name': row[4],
                'taxon': {'id': row[5], 'fullName': row[6]},
                'matches': []
            }

            if row[2] > max_length:
                max_length = row[2]

        proteins[protein_ac]['matches'].append({
            'start': row[7],
            'end': row[8]
        })

    cur.close()
    return jsonify({
        'list': sorted(proteins_all),
        'results': sorted(proteins.values(), key=lambda x: x['id']),
        'maxLength': max_length,
        'count': count,
        'pageInfo': {
            'page': page,
            'pageSize': page_size
        }
    })


@app.route('/api/methods/<path:methods>/matches/')
def api_methods_matches(methods):
    """
    Overlap condensed proteins
    Example:
    ---
    /methods/PF00051/PS50070/SM00130/matches/?page=1&page_size=5
    """
    try:
        taxon_id = int(request.args['taxon'])
    except (KeyError, ValueError):
        taxon_id = 1
    finally:
        taxon = get_taxon(taxon_id)

    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1
    else:
        if page < 1:
            page = 1

    try:
        page_size = int(request.args['pageSize'])
    except (KeyError, ValueError):
        page_size = 5
    else:
        if page_size < 1:
            page_size = 5

    try:
        desc_id = int(request.args['description'])
    except (KeyError, ValueError):
        desc_id = None

    try:
        topic_id = int(request.args['topic'])
        comment_id = int(request.args['comment'])
    except (KeyError, ValueError):
        topic_id = None
        comment_id = None

    try:
        go_id = request.args['term']
    except KeyError:
        go_id = None

    try:
        db = request.args['db'].upper()
    except KeyError:
        db = None
    else:
        db = db if db in ('S', 'T') else None

    code = request.args.get('code')
    force = request.args.get('force', '').split(',')
    exclude = request.args.get('exclude', '').split(',')

    _methods = {}
    for m in methods.split('/'):
        m = m.strip()
        if not len(m):
            continue
        elif m in force:
            _methods[m] = True
        else:
            _methods[m] = None

    _methods.update({m.strip(): False for m in exclude if len(m.strip())})

    proteins, count, max_len = get_overlapping_proteins(
        methods=_methods,
        taxon=taxon,
        page=page,
        page_size=page_size,
        description=desc_id,
        topic=topic_id,
        comment=comment_id,
        term=go_id,
        db=db,
        code=code
    )

    return jsonify({
        'count': count,
        'proteins': proteins,
        'maxLength': max_len,
        'taxon': taxon,
        'database': db,
        'pageInfo': {
            'page': page,
            'pageSize': page_size
        }
    })


@app.route('/api/methods/<path:methods>/taxonomy/')
def api_methods_taxonomy(methods):
    """
    Taxonomic origins
    Example:
    ---
    /taxonomy/MF_00011/PF00709?rank=genus
    """
    try:
        taxon_id = int(request.args['taxon'])
    except (KeyError, ValueError):
        taxon_id = 1
    finally:
        taxon = get_taxon(taxon_id)

    ranks = (
        'superkingdom', 'kingdom', 'phylum', 'class',
        'order', 'family', 'genus', 'species'
    )
    try:
        i = ranks.index(request.args['rank'].lower())
    except (KeyError, ValueError):
        i = 0
    finally:
        rank = ranks[i]

    # try:
    #     i = ranks.index(taxon['rank'])
    # except ValueError:
    #     i = 0
    # else:
    #     try:
    #         ranks[i + 1]
    #     except IndexError:
    #         pass
    #     else:
    #         i += 1
    # finally:
    #     rank = ranks[i]

    taxons, max_cnt = get_taxonomy(methods=methods.split('/'), taxon=taxon, rank=rank)

    return jsonify({
        'taxon': taxon,
        'rank': rank,
        'count': len(taxons),
        'results': taxons,
        'max': max_cnt
    })


@app.route('/api/methods/<path:methods>/descriptions/')
def api_methods_descriptions(methods):
    """
    Protein descriptions
    Example:
    ---
    /methods/PF00051/PS50070/SM00130/descriptions/
    """
    try:
        db = request.args['db'].upper()
    except KeyError:
        db = 'S'
    else:
        if db == 'U':
            db = None
        elif db not in ('S', 'T'):
            db = 'S'

    descriptions = get_descriptions(methods=methods.split('/'), db=db)

    return jsonify({
        'results': descriptions,
        'count': len(descriptions),
        'database': db if db is not None else 'U',
    })


@app.route('/api/methods/<path:methods>/go/')
def api_methods_go(methods):
    """
    GO terms
    Example:
    ---
    /go/MF_00011/PF00709?category=C
    """
    try:
        aspects = [e for e in request.args['aspect'].upper().split(',') if e in ('C', 'P', 'F')]
    except (KeyError, ValueError):
        aspects = None
    else:
        if not aspects:
            aspects = None

    terms, methods = get_go_terms(methods.split('/'), aspects)

    return jsonify({
        'results': terms,
        'count': len(terms),
        'methods': methods,
        'aspects': ('C', 'P', 'F') if aspects is None else aspects,
    })


@app.route('/api/methods/<path:methods>/comments/')
def api_methods_comments(methods):
    """
    Protein comments (Swiss-Prot only)
    Example:
    ---
    /comments/PTHR11846:SF3/PTHR11846:SF2/TIGR00184
    """
    try:
        # todo: accept topic title
        topic_id = int(request.args['topic'])
    except (KeyError, ValueError):
        topic_id = 34

    return jsonify({
        'topic': {
            'id': topic_id,
            'value': get_topic(topic_id)
        },
        'results': get_swissprot_comments(methods.split('/'), topic_id)
    })


@app.route('/api/methods/<path:methods>/matrices/')
def api_methods_matrices(methods):
    """
    Match matrix of overlapping signatures
    Example:
    ---
    /matrix/SSF57440/cd00108/PIRSF500183/PTHR19331:SF315/PTHR44106:SF1
    """
    matrix, max_prot = get_match_matrix(methods.split('/'))
    return jsonify({
        'matrix': matrix,
        'max': max_prot
    })


def has_overlaping_matches(matches1, matches2, min_overlap=0.5):
    for m1 in matches1:
        l1 = m1[1] - m1[0]
        for m2 in matches2:
            l2 = m2[1] - m2[0]
            overlap = min(m1[1], m2[1]) - max(m1[0], m2[0])

            if overlap >= l1 * min_overlap or overlap >= l2 * min_overlap:
                return True

    return False


@app.route('/api/methods/<method_ac1>/<method_ac2>/overlap/')
def api_methods_overlap(method_ac1, method_ac2):
    cur = get_db().cursor()

    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1
    else:
        if page < 1:
            page = 1

    try:
        page_size = int(request.args['pageSize'])
    except (KeyError, ValueError):
        page_size = 10
    else:
        if page_size < 1:
            page_size = 10

    cur.execute(
        """
        SELECT SEQ_ID, FEATURE_ID, POS_FROM, POS_TO
        FROM {0}.MATCH_SUMMARY
        WHERE FEATURE_ID = :1 OR FEATURE_ID = :2
         """.format(app.config['DB_SCHEMA']),
        (method_ac1, method_ac2)
    )

    proteins = {}
    for protein_ac, method_ac, start, end in cur:
        try:
            proteins[protein_ac]
        except KeyError:
            proteins[protein_ac] = {
                'id': protein_ac,
                'methods': {
                    method_ac1: [],
                    method_ac2: []
                }
            }
        finally:
            proteins[protein_ac]['methods'][method_ac].append((start, end))

    overlapping = []
    for protein_ac in sorted(proteins):
        p = proteins[protein_ac]
        matches1 = p['methods'][method_ac1]
        matches2 = p['methods'][method_ac2]

        if has_overlaping_matches(matches1, matches2, min_overlap=0.5):
            overlapping.append(p)

    count = len(overlapping)
    overlapping = overlapping[(page-1)*page_size:page*page_size]

    if count:
        cur.execute(
            """
            SELECT PROTEIN_AC, NAME, LEN, DBCODE
            FROM {0}.PROTEIN
            WHERE PROTEIN_AC IN ({1})
            """.format(
                app.config['DB_SCHEMA'],
                ','.join([':' + str(i+1) for i in range(len(overlapping))])
            ),
            [p['id'] for p in overlapping]
        )

        info = {}
        for row in cur:
            info[row[0]] = {
                'name': row[1],
                'length': row[2],
                'isReviewed': row[3] == 'S'
            }

        for p in overlapping:
            p.update(info[p['id']])

    cur.close()

    return jsonify({
        'count': count,
        'results': overlapping,
        'pageInfo': {
            'page': page,
            'pageSize': page_size
        }
    })


@app.route('/api/description/<int:desc_id>/')
def api_methods_description(desc_id):
    """
    Proteins associated to a description
    Example:
    ---
    /description/403214
    """
    proteins = get_description(desc_id)

    return jsonify({
        'count': len(proteins),
        'results': proteins
    })


@app.route('/api/db/')
def api_db():
    databases = get_db_stats()
    return jsonify({
        'count': len(databases),
        'results': databases
    })


@app.route('/api/db/<dbshort>/')
def api_db_methods(dbshort):
    """

    """
    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1
    else:
        if page < 1:
            page = 1

    try:
        page_size = int(request.args['pageSize'])
    except (KeyError, ValueError):
        page_size = 100
    else:
        if page_size < 1:
            page_size = 100

    search = request.args.get('search', '').strip()
    if not search:
        search = None

    dbname, dbcode, dbversion = get_db_info(dbshort)

    if not dbname:
        return jsonify({
            'results': [],
            'count': 0,
            'database': None
        })

    unint_mode = request.args.get('unintegrated')

    if unint_mode:
        methods = get_unintegrated(dbcode, mode=unint_mode, search=search)
    else:
        try:
            integrated = bool(int(request.args['integrated']))
        except (KeyError, ValueError):
            integrated = None

        try:
            checked = bool(int(request.args['checked']))
        except (KeyError, ValueError):
            checked = None

        try:
            commented = bool(int(request.args['commented']))
        except (KeyError, ValueError):
            commented = None

        methods = get_methods(dbcode, search=search, integrated=integrated, checked=checked, commented=commented)

    return jsonify({
        'pageInfo': {
            'page': page,
            'pageSize': page_size
        },
        'results': methods[(page-1)*page_size:page*page_size],
        'count': len(methods),
        'database': {
            'name': dbname,
            'version': dbversion
        }
    })


@app.route('/api/go/<go_id>/')
def api_go_term(go_id):
    cur = get_db().cursor()

    cur.execute(
        """
        SELECT DISTINCT REF_DB_ID
        FROM {}.PROTEIN2GO_MANUAL
        WHERE GO_ID = :1
        AND EVIDENCE = 'TAS'
        AND REF_DB_CODE = 'PMID'
        ORDER BY REF_DB_ID
        """.format(app.config['DB_SCHEMA']),
        (go_id,)
    )

    references = []
    for row in cur:
        references.append({
            'id': row[0]
        })

    # cur.execute(
    #     """
    #     SELECT DISTINCT P.ID, P.TITLE, P.AUTHORS, P.FIRST_PUBLISH_DATE
    #     FROM (
    #       SELECT DISTINCT ECO_ID, REF_DB_ID
    #       FROM GO.ANNOTATIONS@GOAPRO
    #       WHERE GO_ID = :1
    #       AND REF_DB_CODE = 'PMID'
    #       AND ENTITY_TYPE = 'protein'
    #     ) A
    #     INNER JOIN GO.ECO2EVIDENCE@GOAPRO E ON A.ECO_ID = E.ECO_ID
    #     INNER JOIN GO.PUBLICATIONS@GOAPRO P ON A.REF_DB_ID = P.ID
    #     WHERE E.GO_EVIDENCE = 'TAS'
    #     AND P.IS_RETRACTED = 'N'
    #     ORDER BY P.FIRST_PUBLISH_DATE
    #     """,
    #     (go_id, )
    # )
    #
    # references = []
    # for row in cur:
    #     references.append({
    #         'id': row[0],
    #         'title': row[1],
    #         'authors': row[2],
    #         'date': row[3].strftime('%b %Y'),
    #     })

    cur.close()

    return jsonify({
        'results': references,
        'count': len(references)
    })


@app.route('/api/feed/')
def api_feed():
    try:
        n = int(request.args['n'])
    except (KeyError, ValueError):
        n = 20
    finally:
        feed = get_latest_entries(n)

    return jsonify({
        'count': len(feed),
        'results': feed
    })


if __name__ == '__main__':
    app.run()

