import {dimmer, setClass, openErrorModal, openConfirmModal} from "../ui.js";
import {finaliseHeader} from "../header.js";
import {getEntryComments, postEntryComment} from "../comments.js";

function _getGOTerms(entryID) {
    utils.getJSON('/api/entry/' + entryID + '/go/', data => {
        let content = '<dt>Molecular Function</dt>';
        if (data.hasOwnProperty('F')) {
            data['F'].forEach(term => {
                content += '<dd><a target="_blank" href="http://www.ebi.ac.uk/QuickGO/GTerm?id=' + term.id + '">' + term.id + '&nbsp;<i class="external icon"></i></a>&nbsp;' + term.name;

                if (term.isObsolete)
                    content += '&nbsp;<span class="ui tiny red label">Obsolete</span>';

                if (term.replacedBy)
                    content += '&nbsp;<span class="ui tiny yellow label">Secondary</span>';

                content += '&nbsp;<a data-go-id="'+ term.id +'"><i class="trash icon"></i></a>';
                content += '<i class="right-floated caret left icon"></i><p class="hidden">'+ term.definition +'</p></dd>';
            });
        } else
            content += '<dd>No terms assigned in this category.</dd>';

        content += '<dt>Biological Process</dt>';
        if (data.hasOwnProperty('P')) {
            data['P'].forEach(term => {
                content += '<dd><a target="_blank" href="http://www.ebi.ac.uk/QuickGO/GTerm?id=' + term.id + '">' + term.id + '&nbsp;<i class="external icon"></i></a>&nbsp;' + term.name;

                if (term.isObsolete)
                    content += '&nbsp;<span class="ui tiny red label">Obsolete</span>';

                if (term.replacedBy)
                    content += '&nbsp;<span class="ui tiny yellow label">Secondary</span>';

                content += '&nbsp;<a data-go-id="'+ term.id +'"><i class="trash icon"></i></a>';
                content += '<i class="right-floated caret left icon"></i><p class="hidden">'+ term.definition +'</p></dd>';
            });
        } else
            content += '<dd>No terms assigned in this category.</dd>';

        content += '<dt>Cellular Component</dt>';
        if (data.hasOwnProperty('C')) {
            data['C'].forEach(term => {
                content += '<dd><a target="_blank" href="http://www.ebi.ac.uk/QuickGO/GTerm?id=' + term.id + '">' + term.id + '&nbsp;<i class="external icon"></i></a>&nbsp;' + term.name;

                if (term.isObsolete)
                    content += '&nbsp;<span class="ui tiny red label">Obsolete</span>';

                if (term.replacedBy)
                    content += '&nbsp;<span class="ui tiny yellow label">Secondary</span>';

                content += '&nbsp;<a data-go-id="'+ term.id +'"><i class="trash icon"></i></a>';
                content += '<i class="right-floated caret left icon"></i><p class="hidden">'+ term.definition +'</p></dd>';
            });
        } else
            content += '<dd>No terms assigned in this category.</dd>';


        document.getElementById('interpro2go').innerHTML = content;

        addGOEvents(entryID);
    });
}

function addGOEvents(entryID) {
    // TODO: when adding/removing, the counters should be updated as well.

    // Showing/hiding GO defintions
    Array.from(document.querySelectorAll('dl i.right-floated')).forEach(elem => {
        elem.addEventListener('click', e => {
            const icon = e.target;
            const block = icon.parentNode.querySelector('p');

            if (block.className === 'hidden') {
                block.className = '';
                icon.className = 'right-floated caret down icon';
            } else {
                block.className = 'hidden';
                icon.className = 'right-floated caret left icon';
            }
        });
    });

    Array.from(document.querySelectorAll('a[data-go-id]')).forEach(elem => {
        elem.addEventListener('click', e => {
            const goID = elem.getAttribute('data-go-id');

            utils.openConfirmModal(
                'Delete GO term?',
                '<strong>' + goID + '</strong> will not be associated to <strong>'+ entryID +'</strong> any more.',
                'Delete',
                function () {
                    utils.deletexhr('/api/entry/' + entryID + '/go/', {ids: goID}, data => {
                        if (data.status)
                            getGOTerms(entryID);
                        else {
                            const modal = document.getElementById('error-modal');
                            modal.querySelector('.content p').innerHTML = data.message;
                            $(modal).modal('show');
                        }
                    });
                }
            )
        });
    });
}

