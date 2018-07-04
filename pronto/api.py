#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import re
import urllib.error
import urllib.parse
import urllib.request

import cx_Oracle
from flask import g, session

from pronto import app
from . import xref

RANKS = (
    'superkingdom',
    'kingdom',
    'phylum',
    'class',
    'order',
    'family',
    'genus',
    'species'
)


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


def get_uniprot_version():
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT VERSION
        FROM {}.CV_DATABASE
        WHERE DBCODE = 'u'
        """.format(app.config['DB_SCHEMA'])
    )
    row = cur.fetchone()
    cur.close()
    return row[0] if row else 'N/A'


def build_method2protein_sql(methods, **kwargs):
    taxon = kwargs.get('taxon')
    dbcode = kwargs.get('dbcode')
    desc = kwargs.get('desc')
    topic = kwargs.get('topic')
    comment = kwargs.get('comment')
    goid = kwargs.get('go')
    ecno = kwargs.get('ecno')
    rank = kwargs.get('rank')
    query = kwargs.get('search')

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
    if topic and comment:
        comment_join = 'INNER JOIN {}.PROTEIN_COMMENT PC ON M2P.PROTEIN_AC = PC.PROTEIN_AC'.format(
            app.config['DB_SCHEMA']
        )
        comment_cond = 'AND PC.TOPIC_ID = :topicid AND PC.COMMENT_ID = :commentid'
        params.update({'topicid': topic, 'commentid': comment})
    else:
        comment_join = ''
        comment_cond = ''

    # Exclude proteins that are not associated to the passed UniProt description
    if desc:
        desc_cond = 'AND M2P.DESC_ID = :descid'
        params['descid'] = desc
    else:
        desc_cond = ''

    # Exclude proteins that are/aren't reviewed
    if dbcode:
        source_cond = 'AND M2P.DBCODE = :sourcedb'
        params['sourcedb'] = dbcode
    else:
        source_cond = ''

    # Filter by search (on accession only, not name)
    if query:
        search_cond = 'AND M2P.PROTEIN_AC LIKE :search_like'
        params['search_like'] = query + '%'
    else:
        search_cond = ''

    # Filter by taxon
    if taxon:
        tax_cond = 'AND M2P.LEFT_NUMBER BETWEEN :ln AND :rn'
        params['ln'] = taxon['leftNumber']
        params['rn'] = taxon['rightNumber']
    else:
        tax_cond = ''

    # Exclude proteins that are not associated to the passed GO term ID
    if goid:
        go_join = 'INNER JOIN {}.PROTEIN2GO P2G ON M2P.PROTEIN_AC = P2G.PROTEIN_AC'.format(
            app.config['DB_SCHEMA']
        )
        go_cond = 'AND P2G.GO_ID = :goid'
        params['goid'] = goid
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
    if rank:
        lineage_join = 'LEFT OUTER JOIN {}.LINEAGE L ON M2P.LEFT_NUMBER = L.LEFT_NUMBER AND L.RANK = :rank'.format(
            app.config['DB_SCHEMA']
        )
        lineage_cond = 'AND L.TAX_ID IS NULL'
        params['rank'] = rank
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


def search(query, in_db=True, in_ebi=True, page=1, page_size=20):
    # From DB
    entry_accs = []
    methods_accs = []
    proteins_accs = []

    # From EBIsearch
    hits = []
    hit_count = 0

    if query:
        if in_db:
            cur = get_db().cursor()

            for term in query.split():
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
                    'SELECT PROTEIN_AC from {}.PROTEIN WHERE PROTEIN_AC = :1 OR NAME = :1'.format(app.config['DB_SCHEMA']),
                    (term.upper(),)
                )
                row = cur.fetchone()
                if row:
                    proteins_accs.append(row[0])
                    continue

            cur.close()

        if in_ebi:
            params = urllib.parse.urlencode({
                'query': query,
                'format': 'json',
                'fields': 'id,name,type',
                'size': page_size,
                'start': (page - 1) * page_size
            })

            try:
                req = urllib.request.urlopen('http://www.ebi.ac.uk/ebisearch/ws/rest/interpro?{}'.format(params))
                res = json.loads(req.read().decode())
            except (urllib.error.HTTPError, json.JSONDecodeError):
                pass
            else:
                hit_count = res['hitCount']
                for e in res['entries']:
                    hits.append({
                        'id': e['id'],
                        'name': e['fields']['name'][0],  # EBI search returns an array of name/type fields
                        'type': e['fields']['type'][0][0].upper()
                        # Take the first char only (will display a label on client)
                    })

    return (
        list(sorted(set(entry_accs))),
        list(sorted(set(methods_accs))),
        proteins_accs,
        hits,
        hit_count
    )


def get_feed(n=20):
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT *
        FROM (
          SELECT U.NAME, EM.TIMESTAMP, EM.METHOD_AC, EM.ENTRY_AC, E.ENTRY_TYPE
          FROM INTERPRO.ENTRY2METHOD_AUDIT EM
            INNER JOIN INTERPRO.ENTRY E ON EM.ACTION = 'I' AND EM.ENTRY_AC = E.ENTRY_AC
            INNER JOIN INTERPRO.USER_PRONTO U ON EM.DBUSER = U.DB_USER
          ORDER BY EM.TIMESTAMP DESC
        ) WHERE ROWNUM <= :1
        """,
        (n,)
    )

    events = []
    for row in cur:
        events.append({
            'user': row[0].split()[0],
            'timestamp': row[1].timestamp(),
            'event': (
                'integrated <a href="/method/{0}/">{0}</a> '
                'into <a href="/entry/{1}/" class="type-{2}">{1}</a>'.format(
                    row[2], row[3], row[4]
                )
            )
        })

    cur.close()

    return {
        'count': len(events),
        'results': events
    }


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
          E.SCIENTIFIC_NAME,
          P.FRAGMENT
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
        },
        'isFragment': row[6] == 'Y',
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

    families = {}
    entries = {}
    methods = {}  # unintegrated signatures
    others = {}   # other features (e.g. MobiDB)
    for row in cur:
        entry_ac = row[0]
        entry_name = row[1]
        type_code = row[2]
        parent = row[4]
        method_ac = row[5]
        dbcode = row[7]

        if entry_ac:
            if type_code == 'F' and entry_ac not in families:
                families[entry_ac] = {
                    'id': entry_ac,
                    'name': entry_name,
                    'parent': parent,
                    'children': []
                }

            if entry_ac not in entries:
                entries[entry_ac] = {
                    'id': entry_ac,
                    'name': entry_name,
                    'typeCode': type_code,
                    'type': row[3],
                    'methods': {}
                }

            _methods = entries[entry_ac]['methods']
        elif dbcode in ('g',):
            _methods = others
        else:
            _methods = methods

        if method_ac in _methods:
            method = _methods[method_ac]
        else:
            db = xref.find_ref(dbcode=dbcode, ac=method_ac)
            method = _methods[method_ac] = {
                'id': method_ac,
                'name': row[6],
                'link': db.gen_link(),
                'database': db.name,
                'color': db.color,
                'matches': []
            }

        method['matches'].append({'start': row[8], 'end': row[9]})

    for entry_ac in entries:
        entries[entry_ac]['methods'] = sorted(entries[entry_ac]['methods'].values(), key=lambda x: x['id'])

    tree = []
    while families:
        # Remove nodes, and keep only leaves (i.e. entries without children)
        keys = set(families.keys())
        for entry_ac, entry in families.items():
            if entry['parent']:
                keys.discard(entry['parent'])

        for entry_ac in sorted(keys):
            entry = families.pop(entry_ac)
            parent = entry['parent']
            del entry['parent']
            if parent:
                families[parent]['children'].append(entry)
            else:
                tree.append(entry)
    families = tree

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
        if fam_id in structs:
            fam = structs[fam_id]
        else:
            db = xref.find_ref(dbcode=dbcode, ac=fam_id)
            fam = structs[fam_id] = {
                'id': fam_id,
                'link': db.gen_link(),
                'database': db.name,
                'color': db.color,
                'matches': []
            }

        fam['matches'].append({'start': start, 'end': end})

    cur.close()

    protein.update({
        'entries': sorted(entries.values(), key=lambda x: x['id']),
        'methods': list(methods.values()),
        'others': list(others.values()),
        'structures': list(structs.values()),
        'families': families
    })

    return protein


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
          NVL(EM.PROTEIN_COUNT, 0),
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
              NVL(EM.PROTEIN_COUNT, 0),
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
        'go': {},
        'description': None,
        'references': [],
        'suppReferences': [],
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

    categories = {}
    for term_id, term_name, term_cat, term_def, is_obsolete, replaced_by in cur:
        if term_cat in categories:
            cat = categories[term_cat]
        else:
            cat = categories[term_cat] = []

        cat.append({
            'id': term_id,
            'name': term_name,
            'definition': term_def,
            'isObsolete': is_obsolete == 'Y',
            'replacedBy': replaced_by
        })

    entry['go'] = categories

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
        text = row[0].strip()

        # # Disabled for not breaking the <pre> tags
        # text = re.sub(r'\s{2,}', ' ', text)

        # Wrap text in paragraph
        # (not that it's better, but some annotations already contain the <p> tag)
        if text[:3].lower() != '<p>':
            text = '<p>' + text
        if text[-4:].lower() != '</p>':
            text += '</p>'

        # Find missing references
        for m in re.finditer(r'<cite\s+id="(PUB\d+)"\s*/>', text):
            ref = m.group(1)

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

    ordered_ref = []
    for m in re.finditer(r'<cite\s+id="(PUB\d+)"\s*/>', description):
        ref = m.group(1)
        pub = references.get(ref)

        if pub:
            if ref in ordered_ref:
                i = ordered_ref.index(ref) + 1
            else:
                ordered_ref.append(ref)
                i = len(ordered_ref)
        else:
            i = '?'

        description = description.replace(m.group(0), '<a href=#{}>{}</a>'.format(ref, i))

    entry.update({
        'description': description,
        'references': [references.pop(ref) for ref in ordered_ref],
        'suppReferences': [references[ref] for ref in sorted(references)]
    })

    return entry


