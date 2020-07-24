import * as checkbox from './ui/checkbox.js'
import {fetchTasks, renderTaskList, updateHeader} from "./ui/header.js"
import {setClass, escape, unescape} from "./ui/utils.js";

function getDatabases() {
    return fetch('/api/databases/')
        .then(response => response.json())
        .then(databases => {
            let html = '';
            for (const database of databases) {
                html += `
                    <tr>
                    <td style="border-left: 5px solid ${database.color};" class="collapsing">
                        <a target="_blank" href="${database.link}">${database.name}<i class="external icon"></i></a>
                    </td>
                    <td>
                        <div class="ui basic label">${database.version}<span class="detail">${database.date}</span></div>
                    </td>
                    <td>
                        <a href="/database/${database.id}/">${database.signatures.total.toLocaleString()}</a>
                    </td>
                    <td>${database.signatures.integrated}</td>
                    <td>
                        <a href="/database/${database.id}/unintegrated/?target=integrated">${(database.signatures.total-database.signatures.integrated).toLocaleString()}</a>
                    </td>
                    </tr>
                `;
            }

            const tab = document.querySelector('.segment[data-tab="databases"]');
            tab.querySelector('tbody').innerHTML = html;
        });
}

function getRecentEntries() {
    return fetch('/api/entries/news/')
        .then(response => response.json())
        .then(object => {
            let html = '';
            for (const entry of object.entries) {
                html += `
                    <tr>
                    <td>
                        <span class="ui circular mini label type ${entry.type}">${entry.type}</span>
                        <a href="/entry/${entry.accession}/">${entry.accession}</a>
                    </td>
                    <td>${entry.short_name}</td>
                    <td>${entry.signatures}</td>
                    <td>${checkbox.createDisabled(entry.checked)}</td>
                    <td>${entry.date}</td>
                    <td>${entry.user}</td>
                    </tr>
                `;
            }

            const tab = document.querySelector('.segment[data-tab="news"]');
            tab.querySelector('tbody').innerHTML = html;
            tab.querySelector(':scope > p').innerHTML = `<strong>${object.entries.length}</strong> ${object.entries.length > 1 ? 'entries' : 'entry'} created since <strong>${object.date}</strong>.`;
            document.querySelector('.item[data-tab="news"] .label').innerHTML = object.entries.length.toString();
        });
}

function getUncheckedEntries() {
    return fetch('/api/entries/unchecked/')
        .then(response => response.json())
        .then(entries => {
            let html = '';
            for (const entry of entries) {
                html += `
                    <tr>
                    <td>
                        <span class="ui circular mini label type ${entry.type}">${entry.type}</span>
                        <a href="/entry/${entry.accession}/">${entry.accession}</a>
                    </td>
                    <td>${entry.short_name}</td>
                    <td>${entry.signatures}</td>
                    <td>${entry.created_date}</td>
                    <td>${entry.update_date}</td>
                    <td>${entry.user}</td>
                    <td class="right aligned">
                `;

                if (entry.comments > 0)
                    html += `<a href="/entry/${entry.accession}/" class="ui small basic label"><i class="comments icon"></i> ${entry.comments}</a>`;

                html += '</td></tr>';
            }

            const tab = document.querySelector('.segment[data-tab="unchecked"]');
            tab.querySelector('tbody').innerHTML = html;
            document.querySelector('.item[data-tab="unchecked"] .label').innerHTML = entries.length.toString();
        });
}


async function resolveError(runID, errID) {
    const response = await fetch(`/api/checks/run/${runID}/${errID}/`, {method: 'POST'});
    const result = await response.json();
    return Promise.resolve({status: response.status, result: result});
}


