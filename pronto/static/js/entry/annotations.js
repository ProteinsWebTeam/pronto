import * as references from "./references.js"
import * as dimmer from "../ui/dimmer.js";
import * as modals from "../ui/modals.js"
import {toggleErrorMessage} from "../ui/utils.js";

const REGEX_PUB = /\[cite:(PUB\d+)\]/gi;

async function getSignature(accession) {
    const response = await fetch(`/api/signature/${accession}/`);
    if (response.ok)
        return await response.json();
    return null;
}

export async function create(accession, text, isLLM) {
    const modal = document.getElementById('new-annotation');
    const msg = modal.querySelector('.message');
    const textarea = modal.querySelector('textarea');
    const checkbox = modal.querySelector('input[name="is-llm"]');

    if (text !== undefined && text !== null) {
        /*
            Ensure there are a single space after the comma between citations
            (?=\[cite:PUB\d+\]) a positive lookahead that ensures
                the next part is another citation, without capturing it
         */
        const pattern = /(\[cite:PUB\d+\])\s*,\s*(?=\[cite:PUB\d+\])/g;
        text = text.replaceAll(pattern, '$1, ');

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
                return `interpro:${interproAcc}`;
            return match;
        };

        text = text.replaceAll(/\bPfam:(PF\d+)\b/gi, replacer);
        text = text.replaceAll(/\bswiss:([a-z0-9]+)\b/gi, "[swissprot:$1]");
        textarea.value = text;
    }
    checkbox.checked = isLLM;

    $(modal)
        .modal({
            closable: true,
            onDeny: function() {
                modal.querySelector('textarea').value = null;
                msg.classList.add('hidden');
            },
            onApprove: function() {
                createNewAnnotation(accession, modal, checkbox, msg);

                // Return false to prevent modal to close
                return false;
            }
        })
        .modal('show');

    modal.addEventListener('keydown', function (e) {
        const active = document.activeElement;
        if (active.tagName === 'TEXTAREA') {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
                e.preventDefault();
                createNewAnnotation(accession, modal, checkbox, msg);
            }
        }
    });
}