def check_entry(entry_ac, is_checked):
    user = get_user()

    if not user:
        return {
                   'status': False,
                   'message': 'Please log in to perform this action.'
               }, 401

    con = get_db()
    cur = con.cursor()
    try:
        cur.execute(
            'UPDATE INTERPRO.ENTRY SET CHECKED = :1 WHERE ENTRY_AC = :2',
            ('Y' if is_checked else 'N', entry_ac)
        )
    except cx_Oracle.DatabaseError as e:
        cur.close()
        return {
                   'status': False,
                   'message': 'Could not {}check entry {}: {}.'.format(
                       '' if is_checked else 'un',
                       entry_ac,
                       e
                   )
               }, 400
    else:
        con.commit()
        cur.close()
        return {
                   'status': True,
                   'message': None
               }, 200


def get_entry_go(entry_ac):
    cur = get_db().cursor()

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

    categories = {}
    for term_id, term_name, term_cat, term_def, is_obsolete, replaced_by in cur:
        if term_cat in categories:
            cat = categories[term_cat]
        else:
            cat = categories[term_cat] = []

        cat.append({
            'id': term_id,
            'name': term_name,
            'definition': term_def,
            'isObsolete': is_obsolete == 'Y',
            'replacedBy': replaced_by
        })

    cur.close()

    return categories


