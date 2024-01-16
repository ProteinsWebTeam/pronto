import * as comments from '../ui/comments.js'
import * as dimmer from "../ui/dimmer.js"
import {updateHeader} from "../ui/header.js"
import * as menu from "../ui/menu.js"
import * as modals from "../ui/modals.js";
import {setCharsCountdown, toggleErrorMessage} from "../ui/utils.js";
import * as annotations from "./annotations.js";
import * as go from "./go.js";
import * as references from "./references.js";
import * as relationships from "./relationships.js";
import * as signatures from "./signatures.js";


function getEntry(accession) {
    dimmer.on();

    new Promise(((resolve, reject) => {
        fetch(`/api/entry/${accession}/`)
            .then(response => {
                if (response.ok)
                    resolve(response.json())
                else
                    reject();
            });
    }))
        .then(
            (entry,) => {
                document.title = `${entry.name} (${entry.accession}) | Pronto`;
                document.querySelector('h1.ui.header').innerHTML = `
                    ${entry.name}
                    <div class="sub header">${entry.short_name} (${entry.accession})</div>
                `;
                document.querySelector('input[name="name"]').dataset.value = entry.name;
                document.querySelector('input[name="short_name"]').dataset.value = entry.short_name;
                document.querySelector('select[name="type"]').dataset.value = entry.type.code;
                document.querySelector('input[name="checked"]').checked = entry.status.checked;

                if (entry.status.llm) {
                    const field = document.getElementById('llm-field');
                    field.classList.remove('hidden');
                    field.querySelector('input[name="llm-reviewed"]').checked = entry.status.reviewed;
                }

                const statistics = document.getElementById('statistics');
                statistics.classList.add(entry.type.code);
                statistics.querySelector('[data-statistic="type"]').innerHTML = entry.type.name;
                if (!entry.status.llm)
                    statistics.querySelector('[data-statistic="source"]').innerHTML = `<i class="user graduate icon"></i>`;
                else if (entry.status.reviewed)
                    statistics.querySelector('[data-statistic="source"]').innerHTML = `<i class="robot icon"></i>&nbsp;<i class="eye outline icon"></i>`;
                else
                    statistics.querySelector('[data-statistic="source"]').innerHTML = `<i class="robot icon"></i>&nbsp;<i class="eye slash outline icon"></i>`;

                statistics.querySelector('[data-statistic="checked"]').innerHTML = `<i class="${entry.status.checked ? 'check' : 'times'} icon"></i>`;
                document.getElementById('public-website').href = `//www.ebi.ac.uk/interpro/entry/InterPro/${entry.accession}`;
                document.querySelector('.ui.feed').innerHTML = `
                <div class="event">
                    <div class="content">
                        <div class="date">${entry.last_modification.date}</div>
                        <a class="user">${entry.last_modification.user}</a> edited this entry
                    </div>
                </div>
                <div class="event">
                    <div class="content">
                        <div class="date">${entry.creation.date}</div>
                        <a class="user">${entry.creation.user}</a> created this entry
                    </div>
                </div>
            `;

                const promises = [
                    annotations.refresh(entry.accession),
                    signatures.refresh(accession),
                    relationships.refresh(accession),
                    go.refresh(accession)
                ];

                Promise.all(promises).then(value => {
                    $('.ui.sticky').sticky();
                    dimmer.off();
                });
            },
            () => {
                document.querySelector('.ui.container > .ui.segment').innerHTML = `
                    <div class="ui error message">
                        <div class="header">Entry not found</div>
                        <strong>${accession}</strong> is not a valid InterPro accession.
                    </div>
                `;
                dimmer.off();
            }
        );
}

