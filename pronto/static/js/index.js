import * as checkbox from './ui/checkbox.js'
import * as dimmer from './ui/dimmer.js'
import {fetchTasks, renderTaskList, updateHeader} from "./ui/header.js"
import {setClass, escape, copy2clipboard} from "./ui/utils.js";
import * as modal from "./ui/modals.js";

async function getMemberDatabaseUpdates() {
    const response = await fetch('/api/databases/updates/')
    const data = await response.json();

    let html = '';
    for (const update of data.results) {
        html += `
            <tr>
                <td style="border-left: 5px solid ${update.color};">${update.name}</td>
                <td><span class="ui basic label">${update.version}</span></td>
                <td>${update.date}</td>
            </tr>
        `;
    }

    document.querySelector('#table-updates tbody').innerHTML = html + '</table>';
}

async function getEntryStats() {
    const response = await fetch('/api/entries/checked/')
    const data = await response.json();
    let total = 0;
    const series = [];

    for (const item of data.results) {
        series.push({
            name: item.year,
            y: item.count
        });
        total += item.count;
    }

    Highcharts.chart(document.getElementById('chart-entries'), {
        chart: { type: 'column', height: 250 },
        title: { text: null },
        subtitle: { text: null },
        credits: { enabled: false },
        legend: { enabled: false },
        xAxis: {
            type: 'category',
            title: { text: null },
        },
        yAxis: {
            title: { text: 'Entries' }
        },
        series: [{
            data: series,
            color: '#2c3e50'
        }],
        tooltip: {
            headerFormat: '<span style="font-size: 10px;">{point.key}</span><br/>',
            pointFormat: '<b>{point.y}</b> entries created'
        }
    });

    document.getElementById('stats-entries').innerHTML = total.toLocaleString();
}

async function getInterPro2GoStats() {
    const response = await fetch('/api/entries/go/')
    const data = await response.json();

    // Descending order
    const results = data.results.sort((a, b) => b.terms - a.terms);

    // Map insertion from highest number to lowest
    const counts = new Map();
    let total = 0;
    for (const obj of results) {
        let key = obj.terms < 5 ? obj.terms.toString() : '5+';
        const val = obj.entries;

        total += obj.terms * val;
        if (counts.has(key))
            counts.set(key, counts.get(key) + val);
        else
            counts.set(key, val);
    }

    Highcharts.chart(document.getElementById('chart-interpro2go'), {
        chart: { type: 'bar', height: 250 },
        title: { text: null },
        subtitle: { text: null },
        credits: { enabled: false },
        legend: { enabled: false },
        xAxis: {
            type: 'category',
            title: { text: 'GO terms' },
        },
        yAxis: {
            // type: 'logarithmic',
            title: { text: 'Entries' },
        },
        series: [{
            data: [...counts.entries()],
            color: '#2c3e50'
        }],
        tooltip: {
            headerFormat: '<span style="font-size: 10px;">{point.key} GO Terms</span><br/>',
            pointFormat: '<b>{point.y}</b> entries'
        },
    });

    document.getElementById('stats-interpro2go').innerHTML = total.toLocaleString();
}

async function getIntegrationStats() {
    const response = await fetch('/api/entries/signatures/')
    const data = await response.json();

    document.getElementById('stats-signatures').innerHTML = data.count.toLocaleString();

    Highcharts.chart(document.getElementById('chart-integrated'), {
        chart: { type: 'column', height: 250 },
        title: { text: null },
        subtitle: { text: null },
        credits: { enabled: false },
        legend: { enabled: false },
        xAxis: {
            title: { text: null },
            type: 'datetime',
            labels: {
                formatter: function() {
                    return Highcharts.dateFormat('%b %Y', this.value);
                }
            }
        },
        yAxis: {
            title: { text: 'Signatures' }
        },
        series: [{
            data: data.results.map(e => ({
                x: e.timestamp * 1000,  // seconds to milliseconds
                y: e.count,
                name: e.week
            })),
            color: '#2c3e50'
        }],
        tooltip: {
            formatter: function() {
                return `
                    <span style="font-size: 10px">Week ${this.point.name} (${Highcharts.dateFormat('%e %b', this.x)})</span><br>
                    <b>${this.y}</b> signatures integrated
                `;
            },
        },
    });
}

async function getCitationsStats() {
    const response = await fetch('/api/entries/citations/')
    const data = await response.json();
    document.getElementById('stats-citations').innerHTML = data.count.toLocaleString();
}