async function getSanityCheck() {
    const response = await fetch('/api/checks/run/last/');
    if (!response.ok) {
        const tab = document.querySelector('.segment[data-tab="checks"]');
        tab.innerHTML = `
        <div class="ui error message">
            <div class="header">Sanity checks not available</div>
            <p>Sanity checks have not been migrated, and cannot be used at this time.</p>
        </div>
    `;
        const label = document.querySelector('.item[data-tab="checks"] .label');
        label.parentNode.removeChild(label);
        return Promise.resolve();
    }

    const object = await response.json();
    const tab = document.querySelector('.segment[data-tab="checks"]');
    if (object.id === undefined) {
        tab.querySelector('tbody').innerHTML = '<tr><td colspan="4" class="center aligned">No sanity check report available</td></tr>';
        document.querySelector('.item[data-tab="checks"] .label').innerHTML = '0';
        return;
    }

    const copy2clipboard = (elem) => {
        const input = document.createElement('input');
        input.value = unescape(elem.innerHTML);
        document.body.appendChild(input);
        try {
            input.select();
            document.execCommand('copy');
            elem.className = 'positive';
        } catch (err) {
            console.error(err);
            elem.className = 'negative';
        } finally {
            document.body.removeChild(input);
            setTimeout(() => {
                elem.className = '';
            }, 300);
        }
    };

    const showOccurrences = (count) => {
        return count > 1 ? `&nbsp;&times;&nbsp;${count}` : '';
    };

    let html = '';
    let numUnresolved = 0;
    for (const error of object.errors) {
        const acc = error.annotation !== null ? error.annotation : error.entry;
        html += `
                    <tr>
                    <td class="left marked ${error.resolution.date === null ? 'red' : 'green'}"><a target="_blank" href="/search/?q=${acc}">${acc}</a></td>
                    <td>${error.type}</td>
                    <td><code>${escape(error.error)}</code>${showOccurrences(error.count)}</td>
                `;

        if (error.resolution.user !== null)
            html += `<td class="light-text right aligned"><i class="check icon"></i>Resolved by ${error.resolution.user}</td>`;
        else {
            numUnresolved += 1;
            html += '<td class="right aligned">';

            if (error.exceptions)
                html += `<button data-resolve="${error.id}" data-except class="ui very compact basic button">Add exception</button>`;

            html += `<button data-resolve="${error.id}" class="ui very compact basic button">Resolve</button>`;
        }

        html += '</tr>';
    }

    tab.querySelector('p').innerHTML = `Last sanity checks performed on <strong>${object.date}</strong>.`;

    const tbody = tab.querySelector('tbody');
    tbody.innerHTML = html;

    let raised = null;
    const rows = [...tbody.querySelectorAll('tr')];
    for (const elem of rows) {
        elem.addEventListener('click', e => {
            if (e.target.tagName === 'CODE')
                return;

            const row = e.currentTarget;
            if (raised === row) {
                rows.map(r => setClass(r, 'inactive', false));
                raised = null;
            } else {
                rows.map(r => setClass(r, 'inactive', r !== row));
                raised = row;
            }
        });
    }

    const runID = object.id;
    for (const elem of tbody.querySelectorAll('[data-resolve]')) {
        elem.addEventListener('click', e => {
            const errID = e.currentTarget.dataset.resolve;
            const addException = e.currentTarget.dataset.except !== undefined;
            if (addException)
                return;
            resolveError(runID, errID)
                .then(result => {
                    if (result.status) {
                        getSanityCheck();
                        return;
                    }
                });
        });
    }

    for (const elem of tbody.querySelectorAll('code')) {
        elem.addEventListener('click', e => copy2clipboard(e.currentTarget));
    }

    $(tab.querySelectorAll('[data-content]')).popup();
    document.querySelector('.item[data-tab="checks"] .label').innerHTML = numUnresolved.toString();
}

function runSanityChecks() {
    fetch('/api/checks/', {method: 'PUT'})
        .then(response => response.json())
        .then(object => {
            const tab = document.querySelector('.segment[data-tab="checks"]');
            const message = tab.querySelector('.message');
            if (!object.status) {
                message.className = 'ui error message';
                message.innerHTML = `
                    <div class="header">${object.error.title}</div>
                    <p>${object.error.message}</p>
                `;
                return;
            }
            message.className = 'ui info message';
            message.innerHTML = `
                <div class="header">Sanity checks in progress</div>
                <p>Sanity checks are running. When complete, results will be displayed below.</p>
            `;

            const taskId = object.task;

            renderTaskList().then(tasks => {
                const waitForTask = () => {
                    setTimeout(() => {
                        fetchTasks()
                            .then(tasks => {
                                let complete = false;
                                let success = false;
                                for (let i = tasks.length - 1; i >= 0; i--) {
                                    if (tasks[i].id === taskId) {
                                        if (tasks[i].end_time !== null) {
                                            // Task complete
                                            complete = true;
                                            success = tasks[i].success;
                                        }
                                        break;
                                    }
                                }

                                if (complete) {
                                    if (success) {
                                        message.className = 'ui success message';
                                        message.innerHTML = `
                                            <div class="header">Sanity checks complete!</div>
                                            <p>Sanity checks completed successfully. Results will be displayed in three seconds.</p>
                                        `;
                                        setTimeout(getSanityCheck, 3000);
                                    } else {
                                        message.className = 'ui error message';
                                        message.innerHTML = `
                                            <div class="header">Task failure</div>
                                            <p>An error occurred while running sanity checks. Please try again or contact developers.</p>
                                        `;
                                    }
                                    return;
                                }

                                waitForTask();
                            });
                    }, 5000);
                }

                waitForTask();
            });
        });
}

document.addEventListener('DOMContentLoaded', () => {
    updateHeader();
    const match = location.href.match(/\/#\/(.+)$/);

    // Init tabs
    $('.tabular.menu .item').tab({
        // If URL endswith /#/<tab> and <tab> exists in markup, select this tab, otherwise (true) select the first tab
        autoTabActivation: match !== null && document.querySelector(`.tab[data-tab="${match[1]}"]`) !== null ? match[1] : true,
        onVisible: (tabPath) => {
            const url = new URL(`/#/${tabPath}`, location.origin);
            history.replaceState(null, document.title, url.toString());
        }
    });

    // Init closable messages
    $(document.querySelectorAll('.message .close'))
        .on('click', function() {
            $(this)
                .closest('.message')
                .transition('fade');
        });

    // Run sanity checks
    document.querySelector('.tab[data-tab="checks"] .primary.button').addEventListener('click', e => runSanityChecks());

    const promises = [
        getDatabases(),
        getRecentEntries(),
        getUncheckedEntries(),
        getSanityCheck()
    ];

    Promise.all(promises)
        .then(() => {
            setClass(document.getElementById('welcome'), 'active', false);
        });
});
