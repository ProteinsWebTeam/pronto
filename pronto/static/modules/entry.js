import * as ui from "../ui.js";
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
                ui.openErrorModal({
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

        // // Reset error message
        // const msg = menu.querySelector('.item.message');
        // msg.className = 'item message';
        // msg.innerHTML = null;

        // Display bottom menu
        ui.setClass(menu, 'hidden', false);

        // Save formatted annotation
        segment = this.element.querySelector('.segment');
        this.textFormatted = segment.innerHTML;

        // Display raw annotation
        segment.innerHTML = '<div class="ui form">'
            + '<div class="field">'
            + '<label>Reason for update</label>'
            + '<select>'
            + '<option value="Annotation" selected>Annotation</option>'
            + '<option value="Cross-references">Cross-references</option>'
            + '<option value="References">Literature references</option>'
            + '<option value="Spelling">Typos, grammar errors, spelling mistakes</option>'
            + '</select>'
            + '</div>'
            + '<div class="field"><textarea rows="15"></textarea></div>'
            + '<div class="ui error message"></div> '
            + '</div>';

        const textarea = this.element.querySelector('.segment textarea');
        textarea.value = text;
        // If the annotation contains weird characters, they may be reformatted, so we read back from textarea
        this.textareaText = textarea.value;
    },
    close: function () {
        if (this.element === null) return;

        // Hide bottom menu
        ui.setClass(this.element.querySelector('.ui.bottom.menu'), 'hidden', true);

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
                    getAnnotations(accession, true).then(() => { $('.ui.sticky').sticky(); });
                else
                    ui.openErrorModal(result);
            });
    },
    drop: function (accession, annID) {
        ui.openConfirmModal(
            'Unlink annotation?',
            'This annotation will not be associated to <strong>' + accession + '</strong> any more.',
            'Unlink',
            () => {
                fetch('/api/entry/' + accession + '/annotation/' + annID + '/', {method: 'DELETE'})
                    .then(response => response.json())
                    .then(result => {
                        if (result.status)
                            getAnnotations(accession, true).then(() => { $('.ui.sticky').sticky(); });
                        else
                            ui.openErrorModal(result);
                    });
            }
        );
    },
    save: function (accession, annID) {
        if (this.element === null) return;

        const select = this.element.querySelector('select');
        const reason = select.options[select.selectedIndex].value;

        if (reason.length)
            ui.setClass(select.parentNode, 'error', false);
        else {
            ui.setClass(select.parentNode, 'error', true);
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
                if (result.status) {
                    // Get annotations and supplementary references (may have changed)
                    const promises = [
                        getAnnotations(accession, true),
                        getSupplReferences(accession)
                    ];

                    Promise.all(promises).then(value => {
                        $('.ui.sticky').sticky();
                    });
                } else {
                    const form = this.element.querySelector('.ui.form');
                    form.querySelector('.ui.message').innerHTML = '<div class="header">'+ result.title +'</div><p>'+ result.message.replace(/</g, '&lt;').replace(/>/g, '&gt;') +'</p>';
                    ui.setClass(textarea.parentNode, 'error', true);
                    ui.setClass(form, 'error', true);
                }
            });
    }
};