async function getQuartelyReports() {
    await Promise.all([
        fetch('/api/entries/report/').then(response => response.json()),
        fetch('/api/entries/signatures/report/').then(response => response.json()),
        fetch('/api/entries/go/report/').then(response => response.json()),
        fetch('/api/entries/citations/report/').then(response => response.json()),
    ]).then(objects => {
        const entriesData = new Map(Object.entries(objects[0]))
        const signaturesData = new Map(Object.entries(objects[1]))
        const termsData = new Map(Object.entries(objects[2]))
        const citationsData = new Map(Object.entries(objects[3]))

        let quarters = new Set(entriesData.keys());
        for (const key of signaturesData.keys()) quarters.add(key);
        for (const key of termsData.keys()) quarters.add(key);
        for (const key of citationsData.keys()) quarters.add(key);

        quarters = [...quarters].sort();

        Highcharts.chart(document.getElementById('chart-reports'), {
            chart: { type: 'column', height: 250 },
            title: { text: null },
            subtitle: { text: null },
            credits: { enabled: false },
            xAxis: { categories: quarters },
            yAxis: { title: { text: null } },
            series: [{
                name: 'Entries',
                data: quarters.map(key => entriesData.has(key) ? entriesData.get(key) : 0),
                color: '#241E26'
            }, {
                name: 'Signatures',
                data: quarters.map(key => signaturesData.has(key) ? signaturesData.get(key) : 0),
                color: '#34BFA6'
            }, {
                name: 'GO terms',
                data: quarters.map(key => termsData.has(key) ? termsData.get(key) : 0),
                color: '#F29441'
            }, {
                name: 'Citations',
                data: quarters.map(key => citationsData.has(key) ? citationsData.get(key) : 0),
                color: '#D94E41'
            }]
        });
    })
}

async function getInterPro2GO() {
    const response = await fetch('/api/entries/go/news/')
    const data = await response.json();

    let html = '';
    let label;
    let labelColor;
    for (const obj of data.results) {
        if (obj.term.category === 'cellular_component') {
            label = 'C';
            labelColor = 'violet';
        } else if (obj.term.category === 'biological_process') {
            label = 'P';
            labelColor = 'orange';
        } else {  // molecular_function
            label = 'F';
            labelColor = 'green';
        }

        html += `
            <tr>
            <td>
                <span class="ui circular mini label type ${obj.entry.type}">${obj.entry.type}</span>
                <a href="/entry/${obj.entry.accession}/">${obj.entry.accession}</a>
                <br>
                ${obj.entry.short_name}
            </td>
            <td>
                <span class="ui circular mini basic type label ${labelColor}">${label}</span>
                <a href="//www.ebi.ac.uk/QuickGO/term/${obj.term.id}" target="_blank">${obj.term.id}<i class="external icon"></i></a><br>
                ${obj.term.name}
            </td>
            <td>${obj.date}</td>
            <td>${obj.user}</td>
            </tr>
        `;
    }

    const segment = document.querySelector('.tab[data-tab="interpro2go"]');
    segment.querySelector('tbody').innerHTML = html;

    html = `Since ${data.date}, <strong>${data.results.length} `;
    html += data.results.length > 1 ? 'mappings' : 'mapping';
    html += '</strong> have been created.';
    segment.querySelector(':scope > p').innerHTML = html;

    document.querySelector('.item[data-tab="interpro2go"] .label').innerHTML = data.results.length.toString();
}

