import {dimmer, setClass, openErrorModal, openConfirmModal} from "../ui.js";
import {finaliseHeader} from "../header.js";
import {getEntryComments, postEntryComment} from "../comments.js";
import {nvl} from "../utils.js";

const annotationEditor = {
    element: null,
    textareaText: null,
    textFormatted: null,
    reset: function () {
        this.element = null;
        this.textareaText = null;
        this.textFormatted = null;
    },
    open: function (annID, text) {
        const element = document.getElementById(annID);
        let segment;

        if (this.element === element)
            return;  // Current annotation is being edited: carry on
        else if (this.element !== null) {
            // Another annotation is already being edited
            const textareaText = this.element.querySelector('.segment textarea').value;

            if (textareaText !== this.textareaText) {
                /*
                    Annotation has been changed:
                    need to save or discard changes before editing another annotation
                 */
                openErrorModal({
                    title: 'Cannot edit multiple annotation',
                    message: 'Another annotation is already being edited. Please save or discard changes before editing a second annotation.'
                });
                return;
            }
            else {
                // Edited but not changed: just replace by formatted annotation and move on
                this.close();
            }
        }

        this.element = element;

        const menu = this.element.querySelector('.ui.bottom.menu');

        // Reset error message
        const msg = menu.querySelector('.item.message');
        msg.className = 'item message';
        msg.innerHTML = null;

        // Display bottom menu
        setClass(menu, 'hidden', false);

        // Save formatted annotation
        segment = this.element.querySelector('.segment');
        this.textFormatted = segment.innerHTML;

        // Display raw annotation
        segment.innerHTML = '<div class="ui form">' +
            '<div class="field">' +
            '<label>Reason for update</label>' +
            '<select>' +
            '<option value="Cross-references">Cross-references</option>' +
            '<option value="References">Literature references</option>' +
            '<option value="Text" selected>Text</option>' +
            '<option value="Spelling">Typos, grammar errors, spelling mistakes</option>' +
            '</select>' +
            '</div>' +
            '<div class="field"><textarea rows="15"></textarea></div></div>';

        const textarea = this.element.querySelector('.segment textarea');
        textarea.value = text;
        // If the annotation contains weird characters, they may be reformatted, so we read back from textarea
        this.textareaText = textarea.value;
    },
    close: function () {
        if (this.element === null) return;

        // Hide bottom menu
        setClass(this.element.querySelector('.ui.bottom.menu'), 'hidden', true);

        // Restore formatted annotation
        const segment = this.element.querySelector('.segment');
        segment.innerHTML = this.textFormatted;

        // recreate highlight even listeners for THIS annotation only
        addHighlightEvenListeners(segment);

        this.reset();
    },
    reorder: function(accession, annID, x) {
        fetch('/api/entry/' + accession + '/annotation/' + annID + '/order/' + x + '/', { method: 'POST' })
            .then(response => response.json())
            .then(result => {
                if (result.status)
                    getAnnotations(accession);
                else
                    openErrorModal(result);
            });
    },
    drop: function (accession, annID) {
        openConfirmModal(
            'Unlink annotation?',
            'This annotation will not be associated to <strong>' + accession + '</strong> any more.',
            'Unlink',
            () => {
                fetch('/api/entry/' + accession + '/annotation/' + annID + '/', {method: 'DELETE'})
                    .then(response => response.json())
                    .then(result => {
                        if (result.status)
                            getAnnotations(accession);
                        else
                            openErrorModal(result);
                    });
            }
        );
    },
    save: function (accession, annID) {
        if (this.element === null) return;

        const select = this.element.querySelector('select');
        const reason = select.options[select.selectedIndex].value;

        if (reason.length)
            setClass(select.parentNode, 'error', false);
        else {
            setClass(select.parentNode, 'error', true);
            return;
        }

        // Raw text to save
        const textarea = this.element.querySelector('textarea');
        const textareaText = textarea.value;
        if (textareaText === this.textareaText) {
            // Text did not change: close
            this.close();
            return;
        }

        const options = {
            method: 'POST',
            headers: {
                'Content-type': 'application/x-www-form-urlencoded; charset=UTF-8'
            },
            body: 'text=' + textareaText + '&reason=' + reason
        };

        // Update annotation
        fetch('/api/annotation/' + annID + '/', options)
            .then(response => response.json())
            .then(result => {
                if (result.status)
                    getAnnotations(accession);
                else {
                    const msg = this.element.querySelector('.item.message');
                    msg.innerHTML = result.message.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    msg.className = 'item negative message';
                }
            });
    }
};