def get_entry_comments(entry_ac, n=0):
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

    n_comments = len(comments)

    if n:
        comments = comments[:n]

    for c in comments:
        c['text'] = re.sub(
            r'#(\d+)',
            r'<a href="https://github.com/geneontology/go-annotation/issues/\1">#\1</a>',
            c['text']
        )

    return {
        'count': n_comments,
        'results': comments
    }


def add_comment(entry_ac, author, comment, comment_type='entry'):
    if comment_type == 'entry':
        col_name = 'ENTRY_AC'
        table_name = 'ENTRY_COMMENT'
        # Replace link to GO GitHub issues
        comment = re.sub(r'(?:https://)?github.com/geneontology/go-annotation/issues/(\d+)', r'#\1', comment)
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


def delete_comment(ac, comment_id, comment_type):
    user = get_user()

    if not user:
        return {
                   'status': False,
                   'message': 'Please log in to perform this action.'
               }, 401

    if comment_type == 'entry':
        col_name = 'ENTRY_AC'
        table_name = 'ENTRY_COMMENT'
    elif comment_type == 'method':
        col_name = 'METHOD_AC'
        table_name = 'METHOD_COMMENT'
    else:
        return {
                   'status': False,
                   'message': 'Invalid or missing parameters.'
               }, 400

    con = get_db()
    cur = con.cursor()

    try:
        cur.execute(
            "UPDATE INTERPRO.{} SET STATUS = 'N' WHERE {} = :1 AND ID = :2".format(table_name, col_name),
            (ac, comment_id)
        )
    except cx_Oracle.DatabaseError as e:
        cur.close()
        return {
                   'status': False,
                   'message': 'Could not delete comment for "{}".'.format(ac)
               }, 400
    else:
        con.commit()
        cur.close()
        return {
                   'status': True,
                   'message': None
               }, 200