document.addEventListener('DOMContentLoaded', () => {
    const accession = location.pathname.match(/\/entry\/(.+)\/$/)[1];
    dimmer.on();

    // Initialise coupled modals (one opened on top of the other)
    $('.coupled.modal')
        .modal({
            allowMultiple: true
        });

    menu.listenMenu(document.querySelector('.ui.vertical.menu'));

    // Get comments
    comments.getEntryComments(accession, 2, document.querySelector('.ui.comments'));

    // Event to submit comments
    document.querySelector('.ui.comments form button').addEventListener('click', (e,) => {
        e.preventDefault();
        const form = e.currentTarget.closest('form');
        const textarea = form.querySelector('textarea');

        comments.postEntryComment(accession, textarea.value.trim())
            .then(result => {
                if (result.status)
                    comments.getEntryComments(accession, 2, document.querySelector('.ui.comments'));
                else
                    modals.error(result.error.title, result.error.message);
            });
    });

    document.getElementById('create-annotation').addEventListener('click', (e,) => {annotations.create(accession);});

    // List signatures' annotations
    document.getElementById('signatures-annotations').addEventListener('click', e => {annotations.getSignaturesAnnotations(accession);});

    // Event to show formatting help
    document.getElementById('help-format').addEventListener('click', e => {
        $('#format-help').modal('show');
    });

    // Even to search annotations
    document.getElementById('search-annotations').addEventListener('keyup' , (e,) => {
        if (e.key !== 'Enter')
            return;

        const query = e.currentTarget.value.trim();
        if (query.length >= 3)
            annotations.search(accession, query);
    });

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
                signatures.integrate(accession, signatureAcc, false);
        }
    });

    // Event to add relationships
    (function () {
        const select = document.querySelector('#relationships .ui.dropdown');
        select.innerHTML = `
                <option value="">Relationship type</option>
                <option value="parent">Parent of ${accession}</option>
                <option value="child">Child of ${accession}</option>
        `;
        $(select).dropdown();

        // Using Semantic-UI form validation
        $('#relationships .ui.form').form({
            on: 'submit',
            fields: {
                accession: 'empty',
                type: 'empty'
            },
            onSuccess: function (event, fields) {
                relationships.add(accession, fields.accession.trim(), fields.type);
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
            if (termID.length > 0)
                go.link(accession, termID);
        }
    });

    // Open edit panel
    document.querySelector('#statistics .ui.corner.label').addEventListener('click', e => {
        const segment = document.getElementById('edit-entry');
        if (segment.className.split(' ').includes('hidden')) {
            for (const elem of segment.querySelectorAll('[data-value]')) {
                const name = elem.getAttribute('name');
                const value = elem.dataset.value;

                if (name === 'name' || name === 'short_name')
                    elem.value = value;
                else if (name === 'type')
                    $(elem).dropdown('set selected', value);
                else if (name === 'checked')
                    elem.checked = value.length > 0;
            }

            for (const elem of segment.querySelectorAll('[data-countdown]')) {
                setCharsCountdown(elem);
            }

            segment.classList.remove('hidden');
        } else
            segment.classList.add('hidden');

        $('.ui.sticky').sticky();
    });

    // Close edit panel (cancel changes)
    document.querySelector('#edit-entry .cancel.button').addEventListener('click', e => {
        document.getElementById('edit-entry').classList.add('hidden');
    });

    // Init saving changes in edit panel
    (function () {
        const segment = document.getElementById('edit-entry');
        const fields = {
            type: 'empty'
        };
        for (const elem of segment.querySelectorAll('[data-countdown]')) {
            const n = elem.getAttribute('maxlength');
            fields[elem.name] = [`maxLength[${n}]`, 'empty'];
            elem.addEventListener('input', e => {
                setCharsCountdown(elem);
            })
        }

        $(segment.querySelector('.ui.form')).form({
            fields: fields,
            onSuccess: function (event, fields) {
                const errMsg = segment.querySelector('.ui.message');
                const options = {
                    method: 'POST',
                    headers: {
                        'Content-type': 'application/json; charset=utf-8'
                    },
                    body: JSON.stringify(fields)
                };

                fetch(`/api/entry/${accession}/`, options)
                    .then(response => response.json())
                    .then(result => {
                        if (result.status) {
                            toggleErrorMessage(errMsg, null);
                            segment.classList.add('hidden');
                            getEntry(accession);
                        } else
                            toggleErrorMessage(errMsg, result.error);
                    });
            }
        });
    })();

    // Delete entry
    document.querySelector('#edit-entry .negative.button').addEventListener('click', e => {
        const errMsg = document.querySelector('#edit-entry .ui.message');
        toggleErrorMessage(errMsg, null);
        modals.ask(
            'Delete entry',
            `Do you want to delete <strong>${accession}</strong>?
                    <div class="ui checkbox">
                        <input id="delete-annotations" type="checkbox" name="checked">
                        <label>Delete annotations only assigned to this entry</label>
                    </div>`,
            'Delete',
            () => {
                let url = `/api/entry/${accession}/`;
                if (document.getElementById('delete-annotations').checked) {
                    url += '?delete-annotations';
                }
                fetch(url, { method: 'DELETE' })
                    .then(response => response.json())
                    .then(result => {
                        if (result.status) {
                            // Redirect to home page
                            const form = document.createElement("form");
                            form.name = "gotohome";
                            form.action = "/";
                            document.body.appendChild(form);
                            document.gotohome.submit();
                        } else
                            toggleErrorMessage(errMsg, result.error);
                    });
            }
        );

    });

    /*
        Event to enable/disable editing mode
     */
    $('.ui.toggle.checkbox')
        .checkbox('uncheck')  // Force checkbox to be unchecked
        .checkbox({
            onChange: function () {
                const checked = this.checked;
                annotations.refresh(accession).then(() => {
                    if (checked) {
                        document.getElementById('curation').classList.add('hidden');
                        document.querySelector('#annotations div.header').classList.add('hidden');
                    } else {
                        document.getElementById('curation').classList.remove('hidden');
                        document.querySelector('#annotations div.header').classList.remove('hidden');
                    }
                    $('.ui.sticky').sticky();
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
            return fetch(`/api/entry/${accession}/reference/${fields.pmid.trim()}/`, { method: 'PUT' })
                .then(response => response.json())
                .then(result => {
                    if (result.status) {
                        $(this).form('clear');
                        references.refresh(accession).then(() => { $('.ui.sticky').sticky(); });
                    }
                    else {
                        modals.error(result.error.title, result.error.message);
                        this.querySelector('.field').classList.add('error');
                    }
                });
        }
    });

    updateHeader().then(() => { getEntry(accession); });
});
