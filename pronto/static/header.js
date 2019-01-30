import {setClass, updateCountdown} from "./ui.js";

function getUniProtVersion() {
    fetch("/api/uniprot/version/")
        .then(response => response.json())
        .then(response => {
            document.getElementById("uniprot-version").innerHTML = response.version;
        });
}

function getCurrentUser() {
    return fetch("/api/user/")
        .then(response => response.json())
        .then(response => {
            return new Promise(((resolve, reject) => {
                const menu = document.querySelector("header .right.menu");
                let item;
                if (response.user) {
                    item = document.createElement("div");
                    item.className = "ui simple dropdown item";
                    item.innerHTML = '<i class="user circle icon"></i> '
                        + response.user.name
                        + '<i class="dropdown icon"></i>'
                        + '<div class="menu">'
                        + '<div class="item">'
                        + '<a class="icon" href="/logout/">'
                        + '<i class="sign out icon"></i>&nbsp;Log out'
                        + '</a>'
                        + '</div>'
                        + '</div>';
                    setClass(document.getElementById('new-entry-btn'), 'disabled', false);
                    menu.appendChild(item);
                    resolve(true);
                } else {
                    item = document.createElement("a");
                    item.className = "icon item";
                    item.href = "/login/";
                    item.innerHTML = '<i class="sign in icon"></i>&nbsp;Log in</a>';
                    setClass(document.getElementById('new-entry-btn'), 'disabled', true);
                    menu.appendChild(item);
                    resolve(false);
                }
            }));
        });
}

function getTasks() {
    fetch('/api/tasks/')
        .then(response => response.json())
        .then(tasks => {
            let menu = '';
            let errors = 0;
            let success = 0;

            if (tasks.length) {
                tasks.forEach(task => {
                    menu += '<div class="item">';

                    if (task.status === null)
                        menu += '<i class="loading notched circle icon"></i>';
                    else if (task.status) {
                        menu += '<i class="green check circle icon"></i>';
                        success++;
                    }
                    else {
                        menu += '<i class="red exclamation circle icon"></i>';
                        errors++;
                    }
                    menu += task.name + '</div>';
                });
            } else
                menu += '<div class="item">No tasks</div>';

            let html = '<i class="tasks icon"></i>&nbsp;Tasks';

            if (errors)
                html += '<a class="ui red mini circular label">'+ tasks.length +'</a>';
            else if (success)
                html += '<a class="ui green mini circular label">'+ tasks.length +'</a>';
            else if (tasks.length)
                html += '<a class="ui grey mini circular label">'+ tasks.length +'</a>';

            html += '<i class="dropdown icon"></i>'
                + '<div class="menu">' + menu + '</div>';

            document.getElementById('tasks').innerHTML = html;
        })
}

function getInstance() {
    const dst = document.getElementById("instance");
    if (dst) {
        fetch("/api/instance/")
            .then(response => response.json())
            .then(response => {
                dst.innerHTML = response.instance;
            });
    }
}

function getStatus() {
    return fetch("/api/status/")
        .then(response => {
            return new Promise(((resolve, reject) => {
                const dst = document.getElementById("status");
                if (response.status === 200) {
                    if (dst) {
                        setClass(dst, 'green', true);
                        dst.querySelector('.detail').innerHTML = '<i class="fitted check icon"></i>';
                    }
                    resolve(true);
                } else {
                    if (dst) {
                        setClass(dst, 'red', true);
                        dst.querySelector('.detail').innerHTML = '<i class="fitted close icon"></i>';
                    }
                    resolve(false);
                }
            }));
        });
}

function renderSignatures(signatures) {
    let html = '';
    if (signatures.size) {
        for (let s of signatures.values()) {
            html += '<tr>'
                + '<td class="collapsing">'
                + '<i class="database icon" style="color:'+  s.color +';"></i>'
                + '</td>'
                + '<td>'
                + '<a target="_blank" href="'+ s.link +'">'+ s.database +'&nbsp;<i class="icon external"></i></a>'
                + '</td>'
                + '<td><a href="/prediction/'+ s.accession +'/">'+ s.accession +'</a></td>'
                + '<td>'+ (s.name === null ? '' : s.name) +'</td>'
                + '<td>'+ (s.description === null ? '' : s.description) +'</td>'
                + '<td class="right aligned">'+ s.num_proteins.toLocaleString() +'</td>'
                + '<td class="">'+ (s.integrated ? '<a href="/entry/'+ s.integrated +'/">'+ s.integrated +'</a>' : '') +'</td>'
                + '<td class="collapsing"><i class="remove button icon" data-remove="'+ s.accession +'"></i></td>'
                + '</tr>';
        }
    } else
        html = '<tr><td colspan="8">No signatures</td></tr>';

    document.querySelector('#new-entry-modal tbody').innerHTML = html;
}