def comment_entry(entry_ac, comment):
    user = get_user()

    if not user:
        return {
                   'status': False,
                   'message': 'Please log in to perform this action.'
               }, 401

    if len(comment) < 3:
        return {
                   'status': False,
                   'message': 'Comment too short (must be at least three characters long).'
               }, 400
    elif add_comment(entry_ac, user['username'], comment, comment_type='entry'):
        return {
                   'status': True,
                   'message': None
               }, 200
    else:
        return {
                   'status': False,
                   'message': 'Could not add comment for entry "{}".'.format(entry_ac)
               }, 400


def add_go_mapping(entry_ac, terms):
    user = get_user()
    if not user:
        return {
                   'status': False,
                   'message': 'Please log in to perform this action.'
               }, 401

    con = get_db()
    cur = con.cursor()

    # Check that all passed IDs exist
    cur.execute(
        """
        SELECT GO_ID 
        FROM {}.TERM 
        WHERE GO_ID IN ({})
        """.format(
            app.config['DB_SCHEMA'],
            ','.join([':' + str(i + 1) for i in range(len(terms))])
        ),
        terms
    )
    _terms = set([row[0] for row in cur])
    terms = set(terms)

    status = 201

    if terms == _terms:
        # Remove terms already mapped to the entry
        cur.execute('SELECT GO_ID FROM INTERPRO.INTERPRO2GO WHERE ENTRY_AC = :1', (entry_ac,))
        _terms = set([row[0] for row in cur])
        terms -= _terms

        if terms:
            try:
                cur.executemany(
                    """
                    INSERT INTO INTERPRO.INTERPRO2GO (ENTRY_AC, GO_ID, SOURCE) 
                    VALUES (:1, :2, :3)
                    """,
                    [(entry_ac, term_id, 'MANU') for term_id in terms]
                )
            except cx_Oracle.IntegrityError:
                res = {
                    'status': False,
                    'message': 'Could not add the following GO terms: {}'.format(', '.join(sorted(terms)))
                }
                status = 400
            else:
                con.commit()
                res = {
                    'status': True,
                    'message': None
                }
        else:
            # All terms already associated: do not return an error
            res = {
                'status': True,
                'message': None
            }
            status = 200
    else:
        res = {
            'status': False,
            'message': 'Invalid GO terms: {}'.format(', '.join(sorted(terms - _terms)))
        }
        status = 400

    cur.close()
    return res, status


