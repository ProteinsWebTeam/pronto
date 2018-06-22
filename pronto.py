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
        desc_cond = 'AND M2P.DESC_ID = :descid'
        params['descid'] = desc_id
    else:
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
        SELECT M2P.PROTEIN_AC, MIN(M2P.CONDENSE) CONDENSE, MIN(M2P.LEN) LEN, MIN(M2P.DESC_ID) DESC_ID
        FROM {}.METHOD2PROTEIN M2P
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
        must_join, mustnt_join, comment_join, go_join, ec_join, lineage_join,

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
            return len([p for p in m['predictions'] if p['relation'] == 'ADD_TO' and p['type'] is not None])
    elif mode == 'newint':
        # Method must have at least one prediction that is an unintegrated candidate signature
        def test_method(m):
            return len([p for p in m['predictions'] if p['relation'] == 'ADD_TO' and p['type'] is None and p['isCandidate']])
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

                if p['relation'] == 'ADD_TO':
                    add_to[feature] = e_type
                elif p['relation'] == 'PARENT_OF':
                    children.add(feature)
                elif p['relation'] == 'CHILD_OF':
                    parents.add(feature)

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


























@app.route('/api/method/<method_ac>/proteins/')
def api_method_proteins(method_ac):
    try:
        taxon_id = int(request.args['taxon'])
    except (KeyError, ValueError):
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
        INNER JOIN {0}.DESC_VALUE DV ON M2P.DESC_ID = DV.DESC_ID
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
        taxon = None
    else:
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
        db = None

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
        'taxon': taxon if taxon else get_taxon(1),
        'database': db if db else 'U',
        'pageInfo': {
            'page': page,
            'pageSize': page_size
        }
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
                 M2P.DESC_ID,
                 M2P.METHOD_AC,
                 COUNT(DISTINCT M2P.PROTEIN_AC) N_PROT
               FROM {0}.METHOD2PROTEIN M2P
               WHERE METHOD_AC IN ({1}) {2}
               GROUP BY M2P.METHOD_AC, M2P.DESC_ID
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





if __name__ == '__main__':
    app.run()

