import {setCharsCountdown, toggleErrorMessage} from "./utils.js";


export async function fetchTasks() {
    const response = await fetch(`/api/tasks/`);
    return response.json();
}

export async function renderTaskList() {
    const tasks = await fetchTasks();
    const menu = document.querySelector('#tasks .menu');
    if (tasks.length > 0) {
        let html = '';
        for (const task of tasks) {
            if (task.end_time === null)
                html += `<div class="item"><i class="sync loading icon"></i>${task.id}</div>`;
            else if (task.success)
                html += `<div class="item"><i class="check circle green icon"></i>${task.id}</div>`;
            else
                html += `<div class="item"><i class="exclamation circle red icon"></i>${task.id}</div>`;
        }
        menu.innerHTML = html;
    } else
        menu.innerHTML = '<div class="item">No tasks</div>';

    return Promise.resolve(tasks);
}

export function updateHeader(signatureAcc) {
    document.querySelector('header form').addEventListener('submit', e => {
        if (!e.currentTarget.querySelector('input').value.trim().length)
            e.preventDefault();
    });

    return new Promise(((resolve,) => {
        fetch('/api/')
            .then(response => response.json())
            .then(object => {
                document.getElementById("pronto-info").innerHTML = `<div class="item">UniProt ${object.uniprot}</div>`;

                const menu = document.querySelector("header .right.menu");
                let item;
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

                const modal = document.getElementById('new-entry-modal');
                $(modal.querySelector('.ui.dropdown')).dropdown();

                // Countdown events
                const fields = {type: 'empty'};
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
                $(signaturesForm).form({
                    fields: { accession: 'empty' },
                    onSuccess: function (event, fields) {
                        const acc = fields.accession.trim();
                        fetch(`/api/signature/${acc}/`)
                            .then(response => {
                                if (!response.ok)
                                    throw Error(response.status.toString());
                                return response.json();
                            })
                            .then(signature => {
                                // Clear form (signature linked)
                                $(this).form('clear');

                                // Use signature's info
                                const values = $(infoForm).form('get values');
                                if (values.name.length === 0)
                                    $(infoForm).form('set value', 'name', signature.description);
                                if (values.short_name.length === 0)
                                    $(infoForm).form('set value', 'short_name', signature.name);
                                if (values.type.length === 0) {
                                    /*
                                        API returns signature full type (e.g. Domain, Family, etc.)
                                        but select's options have the type code as value (e.g. D, F, etc.)
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

                                const renderEntry = (entry,) => {
                                    if (entry !== null)
                                        return `<a href="/entry/${entry.accession}/">${entry.accession}</a>`;
                                    return 'N/A';
                                };

                                signatures.set(signature.accession, signature);
                                let html = '';
                                for (const s of signatures.values()) {
                                    html += `
                                        <tr>
                                        <td class="collapsing"><i class="fitted database icon" style="color: ${s.database.color};"></i></td>
                                        <td class="nowrap"><a target="_blank" href="${s.database.link}">${s.database.name}<i class="external icon"></i></a></td>
                                        <td><a href="/signature/${s.accession}">${s.accession}</a></td>
                                        <td>${s.name !== null ? s.name : ''}</td>
                                        <td>${s.description !== null ? s.description : ''}</td>
                                        <td class="right aligned">${s.proteins.total.toLocaleString()}</td>
                                        <td>${renderEntry(s.entry)}</td>
                                        <td class="collapsing"><i data-accession="${s.accession}" class="unlink fitted button icon"></i></td>
                                        </tr>
                                    `;
                                }

                                const tbody = modal.querySelector('tbody');
                                tbody.innerHTML = html

                                // Event lister to unlink signature
                                for (const elem of tbody.querySelectorAll('[data-accession]')) {
                                    elem.addEventListener('click', (e,) => {
                                        const key = e.currentTarget.dataset.accession;
                                        signatures.delete(key);

                                        if (signatures.size > 0) {
                                            const row = elem.closest('tr');
                                            row.parentNode.removeChild(row);
                                        } else
                                            tbody.innerHTML = '<tr><td class="center aligned" colspan="8">No signatures</td></tr>';
                                    });
                                }

                                toggleErrorMessage(errMsg, null);
                            })
                            .catch(() => {
                                toggleErrorMessage(errMsg, {title: 'Signature not found', message: `<strong>${acc}</strong> does not match any member database signature accession or name.`});
                            });
                    }
                });

                $(infoForm).form({
                    fields: fields,
                    onSuccess: (event, fields) => {
                        if (signatures.size === 0) {
                            toggleErrorMessage(errMsg, {title: 'No signatures', message: 'Please add at least one member database signature.'});
                            return;
                        }

                        fields.signatures = [...signatures.keys()];

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
                            if (signatureAcc !== undefined && signatureAcc !== null) {
                                $(signaturesForm)
                                    .form('set value', 'accession', signatureAcc)
                                    .form('validate form');  // to make API call
                            } else {
                                $(infoForm).form('clear');
                                signatures.clear();
                                modal.querySelector('tbody').innerHTML = '<tr><td colspan="8" class="center aligned">No signatures</td></tr>';
                            }
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

                resolve(object.user !== null);
            });
    }));

}