function createNewAnnotation(accession, modal, checkbox, msg) {
    const options = {
        method: 'PUT',
        headers: {
            'Content-type': 'application/x-www-form-urlencoded; charset=UTF-8'
        },
        body: [
            `text=${encodeURIComponent(modal.querySelector('textarea').value)}`,
            `llm=${checkbox.checked ? 'true' : 'false'}`,
            `checked=${checkbox.checked ? 'true' : 'false'}`
        ].join('&')
    };

    fetch('/api/annotation/', options)
        .then(response => response.json())
        .then(result => {
            if (result.status) {
                msg.classList.add('hidden');

                // Return a promise to link the created annotation to the entry
                return link(accession, result.id);
            } else {
                msg.querySelector('.header').innerHTML = result.error.title;
                msg.querySelector('p').innerHTML = result.error.message.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                msg.classList.remove('hidden');
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

                    if (signature.text === null && signature.llm_text === null) {
                        html += '<div class="ui bottom attached secondary segment">No annotation.</div>';
                        continue;
                    }

                    html += '<div class="ui attached segment">';

                    let text;
                    let isLLM;
                    if (signature.text !== null) {
                        text = signature.text;
                        html += `
                            <div class="ui warning message">
                                <div class="header">Automatic Replacements</div>
                                You can find some differences from original Pfam annotation due automatic corrections.
                            </div>
                        `;
                        isLLM = false;
                    } else {
                        text = signature.llm_text;
                        isLLM = true;
                        html += `
                            <div class="ui warning message">
                                <div class="header">AI-generated annotation</div>
                                This annotation has been automatically generated using an AI language model.
                            </div>                        
                        `;
                    }

                    html += `
                        ${escape(text)}
                        </div>
                        <div class="ui bottom attached borderless mini menu">
                            <span class="item message"></span>
                            <div class="right item">
                            <button data-id="${signature.accession}" class="ui primary button">Use</button>
                            </div>
                        </div>
                    `;

                    signatureAnnotations.set(
                        signature.accession,
                        {text: text, llm: isLLM}
                    );
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
                    const {text, llm} = signatureAnnotations.get(key);
                    create(accession, text, llm);
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
            const mainRefs = [];
            const annotations = [];
            const references = new Map(Object.entries(results.references));
            const rights = new Map();
            let html = '';

            for (let i = 0; i < results.annotations.length; i++) {
                const annotationApi = results.annotations[i];
                const annotationClient = new Annotation(
                    annotationApi.id,
                    annotationApi.text,
                    annotationApi.is_llm,
                    annotationApi.is_checked,
                    annotationApi.comment,
                    annotationApi.num_entries,
                    annotationApi.cross_references,
                    results.annotations.length > 1,
                    results.annotations.length > 1  // && annotation.num_entries === 1
                );
                annotations.push(annotationClient);

                html += annotationClient.createEditor(
                    i === 0,
                    i + 1 === results.annotations.length,
                    references,
                    mainRefs,
                    previewMode
                );
            }

            let elem = document.querySelector('#annotations > .content');
            if (annotations.length > 0)
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
                elem.innerHTML = annotations.length.toLocaleString();
            }

            for (const elem of document.querySelectorAll('[data-statistic="references"]')) {
                elem.innerHTML = mainRefs.length.toLocaleString();
            }

            // Highlight selected references
            for (const elem of document.querySelectorAll('.annotation')) {
                addHighlightEvenListeners(elem);
            }

            annotations.forEach((annotation) => {
                annotation.listenActionEvent(accession, references);
            });

            // Init actions tooltips/popups
            $('.popup.item').popup({
                position  : 'top center',
                variation: 'very wide inverted',
                delay: {
                    show: 50,
                    hide: 70
                },
            });

            $('.ui.dropdown').dropdown();
        })
        .catch((error) => {
            console.error(error);
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
                    annotations.set(
                        ann.id,
                        {text: ann.text, entries: ann.num_entries, llm: ann.is_llm}
                    );

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
                    else if (action === 'copy') {
                        const {text, llm} = annotations.get(annID);
                        create(accession, text, llm);
                    }
                    else if (action === 'link') {
                        actionButton.classList.add('disabled');
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
                                    elem.classList.add('disabled');
                                    refresh(accession).then(() => {$('.ui.sticky').sticky();});
                                } else {
                                    actionButton.classList.remove('disabled');
                                    toggleErrorMessage(modal.querySelector('.ui.message'), result.error);
                                }

                            });
                    } else if (action === 'delete') {
                        remove(annID, annotations.get(annID).entries).then((status,) => {
                            if (status)
                                search(accession, query);
                            else
                                actionButton.classList.remove('disabled');
                        });
                    }
                });
            }

            dimmer.off();
            toggleErrorMessage(modal.querySelector('.ui.message'), null);
            $(modal).modal('show');
        });
}

class Annotation {
    constructor(id, text, isLLM, isReviewed, comment, numEntries, xrefs, canUnlink, canDelete) {
        this.id = id;
        this.rawText = text;
        this.formattedText = null;
        this.isLLM = isLLM;
        this.isReviewed = isReviewed;
        this.comment = comment;
        this.numEntries = numEntries;
        this.xrefs = xrefs;
        this.canUnlink = canUnlink;
        this.canDelete = canDelete;
        this.editorIsOpen = false;
    }

    get element() {
        return document.getElementById(this.id);
    }