function linkAnnotation(accession, annID) {
    return fetch('/api/entry/' + accession + '/annotation/' + annID + '/', { method: 'PUT' })
        .then(response => response.json())
}

function addHighlightEvenListeners(div) {
    Array.from(div.querySelectorAll('a[data-ref]')).forEach(elem => {
        elem.addEventListener('click', e => {
            let active = document.querySelector('li.active');
            if (active) setClass(active, 'active', false);

            const id = e.target.getAttribute('href').substr(1);
            active = document.getElementById(id);
            setClass(active, 'active', true);
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

function getAnnotations(accession) {
    return fetch('/api' + location.pathname + 'annotations/')
        .then(response => response.json())
        .then(results => {
            const rePub = /<cite\s+id="(PUB\d+)"\s*\/>/g;
            const orderedRefs = [];
            const supplRefs = [];
            const annotations = new Map();

            let html = '';
            if (results.annotations.length) {
                results.annotations.forEach(ann => {
                    let text = ann.text;
                    annotations.set(ann.id, text);

                    // Search all references in the text
                    let arr;
                    while ((arr = rePub.exec(text)) !== null) {
                        const pubID = arr[1];

                        if (results.references.hasOwnProperty(pubID)) {
                            let i = orderedRefs.indexOf(pubID);
                            if (i === -1) {
                                // First occurrence of the reference in any text
                                orderedRefs.push(pubID);
                                i = orderedRefs.length;
                            } else
                                i++;

                            text = text.replace(arr[0], '<a data-ref href="#'+ pubID +'">'+ i +'</a>');
                        }
                    }

                    // Replace cross-ref tags by links
                    results.cross_references.forEach(xref => {
                        text = text.replace(xref.tag, '<a href="'+ xref.url +'">'+ xref.id +'</a>');
                    });

                    html += '<div id="'+ ann.id +'" class="annotation">'

                        // Action menu
                        + '<div class="ui top attached mini menu">'
                        + '<a data-action="edit" class="item"><abbr title="Edit this annotation"><i class="edit icon"></i></abbr></a>'
                        + '<a data-action="movedown" class="item"><abbr title="Move this annotation down"><i class="arrow down icon"></i></abbr></a>'
                        + '<a data-action="moveup" class="item"><abbr title="Move this annotation up"><i class="arrow up icon"></i></abbr></a>'
                        + '<a data-action="delete" class="item"><abbr title="Delete this annotation"><i class="trash icon"></i></abbr></a>'

                        // Info menu (last edit comment and number of entries using this annotation)
                        + '<div class="right menu">'
                        + nvl(ann.comment, '', '<span class="item">'+ ann.comment +'</span>')
                        + '<span class="item">Associated to '+ ann.count + (ann.count > 1 ? "&nbsp;entries" : "&nbsp;entry") + '</span>'
                        + '</div>'
                        + '</div>'

                        // Text
                        + '<div class="ui attached segment">' + text + '</div>'

                        // Bottom menu
                        + '<div class="hidden ui borderless bottom attached mini menu" data-annid="'+ ann.id +'">'
                        + '<span class="item message"></span>'
                        + '<div class="right menu">'
                        + '<div class="item"><a data-action="cancel" class="ui basic secondary button">Cancel</a></div>'
                        + '<div class="item"><a data-action="save" class="ui primary button">Save</a></div>'
                        + '</div>'
                        + '</div>'
                        + '</div>';
                });
            } else {
                html = '<div class="ui error message">'
                    + '<div class="header">Missing description</div>'
                    + '<p>This entry has not annotations. Please add one, or make sure that this entry is not checked.</p>'
                    + '</div>';
            }

            document.getElementById('annotations').innerHTML = html;

            // Render references
            if (orderedRefs.length) {
                html += '<ol>';
                orderedRefs.forEach(pubID => {
                    const pub = results.references[pubID];

                    html += '<li id="'+ pubID +'">'
                        + '<div class="header">'+ pub.title +'</div>'
                        + '<div class="item">'+ pub.authors +'</div>'
                        + '<div class="item"><em>'+ pub.journal +'</em> '+ pub.year +', '+ pub.volume +':'+ pub.pages +'</div>'
                        + '<div class="ui horizontal link list">';

                    if (pub.doi)
                        html += '<a target="_blank" class="item" href="'+ pub.doi +'">View article&nbsp;<i class="external icon"></i></a>';

                    if (pub.pmid) {
                        html += '<span class="item">Europe PMC:&nbsp;'
                            + '<a target="_blank" class="item" href="http://europepmc.org/abstract/MED/'+ pub.pmid +'/">'
                            + pub.pmid +'&nbsp;<i class="external icon"></i>'
                            + '</a>'
                            + '</span>';
                    }
                });

                html += '</ol>';
            }  else
                html = '<p>This entry has no references.</p>';

            document.getElementById('references-content').innerHTML = html;

            // Render suppl. references
            for (let pubID in results.references) {
                if (results.references.hasOwnProperty(pubID) && !orderedRefs.includes(pubID))
                    supplRefs.push(results.references[pubID]);
            }

            if (supplRefs.length) {
                // Sort chronologically (as they do not appear in annotations)
                supplRefs.sort((a, b) => { return a.year - b.year; });

                html = '<p>The following publications were not referred to in the description, but provide useful additional information.</p>' +
                    '<ul class="ui list">';

                supplRefs.forEach(pub => {
                    html += '<li id="'+ pub.id +'">'
                        + '<div class="header">'+ pub.title +'</div>'
                        + '<div class="item">'+ pub.authors +'</div>'
                        + '<div class="item"><em>'+ pub.journal +'</em> '+ pub.year +', '+ pub.volume +':'+ pub.pages +'</div>'
                        + '<div class="ui horizontal link list">';

                    if (pub.doi)
                        html += '<a target="_blank" class="item" href="'+ pub.doi +'">View article&nbsp;<i class="external icon"></i></a>';

                    if (pub.pmid) {
                        html += '<span class="item">Europe PMC:&nbsp;'
                            + '<a target="_blank" class="item" href="http://europepmc.org/abstract/MED/'+ pub.pmid +'/">'
                            + pub.pmid +'&nbsp;<i class="external icon"></i>'
                            + '</a>'
                            + '</span>';
                    }
                });

                html += '</ul>';
            } else
                html = '<p>This entry has no additional references.</p>';

            document.getElementById('supp-references-content').innerHTML = html;

            // Update references stats
            Array.from(document.querySelectorAll('[data-statistic="references"]')).forEach(elem => {
                elem.innerHTML = (orderedRefs.length + supplRefs.length).toLocaleString();
            });

            // Highlight selected reference
            Array.from(document.querySelectorAll('.annotation')).forEach(elem => {
                addHighlightEvenListeners(elem);
            });

            // Event listener on actions
            annotationEditor.reset();
            Array.from(document.querySelectorAll('#annotations a[data-action]')).forEach(elem => {
                elem.addEventListener('click', e => {
                    // Do not use e.target as it could be the <abbr> or <i> elements

                    const annID = elem.closest('.annotation').getAttribute('id');
                    if (!annotations.has(annID)) {
                        // TODO: display error?
                        return;
                    }

                    const action = elem.getAttribute('data-action');
                    const text = annotations.get(annID);
                    if (action === 'edit')
                        annotationEditor.open(annID, text);
                    else if (action === 'movedown')
                        annotationEditor.reorder(accession, annID, 1);
                    else if (action === 'moveup')
                        annotationEditor.reorder(accession, annID, -1);
                    else if (action === 'delete')
                        annotationEditor.drop(accession, annID);
                    else if (action === 'save')
                        annotationEditor.save(accession, annID);
                    else if (action === 'cancel')
                        annotationEditor.close();
                });
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

function escapeXmlTags(text) {
    return text
        .replace(/<cite\s+id="(PUB\d+)"\s*\/>/g, '&lt;cite id="$1"/&gt;')
        .replace(/<dbxref\s+db\s*=\s*"(\w+)"\s+id\s*=\s*"([\w.\-]+)"\s*\/>/g, '&ltdbxref db="$1" id="$2"/&gt;')
        .replace(/<taxon\s+tax_id\s*=\s*"(\d+)"\s*>([^<]+)<\/taxon>/g, '&lttaxon tax_id="$1"&gt;$2&lt;/taxon&gt;');
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
                getAnnotations(accession)
            ];

            Promise.all(promises).then(value => {
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

            // Event to create annotations
            (function () {
                document.getElementById('create-annotation').addEventListener('click', e => {
                    const modal = document.getElementById('new-annotation');
                    const msg = modal.querySelector('.message');

                    $(modal)
                        .modal({
                            closable: false,
                            onDeny: function() {
                                modal.querySelector('textarea').value = null;
                                setClass(msg, 'hidden', true);
                            },
                            onApprove: function() {
                                const options = {
                                    method: 'PUT',
                                    headers: {
                                        'Content-type': 'application/x-www-form-urlencoded; charset=UTF-8'
                                    },
                                    body: 'text=' + modal.querySelector('textarea').value
                                };

                                fetch('/api/annotation/', options)
                                    .then(response => response.json())
                                    .then(result => {
                                        if (result.status) {
                                            setClass(msg, 'hidden', true);

                                            // Annotation created: clear textarea
                                            modal.querySelector('textarea').value = null;

                                            // Return a promise to link the created annotation to the entry
                                            return linkAnnotation(accession, result.id);
                                        } else {
                                            msg.querySelector('.header').innerHTML = result.title;
                                            msg.querySelector('p').innerHTML = result.message.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                                            setClass(msg, 'hidden', false);
                                        }
                                    })
                                    .then(result => {
                                        if (result.status) {
                                            getAnnotations(accession);
                                            $(modal).modal('hide');
                                        } else {
                                            // todo: show error
                                        }
                                    });

                                // Return false to prevent modal to close
                                return false;
                            }
                        })
                        .modal('show');
                });
            })();

            // Event to list signatures annotations
            (function () {
                document.getElementById('signatures-annotations').addEventListener('click', e => {
                    fetch('/api/entry/' + accession + '/signatures/annotations/')
                        .then(response => response.json())
                        .then(results => {
                            const signatures = new Map();
                            let html = '';
                            if (results.length) {
                                results.forEach(s => {
                                    signatures.set(s.accession, s.text);
                                    html += '<div class="ui top attached mini menu">'
                                        + '<a href="/prediction/'+ s.accession +'/" class="header item">'+ s.accession +'</a>';

                                    if (s.name)
                                        html += '<span class="item">'+ s.name +'</span>';

                                    html += '</div>';
                                    if (s.text) {
                                        html += '<div class="ui attached segment">' + escapeXmlTags(s.text) + '</div>'
                                            + '<div class="ui bottom attached borderless mini menu">'
                                            + '<span class="item message"></span>'
                                            + '<div class="right item">'
                                            + '<button data-id="'+ s.accession +'" class="ui primary button">Add</button>'
                                            + '</div>'
                                            + '</div>';
                                    } else
                                        html += '<div class="ui bottom attached secondary segment">No annotation available.</i></div>';
                                });
                            } else
                                html = '<p><strong>' + accession + '</strong> does not have any signatures.</p>';

                            const modal = document.getElementById('modal-annotations');
                            modal.querySelector('.header').innerHTML = 'Signatures annotations';
                            modal.querySelector('.content').innerHTML = html;

                            Array.from(modal.querySelectorAll('.content button[data-id]')).forEach(btn => {
                                btn.addEventListener('click', e => {
                                    const acc = e.target.getAttribute('data-id');
                                    if (!signatures.has(acc))
                                        return;

                                    const options = {
                                        method: 'PUT',
                                        headers: {
                                            'Content-type': 'application/x-www-form-urlencoded; charset=UTF-8'
                                        },
                                        body: 'text=' + signatures.get(acc)
                                    };

                                    const menu = btn.closest('.ui.menu');
                                    const msg = menu.querySelector('.item.message');

                                    fetch('/api/annotation/', options)
                                        .then(response => response.json())
                                        .then(result => {
                                            /*
                                                Whether the annotation was created (code 200) or it already exists (code 400),
                                                we want to link it to
                                             */
                                            if (result.id)
                                                return linkAnnotation(accession, result.id);
                                            else {
                                                msg.innerHTML = result.message;
                                                msg.className = 'item negative message';
                                            }
                                        })
                                        .then(result => {
                                            if (result.status) {
                                                getAnnotations(accession);
                                                $(modal).modal('hide');
                                            } else {
                                                msg.innerHTML = result.message;
                                                msg.className = 'item negative message';
                                            }
                                        });

                                    // Return false to prevent modal to close
                                    return false;
                                });
                            });

                            $(modal).modal('show');
                        });
                });
            })();

            // Event to search annotations
            (function () {
                document.getElementById('search-annotations').addEventListener('keyup', e => {
                    if (e.which === 13) {
                        const query = e.target.value.trim();

                        if (query.length < 3)
                            return;

                        // Current annotations // TODO: rewrite not to use the DOM?
                        const annotations = new Set(Array.from(document.querySelectorAll('.annotation')).map(elem => elem.getAttribute('id')));

                        dimmer(true);
                        fetch('/api/annotation/search/?q=' + query)
                            .then(response => response.json())
                            .then(hits => {
                                let html = '';

                                if (hits.length) {
                                    hits.forEach(ann => {
                                        if (annotations.has(ann.id))
                                            html += '<div data-annid="'+ ann.id +'" class="ui top attached secondary segment">' + escapeXmlTags(ann.text) + '</div>';
                                        else
                                            html += '<div data-annid="'+ ann.id +'" class="ui top attached segment">' + escapeXmlTags(ann.text) + '</div>';

                                        html += '<div data-annid="'+ ann.id +'" class="ui bottom borderless attached mini menu">' +
                                            '<span class="item">Associated to '+ ann.num_entries + ' entries</span>';

                                        if (!annotations.has(ann.id))
                                            html +=  '<div class="right item"><button class="ui primary button">Add</button></div>';

                                        html += '</div>';
                                    });
                                } else {
                                    html = '<p>No annotations found for <strong>'+ query +'</strong>.</p>';
                                }

                                const modal = document.getElementById('modal-annotations');
                                modal.querySelector('.header').innerHTML = 'Results found:&nbsp;'+ hits.length.toLocaleString();
                                modal.querySelector('.content').innerHTML = html;

                                Array.from(modal.querySelectorAll('.content button')).forEach(elem => {
                                    elem.addEventListener('click', e => {
                                        const menu = e.target.closest('[data-annid]');
                                        const annID = menu.getAttribute('data-annid');
                                        linkAnnotation(accession, annID)
                                            .then(result => {
                                                if (result.status) {
                                                    getAnnotations(accession);

                                                    // Remove menu to prevent user to add the abstract a second time
                                                    menu.parentNode.removeChild(menu);

                                                    // Update segment's style
                                                    const segment = modal.querySelector('.ui.segment[data-annid="'+ annID +'"]');
                                                    segment.className = 'ui secondary segment';
                                                } else {
                                                    // todo: show error
                                                }
                                            });
                                    });
                                });
                                dimmer(false);
                                $(modal).modal('show');
                            });
                    }
                });
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