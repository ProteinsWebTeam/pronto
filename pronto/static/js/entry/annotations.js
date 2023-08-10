import * as references from "./references.js"
import * as dimmer from "../ui/dimmer.js";
import * as modals from "../ui/modals.js"
import {setClass, toggleErrorMessage} from "../ui/utils.js";

async function getSignature(accession) {
    const response = await fetch(`/api/signature/${accession}/`);
    if (response.ok)
        return await response.json();
    return null;
}

export async function create(accession, text) {
    const modal = document.getElementById('new-annotation');
    const msg = modal.querySelector('.message');

    if (text !== undefined && text !== null) {
        const pfams = new Map();
        const promises = [];
        for (const [_, pfamAcc] of [...text.matchAll(/\bPfam:(PF\d+)\b/gi)]) {
            if (!pfams.has(pfamAcc)) {
                pfams.set(pfamAcc, null);
                promises.push(getSignature(pfamAcc));
            }
        }

        const results = await Promise.all(promises);
        for (const object of results) {
            if (object !== null) {
                pfams.set(object.accession, object?.entry?.accession);
            }
        }

        const replacer = (match, pfamAcc, offset, string) => {
            const interproAcc = pfams.get(pfamAcc);
            if (interproAcc !== undefined && interproAcc !== null)
                return `[interpro:${interproAcc}]`;
            return match;
        };

        text = text.replaceAll(/\bPfam:(PF\d+)\b/gi, replacer);
        text = text.replaceAll(/\bswiss:([a-z0-9]+)\d+\b/gi, "[swissprot:$1]");
        modal.querySelector('textarea').value = text;
    }

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

                            // Return a promise to link the created annotation to the entry
                            return link(accession, result.id);
                        } else {
                            msg.querySelector('.header').innerHTML = result.error.title;
                            msg.querySelector('p').innerHTML = result.error.message.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                            setClass(msg, 'hidden', false);
                            return null;
                        }
                    })
                    .then(result => {
                        if (result === null)
                            return;
                        else if (result.status) {
                            refresh(accession).then(() => { $('.ui.sticky').sticky(); });
                            $(modal).modal('hide');
                            modal.querySelector('textarea').value = null;
                        } else {
                            modals.error(result.error.title, result.error.message);
                        }
                    });

                // Return false to prevent modal to close
                return false;
            }
        })
        .modal('show');
}

export function getSignaturesAnnotations(accession) {
    fetch(`/api/entry/${accession}/signatures/annotations/`)
        .then(response => response.json())
        .then(signatures => {
            const signatureAnnotations = new Map();
            let html = '';
            if (signatures.length > 0) {
                for (const signature of signatures) {
                    html += `
                            <div class="ui top attached mini menu">
                            <a class="header item" href="/signature/${signature.accession}/">${signature.accession}</a>
                        `;

                    if (signature.name !== null)
                        html += `<span class="item">${signature.name}</span>`;

                    html += '</div>';

                    if (signature.text !== null) {
                        signatureAnnotations.set(signature.accession, signature.text);
                        html += `
                            <div class="ui attached segment">
                            ${escape(signature.text)}
                            </div>
                            <div class="ui bottom attached borderless mini menu">
                                <span class="item message"></span>
                                <div class="right item">
                                <button data-id="${signature.accession}" class="ui primary button">Use</button>
                                </div>
                            </div>
                        `;
                    } else
                        html += '<div class="ui bottom attached secondary segment">No annotation.</div>';
                }
            } else
                html += `<p><strong>${accession}</strong> has no signatures.</p>`;

            const modal = document.getElementById('list-annotations');
            modal.querySelector('.header').innerHTML = 'Signatures annotations';
            modal.querySelector('.content > .content').innerHTML = html;

            for (const btn of modal.querySelectorAll('.content button[data-id]')) {
                btn.addEventListener('click', (e,) => {
                    const key = e.currentTarget.dataset.id;
                    if (!signatureAnnotations.has(key))
                        return;

                    $(modal).modal('hide');
                    create(accession, signatureAnnotations.get(key));
                });
            }

            toggleErrorMessage(modal.querySelector('.ui.message'), null);
            $(modal).modal('show');
        });
}