def delete_go_mapping(entry_ac, terms):
    user = get_user()
    if not user:
        return {
                   'status': False,
                   'message': 'Please log in to perform this action.'
               }, 401

    con = get_db()
    cur = con.cursor()

    # Delete ID-entry associations
    try:
        cur.execute(
            """
            DELETE FROM INTERPRO.INTERPRO2GO
            WHERE ENTRY_AC = :1 AND GO_ID IN ({})
            """.format(','.join([':' + str(i + 2) for i in range(len(terms))])),
            (entry_ac, *terms)
        )
    except cx_Oracle.IntegrityError:
        res = {
            'status': False,
            'message': 'Could not delete the following GO terms: {}'.format(', '.join(sorted(terms)))
        }
        status = 400
    else:
        con.commit()
        res = {
            'status': True,
            'message': None
        }
        status = 200
    finally:
        cur.close()
        return res, status


def get_method_predictions(method_ac, overlap=0.3):
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

    return {
        'results': methods,
        'count': len(methods)
    }


def comment_method(entry_ac, comment):
    user = get_user()

    if not user:
        return {
                   'status': False,
                   'message': 'Please log in to perform this action.'
               }, 401

    if len(comment) < 3:
        return {
                   'status': False,
                   'message': 'Comment too short (must be at least three characters long).'
               }, 400
    elif add_comment(entry_ac, user['username'], comment, comment_type='method'):
        return {
                   'status': True,
                   'message': None
               }, 200
    else:
        return {
                   'status': False,
                   'message': 'Could not add comment for signature "{}".'.format(entry_ac)
               }, 400


def get_method_comments(entry_ac, n=0):
    """
    Get the curator comments associated to a given method
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

    return {
        'count': len(comments),
        'results': comments[:n] if n else comments
    }


def get_method_references(method_ac, go_id):
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

    return {
        'count': len(references),
        'results': references
    }


def get_method_proteins(method_ac, dbcode=None):
    if dbcode:
        source_cond = 'AND DBCODE = :2'
        params = (method_ac, dbcode)
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
          SELECT DISTINCT PROTEIN_AC, DESC_ID
          FROM {0}.METHOD2PROTEIN
          WHERE METHOD_AC = :1
          {1}
        ) M2P
        INNER JOIN {0}.PROTEIN P ON M2P.PROTEIN_AC = P.PROTEIN_AC
        INNER JOIN {0}.DESC_VALUE D ON M2P.DESC_ID = D.DESC_ID
        INNER JOIN {0}.ETAXI E ON P.TAX_ID = E.TAX_ID
        ORDER BY M2P.PROTEIN_AC
        """.format(app.config['DB_SCHEMA'], source_cond),
        params
    )

    proteins = []
    accessions = []
    for row in cur:
        protein_ac = row[0]

        if row[1] == 'S':
            is_reviewed = True
            prefix = 'http://sp.isb-sib.ch/uniprot/'
        else:
            is_reviewed = False
            prefix = 'http://www.uniprot.org/uniprot/'

        accessions.append(protein_ac)
        proteins.append({
            'accession': protein_ac,
            'link': prefix + protein_ac,
            'isReviewed': is_reviewed,
            'length': row[2],
            'shortName': row[3],
            'name': row[4],
            'taxon': {'id': row[5], 'fullName': row[6]},
            'matches': None
        })

    cur.close()

    return proteins, accessions


