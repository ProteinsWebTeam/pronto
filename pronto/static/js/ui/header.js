import { fetchTasks } from "../tasks.js";
import { setCharsCountdown, toggleErrorMessage } from "./utils.js";

export async function renderTaskList() {
    const tasks = await fetchTasks();
    const menu = document.querySelector('#tasks .menu');
    if (tasks.length > 0) {
        let html = '';
        for (const task of tasks) {
            if (task.end_time === null)
                html += `<div class="item"><i class="sync loading icon"></i>${task.name}</div>`;
            else if (task.success) {
                const match = task.name.match(/^taxon:(\d+)$/);
                if (match !== null)
                    html += `<a href="/taxon/?id=${match[1]}" class="item"><i class="check circle green icon"></i>${task.name}</a>`;
                else
                    html += `<div class="item"><i class="check circle green icon"></i>${task.name}</div>`;
            } else
                html += `<div class="item"><i class="exclamation circle red icon"></i>${task.name}</div>`;
        }
        menu.innerHTML = html;
    } else
        menu.innerHTML = '<div class="item">No tasks</div>';

    return Promise.resolve(tasks);
}

function submitSearch(text) {
    if (!text || text.length === 0)
        return

    const url = new URL(`${location.origin}/search`);
    url.searchParams.set('q', text);
    window.location = url.toString();
}

