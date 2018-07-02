#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import jsonify, redirect, render_template, request, session, url_for

from pronto import app, api


@app.route('/api/feed/')
def api_feed():
    try:
        n = int(request.args['n'])
    except (KeyError, ValueError):
        n = 20

    return jsonify(api.get_feed(n))


@app.route('/api/protein/<protein_ac>/')
def api_protein(protein_ac):
    r = {
        'status': False,
        'result': None,
        'error': None
    }

    protein = api.get_protein(protein_ac)

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
        entry = api.get_entry(entry_ac)
    except:
        r['error'] = 'An error occurred while searching for <strong>{}</strong>.'.format(entry_ac)
        status = 500
    else:
        if entry:
            r.update({
                'status': True,
                'result': entry
            })
            status = 200
        else:
            r['error'] = 'The entry <strong>{}</strong> does not exist.'.format(entry_ac)
            status = 404
    finally:
        return jsonify(r), status


@app.route('/api/entry/<entry_ac>/check/', strict_slashes=False, methods=['POST'])
def api_check_entry(entry_ac):
    try:
        is_checked = bool(int(request.form['checked']))
    except (KeyError, ValueError):
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    response, status = api.check_entry(entry_ac, is_checked)

    return jsonify(response), status


@app.route('/api/entry/<entry_ac>/comments/')
def api_entry_comments(entry_ac):
    try:
        n = int(request.args['size'])
    except (KeyError, ValueError):
        n = 0

    return jsonify(api.get_entry_comments(entry_ac, n)), 200


@app.route('/api/entry/<entry_ac>/comment/', strict_slashes=False, methods=['POST'])
def api_comment_entry(entry_ac):
    try:
        comment = request.form['comment'].strip()
    except (AttributeError, KeyError):
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    response, status = api.comment_entry(entry_ac, comment)
    return jsonify(response), status


@app.route('/api/entry/<entry_ac>/comment/<comment_id>/', strict_slashes=False, methods=['DELETE'])
def api_delete_entry_comment(entry_ac, comment_id):
    try:
        comment_id = int(comment_id)
    except ValueError:
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    response, status = api.delete_comment(entry_ac, comment_id, 'entry')
    return jsonify(response), status


@app.route('/api/entry/<entry_ac>/go/', strict_slashes=False, methods=['GET', 'POST', 'DELETE'])
def api_entry_go(entry_ac):
    if request.method == 'GET':
        return jsonify(api.get_entry_go(entry_ac)), 200

    terms = list(set(request.form.get('ids', '').strip().upper().replace(',', ' ').split()))
    if not terms:
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    if request.method == 'POST':
        response, status = api.add_go_mapping(entry_ac.upper(), terms)
    else:
        response, status = api.delete_go_mapping(entry_ac.upper(), terms)

    return jsonify(response), status


@app.route('/api/method/<method_ac>/proteins/')
def api_method_proteins(method_ac):
    try:
        taxon = int(request.args['taxon'])
    except (KeyError, ValueError):
        taxon = None
    else:
        taxon = api.get_taxon(taxon)

    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args['pageSize'])
    except (KeyError, ValueError):
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

    dbcode = request.args.get('db', '').upper()
    if dbcode not in ('S', 'T'):
        dbcode = None

    # `proteins` is a list of dict, `accessions` is the list of ALL proteins
    proteins, accessions = api.get_method_matches(
        method_ac=method_ac,
        taxon=taxon,
        dbcode=dbcode,
        desc=desc_id,
        topic=topic_id,
        comment=comment_id,
        go=request.args.get('term'),
        ecno=request.args.get('ec'),
        rank=request.args.get('rank'),
        search=request.args.get('search', '').strip(),
        page=page,
        page_size=page_size
    )

    return jsonify({
        'data': {
            'proteins': proteins,
            'accessions': accessions
        },
        'meta': {
            'page': page,
            'pageSize': page_size
        }
    }), 200


@app.route('/api/method/<method_ac>/prediction/')
def api_method_predictions(method_ac):
    """
    Returns the overlapping entries for a given signature.
    Example:
    ---
    /api/method/PF00051/prediction/
    """

    try:
        overlap = float(request.args['overlap'])
    except (KeyError, ValueError):
        overlap = 0.3
    finally:
        return jsonify(api.get_method_predictions(method_ac, overlap)), 200


@app.route('/api/method/<method_ac>/comment/', strict_slashes=False, methods=['POST'])
def api_comment_method(method_ac):
    try:
        comment = request.form['comment'].strip()
    except (AttributeError, KeyError):
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    response, status = api.comment_method(method_ac, comment)
    return jsonify(response), status


