import * as checkbox from './ui/checkbox.js'
import * as dimmer from './ui/dimmer.js'
import {fetchTasks, renderTaskList, updateHeader} from "./ui/header.js"
import {setClass, escape, copy2clipboard} from "./ui/utils.js";
import * as modal from "./ui/modals.js";

function getDatabases() {
    return fetch('/api/databases/')
        .then(response => response.json())
        .then(databases => {
            let html = '';
            for (const database of databases) {
                let total;
                let unint;
                if (database.id === 'mobidblt') {
                    total = database.signatures.total.toLocaleString();
                    unint = (database.signatures.total-database.signatures.integrated).toLocaleString();
                } else {
                    total = `<a href="/database/${database.id}/">${database.signatures.total.toLocaleString()}</a>`;
                    unint = `<a href="/database/${database.id}/unintegrated/?target=integrated">${(database.signatures.total-database.signatures.integrated).toLocaleString()}</a>`;
                }

                html += `
                    <tr>
                    <td style="border-left: 5px solid ${database.color};" class="collapsing">
                        <a target="_blank" href="${database.link}">${database.name}<i class="external icon"></i></a>
                    </td>
                    <td>
                        <div class="ui basic label">${database.version}<span class="detail">${database.date}</span></div>
                    </td>
                    <td>${total}</td>
                    <td>${database.signatures.integrated.toLocaleString()}</td>
                    <td>${unint}</td>
                    </tr>
                `;
            }

            const tab = document.querySelector('.segment[data-tab="databases"]');
            tab.querySelector('tbody').innerHTML = html;
            return databases;
        });
}