export function updateHeader(signatureAcc) {
    return new Promise(((resolve,) => {
        fetch('/api/')
            .then(response => response.json())
            .then(object => {
                let item;
                document.getElementById("pronto-info").innerHTML = `<div class="item">UniProt ${object.uniprot}</div>`;
                if (!object.ready) {
                    item = document.getElementById("not-ready");
                    item.className = "ui red inverted one item menu";
                    item.querySelector('.item').innerHTML = `
                        <div class="header"><i class="warning sign icon"></i> Pronto is currently being updated</div>
                        <p>As a result, some pages may not function properly until the update is complete.</p>
                    `;
                }

                const menu = document.querySelector("header .right.menu");
                if (object.user) {
                    item = document.createElement("div");
                    item.className = "ui simple dropdown item";
                    item.innerHTML = `<i class="user circle icon"></i>${object.user.name}<i class="dropdown icon"></i>
                                      <div class="menu">
                                      <div class="item">
                                      <a class="icon" href="/logout/"><i cass="sign out icon"></i>&nbsp;Log out</a>
                                      </div>
                                      </div>`;
                    menu.appendChild(item);
                } else {
                    item = document.createElement("a");
                    item.className = "icon item";
                    item.href = "/login/";
                    item.innerHTML = '<i class="sign in icon"></i>&nbsp;Log in</a>';
                    menu.appendChild(item);
                }

                // Init search bar
                document.querySelector('#header-search input')
                    .addEventListener('keyup' , (e,) => {
                        if (e.key !== 'Enter')
                            return;

                        submitSearch(e.currentTarget.value.trim());
                    });
                document.querySelector('#header-search i.search.link.icon')
                    .addEventListener('click', (e,) => {
                        const input = e.currentTarget.parentNode.querySelector('input');
                        submitSearch(input.value.trim());
                    });

                const modal = document.getElementById('new-entry-modal');
                $(modal.querySelector('.ui.dropdown')).dropdown();

                // Countdown events
                const fields = { type: 'empty' };
                for (const elem of modal.querySelectorAll('[data-countdown]')) {
                    const n = elem.getAttribute('maxlength');
                    fields[elem.name] = [`maxLength[${n}]`, 'empty'];
                    elem.addEventListener('input', e => {
                        setCharsCountdown(elem);
                    })
                    setCharsCountdown(elem);
                }

                // Adding signatures
                const infoForm = document.getElementById('new-entry-info');
                const signaturesForm = document.getElementById('new-entry-signatures');
                const signatures = new Map();
                const errMsg = modal.querySelector('.ui.message');
                let entryIsReviewedLLM = false;

                $(signaturesForm).form({
                    fields: { accession: 'empty' },
                    onSuccess: function (event, fields) {
                        const acc = fields.accession.trim();
                        fetch(`/api/signature/${acc}/`)
                            .then(response => {
                                if (!response.ok)
                                    throw new Error(
                                        'Signature not found',
                                        {
                                            cause: `<strong>${acc}</strong> does not match any member database signature accession or name.`
                                        }
                                    );
                                return response.json();
                            })
                            .then(signature => {
                                if (signature.entry !== null) {
                                    throw new Error(
                                        'Signature already integrated',
                                        {
                                            cause: `<strong>${signature.accession}</strong> is already integrated in <a href="/entry/${signature.entry.accession}/">${signature.entry.accession}</a>.`
                                        }
                                    );
                                }

                                // Clear form (signature linked)
                                $(this).form('clear');

                                // Use signature's info
                                let name = signature.name;
                                let description = signature.description;
                                let useAIAnnotations = false;
                                if ((name === null || description === null) && signature.llm_name !== null && signature.llm_description !== null) {
                                    name = signature.llm_name;
                                    description = signature.llm_description;
                                    useAIAnnotations = true;
                                }
                                const values = $(infoForm).form('get values');
                                if (values.name.length === 0) {
                                    $(infoForm).form('set value', 'name', description || '');
                                    setCharsCountdown(infoForm.querySelector('input[name="name"]'));
                                }
                                if (values.short_name.length === 0) {
                                    $(infoForm).form('set value', 'short_name', name || '');
                                    setCharsCountdown(infoForm.querySelector('input[name="short_name"]'));
                                }
                                if (values.type.length === 0) {
                                    /*
                                        API returns signature full type (e.g. Domain, Family, etc.)
                                        but the select element's options have the type code as value (e.g. D, F, etc.)
                                     */
                                    let typeCode = null;
                                    for (const option of infoForm.querySelectorAll('select option')) {
                                        if (option.innerHTML === signature.type.replace('_', ' ')) {
                                            typeCode = option.value;
                                            break;
                                        }
                                    }
                                    if (typeCode !== null)
                                        $(infoForm).form('set value', 'type', typeCode);
                                }

                                signatures.set(signature.accession, signature);
                                let html = '';
                                for (const s of signatures.values()) {
                                    html += `
                                        <tr>
                                        <td class="collapsing"><i class="fitted database icon" style="color: ${s.database.color};"></i></td>
                                        <td class="nowrap"><a target="_blank" href="${s.database.link}">${s.database.name}<i class="external icon"></i></a></td>
                                        <td><a href="/signature/${s.accession}">${s.accession}</a></td>
                                        <td>${(s.name !== null && s.description !== null) ? s.name : (s.llm_name !== null ? s.llm_name : (s.name !== null ? s.name : ''))
                                    }</td>
                                        <td>${(s.name !== null && s.description !== null) ? s.description : (s.llm_description !== null ? s.llm_description : (s.description !== null ? s.description : ''))
                                    }</td>
                                        <td class="right aligned">${s.proteins.total.toLocaleString()}</td>
                                        <td class="collapsing"><i data-accession="${s.accession}" class="trash fitted button icon"></i></td>
                                        </tr>
                                    `;
                                }

                                const tbody = modal.querySelector('tbody');
                                tbody.innerHTML = html

                                // Event listener to unlink signature
                                for (const elem of tbody.querySelectorAll('[data-accession]')) {
                                    elem.addEventListener('click', (e,) => {
                                        const key = e.currentTarget.dataset.accession;
                                        signatures.delete(key);

                                        if (signatures.size > 0) {
                                            const row = elem.closest('tr');
                                            row.parentNode.removeChild(row);
                                        } else {
                                            // No signature: reset form
                                            $(infoForm).form('reset');
                                            tbody.innerHTML = '<tr><td class="center aligned" colspan="8">No signatures</td></tr>';
                                        }
                                    });
                                }

                                if ((signatures.size === 1 && useAIAnnotations) || entryIsReviewedLLM) {
                                    // Multiple signatures: use first one to decide whether the entry is AI-generated
                                    entryIsReviewedLLM = true;
                                    document.querySelector('input[name="is-llm"]').checked = true;
                                    const firstAccession = [...signatures.keys()][0];
                                    toggleErrorMessage(
                                        errMsg,
                                        {
                                            title: 'This entry will be marked as AI-generated',
                                            message: `The name, short name, and description of <strong>${firstAccession}</strong> have been generated using AI.`,
                                        }
                                    )
                                } else {
                                    toggleErrorMessage(errMsg, null);
                                }
                            })
                            .catch((error) => {
                                toggleErrorMessage(errMsg, { title: error.message, message:  error.cause});
                            });
                    }
                });

                $(infoForm).form({
                    fields: fields,
                    onSuccess: (event, fields) => {
                        if (signatures.size === 0) {
                            toggleErrorMessage(errMsg, { title: 'No signatures', message: 'Please add at least one member database signature.' });
                            return;
                        }

                        fields.signatures = [...signatures.keys()];
                        fields.is_llm = document.querySelector('input[name="is-llm"]').checked;

                        const options = {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json; charset=utf-8' },
                            body: JSON.stringify(fields)
                        }
                        fetch('/api/entry/', options)
                            .then(response => response.json())
                            .then(result => {
                                if (result.status) {
                                    const form = document.createElement("form");
                                    form.name = "gotoentry";
                                    form.action = `/entry/${result.accession}/`;
                                    document.body.appendChild(form);
                                    document.gotoentry.submit();
                                } else
                                    toggleErrorMessage(errMsg, result.error);
                            });
                    },
                });

                $(modal)
                    .modal({
                        closable: false,
                        onShow: function () {
                            toggleErrorMessage(errMsg, null);
                            if (signatureAcc !== undefined && signatureAcc !== null) {
                                $(signaturesForm)
                                    .form('set value', 'accession', signatureAcc)
                                    .form('validate form');  // to make API call
                            } else {
                                $(infoForm).form('clear');
                                signatures.clear();
                                modal.querySelector('tbody').innerHTML = '<tr><td colspan="8" class="center aligned">No signatures</td></tr>';
                            }
                            document.getElementById('new-entry-btn').blur();
                        },
                        onApprove: function ($element) {
                            $(infoForm).form('validate form');
                            return false;  // prevent to close modal
                        }
                    })
                    .modal('attach events', '#new-entry-btn', 'show');

                renderTaskList()
                    .then(() => {
                        const monitorTasks = () => {
                            setTimeout(() => {
                                renderTaskList()
                                    .then(tasks => {
                                        monitorTasks();
                                    });
                            }, 60000);
                        };

                        monitorTasks();
                    });

                document.getElementById('fluid')
                    .addEventListener('click', (e,) => {
                        const bnt = e.currentTarget;
                        const isActive = bnt.classList.contains('active');
                        bnt.classList.toggle('active');
                        bnt.blur();
                        document.querySelectorAll('.ui.container')
                            .forEach((elem,) => elem.classList.toggle('fluid'));
                        localStorage.setItem('fluid', isActive ? 'no' : 'yes');
                    });

                if (localStorage.getItem('fluid') === 'yes') {
                    document.getElementById('fluid').classList.add('active');
                    document.querySelectorAll('.ui.container')
                            .forEach((elem,) => elem.classList.toggle('fluid'));
                }

                resolve(object.user !== null);
            });
    }));
}