@app.route('/api/method/<method_ac>/comment/<comment_id>/',  strict_slashes=False, methods=['DELETE'])
def api_delete_method_comment(method_ac, comment_id):
    try:
        comment_id = int(comment_id)
    except ValueError:
        return jsonify({
            'status': False,
            'message': 'Invalid or missing parameters.'
        }), 400

    response, status = api.delete_comment(method_ac, comment_id, 'method')
    return jsonify(response), status


@app.route('/api/method/<method_ac>/comments/')
def api_method_comments(method_ac):
    try:
        n = int(request.args['size'])
    except (KeyError, ValueError):
        n = 0

    return jsonify(api.get_method_comments(method_ac, n)), 200


@app.route('/api/method/<method_ac>/references/<go_id>')
def api_method_references(method_ac, go_id):
    return jsonify(api.get_method_references(method_ac, go_id)), 200


@app.route('/api/method/<method_ac>/proteins/all/')
def api_method_proteins_all(method_ac):
    return jsonify(api.get_method_proteins(method_ac, dbcode=request.args.get('db'))), 200


@app.route('/api/methods/<path:methods>/matches/')
def api_methods_matches(methods):
    try:
        taxon = int(request.args['taxon'])
    except (KeyError, ValueError):
        taxon = None
    else:
        taxon = api.get_taxon(taxon)

    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args['pageSize'])
    except (KeyError, ValueError):
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

    dbcode = request.args.get('db', 'S').upper()
    if dbcode not in ('S', 'T'):
        dbcode = None

    count, proteins = api.get_methods_matches(
        methods=[m.strip() for m in methods.split('/') if m.strip()],
        taxon=taxon,
        dbcode=dbcode,
        desc=desc_id,
        topic=topic_id,
        comment=comment_id,
        go=request.args.get('term'),
        ecno=request.args.get('ec'),
        rank=request.args.get('rank'),
        query=request.args.get('search', '').strip(),
        force=request.args.get('force', '').split(','),
        exclude=request.args.get('exclude', '').split(','),
        code=request.args.get('code'),
        page=page,
        page_size=page_size
    )

    return jsonify({
        'count': count,
        'data': proteins,
        'taxon': None,
        'database': dbcode if dbcode else 'U',
        'page': page,
        'pageSize': page_size
    })


@app.route('/api/methods/<path:methods>/enzymes/')
def api_methods_enzymes(methods):
    return jsonify(
        api.get_methods_enzymes(
            methods=[m.strip() for m in methods.split('/') if m.strip()],
            dbcode=request.args.get('db')
        )
    ), 200


@app.route('/api/methods/<path:methods>/taxonomy/')
def api_methods_taxonomy(methods):
    try:
        taxon = int(request.args['taxon'])
    except (KeyError, ValueError):
        taxon = None
    else:
        taxon = api.get_taxon(taxon)

    try:
        i = api.RANKS.index(request.args.get('rank'))
    except ValueError:
        i = 0
    finally:
        rank = api.RANKS[i]

    taxa = api.get_methods_taxonomy(
        methods=[m.strip() for m in methods.split('/') if m.strip()],
        rank=rank,
        taxon=taxon,
        allow_no_taxon=(request.args.get('notaxon') is not None)
    )

    return jsonify({
        'taxon': taxon if taxon else api.get_taxon(1),
        'rank': rank,
        'data': taxa
    })


@app.route('/api/methods/<path:methods>/descriptions/')
def api_methods_descriptions(methods):
    return jsonify(api.get_methods_descriptions(
        methods=[m.strip() for m in methods.split('/') if m.strip()],
        dbcode=request.args.get('db')
    )), 200


@app.route('/api/methods/<path:methods>/go/')
def api_methods_go(methods):
    return jsonify(api.get_methods_go(
        methods=[m.strip() for m in methods.split('/') if m.strip()],
        aspects=request.args.get('aspect', '').upper().split(',')
    )), 200


@app.route('/api/methods/<path:methods>/comments/')
def api_methods_comments(methods):
    try:
        topic = int(request.args['topic'])
    except (KeyError, ValueError):
        topic = 34

    return jsonify(api.get_methods_swissprot_comments(
        methods=[m.strip() for m in methods.split('/') if m.strip()],
        topic=topic
    )), 200


@app.route('/api/methods/<path:methods>/matrices/')
def api_methods_matrix(methods):
    return jsonify(
        api.get_methods_matrix(
            methods=[m.strip() for m in methods.split('/') if m.strip()]
        )
    ), 200


@app.route('/api/database/')
def api_databases():
    return jsonify(api.get_databases()), 200