export function finaliseHeader() {
    return getStatus()
        .then((isOK) => {
            if (isOK) {
                document.getElementById('tasks').addEventListener('click', e => getTasks());

                (function () {
                    // Init new entry modal events
                    const fields = {
                        type: 'empty'
                    };

                    Array.from(document.querySelectorAll('#new-entry-modal [data-countdown]')).forEach(input => {
                        const maxLength = input.getAttribute('maxlength');
                        fields[input.name] = ['maxLength['+ maxLength +']', 'empty'];
                        updateCountdown(input);
                    });

                    $('#new-entry-modal .ui.dropdown').dropdown();

                    const signatures = new Map();
                    const $form = $('#new-entry-modal .content > .ui.form');
                    const msg = document.querySelector('#new-entry-modal .ui.error.message');

                    $form.form({
                        fields: fields,
                        onSuccess: function (event, fields) {
                            if (!signatures.size) {
                                msg.innerHTML = '<div class="header">No signatures</div>'
                                    + '<p>Please integrate at least one member database signature.</p>';
                                setClass(msg, 'hidden', false);
                            } else {
                                fields.signatures = Array.from(signatures.keys());
                                fetch('/api/entry/', {
                                    method: 'PUT',
                                    headers: { 'Content-Type': 'application/json; charset=utf-8' },
                                    body: JSON.stringify(fields)
                                })
                                    .then(response => response.json())
                                    .then(result => {
                                        if (result.status) {
                                            const form = document.createElement("form");
                                            form.name = "gotoentry";  // ;)
                                            form.action = "/entry/" + result.accession + "/";
                                            document.body.appendChild(form);
                                            document.gotoentry.submit();
                                        } else {
                                            setClass(msg, 'hidden', false);
                                            msg.innerHTML = '<div class="header">'+ result.title +'</div>'
                                                + '<p>'+ result.message +'</p>';
                                            setClass(msg, 'hidden', false);
                                        }
                                    });
                            }
                        }
                    });

                    // Adding a signature
                    $('#new-entry-modal .content > table .ui.form').form({
                        fields: { accession: 'empty' },
                        onSuccess: function (event, fields) {
                            const acc = fields.accession.trim();
                            fetch('/api/signature/' + acc + '/')
                                .then(response => response.json())
                                .then(result => {
                                    if (result !== null) {
                                        // Set entry values from signatures' if not defined
                                        const values = $form.form('get values');
                                        if (!values.name)
                                            $form.form('set value', 'name', result.name);
                                        if (!values.description)
                                            $form.form('set value', 'description', result.description);
                                        if (!values.type)
                                            $form.form('set value', 'type', result.type);

                                        setClass(msg, 'hidden', true);
                                        signatures.set(result.accession, result);
                                        renderSignatures(signatures);

                                        Array.from(document.querySelectorAll('#new-entry-modal tbody i[data-remove]')).forEach(icon => {
                                            icon.addEventListener('click', e => {
                                                const accession = e.target.getAttribute('data-remove');
                                                signatures.delete(accession);
                                                const tr = icon.closest('tr');

                                                // Do not call renderSignatures() has the click event on icons would have to be re-bound again
                                                tr.parentNode.removeChild(tr);
                                            });
                                        });

                                        $(this).form('clear');
                                    } else {
                                        msg.innerHTML = '<div class="header">Invalid signature</div>'
                                            + '<p><strong>'+ acc +'</strong> is not a valid member database accession or name.</p>';
                                        setClass(msg, 'hidden', false);
                                    }
                                })
                        }
                    });

                    $('#new-entry-modal')
                        .modal({
                            closable: false,
                            onApprove: function ($element) {
                                $('#new-entry-modal .content > .ui.form').form('validate form');
                                return false;  // prevent to close modal
                            }
                        })
                        .modal('attach events', '#new-entry-btn', 'show');
                })();

                // Create events for *all* data-countdown elements (there are some in the /entry/ page)
                Array.from(document.querySelectorAll('[data-countdown]')).forEach(input => {
                    input.addEventListener('input', e => {
                        updateCountdown(input);
                    })
                });
            } else {
                // TODO: something?
                console.error("database schema not ready");
            }

            getUniProtVersion();
            getInstance();
            getTasks();
            return getCurrentUser();
        });
}