function renderRecentEntries(data, hideChecked) {
    let html = '';
    for (const entry of data.entries) {
        if (entry.checked && hideChecked)
            continue;

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

    if (html.length === 0)
        html = '<tr><td colspan="6" class="center aligned">No entries found</td></tr>';

    const tab = document.querySelector('.segment[data-tab="news"]');
    tab.querySelector('tbody').innerHTML = html;
    tab.querySelector(':scope > p').innerHTML = `<strong>${data.entries.length}</strong> ${data.entries.length > 1 ? 'entries' : 'entry'} created since <strong>${data.date}</strong>.`;
    document.querySelector('.item[data-tab="news"] .label').innerHTML = data.entries.length.toString();
}

function getRecentEntries() {
    return fetch('/api/entries/news/')
        .then(response => response.json())
        .then(object => {
            sessionStorage.setItem('newEntries', JSON.stringify(object));
            const hideChecked = document.querySelector('[data-tab="news"] input[name="unchecked"]').checked;
            renderRecentEntries(object, hideChecked);
        });
}

function initUncheckedEntries(databases) {
    const sigDatabases = databases.filter(db => db.id !== 'mobidblt');
    sigDatabases.splice(0, 0, true, false);
    const fieldsPerCol = Math.ceil(sigDatabases.length / 3);
    const columns = [[], [], []];
    for (let i = 0; i < sigDatabases.length; i++) {
        const x = Math.floor(i / fieldsPerCol);
        const database = sigDatabases[i];
        if (database === true)
            columns[x].push(['any', 'Any', null]);
        else if (database === false)
            columns[x].push(['none', 'None', null]);
        else
            columns[x].push([database.id, database.name, database.color]);
    }

    const form = document.querySelector('#unchecked-databases > .fields');
    form.innerHTML = columns
        .map((fields, index) => {
            const formatField = ([dbID, dbName, color]) => {
                const style = color !== null ? `border-bottom: 3px solid ${color}` : '';
                const status = dbID === 'any' ? 'checked' : '';
                return `<div class="field">
                        <div class="ui radio checkbox">
                        <input type="radio" name="database" value="${dbID}" ${status}>
                        <label><span style="${style}">${dbName}</span></label>
                        </div>
                        </div>`;
            };
            return `
                <div class="field">
                    <div class="grouped fields">
                        ${index === 0 ? '<label>Member database</label>' : '<label>&nbsp;</label>'}
                        ${fields.map(formatField).join('')}
                    </div>
                </div>
            `;
        })
        .join('');

    for (const elem of form.querySelectorAll('input[type="radio"][name="database"]')) {
        elem.addEventListener('change', (e,) => {
            const input = e.currentTarget;
            dimmer.on();
            getUncheckedEntries(input.value).then(() => {dimmer.off()});
        });
    }

    return getUncheckedEntries('any');
}

function getUncheckedEntries(database) {
    return fetch(`/api/entries/unchecked/?db=${database}`)
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
                    <td class="right aligned">
                `;

                if (entry.comments > 0)
                    html += `<a href="/entry/${entry.accession}/" class="ui small basic label"><i class="comments icon"></i> ${entry.comments}</a>`;

                html += '</td></tr>';
            }

            const tab = document.querySelector('.segment[data-tab="unchecked"]');

            if (html.length === 0)
                html = '<tr><td colspan="6" class="center aligned">No results found</td></tr>';

            tab.querySelector('tbody').innerHTML = html;
            document.querySelector('.item[data-tab="unchecked"] .label').innerHTML = entries.length.toString();
        });
}

async function resolveError(runID, errID, addException) {
    let url = `/api/checks/run/${runID}/${errID}/`;
    if (addException)
        url += '?exception';

    const response = await fetch(url, {method: 'POST'});
    return await response.json();
}

async function getSanityCheck() {
    const response = await fetch('/api/checks/run/last/');
    if (response.status !== 200 && response.status !== 404) {
        const tab = document.querySelector('.segment[data-tab="checks"]');
        tab.innerHTML = `
        <div class="ui error message">
            <div class="header">Sanity checks not available</div>
            <p>An internal error occurred: sanity checks cannot be used at this time.</p>
        </div>
    `;
        const label = document.querySelector('.item[data-tab="checks"] .label');
        label.parentNode.removeChild(label);
        return Promise.resolve();
    }

    const object = await response.json();
    const tab = document.querySelector('.segment[data-tab="checks"]');
    if (response.status === 404) {
        tab.querySelector('tbody').innerHTML = '<tr><td colspan="4" class="center aligned">No sanity check report available</td></tr>';
        document.querySelector('.item[data-tab="checks"] .label').innerHTML = '0';
        return;
    }

    const showOccurrences = (count) => {
        return count > 1 ? `&nbsp;&times;&nbsp;${count}` : '';
    };

    let html = '';
    let numUnresolved = 0;
    if (object.errors.length > 0) {
        for (const error of object.errors) {
            const acc = error.annotation !== null ? error.annotation : error.entry;
            const errHTML = error.error !== null ? `<code>${escape(error.error)}</code>`: '';
            html += `
            <tr>
            <td class="left marked ${error.resolution.date === null ? 'red' : 'green'}"><a target="_blank" href="/search/?q=${acc}">${acc}</a></td>
            <td>${error.type}</td>
            <td>${errHTML}${showOccurrences(error.count)}</td>
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
    } else
        html += '<tr><td colspan="4" class="center aligned">No error found. Good job! <i class="thumbs up outline fitted icon"></i></td></tr>';

    tab.querySelector('thead > tr:first-child > th').innerHTML = `Report from ${object.date}`;
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
            resolveError(runID, errID, addException)
                .then(result => {
                    if (result.status) {
                        getSanityCheck();
                    } else
                        modal.error(result.error.title, result.error.message);
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
                                            <p>Sanity checks completed successfully. Results will be displayed in a few seconds.</p>
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

    // Event on toggle
    document.querySelector('[data-tab="news"] input[name="unchecked"]').addEventListener('change', e => {
        const data = sessionStorage.getItem('newEntries');
        if (data === null)
            return;

        const hideChecked = e.currentTarget.checked;
        renderRecentEntries(JSON.parse(data), hideChecked);
    });

    // Run sanity checks
    document.querySelector('.tab[data-tab="checks"] .primary.button').addEventListener('click', e => runSanityChecks());

    const promises = [
        getDatabases().then(databases => initUncheckedEntries(databases)),
        getRecentEntries(),
        getSanityCheck()
    ];

    Promise.all(promises)
        .then(() => {
            setClass(document.getElementById('welcome'), 'active', false);
        });
});