function addGoTerm(accession, termID) {
    return new Promise(((resolve, reject) => {
        return fetch('/api/entry/' + accession + '/go/' + termID + '/', {method: 'PUT'})
            .then(response => response.json())
            .then(result => {
                const msg = document.getElementById('go-error');
                if (result.status) {
                    setClass(msg, 'hidden', true);
                    getGOTerms(accession);
                    resolve();
                } else {
                    msg.querySelector('.header').innerHTML = result.title;
                    msg.querySelector('p').innerHTML = result.message;
                    setClass(msg, 'hidden', false);
                }
            });
    }));

}

function getSignatures(accession) {
    return fetch('/api' + location.pathname + 'signatures/')
        .then(response => response.json())
        .then(signatures => {
            const accessions = signatures.map(s => s.accession).join('/');

            // Links to comparison pages
            Array.from(document.querySelectorAll('a[data-signatures-page]')).forEach(elem => {
                const page = elem.getAttribute('data-signatures-page');
                elem.href = '/signatures/' + accessions + '/' + page + '/';
            });

            // Stats
            Array.from(document.querySelectorAll('[data-statistic="signatures"]')).forEach(elem => {
                elem.innerHTML = signatures.length;
            });

            // Table of signatures
            let html = '';
            signatures.forEach(s => {
                html += '<tr>'
                    + '<td class="collapsing">'
                    + '<i class="database icon" style="color: '+ s.color +'"></i>'
                    + '</td>'
                    + '<td>'
                    +'<a target="_blank" href="'+ s.link +'">'
                    + s.database + '&nbsp;<i class="external icon"></i>'
                    + '</a>'
                    + '</td>'
                    + '<td>'
                    + '<a href="/prediction/'+ s.accession +'/">'+ s.accession +'</a>'
                    + '</td>'
                    + '<td>'+ s.name +'</td>'
                    + '<td class="right aligned">'+ s.num_proteins.toLocaleString() +'</td>'
                    + '<td class="collapsing">'
                    + '<button data-accession="'+ s.accession +'" class="ui circular icon button">'
                    + '<i class="icon trash"></i>'
                    + '</button>'
                    + '</td>'
                    + '</tr>';
            });
            const tbody = document.getElementById('signatures-content');
            tbody.innerHTML = html;
            // todo: events to remove
        });
}

function renderGoTerms(terms, div, accession) {
    let html = '';
    if (terms.length) {
        html = '<div class="ui list">';
        terms.forEach(term => {
            html += '<div class="item">'
                + '<div class="content">'
                + '<div class="header">'
                + '<a target="_blank" href="https://www.ebi.ac.uk/QuickGO/GTerm?id='+ term.id +'">'
                + term.name + ' (' + term.id + ')'
                + '&nbsp;<i class="external icon"></i>'
                + '</a>';

            if (term.is_obsolete)
                html += '&nbsp;<span class="ui mini red label">Obsolete</span>';

            if (term.secondary)
                html += '&nbsp;<span class="ui mini yellow label">Secondary</span>';

            html += '<i data-id="'+ term.id +'" class="right floated trash button icon"></i>'
                + '</div>'
                + '<div class="description">'+ term.definition +'</div>'
                + '</div>'
                + '</div>';
        });
        html += '</div>';
    } else {
        html = 'No terms assigned in this category.';
    }

    div.innerHTML = html;

    Array.from(div.querySelectorAll('[data-id]')).forEach(elem => {
        elem.addEventListener('click', e => {
            const termID = elem.getAttribute('data-id');

            openConfirmModal(
                'Delete GO term?',
                '<strong>' + termID + '</strong> will not be associated to <strong>'+ accession +'</strong> any more.',
                'Delete',
                () => {
                    fetch('/api/entry/' + accession + '/go/' + termID + '/', {method: 'DELETE'})
                        .then(response => response.json())
                        .then(result => {
                            if (result.status)
                                getGOTerms(accession);
                            else
                                openErrorModal(result);
                        });
                }
            );
        });
    });
}