function integrateSignature(entryAcc, signatureAcc, moveIfIntegrated) {
    const options = {
        method: 'PUT',
        headers: {
            'Content-type': 'application/x-www-form-urlencoded; charset=UTF-8'
        }
    };

    if (moveIfIntegrated)
        options.body = 'confirm';

    fetch('/api/entry/' + entryAcc + '/signature/' + signatureAcc + '/', options)
        .then(response => response.json())
        .then(result => {
            const msg = document.querySelector('#signatures .ui.message');

            if (!result.status) {
                msg.querySelector('.header').innerHTML = result.title;
                msg.querySelector('p').innerHTML = result.message;
                msg.className = 'ui error message';
            } else if (result.unchecked) {
                /*
                    Moved signature to one entry to another,
                    and unchecked previous entry (no signature any more)
                */
                msg.querySelector('.header').innerHTML = 'Entry unchecked';
                msg.querySelector('p').innerHTML = '<em><a href="/entry/'+ result.entry +'/">'+ result.entry +'</a></em> has been unchecked because it does not have any signatures.';
                msg.className = 'ui info message';

                $('#signatures .ui.form').form('clear');
                getSignatures(entryAcc).then(() => { $('.ui.sticky').sticky(); });

            } else if (result.entry) {
                // Signature already integrated: ask for confirmation

                msg.querySelector('.header').innerHTML = 'Signature already integrated';
                msg.querySelector('p').innerHTML = '<em>'+ result.signature +'</em> is integrated into '
                    + '<em><a href="/entry/'+ result.entry +'/">'+ result.entry +'</a></em>. '
                    + 'Click <strong><a href="#" data-confirm>here</a></strong> to move it to <em>'+ entryAcc +'</em>.';
                msg.className = 'ui error message';

                // Event listener to confirm re-integration
                msg.querySelector('[data-confirm]').addEventListener('click', e => {
                    e.preventDefault();
                    integrateSignature(entryAcc, signatureAcc, true);
                });
            }  else {
                ui.setClass(msg, 'hidden', true);
                $('#signatures .ui.form').form('clear');
                getSignatures(entryAcc).then(() => { $('.ui.sticky').sticky(); });
            }
        });
}

function linkAnnotation(accession, annID) {
    return fetch('/api/entry/' + accession + '/annotation/' + annID + '/', { method: 'PUT' })
        .then(response => response.json())
}

function addHighlightEvenListeners(div) {
    Array.from(div.querySelectorAll('a[data-ref]')).forEach(elem => {
        elem.addEventListener('click', e => {
            let active = document.querySelector('li.active');
            if (active) ui.setClass(active, 'active', false);

            const id = e.target.getAttribute('href').substr(1);
            active = document.getElementById(id);
            ui.setClass(active, 'active', true);
        });
    });
}

function addGoTerm(accession, termID) {
    return new Promise(((resolve, reject) => {
        return fetch('/api/entry/' + accession + '/go/' + termID + '/', {method: 'PUT'})
            .then(response => response.json())
            .then(result => {
                if (result.status) {
                    getGOTerms(accession).then(() => { $('.ui.sticky').sticky(); });
                    resolve();
                } else
                    reject(result);
            });
    }));
}

function getSupplReferences(accession) {
    return fetch('/api' + location.pathname + 'references/')
        .then(response => response.json())
        .then(references => {
            let html = '';
            if (references.length) {
                html = '<p>The following publications were not referred to in the description, but provide useful additional information.</p>'
                    + '<ul class="ui list">';

                references.sort((a, b) => a.year - b.year)
                    .forEach(pub => {
                        html += '<li id="'+ pub.id +'" class="item">'
                            + '<div class="header">'+ pub.title
                            + '<i data-id="'+ pub.id +'" class="right floated trash button icon"></i>'
                            + '</div>'
                            + '<div class="item">'+ pub.authors +'</div>'
                            + '<div class="item">'
                            + '<em>'+ pub.journal +'</em> '+ pub.year +', '+ pub.volume +':'+ pub.pages
                            + '</div>'
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

                        html += '</div></li>';
                    });

                html += '</ul>';
            } else
                html = '<p>This entry has no additional references.</p>';

            document.querySelector('#supp-references .content').innerHTML = html;

            Array.from(document.querySelectorAll('#supp-references [data-id]')).forEach(elem => {
                elem.addEventListener('click', e => {
                    const pubID = elem.getAttribute('data-id');
                    ui.openConfirmModal(
                        'Delete reference?',
                        'This reference will not be associated to this entry any more.',
                        'Delete',
                        () => {
                            fetch('/api/entry/' + accession + '/reference/' + pubID + '/', {method: 'DELETE'})
                                .then(response => response.json())
                                .then(result => {
                                    if (result.status)
                                        getSupplReferences(accession).then(() => { $('.ui.sticky').sticky(); });
                                    else
                                        ui.openErrorModal(result);
                                });
                        }
                    );
                });
            });
        });
}