def get_methods_enzymes(methods, dbcode=None):
    params = [e for e in methods]

    if dbcode in ('S', 'T'):
        params.append(dbcode)
        source_cond = 'AND M2P.DBCODE = :' + str(len(params))
    else:
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
        """.format(
            app.config['DB_SCHEMA'],
            ','.join([':' + str(i + 1) for i in range(len(params))]),
            source_cond
        ),
        params
    )

    enzymes = {}
    for acc, ezno, n_prot in cur:
        if ezno in enzymes:
            e = enzymes[ezno]
        else:
            e = enzymes[ezno] = {
                'id': ezno,
                'methods': [{'accession': method_ac, 'count': 0} for method_ac in methods]
            }

        try:
            i = methods.index(acc)
        except ValueError:
            pass
        else:
            e['methods'][i]['count'] = n_prot

    cur.close()

    return sorted(enzymes.values(), key=lambda x: -sum([m['count'] for m in x['methods']]))


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

    return {
        'id': row[0],
        'fullName': row[1],
        'leftNumber': int(row[2]),
        'rightNumber': int(row[3]),
        'rank': row[4]
    }


def get_methods_taxonomy(methods, rank=RANKS[0], taxon=None, allow_no_taxon=False):
    fmt = ','.join([':meth' + str(i) for i in range(len(methods))])
    params = {'meth' + str(i): method for i, method in enumerate(methods)}
    params['rank'] = rank

    if taxon:
        params['ln'] = taxon['leftNumber']
        params['rn'] = taxon['rightNumber']
        tax_cond = 'AND M2P.LEFT_NUMBER BETWEEN :ln AND :rn'
    else:
        tax_cond = ''

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT
          L.TAX_ID,
          MIN(E.FULL_NAME),
          M2P.METHOD_AC,
          COUNT(DISTINCT M2P.PROTEIN_AC)
        FROM {0}.METHOD2PROTEIN M2P
          {2} JOIN {0}.LINEAGE L ON M2P.LEFT_NUMBER = L.LEFT_NUMBER AND L.RANK = :rank
          {2} JOIN {0}.ETAXI E ON L.TAX_ID = E.TAX_ID
        WHERE M2P.METHOD_AC IN ({1})
              {3}
        GROUP BY M2P.METHOD_AC, L.TAX_ID
        """.format(
            app.config['DB_SCHEMA'],
            fmt,
            'LEFT OUTER' if allow_no_taxon else 'INNER',
            tax_cond
        ),
        params
    )

    taxa = {}
    for row in cur:
        tax_id = row[0]
        n_prots = row[3]

        if tax_id in taxa:
            t = taxa[tax_id]
        else:
            t = taxa[tax_id] = {
                'id': tax_id,
                'fullName': row[1] if tax_id else 'Others',
                'methods': [{'accession': method_ac, 'count': 0} for method_ac in methods]
            }

        try:
            i = methods.index(row[2])
        except ValueError:
            pass
        else:
            t['methods'][i]['count'] = n_prots

    cur.close()

    # Always place the "Others" category (organisms without taxon for a given rank) at the end
    return sorted(taxa.values(), key=lambda x: (0 if x['id'] else 1, -sum([m['count'] for m in x['methods']])))