function getGOTerms(accession) {
    return fetch('/api' + location.pathname + 'go/')
        .then(response => response.json())
        .then(terms => {
            // Stats
            Array.from(document.querySelectorAll('[data-statistic="go"]')).forEach(elem => {
                elem.innerHTML = terms.length;
            });

            renderGoTerms(terms.filter(t => t.category === 'F'), document.getElementById('molecular-functions'), accession);
            renderGoTerms(terms.filter(t => t.category === 'P'), document.getElementById('biological-processes'), accession);
            renderGoTerms(terms.filter(t => t.category === 'C'), document.getElementById('cellular-components'), accession);
        });
}

function getRelationships(accession) {
    return fetch('/api' + location.pathname + 'relationships/')
        .then(response => response.json())
        .then(relationships => {
            const nest = function(obj, isRoot, accession) {
                let html = '';
                const keys = Object.keys(obj).sort();
                if (keys.length) {
                    if (isRoot)
                        html += '<div class="ui list">';
                    else
                        html += '<div class="list">';

                    keys.forEach(key => {
                        const node = obj[key];
                        html += '<div class="item">'
                            + '<div class="content">'
                            + '<div class="header">'
                            + '<span class="ui mini label circular type-'+ node.type +'">'+ node.type +'</span>';

                        if (node.accession === accession)
                            html += node.name + ' (' + node.accession + ')';
                        else {
                            html += '<a href="/entry/' + node.accession + '/">' + node.name + ' (' + node.accession + ')</a>';

                            if (node.deletable)
                                html += '<i data-id="'+ node.accession +'" class="button right floated trash icon"></i>';
                        }

                        html += '</div>'  // close header
                            + nest(node.children, false, accession)
                            + '</div>'  // close content
                            + '</div>'  // close item;
                    });
                    html += '</div>';
                } else if (isRoot)
                    html += '<p>This entry has no relationships.</p>';

                return html;
            };

            const div = document.getElementById('relationships-content');
            div.innerHTML = nest(relationships, true, accession);
            Array.from(div.querySelectorAll('[data-id]')).forEach(elem => {
                elem.addEventListener('click', e => {
                    const accession2 = elem.getAttribute('data-id');

                    openConfirmModal(
                        'Delete relationship?',
                        '<strong>' + accession + '</strong> and <strong>'+ accession2 +'</strong> will not be related any more.',
                        'Delete',
                        () => {
                            fetch('/api/entry/' + accession + '/relationship/' + accession2 + '/', {method: 'DELETE'})
                                .then(response => response.json())
                                .then(result => {
                                    if (result.status)
                                        getRelationships(accession);
                                    else
                                        openErrorModal(result);
                                });
                        }
                    );
                });
            });
        });
}