function getDatabases() {
    return fetch('/api/databases/')
        .then(response => response.json())
        .then(databases => {
            let html = '';
            // const series = [];
            for (const database of databases) {
                let total;
                let unint;
                if (database.id === 'mobidblt') {
                    total = database.signatures.total.toLocaleString();
                    unint = (database.signatures.total-database.signatures.integrated).toLocaleString();
                } else {
                    total = `<a href="/database/${database.id}/">${database.signatures.total.toLocaleString()}</a>`;
                    unint = `<a href="/database/${database.id}/unintegrated/?target=integrated">${(database.signatures.total-database.signatures.integrated).toLocaleString()}</a>`;

                    // series.push({
                    //     name: database.name,
                    //     int: database.signatures.integrated,
                    //     unint: database.signatures.total - database.signatures.integrated
                    // });
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

            const tab = document.querySelector('.tab[data-tab="databases"]');
            tab.querySelector('tbody').innerHTML = html;

            return databases;
        });
}

function renderRecentEntries(entries, hideChecked) {
    let html = '';
    for (const entry of entries) {
        if (entry.checked && hideChecked)
            continue;

        html += `
            <tr>
            <td>
                <span class="ui circular mini label type ${entry.type}">${entry.type}</span>
                <a href="/entry/${entry.accession}/">${entry.accession}</a>
            </td>
            <td>${entry.short_name}</td>
            <td>${checkbox.createDisabled(entry.checked)}</td>
            <td>${entry.date}</td>
            <td>${entry.user}</td>
            <td>
        `;

        let numComments = entry.comments.entry + entry.comments.signatures;
        if (numComments > 0)
            html += `<a href="/entry/${entry.accession}/" class="ui small basic label"><i class="comments icon"></i> ${numComments}</a>`;

        html += '</td></tr>';
    }

    if (html.length === 0)
        html = '<tr><td colspan="5" class="center aligned">No entries found</td></tr>';

    document.querySelector('.tab[data-tab="news"] tbody').innerHTML = html;
}

async function getRecentEntries() {
    const response = await fetch('/api/entries/news/');
    let data = await response.json();

    sessionStorage.setItem('newEntries', JSON.stringify(data.results));
    const tab = document.querySelector('.tab[data-tab="news"]');
    const hideChecked = tab.querySelector('input[name="unchecked"]').checked;

    // Recent entries
    renderRecentEntries(data.results, hideChecked);

    let text = `Since ${data.date}, <strong>${data.results.length} `;
    text += data.results.length > 1 ? 'entries' : 'entry';
    text += '</strong> have been created.';

    document.getElementById('news-summary').innerHTML = text;
    document.querySelector('.item[data-tab="news"] .label').innerHTML = data.results.length.toString();
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
            const entriesPerYear = new Map();

            for (const entry of entries) {
                const year = Number.parseInt(entry.created_date.split(' ')[2], 10);
                if (entriesPerYear.has(year))
                    entriesPerYear.set(year, entriesPerYear.get(year) + 1);
                else
                    entriesPerYear.set(year, 1);

                html += `
                    <tr>
                    <td>
                        <span class="ui circular mini label type ${entry.type}">${entry.type}</span>
                        <a href="/entry/${entry.accession}/">${entry.accession}</a>
                    </td>
                    <td>${entry.short_name}</td>
                    <td>${entry.created_date}</td>
                    <td>${entry.update_date}</td>
                    <td class="right aligned">
                `;

                let numComments = entry.comments.entry + entry.comments.signatures;
                if (numComments > 0)
                    html += `<a href="/entry/${entry.accession}/" class="ui small basic label"><i class="comments icon"></i> ${numComments}</a>`;

                html += '</td></tr>';
            }

            const tab = document.querySelector('.tab[data-tab="unchecked"]');

            if (html.length === 0)
                html = '<tr><td colspan="5" class="center aligned">No results found</td></tr>';

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
        const tab = document.querySelector('.tab[data-tab="checks"]');
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
    const tab = document.querySelector('.tab[data-tab="checks"]');
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
            html += `
                <tr>
                <td class="left marked ${error.resolution.date === null ? 'red' : 'green'}">
                    <a target="_blank" href="/search/?q=${acc}">${acc}</a>
                </td>
            `;

            if (error.details !== null) {
                html += `<td>${error.type} <span data-tooltip="${error.details}" data-inverted=""><i class="question circle icon"></i></span></td>`;
            } else
                html += `<td>${error.type}</td>`;

            if (error.error !== null)
                html += `<td><code>${escape(error.error)}</code>${showOccurrences(error.count)}</td>`;
            else
                html += `<td>${showOccurrences(error.count)}</td>`;

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
            const tab = document.querySelector('.tab[data-tab="checks"]');
            const message = tab.querySelector('.message');
            if (!object.status) {
                message.className = 'ui error message';
                message.innerHTML = `
                    <div class="header">${object.error.title}</div>
                    <p>${object.error.message}</p>
                `;
                return;
            }
            message.className = 'ui icon info message';
            message.innerHTML = `
                <i class="notched circle loading icon"></i>
                <div class="content">
                    <div class="header">Sanity checks in progress</div>
                    <p>Sanity checks are running. When complete, results will be displayed below.</p>
                </div>
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

    Promise.all([
        getDatabases().then(databases => initUncheckedEntries(databases)),
        getRecentEntries(),
        getSanityCheck(),
        getInterPro2GO()
    ])
        .then(() => {
            setClass(document.getElementById('welcome'), 'active', false);
        });

    (function() {
        const tab = document.querySelector('.tab[data-tab="statistics"]');
        tab.querySelector(':scope > .button').addEventListener('click', e => {
            const button = e.currentTarget;
            setClass(button, 'loading', true);

            Promise.all([
                getEntryStats(),
                getMemberDatabaseUpdates(),
                getInterPro2GoStats(),
                getIntegrationStats(),
                getCitationsStats(),
                getQuartelyReports()
            ]).then(() => {
                setClass(button, 'hidden', true);
                setClass(tab.querySelector(':scope > .content'), 'hidden', false);
            });
        });

    }());
});
