import * as checkbox from './ui/checkbox.js'
import {fetchTasks, renderTaskList, updateHeader} from "./ui/header.js"
import {setClass} from "./ui/utils.js";

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
                    </tr>
                `;
            }

            const tab = document.querySelector('.segment[data-tab="unchecked"]');
            tab.querySelector('tbody').innerHTML = html;
            document.querySelector('.item[data-tab="unchecked"] .label').innerHTML = entries.length.toString();
        });
}

function getSanityCheck() {
    return fetch('/api/checks/run/last/')
        .then(response => response.json())
        .then(object => {
            const tab = document.querySelector('.segment[data-tab="checks"]');
            if (object.id === undefined) {
                tab.querySelector('tbody').innerHTML = '<tr><td colspan="5" class="center aligned">No sanity check report available</td></tr>';
                document.querySelector('.item[data-tab="checks"] .label').innerHTML = '0';
                return;
            }

            const escape = (data) => {
                return data
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
            };
            const showOccurrences = (count) => {
                return count > 1 ? `&nbsp;&times;&nbsp;${count}` : '';
            };
            const makeResolveButton = (resolutionDate, acceptExceptions) => {
                if (resolutionDate !== null)
                    return '';
                else if (acceptExceptions === undefined || acceptExceptions === null)  // resolve-only button
                    return '<i class="check button icon" data-content="Resolve" data-position="top center" data-variation="small"></i>';
                else if (acceptExceptions)
                    return '<i class="double check button icon" data-content="Add exception & resolve" data-position="top center" data-variation="small"></i>';
                return '';
            };

            let html = '';
            for (const error of object.errors) {
                const id = error.annotation !== null ? error.annotation : error.entry;
                html += `
                    <tr>
                    <td class="left marked ${error.resolution.date === null ? 'red' : 'green'}"><a target="_blank" href="/search/?q=${id}">${id}</a></td>
                    <td>${error.type}</td>
                    <td><code>${escape(error.error)}</code>${showOccurrences(error.count)}</td>
                    <td class="right aligned">${makeResolveButton(error.resolution.date)}</td>
                    <td class="right aligned">${makeResolveButton(error.resolution.date, error.exceptions)}</td>
                    </tr>
                `;
            }

            tab.querySelector('p').innerHTML = `Last sanity checks performed on <strong>${object.date}</strong>.`;
            tab.querySelector('tbody').innerHTML = html;
            $(tab.querySelectorAll('[data-content]')).popup();
            document.querySelector('.item[data-tab="checks"] .label').innerHTML = object.errors.length.toString();
        });
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