$(function () {
    finaliseHeader();
    const accession = location.pathname.match(/^\/entry\/(.+)\/$/)[1];

    dimmer(true);
    fetch('/api' + location.pathname)
        .then(response => {
            if (response.status === 200)
                return response.json();
            else {
                document.querySelector('.ui.container.segment').innerHTML = '<div class="ui error message">'
                    + '<div class="header">Entry not found</div>'
                    + '<strong>'+ accession +'</strong> is not a valid InterPro accession.'
                    + '</div>';
                dimmer(false);
                return null;
            }
        })
        .then(entry => {
            if (entry === null) return;
            document.title = entry.name + ' (' + entry.accession + ') | Pronto';

            let html;

            // Header
            html = entry.name + '<div class="sub header">';
            if (entry.is_checked)
                html += '<i class="checkmark icon"></i>';
            html += entry.short_name + ' (' + entry.accession + ')';
            document.querySelector('h1.header').innerHTML = html;

            // Statistics
            setClass(document.getElementById('segment-statistics'), 'type-' + entry.type.code, true);
            document.querySelector('[data-statistic="type"]').innerHTML = entry.type.name;
            document.querySelector('[data-statistic="update"]').innerHTML = entry.last_modification;

            // Links to public website
            Array.from(document.querySelectorAll('a[data-public-href]')).forEach(elem => {
                const base = elem.getAttribute('data-public-href');
                elem.href = base + '/' + accession;
            });

            const promises = [
                getSignatures(accession),
                getGOTerms(accession),
                getRelationships(accession),

            ];

            Promise.all(promises).then(value => {
                console.log(value);
                dimmer(false);
            });

            // Event to add comments
            document.querySelector('.ui.comments form button').addEventListener('click', e => {
                e.preventDefault();
                const form = e.target.closest('form');
                const accession = form.getAttribute('data-id');
                const textarea = form.querySelector('textarea');

                postEntryComment(accession, textarea.value.trim())
                    .then(result => {
                        if (result.status)
                            getEntryComments(accession, 2, e.target.closest(".ui.comments"));
                        else
                            openErrorModal(result.message);
                    });
            });

            // Get comments
            getEntryComments(accession, 2, document.querySelector('.ui.comments'));

            // Event to add GO annotations
            (function () {
                const form = document.getElementById('add-terms');
                const input = form.querySelector('.ui.input input');
                input.addEventListener('keyup', e => {
                    if (e.which === 13 && e.target.value.trim().length) {
                        addGoTerm(accession, e.target.value.trim())
                            .then(() => {
                                input.value = null;
                            })
                    }
                });
                form.querySelector('.ui.input button').addEventListener('click', e => {
                    if (input.value.trim().length) {
                        addGoTerm(accession, input.value.trim())
                            .then(() => {
                                input.value = null;
                            })
                    }

                });
            })();

            // Event to add relationships
            (function () {
                const select = document.querySelector('#add-relationship .ui.dropdown');
                select.innerHTML = '<option value="">Relationship type</option>'
                    + '<option value="parent">Parent of '+ accession +'</option>'
                    + '<option value="child">Child of '+ accession +'</option>';
                $(select).dropdown();

                // Using Semantic-UI form validation
                $('#add-relationship').form({
                    on: 'submit',
                    fields: {
                        accession: 'empty',
                        type: 'empty'
                    },
                    onSuccess: function (event, fields) {
                        let url;
                        if (fields.type === 'parent')
                            url = '/api/entry/' + fields.accession.trim() + '/child/' + accession + '/';
                        else
                            url = '/api/entry/' + accession + '/child/' + fields.accession.trim() + '/';

                        fetch(url, {method: 'PUT'})
                            .then(response => response.json())
                            .then(result => {
                                const msg = document.getElementById('relationship-error');
                                if (result.status) {
                                    $(this).form('clear');
                                    setClass(msg, 'hidden', true);
                                    getRelationships(accession);
                                } else {
                                    msg.querySelector('.header').innerHTML = result.title;
                                    msg.querySelector('p').innerHTML = result.message;
                                    setClass(msg, 'hidden', false);
                                }
                            });
                    }
                })
            })();
        });

    return;



    // Init Semantic-UI elements
    $('[data-content]').popup();

    const entryID = match[1];

    utils.getComments(
        document.querySelector('.ui.sticky .ui.comments'),
        'entry', entryID, 2, null
    );

    // Adding comments
    document.querySelector('.ui.comments form button').addEventListener('click', e => {
        e.preventDefault();
        const form = e.target.closest('form');
        const textarea = form.querySelector('textarea');

        utils.post('/api/entry/'+ entryID +'/comment/', {
            comment: textarea.value.trim()
        }, data => {
            utils.setClass(textarea.closest('.field'), 'error', !data.status);

            if (!data.status) {
                const modal = document.getElementById('error-modal');
                modal.querySelector('.content p').innerHTML = data.message;
                $(modal).modal('show');
            } else
                utils.getComments(
                    e.target.closest('.ui.comments'),
                    'entry', entryID, 2, null
                );
        });
    });

    addGOEvents(entryID);

    const div = document.getElementById('add-terms');
    const input = div.querySelector('.ui.input input');
    input.addEventListener('keyup', e => {
        if (e.which === 13 && e.target.value.trim().length)
            addGoTerms(entryID, e.target.value.trim(), function () {
                getGOTerms(entryID);
                input.value = null;
            });
    });

    div.querySelector('.ui.input button').addEventListener('click', e => {
        if (input.value.trim().length)
            addGoTerms(entryID, input.value.trim(), function () {
                getGOTerms(entryID);
                input.value = null;
            });
    });

    Array.from(document.querySelectorAll('a[data-ref]')).forEach(elem => {
        elem.addEventListener('click', e => {
            let active = document.querySelector('li.active');
            if (active) utils.setClass(active, 'active', false);

            const id = e.target.getAttribute('href').substr(1);
            active = document.getElementById(id);
            utils.setClass(active, 'active', true);
        });
    });

    utils.listenMenu(document.querySelector('.ui.vertical.menu'));
});