    createEditor(isFirst, isLast, references, mainRefs, previewMode) {
        let text = this.rawText.replaceAll(
            REGEX_PUB,
            (match, pubID) => {
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
            }
        );

        // Replace cross-ref tags by links
        for (const xref of this.xrefs) {
            const pattern = xref.match
                .replace('[', '\\[')
                .replace(']', '\\]');
            const regex = new RegExp(pattern, 'g');
            text = text.replace(
                regex,
                `<a target="_blank" href="${xref.url}">${xref.id}<i class="external icon"></i></a>`
            );
        }

        this.formattedText = text;
        if (previewMode)
            return `<div class="ui vertical segment annotation">${text}</div>`;

        let llmItem = '';
        if (this.isLLM) {
            let subItems = '';
            if (!this.isReviewed) {
                subItems += `
                    <a data-action="mark-as-reviewed" class="item">
                        <i class="check icon"></i> Mark as reviewed
                    </a>
                `;
            }

            subItems += `
                <a data-action="mark-as-curated" class="item">
                    <i class="user icon"></i> Mark as curated
                </a>
            `;

            llmItem = `
                <div class="ui floating dropdown item">
                    <i class="magic icon"></i>
                    AI/${this.isReviewed ? 'Reviewed' : 'Unreviewed'}
                    <i class="dropdown icon"></i>
                    <div class="menu">
                        ${subItems}
                    </div>
                </div>
            `;
        } else {
            llmItem = '<span class="item"><i class="user icon"></i> Curated</span>';
        }

        return `
            <div id="${this.id}" class="annotation">
                <div class="ui top attached mini menu">
                    <span class="selectable popup item" data-content="${this.comment || 'N/A'}">
                        ${this.id}
                    </span>
                    <a data-action="edit" class="item">
                        <i class="edit icon"></i> Edit
                    </a>
                    <a data-action="moveup" class="${isFirst ? 'disabled' : ''} item">
                        <i class="arrow up icon"></i> Move up
                    </a>
                    <a data-action="movedown" class="${isLast ? 'disabled' : ''} item">
                        <i class="arrow down icon"></i> Move down
                    </a>
                    <a data-action="unlink" class="item">
                        <i class="unlink icon"></i> Unlink
                    </a>
                    <a data-action="delete" class="item">
                        <i class="trash icon"></i> Delete
                    </a>
                    ${llmItem}
                    <div class="right menu">
                        <a data-action="list-entries" class="item"><i class="list icon"></i>
                        Associated to ${this.numEntries} ${this.numEntries === 1 ? 'entry' : 'entries'}</a>
                    </div>
                </div>
                <div class="ui attached segment">${text}</div>
                <div class="hidden ui borderless bottom attached mini menu" data-id="${this.id}">
                    <div class="right menu">
                        <div class="item"><a data-action="cancel" class="ui basic secondary button">Cancel</a></div>
                        <div class="item"><a data-action="save" class="ui primary button">Save</a></div>
                    </div>
                </div>
            </div>        
        `;
    }