def get_methods_descriptions(methods, dbcode):
    params = [e for e in methods]

    if dbcode:
        params.append(dbcode)
        source_cond = 'AND M2P.DBCODE = :' + str(len(params))
    else:
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
        """.format(
            app.config['DB_SCHEMA'],
            ','.join([':' + str(i + 1) for i in range(len(methods))]),
            source_cond
        ),
        params
    )

    descriptions = {}
    for desc_id, desc, method_ac, n_prot in cur:
        if desc_id in descriptions:
            d = descriptions[desc_id]
        else:
            d = descriptions[desc_id] = {
                'id': desc_id,
                'value': desc,
                'methods': [{'accession': method_ac, 'count': 0} for method_ac in methods]
            }

        try:
            i = methods.index(method_ac)
        except ValueError:
            pass
        else:
            d['methods'][i]['count'] = n_prot

    cur.close()

    return sorted(descriptions.values(), key=lambda x: (-sum([m['count'] for m in x['methods']]), x['value']))


def get_methods_go(methods, aspects=('C', 'P', 'F')):
    params = {'meth' + str(i): method for i, method in enumerate(methods)}

    if 0 < len(aspects) < 3:
        aspect_cond = 'AND T.CATEGORY IN ({})'.format(','.join([':aspect' + str(i) for i in range(len(aspects))]))
        params.update({'aspect' + str(i): aspect for i, aspect in enumerate(aspects)})
    else:
        aspect_cond = ''

    cur = get_db().cursor()
    cur.execute(
        """
        SELECT M.METHOD_AC, T.GO_ID, T.NAME, T.CATEGORY, P.PROTEIN_AC, P.REF_DB_CODE, P.REF_DB_ID
        FROM {0}.METHOD2PROTEIN M
          INNER JOIN {0}.PROTEIN2GO P ON M.PROTEIN_AC = P.PROTEIN_AC
          INNER JOIN {0}.TERM T ON P.GO_ID = T.GO_ID
        WHERE M.METHOD_AC IN ({1}) {2}
        """.format(
            app.config['DB_SCHEMA'],
            ','.join([':meth' + str(i) for i in range(len(methods))]),
            aspect_cond
        ),
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
                'methods': [
                    {'accession': method_ac, 'proteins': set(), 'references': set()}
                    for method_ac in methods
                ],
                'aspect': aspect
            }

        try:
            i = methods.index(method_ac)
        except ValueError:
            pass
        else:
            t['methods'][i]['proteins'].add(protein_ac)
            if ref_db == 'PMID':
                t['methods'][i]['references'].add(ref_id)

    cur.close()

    for t in terms.values():
        for i, m in enumerate(t['methods']):
            t['methods'][i].update({
                'count': len(m.pop('proteins')),
                'references': len(m['references']),
            })

    # Sort by sum of proteins counts (desc), and GO ID (asc)
    return sorted(terms.values(), key=lambda x: (-sum(m['count'] for m in x['methods']), x['id']))


def get_swissprot_topics():
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


def get_swissprot_topic(topic_id):
    cur = get_db().cursor()
    cur.execute(
        """
        SELECT TOPIC
        FROM {}.CV_COMMENT_TOPIC
        WHERE TOPIC_ID = :1
        """.format(app.config['DB_SCHEMA']),
        (topic_id, )
    )
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def get_methods_swissprot_comments(methods, topic_id=34):
    params = {'meth' + str(i): method for i, method in enumerate(methods)}
    params['topicid'] = topic_id

    cur = get_db().cursor()
    comments = {}
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
        """.format(
            app.config['DB_SCHEMA'],
            ','.join([':meth' + str(i) for i in range(len(methods))])
        ),
        params
    )

    for method_ac, comment_id, comment, n_prot in cur:
        if comment_id in comments:
            c = comments[comment_id]
        else:
            c = comments[comment_id] = {
                'id': comment_id,
                'value': comment,
                'methods': [{'accession': method_ac, 'count': 0} for method_ac in methods]
            }

        try:
            i = methods.index(method_ac)
        except ValueError:
            pass
        else:
            c['methods'][i]['count'] = n_prot

    cur.close()

    return sorted(comments.values(), key=lambda x: -sum([m['count'] for m in x['methods']]))