export function refresh(accession) {
    references.refresh(accession);

    const previewMode = $('.ui.toggle.checkbox').checkbox('is checked');

    return fetch(`/api/entry/${accession}/annotations/`)
        .then(response => response.json())
        .then(results => {
            const rePub = /\[cite:(PUB\d+)\]/gi;
            const mainRefs = [];
            const annotations = new Map();
            const references = new Map(Object.entries(results.references));
            const rights = new Map();
            let html = '';

            for (let i = 0; i < results.annotations.length; i++) {
                const annotation = results.annotations[i];
                let text = annotation.text;

                annotations.set(annotation.id, {text: text, entries: annotation.num_entries});

                text = text.replaceAll(rePub, (match, pubID) => {
                    if (references.has(pubID)) {
                        let i = mainRefs.indexOf(pubID);
                        if (i === -1) {
                            // First occurence of the reference in any annotation
                            mainRefs.push(pubID);
                            i = mainRefs.length;
                        } else
                            i++;

                        return `<a data-ref href="#${pubID}">${i}</a>`
                    }
                    
                    return match;
                });

                // Replace cross-ref tags by links
                for (const xref of annotation.cross_references) {
                    const pattern = xref.match.replace('[', '\\[').replace(']', '\\]');
                    const regex = new RegExp(pattern, 'g');
                    text = text.replace(regex, `<a target="_blank" href="${xref.url}">${xref.id}<i class="external icon"></i></a>`);
                }

                if (previewMode)
                    html += `<div class="ui vertical segment annotation">${text}</div>`;
                else {
                    rights.set(annotation.id, {
                        unlink: results.annotations.length > 1,
                        delete: results.annotations.length > 1 && annotation.num_entries === 1
                    });

                    html += `
                        <div id="${annotation.id}" class="annotation">
                        <div class="ui top attached mini menu">
                        <a data-action="edit" class="item"><abbr title="Edit annotation"><i class="edit fitted icon"></i></abbr></a>
                        <a data-action="moveup" class="${i === 0 ? 'disabled' : ''} item"><abbr title="Move annotation up"><i class="arrow up fitted icon"></i></abbr></a>
                        <a data-action="movedown" class="${i + 1 === results.annotations.length ? 'disabled' : ''} item"><abbr title="Move annotation down"><i class="arrow down fitted icon"></i></abbr></a>
                        <a data-action="unlink" class="item"><abbr title="Unlink annotation"><i class="unlink fitted icon"></i></abbr></a>
                        <a data-action="delete" class="item"><abbr title="Delete annotation"><i class="trash fitted icon"></i></abbr></a>
                        <div class="right menu">
                            <span class="selectable item">${annotation.id}</span>
                            ${annotation.comment ? '<span class="item">'+annotation.comment+'</span>' : ''}
                            <a data-action="list" class="item"><i class="list icon"></i> Associated to ${annotation.num_entries} ${annotation.num_entries === 1 ? 'entry' : 'entries'}</a>
                        </div>
                        </div>
                        <div class="ui attached segment">${text}</div>
                        <div class="hidden ui borderless bottom attached mini menu" data-id="${annotation.id}">
                            <div class="right menu">
                                <div class="item"><a data-action="cancel" class="ui basic secondary button">Cancel</a></div>
                                <div class="item"><a data-action="save" class="ui primary button">Save</a></div>
                            </div>
                        </div>
                        </div>  
                    `;
                }
            }

            let elem = document.querySelector('#annotations > .content');
            if (annotations.size)
                elem.innerHTML = html;
            else
                elem.innerHTML = `
                    <div class="ui error message">
                        <div class="header">No annotations</div>
                        <p>This entry has no annotations. Entries without annotations cannot be checked.</p>
                    </div>
                `;

            // Render references
            elem = document.querySelector('#references .content');
            if (mainRefs.length) {
                html = '<ol>';
                for (const pubID of mainRefs) {
                    const pub = references.get(pubID);
                    let details = '';
                    if (pub.volume && pub.issue && pub.pages)
                        details = `, ${pub.volume}(${pub.issue}):${pub.pages}`;

                    html += `
                        <li id="${pubID}">
                        <div><strong>${pub.title}</strong></div>
                        <div>${pub.authors}</div>
                        <div><em>${pub.journal}</em> ${pub.year}${details}</div>
                        <div class="ui horizontal link list">
                    `;

                    if (pub.doi) {
                        html += `<span class="item"><a target="_blank" href="${pub.doi}">View article<i class="external icon"></i></a></span>`
                    }

                    if (pub.pmid) {
                        html += `<span class="item">Europe PMC: <a target="_blank" href="//europepmc.org/abstract/MED/${pub.pmid}/">${pub.pmid}<i class="external icon"></i></a></span>`;
                    }

                    html += '</div></li>'
                }
                elem.innerHTML = html + '</ol>';
            } else
                elem.innerHTML = '<p>This entry has no references</p>';

            // Update stats
            for (const elem of document.querySelectorAll('[data-statistic="annotations"]')) {
                elem.innerHTML = annotations.size.toLocaleString();
            }

            for (const elem of document.querySelectorAll('[data-statistic="references"]')) {
                elem.innerHTML = mainRefs.length;
            }

            // Highlight selected references
            for (const elem of document.querySelectorAll('.annotation')) {
                addHighlightEvenListeners(elem);
            }

            // Event listener on actions
            annotationEditor.reset();
            for (const elem of document.querySelectorAll('.annotation a[data-action]:not(.disabled)')) {
                elem.addEventListener('click', e => {
                    const annID = e.currentTarget.closest('.annotation').getAttribute('id');
                    const action = e.currentTarget.dataset.action;
                    const annotation = annotations.get(annID);
                    if (action === 'edit')
                        annotationEditor.open(annID, annotation.text, references);
                    else if (action === 'movedown')
                        annotationEditor.reorder(accession, annID, 'down');
                    else if (action === 'moveup')
                        annotationEditor.reorder(accession, annID, 'up');
                    else if (action === 'unlink') {
                        if (rights.get(annID).unlink)
                            unlink(accession, annID);
                        else {
                            modals.error(
                                `Cannot unlink ${annID}`,
                                `${annID} is the only annotation associated to ${accession}. Please make sure that ${accession} has at least one other annotation.`
                            );
                        }
                    }
                    else if (action === 'delete') {
                        if (rights.get(annID).delete) {
                            remove(annID).then((status,) => {
                                if (status)
                                    refresh(accession).then(() => {$('.ui.sticky').sticky();});
                            });
                        } else {
                            modals.error(
                                `Cannot remove ${annID}`,
                                `${annID} cannot be removed, either because it is associated to more than one entry, or because it is the only annotation associated to ${accession}. Please make sure that ${annID} is associated to ${accession} only, and that ${accession} has at least one other annotation.`
                            );
                        }
                    } else if (action === 'save') {
                        if (annotation.entries > 1) {
                            modals.ask(
                                'Save changes?',
                                'This annotation is used by <strong>' + annotation.entries + ' entries</strong>. Changes will be visible in all entries.',
                                'Save',
                                () => annotationEditor.save(accession, annID)
                            );

                        } else
                            annotationEditor.save(accession, annID);
                    } else if (action === 'cancel')
                        annotationEditor.close();
                    else if (action === 'list') {
                        getAnnotationEntries(annID);
                    }
                });
            }
        });
}