@app.route('/api/database/<dbshort>/')
def api_database(dbshort):
    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args['pageSize'])
    except (KeyError, ValueError):
        page_size = 100

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

    query = request.args.get('search', '').strip()

    response, status = api.get_database_methods(
        dbshort,
        query=query,
        integrated=integrated,
        checked=checked,
        commented=commented,
        page=page,
        page_size=page_size
    )

    return jsonify(response), status


@app.route('/api/database/<dbshort>/unintegrated/')
def api_database_unintegrated(dbshort):
    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1

    try:
        page_size = int(request.args['pageSize'])
    except (KeyError, ValueError):
        page_size = 100

    response, status = api.get_database_unintegrated_methods(
        dbshort,
        query=request.args.get('search', '').strip(),
        filter=request.args.get('filter', 'exist'),
        page=page,
        page_size=page_size
    )

    return jsonify(response), status


@app.route('/')
def v_index():
    return render_template('index.html', databases=api.get_databases(),
                           user=api.get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/search/')
def v_search():
    query = request.args.get('q', '').strip()

    try:
        page = int(request.args['page'])
    except (KeyError, ValueError):
        page = 1

    page_size = 20

    entries, methods, proteins, hits, hit_count = api.search(query=query, page=page, page_size=page_size)

    if len(entries) == 1 and not methods and not proteins:
        return redirect(url_for('v_entry', accession=entries[0]))
    elif not entries and len(methods) == 1 and not proteins:
        return redirect(url_for('v_method', accession=methods[0]))
    elif not entries and not methods and len(proteins) == 1:
        return redirect(url_for('v_protein', accession=proteins[0]))

    suggestions = []
    if entries:
        suggestions.append('<li>Entries: {}</li>'.format(
            ', '.join(['<a href="/entry/{0}/">{0}</a>'.format(accession) for accession in entries])
        ))

    if methods:
        suggestions.append('<li>Signatures: {}</li>'.format(
            ', '.join(['<a href="/method/{0}/">{0}</a>'.format(accession) for accession in methods])
        ))

    if proteins:
        suggestions.append('<li>Proteins: {}</li>'.format(
            ', '.join(['<a href="/protein/{0}/">{0}</a>'.format(accession) for accession in proteins])
        ))

    return render_template('search.html',
                           query=query,
                           entries=entries,
                           methods=methods,
                           proteins=proteins,
                           hits=hits,
                           hit_count=hit_count,
                           page=page,
                           page_size=page_size,
                           user=api.get_user(),
                           schema=app.config['DB_SCHEMA'])


@app.route('/database/<dbcode>/')
def v_database(dbcode):
    return render_template('database.html', user=api.get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/database/<dbcode>/unintegrated/')
def v_database_unintegrated(dbcode):
    return render_template('database2.html', user=api.get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/protein/<accession>/')
def v_protein(accession):
    protein = api.get_protein(accession)
    return render_template('protein.html', protein=protein, user=api.get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/method/<accession>/')
def v_method(accession):
    return render_template('method.html', method=accession, user=api.get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/methods/<path:accessions>/matches/')
def v_matches(accessions):
    return render_template('matches.html', user=api.get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/methods/<path:accessions>/taxonomy/')
def v_taxonomy(accessions):
    accessions = accessions.split('/')
    return render_template('taxonomy.html', user=api.get_user(), schema=app.config['DB_SCHEMA'])


@app.route('/entry/<accession>/')
def v_entry(accession):
    try:
        entry = api.get_entry(accession)
    except Exception:
        entry = None
        # todo: return 500

    # todo: return 404 if entry does not exist
    return render_template('entry.html',
                           entry=entry,
                           user=api.get_user(),
                           schema=app.config['DB_SCHEMA'])


@app.route('/login', methods=['GET', 'POST'])
def v_signin():
    """Login page. Display a form on GET, and test the credentials on POST."""
    if api.get_user():
        return redirect(url_for('v_index'))
    elif request.method == 'GET':
        return render_template('login.html', referrer=request.referrer)
    else:
        username = request.form['username'].strip().lower()
        password = request.form['password'].strip()
        user = api.verify_user(username, password)

        if user and user['active'] and user['status']:
            session.permanent = True
            session['user'] = user
            return redirect(request.args.get('next', url_for('v_index')))
        else:
            msg = 'Wrong username or password.'
            return render_template(
                'login.html',
                username=username,
                error=msg,
                referrer=request.args.get('next', url_for('v_index'))
            )


@app.route('/logout/')
def v_signout():
    """Clear the cookie, which logs the user out."""
    session.clear()
    return redirect(request.referrer)