def get_methods_matrix(methods):
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
        """.format(
            app.config['DB_SCHEMA'],
            ','.join([':meth' + str(i) for i in range(len(methods))])
        ),
        {'meth' + str(i): method for i, method in enumerate(methods)}
    )

    data = {}
    for acc_1, n_prot, acc_2, n_coloc, avg_over, n_overlap in cur:
        if acc_1 in data:
            m = data[acc_1]
        else:
            m = data[acc_1] = {
                'prot': n_prot,
                'methods': {}
            }

        m['methods'][acc_2] = {
            'coloc': n_coloc,
            'over': n_overlap,
            'avgOver': avg_over
        }

    cur.close()

    matrix = [
        {
            'accession': acc_1,
            'count': data.get(acc_1, {}).get('prot', 0),
            'data': [
                data.get(acc_1, {}).get('methods', {}).get(acc_2, {'coloc': 0, 'over': 0, 'avgOver': 0})
                for acc_2 in methods
            ]
        }
        for acc_1 in methods
    ]

    return matrix


def get_databases():
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


def get_database(dbshort):
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

    if row:
        dbname, dbcode, dbversion = row
    else:
        dbname = dbcode = dbversion = None

    cur.close()

    return dbname, dbcode, dbversion


def get_database_methods(dbshort, **kwargs):
    query = kwargs.get('query')
    integrated = kwargs.get('integrated')
    checked = kwargs.get('checked')
    commented = kwargs.get('commented')
    page = kwargs.get('page', 1)
    page_size = kwargs.get('page_size', 20)

    dbname, dbcode, dbversion = get_database(dbshort)

    if not dbname:
        return {
                   'results': [],
                   'count': 0,
                   'database': None
               }, 404

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

    if query:
        sql += " AND M.METHOD_AC LIKE :2"
        params = (dbcode, query + '%')
    else:
        params = (dbcode,)

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
            'latestComment': {'text': row[5], 'author': row[6], 'date': row[7].strftime('%Y-%m-%d %H:%M:%S')} if row[
                                                                                                                     5] is not None else None
        })

    cur.close()

    return {
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
           }, 200


def get_database_unintegrated_methods(dbshort, **kwargs):
    query = kwargs.get('query')
    _filter = kwargs.get('filter')
    page = kwargs.get('page', 1)
    page_size = kwargs.get('page_size', 20)

    dbname, dbcode, dbversion = get_database(dbshort)

    if not dbname:
        return {
                   'results': [],
                   'count': 0,
                   'database': None
               }, 404

    cur = get_db().cursor()

    sql = """
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
    """.format(app.config['DB_SCHEMA'])

    if query:
        sql += " MM.METHOD_AC LIKE :2"
        params = (dbcode, query + '%')
    else:
        params = (dbcode,)

    cur.execute(sql, params)

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
    if _filter == 'norel':
        # Method mustn't have any non-null relation
        def test_method(m):
            return not len([p for p in m['predictions'] if p['relation'] is not None])
    elif _filter == 'exist':
        # Method must have at least one InterPro prediction
        def test_method(m):
            return len([p for p in m['predictions'] if p['relation'] == 'ADD_TO' and p['type'] is not None])
    elif _filter == 'newint':
        # Method must have at least one prediction that is an unintegrated candidate signature
        def test_method(m):
            return len(
                [p for p in m['predictions'] if p['relation'] == 'ADD_TO' and p['type'] is None and p['isCandidate']])
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

    return {
               'pageInfo': {
                   'page': page,
                   'pageSize': page_size
               },
               'results': _methods[(page-1)*page_size:page*page_size],
               'count': len(_methods),
               'database': {
                   'name': dbname,
                   'version': dbversion
               }
           }, 200


def get_method_matches(method_ac, **kwargs):
    page = kwargs.get('page', 1)
    page_size = kwargs.get('page_size', 25)

    sql, params = build_method2protein_sql({method_ac: None}, **kwargs)

    cur = get_db().cursor()
    cur.execute(sql, params)
    proteins_all = sorted([row[0] for row in cur])

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
                'accession': protein_ac,
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

    return sorted(proteins.values(), key=lambda x: x['accession']), proteins_all


def get_methods_matches(methods, **kwargs):
    force = kwargs.get('force', [])
    exclude = kwargs.get('exclude', [])
    code = kwargs.get('code')
    page = kwargs.get('page', 1)
    page_size = kwargs.get('page_size', 5)

    _methods = {}
    for m in methods:
        m = m.strip()
        if not len(m):
            continue
        elif m in force:
            _methods[m] = True
        else:
            _methods[m] = None

    _methods.update({m.strip(): False for m in exclude if len(m.strip())})

    sql, params = build_method2protein_sql(_methods, **kwargs)

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

            method_ac = row[5]

            if method_ac in p['methods']:
                m = p['methods'][method_ac]
            else:
                method_db = row[8]
                if method_db is not None:
                    m = xref.find_ref(method_db, method_ac)
                    link = m.gen_link()
                    color = m.color
                else:
                    link = color = None

                m = p['methods'][method_ac] = {
                    'id': method_ac,
                    'name': row[6],
                    'isCandidate': row[7] == 'Y',
                    'entryId': row[9],
                    'isSelected': method_ac in methods,
                    'link': link,
                    'color': color,
                    'matches': []
                }

            m['matches'].append({'start': row[10], 'end': row[11]})

        cur.close()

        for p in sorted(proteins.values(), key=lambda p: (-p['count'], p['id'])):
            for m in p['methods'].values():
                m['matches'].sort(key=lambda m: m['start'])

            p['methods'] = sorted(p['methods'].values(),
                                  key=lambda m: (0 if m['entryId'] else 1, m['entryId'], m['id']))
            _proteins.append(p)

    return n_proteins, _proteins