export function search(accession, query) {
    const annIDs = new Set(Array.from(document.querySelectorAll('.annotation'), (elem,) => elem.getAttribute('id')));

    dimmer.on();
    fetch('/api/annotation/search/?q=' + query)
        .then(response => response.json())
        .then(result => {
            const annotations = new Map();
            let html = '';
            if (result.hits.length > 0) {
                // Create a regular expression to match the search query (case insensitive, and escaping special characters)
                const re = new RegExp(result.query.replace(/([.?*+^$[\]\\(){}|-])/g, '\\$1'), 'gi');
                for (const ann of result.hits) {
                    // Highlight search query in text
                    const text = escape(ann.text).replace(re, '<span class="hl-search">$&</span>');
                    annotations.set(ann.id, ann.text);

                    html += `
                        <div class="ui top attached segment">${text}</div>
                        <div data-annid="${ann.id}" class="ui bottom attached mini menu">
                            <a data-action="list" data-count="${ann.num_entries}" class="item">Associated to ${ann.num_entries} ${ann.num_entries === 1 ? 'entry' : 'entries'}</a>
                            <div class="right menu">
                                <a data-action="copy" class="item"><abbr title="Copy annotation"><i class="copy fitted icon"></i></abbr></a>
                                <a data-action="link" class="${annIDs.has(ann.id) ? 'disabled': ''} item"><abbr title="Link annotation"><i class="linkify fitted icon"></i></abbr></a>
                                <a data-action="delete" class="${ann.num_entries > 0 ? 'disabled': ''} item"><abbr title="Delete annotation"><i class="trash fitted icon"></i></abbr></a>
                            </div>
                        </div>
                    `;
                }
            } else
                html = `<p>No results found for <strong>${result.query}</strong>.</p>`;

            const modal = document.getElementById('list-annotations');
            modal.querySelector('.header').innerHTML = `${result.hits.length.toLocaleString()} results`;
            modal.querySelector('.content > .content').innerHTML = html;

            for (const elem of modal.querySelectorAll('.content .ui.bottom.menu a[data-action]:not(.disabled)')) {
                elem.addEventListener('click', (e,) => {
                    const actionButton = e.currentTarget;
                    const action = actionButton.dataset.action;
                    const menu = actionButton.closest('[data-annid]');
                    const annID = menu.dataset.annid;
                    if (!annotations.has(annID))
                        return;

                    if (action === 'list')
                        getAnnotationEntries(annID);
                    else if (action === 'copy')
                        create(accession, annotations.get(annID));
                    else if (action === 'link') {
                        setClass(actionButton, 'disabled', true);
                        link(accession, annID)
                            .then((result,) => {
                                if (result.status) {
                                    // Update count
                                    let elem = menu.querySelector('[data-count]');
                                    const count = Number.parseInt(elem.dataset.count, 10) + 1;
                                    elem.dataset.count = count.toString();
                                    elem.innerHTML = `Associated to ${count} ${count === 1 ? 'entry' : 'entries'}`;
                                    // Disable 'delete' button
                                    elem = menu.querySelector('[data-action="delete"]');
                                    setClass(elem, 'disabled', true);
                                    refresh(accession).then(() => {$('.ui.sticky').sticky();});
                                } else {
                                    setClass(actionButton, 'disabled', false);
                                    toggleErrorMessage(modal.querySelector('.ui.message'), result.error);
                                }

                            });
                    } else if (action === 'delete') {
                        remove(annID).then((status,) => {
                            if (status)
                                search(accession, query);
                            else
                                setClass(actionButton, 'disabled', false);
                        });
                    }
                });
            }

            // Delete annotation
            for (const elem of modal.querySelectorAll('.content .ui.bottom.menu .red')) {
                elem.addEventListener('click', (e,) => {
                    const btn = e.currentTarget;
                    const menu = btn.closest('[data-annid]');
                    const annID = menu.dataset.annid;
                    const count = Number.parseInt(menu.querySelector('[data-count]').dataset.count, 10);
                    remove(annID, count);
                });
            }

            dimmer.off();
            toggleErrorMessage(modal.querySelector('.ui.message'), null);
            $(modal).modal('show');
        });
}

