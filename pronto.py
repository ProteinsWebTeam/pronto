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


# TODO: do not hardcode INTERPRO schema, but use synonyms (e.g. MV_ENTRY2PROTEIN is not a synonym yet)
# todo: refactoring: do not use functions if only called once


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
          MIN(DB.DBNAME) DBNAME,
          MIN(DB.DBSHORT),
          MIN(DB.VERSION),
          COUNT(M.METHOD_AC),
          SUM(CASE WHEN E2M.ENTRY_AC IS NOT NULL THEN 1 ELSE 0 END),
          SUM(CASE WHEN E2M.ENTRY_AC IS NULL THEN 1 ELSE 0 END)
        FROM INTERPRO.METHOD M
        LEFT OUTER JOIN {}.CV_DATABASE DB ON M.DBCODE = DB.DBCODE
        LEFT OUTER JOIN INTERPRO.ENTRY2METHOD E2M ON M.METHOD_AC = E2M.METHOD_AC
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
        FROM {}.CV_COMMENT_TOPIC
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
        FROM {}.CV_COMMENT_TOPIC
        ORDER BY TOPIC
        """.format(app.config['DB_SCHEMA'])
    )

    topics = [dict(zip(('id', 'value'), row)) for row in cur]
    cur.close()

    return topics


def build_method2protein_sql(methods, **kwargs):
    taxon = kwargs.get('taxon')
    source_db = kwargs.get('source_db')
    desc_id = kwargs.get('desc_id')
    topic_id = kwargs.get('topic_id')
    comment_id = kwargs.get('comment_id')
    go_id = kwargs.get('go_id')
    ecno = kwargs.get('ecno')
    no_rank = kwargs.get('no_rank')
    search = kwargs.get('search')

    may = []        # Methods that may match the set of returned proteins
    must = []       # Methods that must match a protein for this protein to be selected
    mustnt = []     # Methods that must not match a protein for this protein to be selected
    for acc, status in methods.items():
        if status is None:
            may.append(acc)
        elif status:
            must.append(acc)
        else:
            mustnt.append(acc)

    # Get proteins matched by any of the 'may', and 'must' signatures
    may_cond = ','.join([':may' + str(i) for i in range(len(may + must))])
    params = {'may' + str(i): acc for i, acc in enumerate(may + must)}

    # Exclude proteins that are not matched by any of the 'must' signatures
    if must:
        must_join = """
            INNER JOIN (
                SELECT PROTEIN_AC, COUNT(DISTINCT METHOD_AC) CT
                FROM {}.METHOD2PROTEIN
                WHERE METHOD_AC IN ({})
                GROUP BY PROTEIN_AC
            ) MC ON M2P.PROTEIN_AC = MC.PROTEIN_AC
        """.format(
            app.config['DB_SCHEMA'],
            ','.join([':must' + str(i) for i in range(len(must))])
        )
        must_cond = 'AND MC.CT = :n_must'
        params.update({'must' + str(i): acc for i, acc in enumerate(must)})
        params['n_must'] = len(must)
    else:
        must_join = ''
        must_cond = ''

    # Exclude proteins that are matched by any of the 'mustnt' signatures
    if mustnt:
        mustnt_join = """
            LEFT OUTER JOIN (
                SELECT DISTINCT PROTEIN_AC
                FROM {}.METHOD2PROTEIN
                WHERE METHOD_AC IN ({})
            ) MNC ON M2P.PROTEIN_AC = MNC.PROTEIN_AC
        """.format(
            app.config['DB_SCHEMA'],
            ','.join([':mustnt' + str(i) for i in range(len(mustnt))])
        )
        mustnt_cond = 'AND MNC.PROTEIN_AC IS NULL'
        params.update({'mustnt' + str(i): acc for i, acc in enumerate(mustnt)})
    else:
        mustnt_join = ''
        mustnt_cond = ''

    # Exclude proteins that are not associated to the passed SwissProt topic/comment ID
    if topic_id and comment_id:
        comment_join = 'INNER JOIN {}.PROTEIN_COMMENT PC ON M2P.PROTEIN_AC = PC.PROTEIN_AC'.format(
            app.config['DB_SCHEMA']
        )
        comment_cond = 'AND PC.TOPIC_ID = :topicid AND PC.COMMENT_ID = :commentid'
        params.update({'topicid': topic_id, 'commentid': comment_id})
    else:
        comment_join = ''
        comment_cond = ''

    # Exclude proteins that are not associated to the passed UniProt description
    if desc_id:
        desc_join = 'INNER JOIN {}.PROTEIN_DESC PD ON M2P.PROTEIN_AC = PD.PROTEIN_AC'.format(
            app.config['DB_SCHEMA']
        )
        desc_cond = 'AND PD.DESC_ID = :descid'
        params['descid'] = desc_id
    else:
        desc_join = ''
        desc_cond = ''

    # Exclude proteins that are/aren't reviewed
    if source_db is not None:
        source_cond = 'AND M2P.DBCODE = :sourcedb'
        params['sourcedb'] = source_db
    else:
        source_cond = ''

    # Filter by search (on accession only, not name)
    if search:
        search_cond = 'AND M2P.PROTEIN_AC LIKE :search_like'
        params['search_like'] = search + '%'
    else:
        search_cond = ''

    # Filter by taxon
    if taxon:
        tax_cond = 'AND M2P.LEFT_NUMBER BETWEEN :ln AND :rn'
        params['ln'] = int(taxon['leftNumber'])
        params['rn'] = int(taxon['rightNumber'])
    else:
        tax_cond = ''

    # Exclude proteins that are not associated to the passed GO term ID
    if go_id:
        go_join = 'INNER JOIN {}.PROTEIN2GO P2G ON M2P.PROTEIN_AC = P2G.PROTEIN_AC'.format(
            app.config['DB_SCHEMA']
        )
        go_cond = 'AND P2G.GO_ID = :goid'
        params['goid'] = go_id
    else:
        go_join = ''
        go_cond = ''

    # Exclude proteins that are not associated to the passed EC number
    if ecno:
        ec_join = 'INNER JOIN {}.ENZYME EZ ON M2P.PROTEIN_AC = EZ.PROTEIN_AC'.format(
            app.config['DB_SCHEMA']
        )
        ec_cond = 'AND EZ.ECNO = :ecno'
        params['ecno'] = ecno
    else:
        ec_join = ''
        ec_cond = ''

    # Exclude proteins that are not associated to a taxon of the passed rank
    if no_rank:
        lineage_join = 'LEFT OUTER JOIN {}.LINEAGE L ON M2P.LEFT_NUMBER = L.LEFT_NUMBER AND L.RANK = :rank'.format(
            app.config['DB_SCHEMA']
        )
        lineage_cond = 'AND L.TAX_ID IS NULL'
        params['rank'] = no_rank
    else:
        lineage_join = ''
        lineage_cond = ''

    sql = """
        SELECT M2P.PROTEIN_AC, MIN(M2P.CONDENSE) CONDENSE, MIN(M2P.LEN) LEN
        FROM {}.METHOD2PROTEIN M2P
        {}
        {}
        {}
        {}
        {}
        {}
        {}
        WHERE M2P.METHOD_AC IN ({})
        {}
        {}
        {}
        {}
        {}
        {}
        {}
        {}
        {}
        {}
        GROUP BY M2P.PROTEIN_AC
    """.format(
        app.config['DB_SCHEMA'],

        # filter joins
        must_join, mustnt_join, comment_join, desc_join, go_join, ec_join, lineage_join,

        # 'WHERE M2P.METHOD_AC IN' statement
        may_cond,

        # Other conditions
        must_cond,
        mustnt_cond,
        source_cond,
        search_cond,
        tax_cond,
        comment_cond,
        desc_cond,
        go_cond,
        ec_cond,
        lineage_cond
    )

    return sql, params


def get_db_info(dbshort):
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT DBNAME, DBCODE, VERSION
        FROM {}.CV_DATABASE
        WHERE LOWER(DBSHORT) = :1
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
            MM.METHOD_AC,
            MP.METHOD_AC2,
            M2.CANDIDATE,
            MP.RELATION,
            EM2.ENTRY_AC,
            E.ENTRY_TYPE
        FROM {0}.METHOD_MATCH MM
        INNER JOIN {0}.METHOD M1 ON MM.METHOD_AC = M1.METHOD_AC
        LEFT OUTER JOIN {0}.METHOD_PREDICTION MP ON (MM.METHOD_AC = MP.METHOD_AC1)
        LEFT OUTER JOIN {0}.METHOD M2 ON MP.METHOD_AC2 = M2.METHOD_AC
        LEFT OUTER JOIN {0}.ENTRY2METHOD EM1 ON MM.METHOD_AC = EM1.METHOD_AC
        LEFT OUTER JOIN {0}.ENTRY2METHOD EM2 ON MP.METHOD_AC2 = EM2.METHOD_AC
        LEFT OUTER JOIN {0}.ENTRY E ON EM2.ENTRY_AC = E.ENTRY_AC
        WHERE M1.DBCODE = :1
        AND EM1.ENTRY_AC IS NULL
        AND (:2 IS NULL OR MM.METHOD_AC LIKE :2)
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
        LEFT OUTER JOIN INTERPRO.MV_METHOD_MATCH@IPREL MM_THEN ON M.METHOD_AC = MM_THEN.METHOD_AC
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
        SELECT T.GO_ID, T.NAME, T.CATEGORY, T.DEFINITION, T.IS_OBSOLETE, T.REPLACED_BY
        FROM INTERPRO.INTERPRO2GO I
          INNER JOIN INTERPRO_ANALYSIS.TERM T ON I.GO_ID = T.GO_ID
        WHERE I.ENTRY_AC = :1
        ORDER BY T.GO_ID
        """,
        (entry_ac,)
    )

    terms = []
    for row in cur:
        terms.append({
            'id': row[0],
            'name': row[1],
            'category': row[2],
            'definition': row[3],
            'isObsolete': row[4] == 'Y',
            'replacedBy': row[5]
        })

    entry['go'] = terms

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

        g.oracle_db = cx_Oracle.connect(uri, encoding='utf-8', nencoding='utf-8')
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
    return render_template('main.html', user=get_user(), schema=app.config['DB_SCHEMA'])


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
    return render_template('main.html', user=get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/entry/<entry_ac>/')
def view_entry(entry_ac):
    return render_template('main.html', user=get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/protein/<protein_ac>/')
def view_protein(protein_ac):
    return render_template('main.html', user=get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/method/<method_ac>/')
def view_method(method_ac):
    return render_template('main.html', user=get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/methods/<path:methods>/matches/')
@app.route('/methods/<path:methods>/taxonomy/')
@app.route('/methods/<path:methods>/descriptions/')
@app.route('/methods/<path:methods>/comments/')
@app.route('/methods/<path:methods>/go/')
@app.route('/methods/<path:methods>/matrices/')
@app.route('/methods/<path:methods>/enzymes/')
def view_compare(methods):
    return render_template('main.html', user=get_user(), topics=get_topics(), schema=app.config['DB_SCHEMA'])


@app.route('/search/')
def view_search():
    return render_template('main.html', user=get_user(), schema=app.config['DB_SCHEMA'])


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
        hits = [{
            'id': entry_ac,
            'name': names[entry_ac][0],
            'type': names[entry_ac][1]
        } for entry_ac in hits if entry_ac in names]

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
    Returns the overlapping entries for a given signature.
    Example:
    ---
    /api/method/PF00051/prediction/
    """

    try:
        overlap = float(request.args.get('overlap', 0.3))
    except ValueError:
        overlap = 0.3

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT
          MO.C_AC,
          DB.DBCODE,
          DB.DBSHORT,

          E.ENTRY_AC,
          E.CHECKED,
          E.ENTRY_TYPE,
          E.NAME,
          
          MO.N_PROT_OVER,
          MO.N_OVER,          

          MO.C_N_PROT,
          MO.C_N_MATCHES,
          MO.Q_N_PROT,
          MO.Q_N_MATCHES,

          MP.RELATION
        FROM (
            SELECT
                MMQ.METHOD_AC Q_AC,
                MMQ.N_PROT Q_N_PROT,
                MMQ.N_MATCHES Q_N_MATCHES,
                MMC.METHOD_AC C_AC,
                MMC.N_PROT C_N_PROT,
                MMC.N_MATCHES C_N_MATCHES,
                MO.N_PROT_OVER,
                MO.N_OVER
            FROM (
                SELECT METHOD_AC1, METHOD_AC2, N_PROT_OVER, N_OVER, AVG_FRAC1, AVG_FRAC2
                FROM {0}.METHOD_OVERLAP
                WHERE METHOD_AC1 = :method
            ) MO
            INNER JOIN {0}.METHOD_MATCH MMQ ON MO.METHOD_AC1 = MMQ.METHOD_AC
            INNER JOIN {0}.METHOD_MATCH MMC ON MO.METHOD_AC2 = MMC.METHOD_AC
            WHERE ((MO.N_PROT_OVER >= (:overlap * MMQ.N_PROT)) OR (MO.N_PROT_OVER >= (:overlap * MMC.N_PROT)))
        ) MO
        LEFT OUTER JOIN {0}.METHOD_PREDICTION MP ON MO.Q_AC = MP.METHOD_AC1 AND MO.C_AC = MP.METHOD_AC2
        LEFT OUTER JOIN {0}.METHOD M ON MO.C_AC = M.METHOD_AC
        LEFT OUTER JOIN {0}.CV_DATABASE DB ON M.DBCODE = DB.DBCODE
        LEFT OUTER JOIN {0}.ENTRY2METHOD E2M ON MO.C_AC = E2M.METHOD_AC
        LEFT OUTER JOIN {0}.ENTRY E ON E2M.ENTRY_AC = E.ENTRY_AC
        ORDER BY MO.N_PROT_OVER DESC, MO.N_OVER DESC, MO.C_AC
        """.format(app.config['DB_SCHEMA']),
        {'method': method_ac, 'overlap': overlap}
    )

    methods = []
    for row in cur:
        db = xref.find_ref(row[1], row[0])

        methods.append({
            # method and member database
            'id': row[0],
            'dbCode': row[1],  # if None, the signature is a MEROPS entry (because not in the METHOD table)
            'dbShort': row[2],
            'dbLink': db.gen_link() if db else None,

            # InterPro entry info
            'entryId': row[3],
            'entryHierarchy': [],
            'isChecked': row[4] == 'Y',
            'entryType': row[5],
            'entryName': row[6],

            'nProts': row[7],  # number of proteins where both query and candidate signatures overlap
            'nBlobs': row[8],  # number of overlapping blobs with query and candidate signature

            'nProtsCand': row[9],  # number of proteins for every candidate signature
            'nBlobsCand': row[10],
            'nProtsQuery': row[11],  # number of proteins in the query signature found
            'nBlobsQuery': row[12],

            'relation': row[13]  # predicted relationship
        })

    cur.execute(
        """
        SELECT ENTRY_AC, PARENT_AC
        FROM {}.ENTRY2ENTRY
        """.format(app.config['DB_SCHEMA'])
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
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT ID, TITLE, FIRST_PUBLISHED_DATE
        FROM {0}.PUBLICATION
        WHERE ID IN (
          SELECT REF_DB_ID
          FROM {0}.PROTEIN2GO P
            INNER JOIN {0}.METHOD2PROTEIN M ON P.PROTEIN_AC = M.PROTEIN_AC
          WHERE M.METHOD_AC = :1
                AND P.GO_ID = :2
                AND REF_DB_CODE = 'PMID'
        )
        ORDER BY FIRST_PUBLISHED_DATE
        """.format(app.config['DB_SCHEMA']),
        (method_ac, go_id)
    )

    references = []
    for row in cur:
        references.append({
            'id': row[0],
            'title': row[1],
            'date': row[2].strftime('%d %b %Y') if row[2] else None
        })

    cur.close()

    return jsonify({
        'count': len(references),
        'results': references
    })


@app.route('/api/method/<method_ac>/proteins/all/')
def get_method_proteins(method_ac):
    source_db = request.args.get('db', '').upper()

    if source_db in ('S', 'T'):
        source_cond = 'AND DBCODE = :2'
        params = (method_ac, source_db)
    else:
        source_cond = ''
        params = (method_ac,)

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT
          M2P.PROTEIN_AC,
          P.DBCODE,
          P.LEN,
          P.NAME,
          D.TEXT,
          E.TAX_ID,
          E.FULL_NAME
        FROM (
          SELECT DISTINCT PROTEIN_AC
          FROM {0}.METHOD2PROTEIN
          WHERE METHOD_AC = :1
          {1}
        ) M2P
        INNER JOIN {0}.PROTEIN P ON M2P.PROTEIN_AC = P.PROTEIN_AC
        INNER JOIN {0}.PROTEIN_DESC PD ON M2P.PROTEIN_AC = PD.PROTEIN_AC
        INNER JOIN {0}.DESC_VALUE D ON PD.DESC_ID = D.DESC_ID
        INNER JOIN {0}.ETAXI E ON P.TAX_ID = E.TAX_ID
        ORDER BY M2P.PROTEIN_AC
        """.format(app.config['DB_SCHEMA'], source_cond),
        params
    )

    proteins = []
    for row in cur:
        protein_ac = row[0]

        if row[1] == 'S':
            is_reviewed = True
            prefix = 'http://sp.isb-sib.ch/uniprot/'
        else:
            is_reviewed = False
            prefix = 'http://www.uniprot.org/uniprot/'

        proteins.append({
            'id': protein_ac,
            'link': prefix + protein_ac,
            'isReviewed': is_reviewed,
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
        taxon_id = int(request.args.get('taxon'))
    except (TypeError, ValueError):
        taxon = None
    else:
        taxon = get_taxon(taxon_id)

    rank = request.args.get('rank')

    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
    else:
        if page < 1:
            page = 1

    try:
        page_size = int(request.args.get('pageSize', 25))
    except ValueError:
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

    go_id = request.args.get('term')

    source_db = request.args.get('db', '').upper()
    if source_db not in ('S', 'T'):
        source_db = None

    ecno = request.args.get('ec')

    search = request.args.get('search', '').strip()
    if not search:
        search = None

    sql, params = build_method2protein_sql(
        methods={method_ac: None},
        taxon=taxon,
        source_db=source_db,
        desc_id=desc_id,
        topic_id=topic_id,
        comment_id=comment_id,
        go_id=go_id,
        ecno=ecno,
        search=search,
        no_rank=rank
    )

    cur = get_db().cursor()
    cur.execute(sql, params)
    proteins_all = [row[0] for row in cur]
    count = len(proteins_all)

    params['i_start'] = 1 + (page - 1) * page_size
    params['i_end'] = page * page_size
    params['method'] = method_ac

    cur.execute(
        """
        SELECT P.PROTEIN_AC, P.DBCODE, P.LEN, P.NAME, DV.TEXT, E.TAX_ID, E.FULL_NAME, M.POS_FROM, M.POS_TO
        FROM {0}.PROTEIN P
        INNER JOIN (
            SELECT *
            FROM (
                SELECT M2P.*, ROWNUM RN
                FROM (
                    {1}
                    ORDER BY M2P.PROTEIN_AC
                  ) M2P
                WHERE ROWNUM <= :i_end
            ) WHERE RN >= :i_start

        ) M2P ON P.PROTEIN_AC = M2P.PROTEIN_AC
        INNER JOIN {0}.PROTEIN_DESC PD ON P.PROTEIN_AC = PD.PROTEIN_AC
        INNER JOIN {0}.DESC_VALUE DV ON PD.DESC_ID = DV.DESC_ID
        INNER JOIN {0}.ETAXI E ON P.TAX_ID = E.TAX_ID
        INNER JOIN {0}.MATCH M ON P.PROTEIN_AC = M.PROTEIN_AC
        WHERE M.METHOD_AC = :method
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


@app.route('/api/methods/<path:methods>/enzymes/')
def api_methods_enzymes(methods):
    params = [m.strip() for m in methods.split('/') if m.strip()]
    meth_var = ','.join([':' + str(i+1) for i in range(len(params))])
    source_db = request.args.get('db', 'S').upper()

    if source_db in ('S', 'T'):
        source_cond = 'AND M2P.DBCODE = :' + str(len(params)+1)
        params.append(source_db)
    else:
        source_db = 'U'
        source_cond = ''

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT
          M2P.METHOD_AC,
          EZ.ECNO,
          COUNT(DISTINCT M2P.PROTEIN_AC)
        FROM {0}.METHOD2PROTEIN M2P
          INNER JOIN {0}.ENZYME EZ ON M2P.PROTEIN_AC = EZ.PROTEIN_AC
        WHERE M2P.METHOD_AC IN ({1})
        {2}
        GROUP BY M2P.METHOD_AC, EZ.ECNO
        """.format(app.config['DB_SCHEMA'], meth_var, source_cond),
        params
    )

    enzymes = {}
    max_prot = 0
    for acc, ezno, n_prot in cur:
        if ezno in enzymes:
            e = enzymes[ezno]
        else:
            e = enzymes[ezno] = {
                'id': ezno,
                'methods': {}
            }

        e['methods'][acc] = n_prot

        if n_prot > max_prot:
            max_prot = n_prot

    cur.close()

    return jsonify({
        'results': sorted(enzymes.values(), key=lambda e: -max(e['methods'].values())),
        'database': source_db,
        'max': max_prot
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

    db = request.args.get('db', 'S').upper()
    if db not in ('S', 'T'):
        db = NotImplementedError

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

    sql, params = build_method2protein_sql(
        _methods,
        taxon=taxon,
        source_db=db,
        desc_id=desc_id,
        topic_id=topic_id,
        comment_id=comment_id,
        go_id=go_id
    )

    cur = get_db().cursor()
    if code:
        params['code'] = code

        cur.execute(
            """
            SELECT
                PROTEIN_AC,
                CONDENSE
            FROM (
                {}
            )
            WHERE CONDENSE = :code
            ORDER BY PROTEIN_AC
            """.format(sql),
            params
        )

        proteins = [(row[0], row[1], 1) for row in cur]
    else:
        cur.execute(
            """
            SELECT
                PROTEIN_AC,
                CONDENSE,
                N_PROT
            FROM (
                SELECT
                    PROTEIN_AC,
                    CONDENSE,
                    COUNT(*) OVER (PARTITION BY CONDENSE) AS N_PROT,
                    ROW_NUMBER() OVER (PARTITION BY CONDENSE ORDER BY LEN) AS RN
                FROM (
                    {}
                )
            )
            WHERE RN = 1
            ORDER BY N_PROT DESC, PROTEIN_AC
            """.format(sql),
            params
        )
        proteins = [row for row in cur]

    n_proteins = len(proteins)
    max_len = 0
    _proteins = []

    if n_proteins:
        # Select requested page
        proteins = proteins[(page - 1) * page_size:page * page_size]

        # Creat list of protein accessions and a dictionary of info for condensed proteins
        accessions = []
        codes = {}
        for acc, code, count in proteins:
            accessions.append(acc)
            codes[acc] = {'code': code, 'count': count}

        # Get info on proteins (description, taxon, etc.)
        proteins_cond = ','.join([':' + str(i + 1) for i in range(len(accessions))])
        cur.execute(
            """
            SELECT MA.PROTEIN_AC, P.DBCODE, P.LEN, D.TEXT, E.FULL_NAME,
              MA.METHOD_AC, ME.NAME, ME.CANDIDATE, ME.DBCODE,
              EM.ENTRY_AC,
              MA.POS_FROM, MA.POS_TO
            FROM {0}.MATCH MA
              INNER JOIN {0}.PROTEIN P ON MA.PROTEIN_AC = P.PROTEIN_AC
              INNER JOIN {0}.PROTEIN_DESC PD ON MA.PROTEIN_AC = PD.PROTEIN_AC
              INNER JOIN {0}.DESC_VALUE D ON PD.DESC_ID = D.DESC_ID
              INNER JOIN {0}.ETAXI E ON P.TAX_ID = E.TAX_ID
              LEFT OUTER JOIN {0}.METHOD ME ON MA.METHOD_AC = ME.METHOD_AC
              LEFT OUTER JOIN {0}.ENTRY2METHOD EM ON MA.METHOD_AC = EM.METHOD_AC
            WHERE MA.PROTEIN_AC IN ({1})
            """.format(app.config['DB_SCHEMA'], proteins_cond),
            accessions
        )

        proteins = {}
        for row in cur:
            protein_ac = row[0]

            if protein_ac in proteins:
                p = proteins[protein_ac]
            else:
                if row[1] == 'S':
                    is_reviewed = True
                    prefix = 'http://sp.isb-sib.ch/uniprot/'
                else:
                    is_reviewed = False
                    prefix = 'http://www.uniprot.org/uniprot/'

                p = proteins[protein_ac] = {
                    'id': protein_ac,
                    'isReviewed': is_reviewed,
                    'length': row[2],
                    'description': row[3],
                    'organism': row[4],
                    'link': prefix + protein_ac,
                    'code': codes[protein_ac]['code'],
                    'count': codes[protein_ac]['count'],
                    'methods': {}
                }

                if row[2] > max_len:
                    max_len = row[2]

            method_ac = row[5]

            if method_ac in p['methods']:
                m = p['methods'][method_ac]
            else:
                method_db = row[8]
                if method_db is not None:
                    m = xref.find_ref(method_db, method_ac)
                    method_db = {
                        'link': m.gen_link(),
                        'color': m.color
                    }

                m = p['methods'][method_ac] = {
                    'id': method_ac,
                    'name': row[6],
                    'isCandidate': row[7] == 'Y',
                    'entryId': row[9],
                    'isSelected': method_ac in methods,
                    'db': method_db,
                    'matches': []
                }

            m['matches'].append({'start': row[10], 'end': row[11]})

        cur.close()

        for p in sorted(proteins.values(), key=lambda p: (-p['count'], p['id'])):
            for m in p['methods'].values():
                m['matches'].sort(key=lambda m: m['start'])

            p['methods'] = sorted(p['methods'].values(), key=lambda m: (0 if m['entryId'] else 1, m['entryId'], m['id']))
            _proteins.append(p)

    return jsonify({
        'count': n_proteins,
        'proteins': _proteins,
        'maxLength': max_len,
        'taxon': taxon,
        'database': db if db else 'U',
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
    /methods/MF_00011/PF00709/taxonomy/?rank=genus
    """
    methods = [m.strip() for m in methods.split('/') if m.strip()]

    try:
        taxon_id = int(request.args.get('taxon', ''))
    except ValueError:
        taxon_id = 1
    finally:
        taxon = get_taxon(taxon_id)

    ranks = ('superkingdom', 'kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species')
    try:
        i = ranks.index(request.args.get('rank', 'superkingdom').lower())
    except ValueError:
        i = 0
    finally:
        rank = ranks[i]

    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}
    params['ln'] = taxon['leftNumber']
    params['rn'] = taxon['rightNumber']
    params['rank'] = rank

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT
          L.TAX_ID,
          MIN(E.FULL_NAME),
          M2P.METHOD_AC,
          COUNT(DISTINCT M2P.PROTEIN_AC)
        FROM {0}.METHOD2PROTEIN M2P
          LEFT OUTER JOIN {0}.LINEAGE L ON M2P.LEFT_NUMBER = L.LEFT_NUMBER
          LEFT OUTER JOIN {0}.ETAXI E ON L.TAX_ID = E.TAX_ID
        WHERE M2P.METHOD_AC IN ({1})
              AND M2P.LEFT_NUMBER BETWEEN :ln AND :rn
              AND L.RANK = :rank
        GROUP BY M2P.METHOD_AC, L.TAX_ID
        """.format(app.config['DB_SCHEMA'], fmt),
        params
    )

    taxons = {}
    max_prots = 0
    for row in cur:
        tax_id = row[0]
        n_prots = row[3]

        if tax_id in taxons:
            t = taxons[tax_id]
        else:
            t = taxons[tax_id] = {
                'id': tax_id,
                'fullName': row[1] if tax_id else 'Others',
                'methods': {}
            }

        t['methods'][row[2]] = n_prots

        if n_prots > max_prots:
            max_prots = n_prots

    cur.close()

    return jsonify({
        'taxon': taxon,
        'rank': rank,
        'results': sorted(taxons.values(), key=lambda x: (0 if x['id'] else 1, -sum(x['methods'].values()))),
        'max': max_prots
    })


@app.route('/api/methods/<path:methods>/descriptions/')
def api_methods_descriptions(methods):
    """
    Returns UniProt descriptions associated to a set of signatures
    Example:
    ---
    /methods/PF00051/PS50070/SM00130/descriptions/
    """
    params = [m.strip() for m in methods.split('/') if m.strip()]
    meth_var = ','.join([':' + str(i+1) for i in range(len(params))])
    source_db = request.args.get('db', 'S').upper()

    if source_db in ('S', 'T'):
        source_cond = 'AND M2P.DBCODE = :' + str(len(params)+1)
        params.append(source_db)
    else:
        source_db = 'U'
        source_cond = ''

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT M.DESC_ID, D.TEXT, M.METHOD_AC, M.N_PROT
        FROM (
               SELECT
                 PD.DESC_ID,
                 M2P.METHOD_AC,
                 COUNT(DISTINCT M2P.PROTEIN_AC) N_PROT
               FROM {0}.METHOD2PROTEIN M2P
                 INNER JOIN {0}.PROTEIN_DESC PD ON M2P.PROTEIN_AC = PD.PROTEIN_AC
               WHERE METHOD_AC IN ({1}) {2}
               GROUP BY M2P.METHOD_AC, PD.DESC_ID
             ) M
          INNER JOIN {0}.DESC_VALUE D ON M.DESC_ID = D.DESC_ID
        """.format(app.config['DB_SCHEMA'], meth_var, source_cond),
        params
    )

    descriptions = {}
    max_prot = 0
    for desc_id, desc, method_ac, n_prot in cur:
        if desc_id in descriptions:
            d = descriptions[desc_id]
        else:
            d = descriptions[desc_id] = {
                'id': desc_id,
                'value': desc,
                'methods': {}
            }

        d['methods'][method_ac] = n_prot

        if n_prot > max_prot:
            max_prot = n_prot

    cur.close()

    return jsonify({
        'results': sorted(descriptions.values(), key=lambda x: (-max(x['methods'].values()), x['value'])),
        'database': source_db,
        'max': max_prot
    })


@app.route('/api/methods/<path:methods>/go/')
def api_methods_go(methods):
    """
    Return the GO terms associated to a set of signatures.
    Example:
    ---
    /api/methods/MF_00011/PF00709/go/?category=C
    """
    methods = [m.strip() for m in methods.split('/') if m.strip()]
    meth_var = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}

    _aspects = ('C', 'P', 'F')
    aspects = [e for e in request.args.get('aspect', '').upper().split(',') if e in _aspects]
    if 0 < len(aspects) < 3:
        aspect_cond = 'AND T.CATEGORY IN ({})'.format(','.join([':aspect' + str(i) for i in range(len(aspects))]))
        params.update({'aspect' + str(i): aspect for i, aspect in enumerate(aspects)})
    else:
        aspects = _aspects
        aspect_cond = ''

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT M.METHOD_AC, T.GO_ID, T.NAME, T.CATEGORY, P.PROTEIN_AC, P.REF_DB_CODE, P.REF_DB_ID
        FROM {0}.METHOD2PROTEIN M
          INNER JOIN {0}.PROTEIN2GO P ON M.PROTEIN_AC = P.PROTEIN_AC
          INNER JOIN {0}.TERM T ON P.GO_ID = T.GO_ID
        WHERE M.METHOD_AC IN ({1}) {2}
        """.format(app.config['DB_SCHEMA'], meth_var, aspect_cond),
        params
    )

    terms = {}
    for method_ac, go_id, term, aspect, protein_ac, ref_db, ref_id in cur:
        if go_id in terms:
            t = terms[go_id]
        else:
            t = terms[go_id] = {
                'id': go_id,
                'value': term,
                'methods': {},
                'aspect': aspect
            }

        if method_ac in t['methods']:
            m = t['methods'][method_ac]
        else:
            m = t['methods'][method_ac] = {
                'proteins': set(),
                'references': set()
            }

        m['proteins'].add(protein_ac)
        if ref_db == 'PMID':
            m['references'].add(ref_id)

    cur.close()

    max_prot = 0
    for t in terms.values():
        for m in t['methods'].values():
            n_prot = len(m['proteins'])
            m['proteins'] = n_prot
            m['references'] = len(m['references'])

            if n_prot > max_prot:
                max_prot = n_prot

    return jsonify({
        # Sort by sum of proteins counts (desc), and GO ID (asc)
        'results': sorted(terms.values(), key=lambda t: (-max(m['proteins'] for m in t['methods'].values()), t['id'])),
        'aspects': aspects,
        'max': max_prot
    })


@app.route('/api/methods/<path:methods>/comments/')
def api_methods_comments(methods):
    """
    Returns Swiss-Prot comments of a given topic associated to a set of signatures
    Example:
    ---
    /api/methods/PTHR11846:SF3/PTHR11846:SF2/TIGR00184/comments/
    """
    methods = [m.strip() for m in methods.split('/') if m.strip()]
    meth_var = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}

    try:
        topic_id = int(request.args.get('topic', 34))
    except ValueError:
        topic_id = 34  # Similarity
    finally:
        params['topicid'] = topic_id

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT M.METHOD_AC, M.COMMENT_ID, C.TEXT, M.N_PROT
        FROM (
               SELECT PC.COMMENT_ID, M2P.METHOD_AC, COUNT(DISTINCT M2P.PROTEIN_AC) N_PROT
               FROM {0}.METHOD2PROTEIN M2P
                 INNER JOIN {0}.PROTEIN_COMMENT PC ON M2P.PROTEIN_AC = PC.PROTEIN_AC
               WHERE M2P.METHOD_AC IN ({1})
                     AND PC.TOPIC_ID = :topicid
               GROUP BY PC.COMMENT_ID, M2P.METHOD_AC
             ) M
          INNER JOIN {0}.COMMENT_VALUE C ON M.COMMENT_ID = C.COMMENT_ID AND C.TOPIC_ID = :topicid
        """.format(app.config['DB_SCHEMA'], meth_var),
        params
    )

    comments = {}
    max_prot = 0
    for method_ac, comment_id, comment, n_prot in cur:
        if comment_id in comments:
            c = comments[comment_id]
        else:
            c = comments[comment_id] = {
                'id': comment_id,
                'value': comment,
                'methods': {}
            }

        c['methods'][method_ac] = n_prot

        if n_prot > max_prot:
            max_prot = n_prot

    cur.close()

    return jsonify({
        'topic': {
            'id': topic_id,
            'value': get_topic(topic_id)
        },
        'results': sorted(comments.values(), key=lambda x: -max(x['methods'].values())),
        'max': max_prot
    })


@app.route('/api/methods/<path:methods>/matrices/')
def api_methods_matrices(methods):
    """
    Returns the overlap match matrix, and the collocation match matrix for a set of signatures
    Example:
    ---
    /api/methods/SSF57440/cd00108/PIRSF500183/PTHR19331:SF315/PTHR44106:SF1/matrices/
    """
    methods = [m.strip() for m in methods.split('/') if m.strip()]
    meth_var = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT MM.METHOD_AC, MM.N_PROT, MO.METHOD_AC2, MO.N_PROT, MO.AVG_OVER, MO.N_PROT_OVER
        FROM {0}.METHOD_MATCH MM
          INNER JOIN (
                       SELECT METHOD_AC1, METHOD_AC2, N_PROT, AVG_OVER, N_PROT_OVER
                       FROM {0}.METHOD_OVERLAP MO
                       WHERE METHOD_AC1 IN ({1})
                             AND METHOD_AC2 IN ({1})
                     ) MO ON MM.METHOD_AC = MO.METHOD_AC1
        WHERE METHOD_AC IN ({1})
        """.format(app.config['DB_SCHEMA'], meth_var),
        params
    )

    matrix = {}
    for acc_1, n_prot, acc_2, n_coloc, avg_over, n_overlap in cur:
        if acc_1 in matrix:
            m = matrix[acc_1]
        else:
            m = matrix[acc_1] = {
                'prot': n_prot,
                'methods': {}
            }

        m['methods'][acc_2] = {
            'coloc': n_coloc,
            'over': n_overlap,
            'avgOver': avg_over
        }

    cur.close()

    return jsonify({
        'matrix': matrix,
        'max': max([m['prot'] for m in matrix.values()])
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