    listenActionEvent(entryAccession, references) {
        const elements = this.element.querySelectorAll('a[data-action]:not(.disabled)');
        for (const element of elements) {
            element.addEventListener('click', (e) => {
                const action = e.currentTarget.dataset.action;
                if (action === 'edit') {
                    this.openEditor(references);
                } else if (action === 'moveup') {
                    this.reorder(entryAccession, 'up');
                } else if (action === 'movedown') {
                    this.reorder(entryAccession, 'down');
                } else if (action === 'unlink') {
                    if (this.canUnlink) {
                        unlink(entryAccession, this.id);
                    } else {
                        modals.error(
                            `Cannot unlink ${this.id}`,
                            `${this.id} is the only annotation associated to ${entryAccession}. 
                            Please make sure that ${entryAccession} has at least one other annotation.`
                        );
                    }
                } else if (action === 'delete') {
                    if (this.canDelete) {
                        remove(this.id, this.numEntries)
                            .then((status,) => {
                                    if (status) {
                                        refresh(entryAccession)
                                            .then(() => {
                                                $('.ui.sticky').sticky();
                                            });
                                    }
                                }
                            );
                    } else {
                        modals.error(
                            `Cannot unlink ${this.id}`,
                            `${this.id} is the only annotation associated to ${entryAccession}. 
                            Please make sure that ${entryAccession} has at least one other annotation.`
                        );
                    }
                } else if (['mark-as-reviewed', 'mark-as-curated', 'save'].includes(action)) {
                    let header;
                    let reason;
                    switch (action) {
                        case 'mark-as-reviewed': {
                            header = 'Mark as reviewed';
                            reason = 'Reviewed';
                            break;
                        }
                        case 'mark-as-curated': {
                            header = 'Mark as curated';
                            reason = 'Curated';
                            break;
                        }
                        case 'save': {
                            header = 'Save changes';
                            reason = null;
                            break
                        }
                    }

                    if (this.numEntries > 1) {
                        modals.ask(
                            header,
                            `This annotation is used by <strong>${this.numEntries} entries</strong>. Changes will be visible in all entries.`,
                            'Save',
                            () => {
                                this.saveChanges(entryAccession, reason);
                            }
                        );
                    } else {
                        this.saveChanges(entryAccession, reason);
                    }
                } else if (action === 'list-entries') {
                    getAnnotationEntries(this.id);
                } else if (action === 'cancel') {
                    this.closeEditor();
                }
            });
        }

        const self = this;
        this.element.addEventListener('keydown', function (e) {
            const active = document.activeElement;
            if (active.tagName === 'TEXTAREA') {
                if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
                    e.preventDefault();
                    self.saveChanges(entryAccession, null);
                }
            }
        });
    }

    openEditor(references) {
        if (this.editorIsOpen)
            return;

        const text = this.rawText.replaceAll(
            REGEX_PUB,
            (match, pubID) => {
                if (references.has(pubID)) {
                    const pub = references.get(pubID);
                    return `[cite:${pub.pmid}]`
                }

                return match;
            }
        );

        const menu = this.element.querySelector('.ui.bottom.menu');

        // Display bottom menu
        menu.classList.remove('hidden');

        // Open editor
        const segment = this.element.querySelector('.segment');
        segment.innerHTML = `
            <div class="ui form">
                <div class="field">
                    <label>Reason for update</label>
                    <select>
                    <option value="Annotation updated" selected>Annotation</option>
                    <option value="Cross-references updated">Cross-references</option>
                    <option value="References updated">Literature references</option>
                    <option value="Spelling updated">Typos, grammar errors, spelling mistakes</option>
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
        this.rawText = textarea.value;  // TODO: Do we need this? Try with weird characters to see if the textarea reformat them.
        this.editorIsOpen = true;
    }

    closeEditor() {
        if (!this.editorIsOpen) return;

        // Hide bottom menu
        this.element.querySelector('.ui.bottom.menu').classList.add('hidden');

        // Restore formatted annotation
        const segment = this.element.querySelector('.segment');
        segment.innerHTML = this.formattedText;

        // recreate highlight even listeners for THIS annotation only
        addHighlightEvenListeners(segment);
        this.editorIsOpen = false;
    }

    reorder(entryAccession, direction) {
        const editors= document.querySelectorAll('.annotation > .ui.segment > .ui.form');
        if (editors.length !== 0) {
            modals.error(
                'Cannot reorder while editing',
                'Please save or cancel all edits before reordering annotations to prevent losing unsaved changes.'
            );
            return;
        }
        const url = `/api/entry/${entryAccession}/annotation/${this.id}/order/${direction}/`;
        fetch(url, { method: 'POST' })
            .then(response => response.json())
            .then(object => {
                if (object.status)
                    refresh(entryAccession).then(() => { $('.ui.sticky').sticky(); });
                else
                    modals.error(object.error.title, object.error.message);
            });
    }

    saveChanges(entryAccession, reason) {
        let text;
        if (this.editorIsOpen) {
            text = this.element.querySelector('textarea').value;

            if (!reason) {
                const select = this.element.querySelector('select');
                reason = select.options[select.selectedIndex].value;

                if (reason.length)
                    select.parentNode.classList.remove('error');
                else {
                    select.parentNode.classList.add('error');
                }
            }
        } else if (reason) {
            text = this.rawText;
        } else {
            return;
        }

        let isLLM = this.isLLM;
        let isReviewed = isLLM;

        if (reason === 'Reviewed') {
            // Nothing changes (`isReviewed` already implied to be true)
        } else if (reason === 'Curated') {
            isLLM = false;
            isReviewed = false;
        }

        const options = {
            method: 'POST',
            headers: {
                'Content-type': 'application/x-www-form-urlencoded; charset=UTF-8'
            },
            body: [
                `text=${encodeURIComponent(text)}`,
                `reason=${reason}`,
                `llm=${isLLM ? 'true' : 'false'}`,
                `checked=${isReviewed ? 'true' : 'false'}`,
            ].join('&')
        };

        fetch(`/api/annotation/${this.id}/`, options)
            .then(response => response.json())
            .then((result) => {
                if (result.status) {
                    refresh(entryAccession)
                        .then(() => {
                            $('.ui.sticky').sticky();
                        });
                } else {
                    const title = result.error.title;
                    // Escape lesser/greater signs because if the error message contains "<p>" it will be interpreted
                    const message = result.error.message.replace(/</g, '&lt;').replace(/>/g, '&gt;');

                    if (this.editorIsOpen) {
                        const form = this.element.querySelector('.ui.form');
                        form.querySelector('.ui.message').innerHTML = `
                            <div class="header">${title}</div>
                            <p>${message}</p>
                        `;
                        form.classList.add('error');
                    } else {
                        modals.error(title, message);
                    }
                }
            });
    }
}

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
                active.classList.remove('active');

            const id = e.currentTarget.getAttribute('href').substring(1);
            document.getElementById(id).classList.add('active');
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

function remove(annID, numEntries) {
    let content = 'Do you want to to delete this annotation? This action cannot be undone.';

    if (numEntries > 1)
        content += `
            <br>
            <strong>
                Please note that this annotation is associated to multiple entries.
            </strong>
        `;

    return new Promise(resolve => {
        modals.ask(
            'Delete annotation?',
            content,
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