const annotationEditor = {
    element: null,
    textareaText: null,
    textFormatted: null,
    reset: function () {
        this.element = null;
        this.textareaText = null;
        this.textFormatted = null;
    },
    open: function (annID, text, references) {
        const element = document.getElementById(annID);
        const rePub = /\[cite:(PUB\d+)\]/gi;
        let segment;

        text = text.replaceAll(rePub, (match, pubID) => {
            if (references.has(pubID)) {
                const pub = references.get(pubID);
                return `[cite:${pub.pmid}]`    
            }
            
            return match;
        });

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
                modals.error(
                    'Cannot edit multiple annotations',
                    'Another annotation is being edited. Please save or discard changes before editing a second annotation.'
                );
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
        setClass(menu, 'hidden', false);

        // Save formatted annotation
        segment = this.element.querySelector('.segment');
        this.textFormatted = segment.innerHTML;

        // Display raw annotation
        segment.innerHTML = `
            <div class="ui form">
                <div class="field">
                    <label>Reason for update</label>
                    <select>
                    <option value="Annotation" selected>Annotation</option>
                    <option value="Cross-references">Cross-references</option>
                    <option value="References">Literature references</option>
                    <option value="Spelling">Typos, grammar errors, spelling mistakes</option>
                    </select>
                </div>
                <div class="field">
                    <textarea rows="15"></textarea>
                </div>
                <div class="ui error message"></div>
            </div>
        `;

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
    reorder: function(accession, annID, direction) {
        fetch(`/api/entry/${accession}/annotation/${annID}/order/${direction}/`, { method: 'POST' })
            .then(response => response.json())
            .then(object => {
                if (object.status)
                    refresh(accession).then(() => { $('.ui.sticky').sticky(); });
                else
                    modals.error(object.error.title, object.error.message);
            });
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
            body: 'text=' + encodeURIComponent(textareaText) + '&reason=' + reason
        };

        // Update annotation
        fetch(`/api/annotation/${annID}/`, options)
            .then(response => response.json())
            .then(result => {
                if (result.status)
                    refresh(accession).then(() => { $('.ui.sticky').sticky(); });
                else {
                    const form = this.element.querySelector('.ui.form');
                    // Escape lesser/greater signs because if the error message contains "<p>" it will be interpreted
                    form.querySelector('.ui.message').innerHTML = '<div class="header">'+ result.error.title +'</div><p>'+ result.error.message.replace(/</g, '&lt;').replace(/>/g, '&gt;') +'</p>';
                    setClass(textarea.parentNode, 'error', true);
                    setClass(form, 'error', true);
                }
            });
    }
};