function getAnnotations(accession, _editingMode) {
    return fetch('/api' + location.pathname + 'annotations/')
        .then(response => response.json())
        .then(results => {
            const editingMode = _editingMode !== undefined ? _editingMode : $('#annotations .ui.toggle.checkbox').checkbox('is checked');

            const rePub = /\[cite:(PUB\d+)\]/gi;
            const mainRefs = [];
            const annotations = new Map();
            const references = new Map(Object.entries(results.references));
            let html = '';
            if (results.annotations.length) {
                results.annotations.forEach(ann => {
                    let text = ann.text;
                    annotations.set(ann.id, {text: text, entries: ann.num_entries});

                    // Search all references in the text
                    let arr;
                    while ((arr = rePub.exec(text)) !== null) {
                        const pubID = arr[1];
                        if (references.has(pubID)) {
                            let i = mainRefs.indexOf(pubID);
                            if (i === -1) {
                                // First occurence of the reference in any annotation
                                mainRefs.push(pubID);
                                i = mainRefs.length;
                            } else
                                i++;

                            text = text.replace(arr[0], '<a data-ref href="#'+ pubID +'">'+ i +'</a>');
                        }
                    }

                    // Replace cross-ref tags by links
                    ann.xrefs.forEach(xref => {
                        text = text.replace(xref.match, '<a target="_blank" href="'+ xref.url +'">'+ xref.id +'&nbsp;<i class="external icon"></i></a>');
                    });

                    if (editingMode) {
                        html += '<div id="'+ ann.id +'" class="annotation">'

                            // Action menu
                            + '<div class="ui top attached mini menu">'
                            + '<a data-action="edit" class="item"><abbr title="Edit this annotation"><i class="edit fitted icon"></i></abbr></a>'
                            + '<a data-action="movedown" class="item"><abbr title="Move this annotation down"><i class="arrow down fitted icon"></i></abbr></a>'
                            + '<a data-action="moveup" class="item"><abbr title="Move this annotation up"><i class="arrow up fitted icon"></i></abbr></a>'
                            + '<a data-action="delete" class="item"><abbr title="Unlink this annotation"><i class="trash fitted icon"></i></abbr></a>'

                            // Info menu (last edit comment and number of entries using this annotation)
                            + '<div class="right menu">'
                            + nvl(ann.comment, '', '<span class="item">'+ ann.comment +'</span>')
                            + '<a data-action="list" class="item"><i class="list fitted icon"></i> Associated to '+ ann.num_entries + ' entries</a>'
                            + '</div>'
                            + '</div>'

                            // Text
                            + '<div class="ui attached segment">' + text + '</div>'

                            // Bottom menu
                            + '<div class="hidden ui borderless bottom attached mini menu" data-annid="'+ ann.id +'">'
                            + '<div class="right menu">'
                            + '<div class="item"><a data-action="cancel" class="ui basic secondary button">Cancel</a></div>'
                            + '<div class="item"><a data-action="save" class="ui primary button">Save</a></div>'
                            + '</div>'
                            + '</div>'
                            + '</div>';
                    } else
                        html += '<div class="ui vertical segment">' + text + '</div>';
                });
            } else {
                html = '<div class="ui error message">'
                    + '<div class="header">Missing description</div>'
                    + '<p>This entry has not annotations. Please add one, or make sure that this entry is not checked.</p>'
                    + '</div>';
            }

            document.querySelector('#annotations > .content').innerHTML = html;

            // Render references
            html = '';
            if (mainRefs.length) {
                html += '<ol>';
                mainRefs.forEach(pubID => {
                    const pub = references.get(pubID);

                    html += '<li id="'+ pubID +'">'
                        + '<div class="header">'+ pub.title +'</div>'
                        + '<div class="item">'+ pub.authors +'</div>'
                        + '<div class="item">'
                        + '<em>'+ pub.journal +'</em> '+ pub.year +', '+ pub.volume +':'+ pub.pages
                        + '</div>'
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

                    html += '</div></li>';
                });

                html += '</ol>';
            }  else
                html = '<p>This entry has no references.</p>';

            document.querySelector('#references .content').innerHTML = html;

            // Update annotations stats
            Array.from(document.querySelectorAll('[data-statistic="annotations"]')).forEach(elem => {
                elem.innerHTML = annotations.size.toLocaleString();
            });

            // Update references stats
            Array.from(document.querySelectorAll('[data-statistic="references"]')).forEach(elem => {
                elem.innerHTML = mainRefs.length.toLocaleString();
            });

            // Highlight selected reference
            Array.from(document.querySelectorAll('.annotation')).forEach(elem => {
                addHighlightEvenListeners(elem);
            });

            // Event listener on actions
            annotationEditor.reset();
            Array.from(document.querySelectorAll('.annotation a[data-action]')).forEach(elem => {
                elem.addEventListener('click', e => {
                    // Do not use e.target as it could be the <abbr> or <i> elements

                    const annID = elem.closest('.annotation').getAttribute('id');
                    if (!annotations.has(annID)) {
                        // TODO: display error?
                        return;
                    }

                    const action = elem.getAttribute('data-action');
                    const ann = annotations.get(annID);
                    const text = ann.text;
                    if (action === 'edit')
                        annotationEditor.open(annID, text);
                    else if (action === 'movedown')
                        annotationEditor.reorder(accession, annID, 1);
                    else if (action === 'moveup')
                        annotationEditor.reorder(accession, annID, -1);
                    else if (action === 'delete')
                        annotationEditor.drop(accession, annID);
                    else if (action === 'save') {
                        if (ann.entries > 1) {
                            ui.openConfirmModal(
                                'Save changes?',
                                'This annotation is used by <strong>' + ann.entries + ' entries</strong>. Changes will be visible for all entries.',
                                'Save',
                                () => annotationEditor.save(accession, annID)
                            );

                        } else
                            annotationEditor.save(accession, annID);
                    } else if (action === 'cancel')
                        annotationEditor.close();
                    else if (action === 'list') {
                        fetch('/api/annotation/' + annID + '/entries/')
                            .then(response => response.json())
                            .then(entries => {
                                let html = '<table class="ui very basic table"><tbody>';
                                entries.forEach(e => {
                                    html += '<tr>' +
                                        '<td class="collapsing">' +
                                        '<span class="ui label circular type-'+ e.type +'">'+ e.type +'</span>' +
                                        '</td>'
                                        + '<td><a href="/entry/'+ e.accession +'/">'+ e.accession +'</a></td>'
                                        + '<td>'+ e.name +'</td></tr>';

                                });

                                const modal = document.getElementById('modal-entries');
                                modal.querySelector('.content').innerHTML = html;
                                $(modal).modal('show');
                            });
                    }
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
                                html += '<i data-id="'+ node.accession +'" class="right floated trash button icon"></i>';
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

            const div = document.querySelector('#relationships > .content');
            div.innerHTML = nest(relationships, true, accession);

            const directRelationships = Array.from(div.querySelectorAll('[data-id]'));

            // Update relationships stats
            Array.from(document.querySelectorAll('[data-statistic="relationships"]')).forEach(elem => {
                elem.innerHTML = directRelationships.length.toLocaleString();
            });

            // Event to delete relationships
            directRelationships.forEach(elem => {
                elem.addEventListener('click', e => {
                    const accession2 = elem.getAttribute('data-id');

                    ui.openConfirmModal(
                        'Delete relationship?',
                        '<strong>' + accession + '</strong> and <strong>'+ accession2 +'</strong> will not be related any more.',
                        'Delete',
                        () => {
                            fetch('/api/entry/' + accession + '/relationship/' + accession2 + '/', {method: 'DELETE'})
                                .then(response => response.json())
                                .then(result => {
                                    if (result.status)
                                        getRelationships(accession).then(() => { $('.ui.sticky').sticky(); });
                                    else
                                        ui.openErrorModal(result);
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
            // Stats
            Array.from(document.querySelectorAll('[data-statistic="signatures"]')).forEach(elem => {
                elem.innerHTML = signatures.length;
            });

            // Table of signatures
            let html = '';
            if (signatures.length) {
                const accessions = signatures.map(s => s.accession).join('/');

                // Links to comparison pages
                Array.from(document.querySelectorAll('a[data-signatures-page]')).forEach(elem => {
                    const page = elem.getAttribute('data-signatures-page');
                    elem.href = '/signatures/' + accessions + '/' + page + '/';
                });

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
            } else {
                // Links to comparison pages
                Array.from(document.querySelectorAll('a[data-signatures-page]')).forEach(elem => {
                    elem.href = '#';
                });

                html = '<tr><td colspan="6" class="center aligned">No integrated signatures</td></tr>';
            }

            const tbody = document.querySelector('#signatures tbody');
            tbody.innerHTML = html;

            Array.from(tbody.querySelectorAll('[data-accession]')).forEach(elem => {
                elem.addEventListener('click', e => {
                    const signatureAcc = elem.getAttribute('data-accession');

                    ui.openConfirmModal(
                        'Unintegrate signature?',
                        '<strong>' + signatureAcc + '</strong> will not be integrated into <strong>'+ accession +'</strong> any more.',
                        'Unintegrate',
                        () => {
                            fetch('/api/entry/' + accession + '/signature/' + signatureAcc + '/', {method: 'DELETE'})
                                .then(response => response.json())
                                .then(result => {
                                    const msg = document.querySelector('#signatures .ui.message');
                                    if (result.unchecked) {
                                        msg.querySelector('.header').innerHTML = 'Entry unchecked';
                                        msg.querySelector('p').innerHTML = '<em>'+ accession +'</em> has been unchecked because it does not have any signatures.';
                                        msg.className = 'ui info message';

                                        getSignatures(accession).then(() => { $('.ui.sticky').sticky(); });
                                    } else if (result.status) {
                                        ui.setClass(msg, 'hidden', true);
                                        getSignatures(accession).then(() => { $('.ui.sticky').sticky(); });
                                    } else {
                                        msg.querySelector('.header').innerHTML = result.title;
                                        msg.querySelector('p').innerHTML = result.message;
                                        msg.className = 'ui error message';
                                    }
                                });
                        }
                    );
                });
            });
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

            ui.openConfirmModal(
                'Delete GO term?',
                '<strong>' + termID + '</strong> will not be associated to <strong>'+ accession +'</strong> any more.',
                'Delete',
                () => {
                    fetch('/api/entry/' + accession + '/go/' + termID + '/', {method: 'DELETE'})
                        .then(response => response.json())
                        .then(result => {
                            if (result.status)
                                getGOTerms(accession).then(() => { $('.ui.sticky').sticky(); });
                            else
                                ui.openErrorModal(result);
                        });
                }
            );
        });
    });
}

const entryEditor = {
    accession: null,
    name: null,
    description: null,
    type: null,
    isChecked: false,
    init: function () {
        const fields = {
            type: 'empty'
        };
        Array.from(document.querySelectorAll('#edit-entry [data-countdown]')).forEach(input => {
            const maxLength = input.getAttribute('maxlength');
            fields[input.name] = ['maxLength['+ maxLength +']', 'empty'];
            ui.updateCountdown(input);
        });
        const self = this;
        const segment = document.getElementById('edit-entry');
        $(segment.querySelector('.ui.dropdown')).dropdown();
        $(segment.querySelector('.ui.form')).form({
            fields: fields,
            onSuccess: function (event, fields) {
                self.save(fields)
                    .then(success => {
                        if (success) {
                            self.close();
                            getEntry(self.accession);
                        }
                    });
            }
        });

        segment.querySelector('.cancel.button').addEventListener('click', e => {
            self.close();
        });

        segment.querySelector('.negative.button').addEventListener('click', e => {
            self.delete(self.accession);
        });
    },
    update: function (accession, name, description, type, isChecked) {
        this.accession = accession;
        this.name = name;
        this.description = description;
        this.type = type;
        this.isChecked = isChecked;
    },
    open: function () {
        const segment = document.getElementById('edit-entry');
        let input;

        input = segment.querySelector('input[name="name"]');
        input.value = this.name;
        ui.updateCountdown(input);

        input = segment.querySelector('input[name="description"]');
        input.value = this.description;
        ui.updateCountdown(input);

        $(segment.querySelector('.ui.dropdown')).dropdown('set selected', this.type);

        segment.querySelector('input[type="checkbox"]').checked = this.isChecked;

        ui.setClass(document.querySelector('#edit-entry .ui.error.message'), 'hidden', true);

        ui.setClass(segment, 'hidden', false);
        $('.ui.sticky').sticky();
    },
    save: function (fields) {
        const options = {
            method: 'POST',
            headers: {
                'Content-type': 'application/x-www-form-urlencoded; charset=UTF-8'
            },
            body: 'name=' + encodeURIComponent(fields.name.trim())
            + '&description=' + encodeURIComponent(fields.description.trim())
            + '&type=' + encodeURIComponent(fields.type)
            + '&checked=' + (fields.checked ? 1 : 0)
        };
        return fetch('/api/entry/' + this.accession + '/', options)
            .then(response => response.json())
            .then(result => {
                if (!result.status) {
                    const msg = document.querySelector('#edit-entry .ui.error.message');
                    msg.innerHTML = '<div class="header">'+ result.title +'</div>'
                        + '<p>'+ result.message +'</p>';
                    ui.setClass(msg, 'hidden', false);
                }

                return result.status;
            });

    },
    close: function () {
        ui.setClass(document.getElementById('edit-entry'), 'hidden', true);
    },
    delete: function (accession) {
        ui.openConfirmModal(
            'Delete entry?',
            'Are you sure you want to delete <strong>' + accession + '</strong>?',
            'Delete',
            () => {
                fetch('/api/entry/' + accession + '/', {method: 'DELETE'})
                    .then(response => response.json())
                    .then(result => {
                        if (result.status) {
                            // Redirect to home page
                            const form = document.createElement("form");
                            form.name = "gotohome";
                            form.action = "/";
                            document.body.appendChild(form);
                            document.gotohome.submit();
                        }
                        else {
                            const msg = document.querySelector('#edit-entry .ui.error.message');
                            msg.innerHTML = '<div class="header">'+ result.title +'</div>'
                                + '<p>'+ result.message +'</p>';
                            ui.setClass(msg, 'hidden', false);
                        }
                    });
            }
        );
    }
};


function escapeXmlTags(text) {
    return text
        .replace(/<cite\s+id="(PUB\d+)"\s*\/>/g, '&lt;cite id="$1"/&gt;')
        .replace(/<dbxref\s+db\s*=\s*"(\w+)"\s+id\s*=\s*"([\w.\-]+)"\s*\/>/g, '&ltdbxref db="$1" id="$2"/&gt;')
        .replace(/<taxon\s+tax_id\s*=\s*"(\d+)"\s*>([^<]+)<\/taxon>/g, '&lttaxon tax_id="$1"&gt;$2&lt;/taxon&gt;');
}

function getEntry(accession) {
    fetch('/api/entry/' + accession + '/')
        .then(response => {
            if (response.status === 200)
                return response.json();
            else {
                document.querySelector('.ui.container.segment').innerHTML = '<div class="ui error message">'
                    + '<div class="header">Entry not found</div>'
                    + '<strong>'+ accession +'</strong> is not a valid InterPro accession.'
                    + '</div>';
                ui.dimmer(false);
                return null;
            }
        })
        .then(entry => {
            if (entry === null) return;
            document.title = entry.name + ' (' + entry.accession + ') | Pronto';

            entryEditor.update(accession, entry.short_name, entry.name, entry.type.code, entry.is_checked);

            // Header
            let html = '';
            if (entry.is_checked)
                html += '<i class="checkmark icon"></i>';

            html += entry.name
                + '<div class="sub header">' + entry.short_name + ' (' + entry.accession + ')' + '</div>';
            document.querySelector('h1.header').innerHTML = html;

            // Statistics
            ui.setClass(document.getElementById('segment-statistics'), 'type-' + entry.type.code, true);
            document.querySelector('[data-statistic="type"]').innerHTML = entry.type.name;

            // Links to public website
            Array.from(document.querySelectorAll('a[data-public-href]')).forEach(elem => {
                const base = elem.getAttribute('data-public-href');
                elem.href = base + '/' + accession;
            });

            // History
            document.querySelector('.ui.feed').innerHTML = '<div class="event">'
                + '<div class="content">'
                + '<div class="date">'+ entry.last_modification.date +'</div>'
                + '<a class="user">'+ entry.last_modification.user +'</a> edited the entry'
                + '</div>'
                + '</div>'
                + '<div class="event">'
                + '<div class="content">'
                + '<div class="date">'+ entry.creation.date +'</div>'
                + '<a class="user">'+ entry.creation.user +'</a> created the entry'
                + '</div>'
                + '</div>';

            const promises = [
                getSignatures(accession),
                getGOTerms(accession),
                getRelationships(accession),
                getAnnotations(accession, false),
                getSupplReferences(accession)
            ];

            Promise.all(promises).then(value => {
                $('.ui.sticky').sticky();
                ui.dimmer(false);
            });
        });
}

$(function () {
    finaliseHeader();
    const accession = location.pathname.match(/^\/entry\/(.+)\/$/)[1];

    ui.dimmer(true);

    // Initialise coupled modals (one opened on top of the other)
    $('.coupled.modal')
        .modal({
            allowMultiple: true
        });

    ui.listenMenu(document.querySelector('.ui.vertical.menu'));

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
                    ui.openErrorModal(result);
            });
    });

    // Get comments
    getEntryComments(accession, 2, document.querySelector('.ui.comments'));

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
                        ui.setClass(msg, 'hidden', true);
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
                                    ui.setClass(msg, 'hidden', true);

                                    // Annotation created: clear textarea
                                    modal.querySelector('textarea').value = null;

                                    // Return a promise to link the created annotation to the entry
                                    return linkAnnotation(accession, result.id);
                                } else {
                                    msg.querySelector('.header').innerHTML = result.title;
                                    msg.querySelector('p').innerHTML = result.message.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                                    ui.setClass(msg, 'hidden', false);
                                }
                            })
                            .then(result => {
                                if (result.status) {
                                    getAnnotations(accession).then(() => { $('.ui.sticky').sticky(); });
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
                                        getAnnotations(accession, false).then(() => { $('.ui.sticky').sticky(); });
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

                ui.dimmer(true);
                fetch('/api/annotation/search/?q=' + query)
                    .then(response => response.json())
                    .then(result => {
                        let html = '';

                        if (result.hits.length) {
                            // Create a regular expression to match the search query (case insensitive, and escaping special characters)
                            const re = new RegExp(result.query.replace(/([.?*+^$[\]\\(){}|-])/g, '\\$1'), 'gi');

                            result.hits.forEach(ann => {
                                // Highlight search query in text
                                const text = escapeXmlTags(ann.text).replace(re, '<span class="hl-search">$&</span>');

                                if (annotations.has(ann.id))
                                    html += '<div data-annid="'+ ann.id +'" class="ui top attached secondary segment">' + text + '</div>';
                                else
                                    html += '<div data-annid="'+ ann.id +'" class="ui top attached segment">' + text + '</div>';

                                html += '<div data-annid="'+ ann.id +'" class="ui bottom borderless attached mini menu">';

                                if (ann.num_entries)
                                    html += '<a class="item"><i class="list icon"></i> Associated to '+ ann.num_entries + ' entries</a>';

                                if (!annotations.has(ann.id))
                                    html +=  '<div class="right item"><button class="ui primary button">Add</button></div>';

                                html += '</div>';
                            });
                        } else {
                            html = '<p>No annotations found for <strong>'+ query +'</strong>.</p>';
                        }

                        const modal = document.getElementById('modal-annotations');
                        modal.querySelector('.header').innerHTML = 'Results found:&nbsp;'+ result.hits.length.toLocaleString();
                        modal.querySelector('.content').innerHTML = html;

                        Array.from(modal.querySelectorAll('.content .ui.bottom.menu > a')).forEach(elem => {
                            elem.addEventListener('click', e => {
                                const annID = e.target.closest('[data-annid]').getAttribute('data-annid');
                                fetch('/api/annotation/' + annID + '/entries/')
                                    .then(response => response.json())
                                    .then(entries => {
                                        let html = '<table class="ui very basic table"><tbody>';
                                        entries.forEach(e => {
                                            html += '<tr>' +
                                                '<td class="collapsing">' +
                                                '<span class="ui label circular type-'+ e.type +'">'+ e.type +'</span>' +
                                                '</td>'
                                                + '<td><a href="/entry/'+ e.accession +'/">'+ e.accession +'</a></td>'
                                                + '<td>'+ e.name +'</td></tr>';

                                        });

                                        const modal = document.getElementById('modal-entries');
                                        modal.querySelector('.content').innerHTML = html;
                                        $(modal).modal('show');
                                    });
                            });
                        });

                        Array.from(modal.querySelectorAll('.content button')).forEach(elem => {
                            elem.addEventListener('click', e => {
                                const menu = e.target.closest('[data-annid]');
                                const annID = menu.getAttribute('data-annid');
                                linkAnnotation(accession, annID)
                                    .then(result => {
                                        if (result.status) {
                                            getAnnotations(accession).then(() => {
                                                // Remove menu to prevent user to add the abstract a second time
                                                menu.parentNode.removeChild(menu);

                                                $('.ui.sticky').sticky();
                                            });

                                            // Update segment's style
                                            const segment = modal.querySelector('.ui.segment[data-annid="'+ annID +'"]');
                                            segment.className = 'ui secondary segment';
                                        } else {
                                            // todo: show error
                                        }
                                    });
                            });
                        });
                        ui.dimmer(false);
                        $(modal).modal('show');
                    });
            }
        });
    })();

    /*
        Event to integrate signatures
        Using Semantic-UI form validation
     */
    $('#signatures .ui.form').form({
        on: 'submit',
        fields: { accession: 'empty' },
        onSuccess: function (event, fields) {
            const signatureAcc = fields.accession.trim();
            if (signatureAcc.length)
                integrateSignature(accession, signatureAcc, false);
        }
    });

    // Event to add relationships
    (function () {
        const select = document.querySelector('#relationships .ui.dropdown');
        select.innerHTML = '<option value="">Relationship type</option>'
            + '<option value="parent">Parent of '+ accession +'</option>'
            + '<option value="child">Child of '+ accession +'</option>';
        $(select).dropdown();

        // Using Semantic-UI form validation
        $('#relationships .ui.form').form({
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
                        const msg = document.querySelector('#relationships .ui.error.message');
                        if (result.status) {
                            $(this).form('clear');
                            ui.setClass(msg, 'hidden', true);
                            getRelationships(accession).then(() => { $('.ui.sticky').sticky(); });
                        } else {
                            msg.querySelector('.header').innerHTML = result.title;
                            msg.querySelector('p').innerHTML = result.message;
                            ui.setClass(msg, 'hidden', false);
                        }
                    });
            }
        });
    })();

    /*
        Event to add GO annotations
        Using Semantic-UI form validation
     */
    $('#go-terms .ui.form').form({
        on: 'submit',
        fields: { term: 'empty' },
        onSuccess: function (event, fields) {
            const termID = fields.term.trim();
            if (!termID.length)
                return;

            const msg = document.querySelector('#go-terms .ui.error.message');
            addGoTerm(accession, termID)
                .then(() => {
                    $(this).form('clear');
                })
                .then(
                    () => {
                        ui.setClass(msg, 'hidden', true);
                    },
                    error => {
                        msg.querySelector('.header').innerHTML = error.title;
                        msg.querySelector('p').innerHTML = error.message;
                        ui.setClass(msg, 'hidden', false);
                    });
        }
    });

    /*
        Event to add supp. references
        Using Semantic-UI form validation
     */
    $('#supp-references .ui.form').form({
        on: 'submit',
        fields: { pmid: 'integer' },
        onSuccess: function (event, fields) {
            return fetch('/api/entry/' + accession + '/reference/' + fields.pmid.trim() + '/', { method: 'PUT' })
                .then(response => response.json())
                .then(result => {
                    if (result.status) {
                        $(this).form('clear');
                        getSupplReferences(accession).then(() => { $('.ui.sticky').sticky(); });
                    }
                    else
                        ui.openErrorModal(result);
                });
        }
    });

    /*
        Event to enable/disable editing mode
     */
    $('#annotations .ui.toggle.checkbox')
        .checkbox('uncheck')  // Force checkbox to be unchecked
        .checkbox({
            onChange: function () {
                const checked = this.checked;
                getAnnotations(accession, checked).then(() => {
                    ui.setClass(document.querySelector('#annotations div.header'), 'hidden', !checked);
                    $('.ui.sticky').sticky();
                });
            }
        });

    entryEditor.init();

    // Open the hidden segment to edit the entry
    document.querySelector('#segment-statistics .ui.corner.label').addEventListener('click', e => {
        entryEditor.open();
    });

    getEntry(accession);
});