function getAnnotationEntries(annID) {
    fetch(`/api/annotation/${annID}/entries/`)
        .then(response => response.json())
        .then(entries => {
            let html = '<table class="ui very basic table"><tbody>';
            for (const e of entries) {
                html += `
                        <tr>
                        <td class="collapsing">
                            <span class="ui label circular type ${e.type}">${e.type}</span>
                        </td>
                        <td><a href="/entry/${e.accession}/">${e.accession}</a></td>
                        <td>${e.name}</td>
                        </tr>
                    `;
            }
            if (entries.length === 0)
                html += '<tr><td>Not associated to any entry.</td></tr>';

            const modal = document.getElementById('list-entries');
            modal.querySelector('.content').innerHTML = html + '</tbody></table>';
            $(modal).modal('show');
        });
}

function addHighlightEvenListeners(div) {
    for (const elem of div.querySelectorAll('a[data-ref]')) {
        elem.addEventListener('click', e => {
            let active = document.querySelector('li.active');
            if (active)
                setClass(active, 'active', false);

            const id = e.currentTarget.getAttribute('href').substr(1);
            active = document.getElementById(id);
            setClass(active, 'active', true);
        });
    }
}

function escape(text) {
    return text
        .replace(/<cite\s+id="(PUB\d+)"\s*\/>/g, '&lt;cite id="$1"/&gt;')
        .replace(/<dbxref\s+db\s*=\s*"(\w+)"\s+id\s*=\s*"([\w.\-]+)"\s*\/>/g, '&ltdbxref db="$1" id="$2"/&gt;')
        .replace(/<taxon\s+tax_id\s*=\s*"(\d+)"\s*>([^<]+)<\/taxon>/g, '&lttaxon tax_id="$1"&gt;$2&lt;/taxon&gt;');
}

function link(accession, annID) {
    return fetch(`/api/entry/${accession}/annotation/${annID}/`, {method: 'PUT'})
        .then(response => response.json());
}

function unlink(accession, annID) {
    modals.ask(
        'Unlink annotation?',
        `This annotation will not be associated to <strong>${accession}</strong> anymore.`,
        'Unlink',
        () => {
            fetch(`/api/entry/${accession}/annotation/${annID}/`, {method: 'DELETE'})
                .then(response => response.json())
                .then(object => {
                    if (object.status)
                        refresh(accession).then(() => { $('.ui.sticky').sticky(); });
                    else
                        modals.error(object.error.title, object.error.message);
                });
        }
    );
}

function remove(annID) {
    return new Promise(resolve => {
        modals.ask(
            'Delete annotation?',
            'Do you want to to delete this annotation? This action cannot be undone.',
            'Delete',
            () => {
                fetch(`/api/annotation/${annID}/`, {method: 'DELETE'})
                    .then(response => response.json())
                    .then(result => {
                        if (result.status)
                            resolve(true);
                        else {
                            modals.error(result.error.title, result.error.message);
                            resolve(false);
                        }
                    });
            }
        );
    });

}
