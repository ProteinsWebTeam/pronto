import * as checkbox from './ui/checkbox.js'
import * as dimmer from './ui/dimmer.js'
import { renderTaskList, updateHeader } from "./ui/header.js"
import { setClass, escape, copy2clipboard } from "./ui/utils.js";
import { waitForTask } from "./tasks.js";
import * as modal from "./ui/modals.js";
import { backToTop } from "./ui/backtotop.js";
import { initPopups, createPopup } from './ui/comments.js';

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
    const response = await fetch('/api/entries/counts/')
    const data = await response.json();

    let total = 0;
    const seriesData = [];
    for (const item of data.results) {
        seriesData.push({
            name: item.year,
            y: item.checked
        });
        total += item.checked;
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
            data: seriesData,
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
    const response = await fetch('/api/entries/counts/go/')
    const data = await response.json();

    // Descending order
    const results = data.results.sort((a, b) => b.terms - a.terms);

    // Only one category for entries having five GO terms or more
    const getKey = (obj) => obj.terms < 5 ? obj.terms.toString() : '5+';

    // Find categories
    const categories = [...new Set(results.map(getKey))];

    const series = new Map();
    let total = 0;
    for (const obj of results) {
        const category = getKey(obj);

        for (const entryType of obj.types) {
            const key = entryType.name;
            const val = entryType.count;
            total += val;

            if (!series.has(key))
                // Init array with zeros
                series.set(key, new Array(categories.length).fill(0));

            // Incr count
            const i = categories.indexOf(category);
            series.get(key)[i] += val;
        }
    }

    const colors = new Map([
        ['Repeat', '#f2711c'],
        ['Homologous_superfamily', '#1678c2'],
        ['Domain', '#21ba45'],
        ['Family', '#db2828'],
    ]);
    const defaultColor = '#a333c8';

    Highcharts.chart(document.getElementById('chart-interpro2go'), {
        chart: {
            type: 'bar',
            height: 250,
            events: {
                load: function () {
                    this.setSize(null, this.chartHeight + this.legend.legendHeight + this.legend.padding);
                }
            }
        },
        title: { text: null },
        subtitle: { text: null },
        credits: { enabled: false },
        // legend: { enabled: false },
        xAxis: {
            type: 'category',
            title: { text: 'GO terms' },
            categories: categories
        },
        yAxis: {
            // type: 'logarithmic',
            title: { text: 'Entries' },
        },
        plotOptions: {
            series: {
                stacking: 'normal'
            }
        },
        series: [...series.entries()].map(([key, value]) => ({
            name: key.replace('_', ' '),
            color: colors.has(key) ? colors.get(key) : defaultColor,
            data: value
        }))
            .sort((a, b) => a.name.localeCompare(b.name)),
        tooltip: {
            headerFormat: '<span style="font-size: 10px;">{point.key} GO term(s)</span><br/>',
            pointFormat: '{series.name}: <b>{point.y}</b> entries'
        },
    });

    document.getElementById('stats-interpro2go').innerHTML = total.toLocaleString();
}

async function getIntegrationStats() {
    const response = await fetch('/api/entries/counts/signatures/')
    const data = await response.json();

    document.getElementById('stats-signatures').innerHTML = data.checked.toLocaleString();

    const addData = [];
    const delData = [];

    for (const week of data.results) {
        const x = week.timestamp * 1000;  // seconds to milliseconds

        addData.push({
            x: x,
            y: week.counts.integrated.all,
            name: week.number,
            checked: week.counts.integrated.checked
        });

        delData.push({
            x: x,
            y: week.counts.unintegrated.all,
            name: week.number,
            checked: week.counts.unintegrated.checked
        });
    }

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
                formatter: function () {
                    return Highcharts.dateFormat('%b %Y', this.value);
                }
            }
        },
        yAxis: {
            title: { text: 'Signatures' }
        },
        series: [{
            name: 'integrated',
            color: '#27ae60',
            data: addData
        }, {
            name: 'unintegrated',
            color: '#c0392b',
            data: delData
        }],
        tooltip: {
            formatter: function () {
                return `
                    <span style="font-size: 10px">Week ${this.point.name} (${Highcharts.dateFormat('%e %b', this.x)})</span><br>
                    <b>${this.y}</b> signature${this.y !== 1 ? 's' : ''} ${this.series.name}<br>
                    <span style="font-size: 10px">${this.point.checked} ${this.point.checked === 1 ? 'is' : 'are'} currently integrated in a checked entry</span>
                `;
            },
        },
    });
}

async function getCitationsStats() {
    const response = await fetch('/api/entries/counts/citations/')
    const data = await response.json();

    // Descending order
    const results = data.results.sort((a, b) => b.citations - a.citations);

    // Map insertion from highest number to lowest
    const counts = new Map();
    let total = 0;
    for (const obj of results) {
        let key = obj.citations < 5 ? obj.citations.toString() : '5+';
        const val = obj.entries;

        total += obj.citations * val;
        if (counts.has(key))
            counts.set(key, counts.get(key) + val);
        else
            counts.set(key, val);
    }

    Highcharts.chart(document.getElementById('chart-citations'), {
        chart: { type: 'bar', height: 250 },
        title: { text: null },
        subtitle: { text: null },
        credits: { enabled: false },
        legend: { enabled: false },
        xAxis: {
            type: 'category',
            title: { text: 'Citations' },
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
            headerFormat: '<span style="font-size: 10px;">{point.key} citations</span><br/>',
            pointFormat: '<b>{point.y}</b> entries'
        },
    });

    document.getElementById('stats-citations').innerHTML = total.toLocaleString();
}

async function getRecentActivity(days, max) {
    const seconds = (days || 7) * 24 * 3600;
    const response = await fetch(`/api/activity/?s=${seconds}`);
    const data = await response.json();

    const actions = new Map([
        ['I', ['plus', 'created']],
        ['U', ['pencil alternate', 'edited']],
        ['D', ['trash alternate', 'deleted']]
    ]);

    const createAbstractLink = (annId) => {
        return `<a href="/search/?q=${annId}">${annId}</a>`;
    };
    const createEntryLink = (accession) => {
        return `<a href="/entry/${accession}/">${accession}</a>`;
    };
    const createSignatureLink = (accession) => {
        return `<a href="/signature/${accession}/">${accession}</a>`;
    };

    const dateReg = /^(\d+ [a-z]+) \d+ at \d+:\d+$/i;
    let html = '';
    let n = 0;
    for (const event of data) {
        if (!actions.has(event.action))
            continue

        let [icon, action] = actions.get(event.action);
        const user = event.user.split(' ')[0];

        let target = null;
        if (event.type === 'CA') {
            if (action === 'deleted')
                target = event.primary_id
        }
        switch (event.type) {
            case 'CA':
                if (action === 'deleted')
                    target = event.primary_id;
                else
                    target = createAbstractLink(event.primary_id);
                break;
            case 'E2C':
                if (action === 'created') {
                    action = 'added';
                    target = `${createAbstractLink(event.secondary_id)} to ${createEntryLink(event.primary_id)}`;
                } else if (action === 'deleted') {
                    target = `${createAbstractLink(event.secondary_id)} from ${createEntryLink(event.primary_id)}`;
                } else {
                    action = 're-ordered';
                    target = `${createAbstractLink(event.secondary_id)} in ${createEntryLink(event.primary_id)}`;
                }
                break;
            case 'E2E':
                if (action === 'created') {
                    action = 'added';
                    target = `${createEntryLink(event.primary_id)} to ${createAbstractLink(event.secondary_id)}`;
                } else if (action === 'deleted') {
                    action = 'unlinked';
                    target = `${createEntryLink(event.primary_id)} and ${createAbstractLink(event.secondary_id)}`;
                }
                break;
            case 'E2M':
                if (action === 'created') {
                    action = 'integrated';
                    target = `${createSignatureLink(event.secondary_id)} in ${createEntryLink(event.primary_id)}`;
                } else if (action === 'deleted') {
                    action = 'unintegrated';
                    target = `${createSignatureLink(event.secondary_id)} from ${createEntryLink(event.primary_id)}`;
                }
                break;
            case 'E':
                target = action === 'deleted' ? event.primary_id : createEntryLink(event.primary_id);
                break;
            case 'I2G':
                if (action === 'created') {
                    action = 'added';
                    target = `${event.secondary_id} to ${createEntryLink(event.primary_id)}`;
                } else if (action === 'deleted') {
                    target = `${event.secondary_id} from ${createEntryLink(event.primary_id)}`;
                }
                break;
        }

        if (target === null)
            continue;

        html += `
            <div class="event">
                <div class="label">
                    <i class="${icon} icon"></i>
                </div>
                <div class="content">
                    <div class="date">
                        ${event.timestamp}
                    </div>                
                    ${user} ${action} ${target}
                </div>
            </div>
        `;

        if (max && ++n === max)
            break;
    }

    document.getElementById('activity').innerHTML = html;
}

async function getQuartelyStats() {
    const response = await fetch('/api/entries/stats/');
    const data = await response.json();

    Highcharts.chart(document.getElementById('chart-reports'), {
        chart: { type: 'column', height: 250 },
        title: { text: null },
        subtitle: { text: null },
        credits: { enabled: false },
        xAxis: { categories: data.map(x => x.quarter) },
        yAxis: { title: { text: null } },
        series: [{
            name: 'Entries',
            data: data.map(x => x.entries),
            color: '#241E26'
        }, {
            name: 'Signatures',
            data: data.map(x => x.signatures),
            color: '#34BFA6'
        }, {
            name: 'GO terms',
            data: data.map(x => x.terms),
            color: '#F29441'
        }]
    });
}

async function getInterPro2GO() {
    const response = await fetch('/api/entries/news/go/')
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
                    unint = (database.signatures.total - database.signatures.integrated).toLocaleString();
                } else {
                    total = `<a href="/database/${database.id}/">${database.signatures.total.toLocaleString()}</a>`;
                    unint = `<a href="/database/${database.id}/unintegrated/?sort-by=single-domain-proteins&sort-order=desc">${(database.signatures.total - database.signatures.integrated).toLocaleString()}</a>`;

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

function renderRecentEntries(entries) {
    const tab = document.querySelector('.tab[data-tab="news"]');
    const authorFilter = tab.querySelector('input[name="entries-author"]:checked').value;
    const uncheckedOnly = tab.querySelector('input[name="entries-unchecked"]').checked

    let html = '';
    let count = 0;
    for (const entry of entries) {
        if (entry.checked && uncheckedOnly)
            continue;
        else if (authorFilter === 'me' && !entry.user.by_me)
            continue
        else if (authorFilter === 'others' && entry.user.by_me)
            continue

        count += 1;
        html += `
            <tr>
            <td>${count}</td>
            <td>
                <span class="ui circular mini label type ${entry.type}">${entry.type}</span>
                <a href="/entry/${entry.accession}/">${entry.accession}</a>
            </td>
            <td>${entry.short_name}</td>
            <td>${checkbox.createDisabled(entry.checked)}</td>
            <td>${entry.date}</td>
            <td>${entry.user.name}</td>
            <td>
        `;

        let numComments = entry.comments.entry + entry.comments.signatures;
        if (numComments > 0)
            html += `<a data-accession="${entry.accession}" class="ui small basic label"><i class="comments icon"></i> ${numComments}</a>`;

        html += '</td></tr>';
    }

    if (html.length === 0)
        html = '<tr><td colspan="5" class="center aligned">No entries found</td></tr>';

    tab.querySelector('thead th:first-child').innerHTML = `${count.toLocaleString()} entr${count === 1 ? 'y' : 'ies'}`;
    tab.querySelector('tbody').innerHTML = html;

    initPopups({
        element: tab,
        buildUrl: (accession) => `/api/entry/${accession}/comments/?signatures`,
        createPopup: createPopup
    });
}

async function getRecentEntries() {
    const response = await fetch('/api/entries/news/');
    let data = await response.json();

    sessionStorage.setItem('newEntries', JSON.stringify(data.results));

    // Recent entries
    renderRecentEntries(data.results);

    let text = `Since ${data.date}, <strong>${data.results.length} `;
    text += data.results.length > 1 ? 'entries' : 'entry';
    text += '</strong> have been created.';

    document.getElementById('news-summary').innerHTML = text;
    document.querySelector('.item[data-tab="news"] .label').innerHTML = data.results.length.toString();
}

async function getNumOfUncheckedEntries() {
    const response = await fetch('/api/entries/unchecked/?counts');
    const data = await response.json();
    document.querySelector('.item[data-tab="unchecked"] .label').innerHTML = data.results.toString();
}

function initUncheckedEntriesForm(databases) {
    const sigDatabases = databases.filter(db => db.id !== 'mobidblt');
    sigDatabases.splice(0, 0, 'any', 'none');
    const fieldsPerCol = Math.ceil(sigDatabases.length / 3);
    const columns = [[], [], []];
    for (let i = 0; i < sigDatabases.length; i++) {
        const x = Math.floor(i / fieldsPerCol);
        const database = sigDatabases[i];
        if (database === 'any')
            columns[x].push(['any', 'Any', null]);
        else if (database === 'none')
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
}

async function getUncheckedEntries() {
    const tab = document.querySelector('.tab[data-tab="unchecked"]');
    if (tab.dataset.status === 'loaded')
        return;

    dimmer.on();
    const response = await fetch(`/api/entries/unchecked/`);
    const data = await response.json();

    const refresh = () => {
        let keepEntry;
        const db = tab.querySelector('input[type="radio"][name="database"]:checked').value;
        if (db === 'any')
            keepEntry = (entry) => entry.databases.length >= 1;
        else if (db === 'none')
            keepEntry = (entry) => entry.databases.length === 0;
        else
            keepEntry = (entry) => entry.databases.includes(db);

        let html = '';
        const entries = data.results.filter(keepEntry);
        for (const entry of entries) {
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
                html += `<a data-accession="${entry.accession}" class="ui small basic label"><i class="comments icon"></i> ${numComments}</a>`;

            html += '</td></tr>';
        }

        if (entries.length === 0)
            html = '<tr><td colspan="5" class="center aligned">No results found</td></tr>';

        tab.querySelector('tbody').innerHTML = html;
        tab.querySelector('thead > tr:first-child > th:first-child').innerHTML = `${entries.length} entries`;

        initPopups({
            element: tab,
            buildUrl: (accession) => `/api/entry/${accession}/comments/?signatures`,
            createPopup: createPopup
        });
    };


    for (const elem of tab.querySelectorAll('input[type="radio"][name="database"]')) {
        elem.addEventListener('change', (e,) => {
            refresh();
        });
    }

    refresh();

    tab.dataset.status = 'loaded';
    dimmer.off();
}

async function resolveError(runID, errID, addException) {
    let url = `/api/checks/run/${runID}/${errID}/`;
    if (addException)
        url += '?exception';

    const response = await fetch(url, { method: 'POST' });
    return await response.json();
}

async function getSanityCheck() {
    const response = await fetch('/api/checks/run/latest/');
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
        tab.querySelector('tbody').innerHTML = '<tr><td colspan="5" class="center aligned">No sanity check report available</td></tr>';
        document.querySelector('.item[data-tab="checks"] .label').innerHTML = '0';
        return;
    }

    const showOccurrences = (count) => {
        return count > 1 ? `&nbsp;&times;&nbsp;${count}` : '';
    };

    let html = '';
    let numUnresolved = 0;
    if (object.errors.length > 0) {
        let count = 0
        for (const error of object.errors) {
            count += 1
            const acc = error.annotation !== null ? error.annotation : error.entry;
            html += `
                <tr>
                <td class="left marked ${error.resolution.date === null ? 'red' : 'green'}">${count}</td>
                <td>
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

                if (error.exceptions && error.type !== 'Invalid character')
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

async function runSanityChecks() {
    const tab = document.querySelector('.tab[data-tab="checks"]');
    const response = await fetch(`/api/checks/`, { method: 'PUT' });
    const run = await response.json();

    const message = tab.querySelector('.message');
    if (!run.status) {
        message.className = 'ui error message';
        message.innerHTML = `
            <div class="header">${run.error.title}</div>
            <p>${run.error.message}</p>
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

    const taskId = run.task.id;

    // Update task list
    renderTaskList();

    // Wait for task to complete
    const task = await waitForTask(taskId);
    if (task.success) {
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

    // Update task list
    renderTaskList();
}

async function getInterProScanAnalyses(progressBar, numSequences) {
    const response = await fetch('/api/interproscan/');
    const analyses = await response.json();
    const activeAnalyses = analyses.filter((x) => x.active);

    const $progress = $(progressBar);
    $progress.progress({
        percent: 0,
        total: activeAnalyses.length
    });

    const trackProgress = (promises) => {
        const increment = (promise) => {
            promise.then(function () {
                $progress.progress('increment');
            });
            return promise;
        };

        return Promise.all(promises.map(increment));
    };

    const promises = activeAnalyses.map((x) => getInterProScanAnalysis(x.name, x.version, numSequences));
    const results = await trackProgress(promises);

    const sequenceCounts = [];
    results
        .filter((x) => x.name !== 'SignalP')
        .forEach((x) => {
            if (!sequenceCounts.includes(x.proteins.count)) {
                sequenceCounts.push(x.proteins.count);
            }
        });

    if (sequenceCounts.length === 1) {
        progressBar
            .parentNode
            .querySelector(':scope > .content > .ui.info.message > strong')
            .innerHTML = sequenceCounts[0].toLocaleString();
    } else {
        // TODO: show warning that not all stats use the same number of sequences
        progressBar
            .parentNode
            .querySelector(':scope > .content > .ui.info.message > strong')
            .innerHTML = sequenceCounts[0].toLocaleString();
    }


    sessionStorage.setItem('jobs', JSON.stringify(results));
}

async function getInterProScanAnalysis(name, version, numSequences) {
    const response = await fetch(`/api/interproscan/${name}/${version}/?sequences=${numSequences}`);
    return await response.json();
}

function plotJobTimeChart() {
    const databases = JSON.parse(sessionStorage.getItem('jobs'));
    const dataType = document.querySelector('input[name="data-type"]:checked').value;
    const chartType = document.querySelector('input[name="chart-type"]:checked').value;
    const orderBy = document.querySelector('input[name="order-type"]:checked').value;

    const seriesData = [];
    const otherColors = ['#1b9e77','#d95f02','#7570b3','#e7298a','#66a61e','#e6ab02','#a6761d','#666666'];
    const colorMap = new Map();

    for (const item of databases) {
        let color = null;
        if (item.color !== null) {
            color = item.color
        } else if (colorMap.has(item.name)) {
            color = colorMap.get(item.name);
        } else if (otherColors.length > 0) {
            color = otherColors.shift();
            colorMap.set(item.name, color);
        }

        seriesData.push({
            name: `${item.name} ${item.version}`,
            y: (dataType === 'cputime' ?  item.cputime : item.runtime) / 3600,
            color: color,
            dbName: item.name,
            dbVersion: item.version
        });
    }

    if (orderBy === 'time')
        seriesData.sort((a, b) => b.y - a.y );
    else
        seriesData.sort((a, b) => a.name.localeCompare(b.name) );

    const onClick = (e) => {
        // getDatabaseInterProScanJobs(e.point.dbName, e.point.dbVersion)
        //     .then(() => {});
    };

    if (chartType === 'pie') {
        Highcharts.chart('chart-jobs-time', {
            chart: { type: 'pie', height: 500 },
            title: { text: null },
            subtitle: { text: null },
            credits: { enabled: false },
            legend: { enabled: false },
            plotOptions: {
                series: {
                    allowPointSelect: true,
                    cursor: 'pointer',
                    dataLabels: {
                        enabled: true,
                        format: '<b>{point.name}</b>'
                    },
                    point: {
                        events: {
                            click: onClick
                        }
                    }
                }
            },
            series: [{
                data: seriesData
            }],
            tooltip: {
                pointFormat: '<b>{point.y:.0f}</b> hours ({point.percentage:.1f}%)'
            },
        });
    } else {
        Highcharts.chart('chart-jobs-time', {
            chart: { type: 'column', height: 500 },
            title: { text: null },
            subtitle: { text: null },
            credits: { enabled: false },
            legend: { enabled: false },
            plotOptions: {
                series: {
                    point: {
                        events: {
                            click: onClick
                        }
                    }
                }
            },
            xAxis: {
                type: 'category',
                title: { text: null },
            },
            yAxis: {
                title: { text: dataType === 'cputime' ? 'CPU time' : 'Runtime' },
                labels: { format: '{value} h' },
            },
            series: [{
                data: seriesData,
                // color: '#2c3e50'
            }],
            tooltip: {
                headerFormat: '<span style="font-size: 10px;">{point.key}</span><br/>',
                pointFormat: '<b>{point.y:.1f}</b> hours'
            }
        });
    }
}

function plotJobMemoryChart() {
    const databases = JSON.parse(sessionStorage.getItem('jobs'));
    databases.sort((a, b) => {
        if (a.name !== b.name)
            return a.name.localeCompare(b.name);
        return a.version.localeCompare(b.version);
    });

    const boxPlotData = [];
    for (const item of databases) {
        // See https://api.highcharts.com/highcharts/series.boxplot.data
        boxPlotData.push([
            `${item.name} ${item.version}`,
            +(item.maxmem.min / 1024).toFixed(1),
            +(item.maxmem.q1 / 1024).toFixed(1),
            +(item.maxmem.q2 / 1024).toFixed(1),
            +(item.maxmem.q3 / 1024).toFixed(1),
            +(item.maxmem.max / 1024).toFixed(1),
        ]);
    }

    Highcharts.chart('chart-jobs-memory', {
        chart: { type: 'boxplot', height: 500 },
        title: { text: null },
        subtitle: { text: null },
        credits: { enabled: false },
        legend: { enabled: false },
        xAxis: {
            type: 'category',
            title: { text: null },
        },
        yAxis: {
            title: { text: 'Memory' },
            labels: { format: '{value} GB' },
        },
        tooltip: {
            formatter: function() {
                return `
                    <span style="font-size: 10px; font-weight: bold;">${this.key}</span>
                    <table class="simple">
                        <tbody>
                            <tr>
                                <td>Maximum</td>
                                <td class="right-align">${this.point.high.toLocaleString()} GB</td>
                            </tr>
                            <tr>
                                <td>Upper quartile</td>
                                <td class="right-align">${this.point.q3.toLocaleString()} GB</td>
                            </tr>
                            <tr>
                                <td>Median</td>
                                <td class="right-align">${this.point.median.toLocaleString()} GB</td>
                            </tr>
                            <tr>
                                <td>Lower quartile</td>
                                <td class="right-align">${this.point.q1.toLocaleString()} GB</td>
                            </tr>
                            <tr>
                                <td>Minimum</td>
                                <td class="right-align">${this.point.low.toLocaleString()} GB</td>
                            </tr>
                        </tbody>
                    </table>
                `;
            },
            hideDelay: 1500,
            style: {
                pointerEvents: 'auto'
            },
            useHTML: true,
        },
        series: [{
            data: boxPlotData,
        }]
    });
}

document.addEventListener('DOMContentLoaded', () => {
    updateHeader();
    backToTop();
    const match = location.href.match(/\/#\/(.+)$/);

    // Init tabs
    $('.tabular.menu .item').tab({
        // If URL endswith /#/<tab> and <tab> exists in markup, select this tab, otherwise (true) select the first tab
        autoTabActivation: match !== null && document.querySelector(`.tab[data-tab="${match[1]}"]`) !== null ? match[1] : true,
        onVisible: (tabPath) => {
            const url = new URL(`/#/${tabPath}`, location.origin);
            history.replaceState(null, document.title, url.toString());

            if (tabPath === 'unchecked')
                getUncheckedEntries();
        }
    });

    // Init closable messages
    $(document.querySelectorAll('.message .close'))
        .on('click', function () {
            $(this)
                .closest('.message')
                .transition('fade');
        });

    // Init checkboxes in "Recent entries" tab
    $('[data-tab="news"] .checkbox').checkbox({
        onChange: function () {
            const data = sessionStorage.getItem('newEntries');
            if (data !== null) renderRecentEntries(JSON.parse(data));
        }
    });

    // Run sanity checks
    document.querySelector('.tab[data-tab="checks"] .primary.button').addEventListener('click', e => runSanityChecks());

    Promise.all([
        getDatabases().then(databases => initUncheckedEntriesForm(databases)),
        getRecentEntries(),
        getInterPro2GO(),
        getSanityCheck(),
        getNumOfUncheckedEntries(),
    ])
        .then(() => {
            setClass(document.getElementById('welcome'), 'active', false);
        });

    document.querySelector('.tab[data-tab="statistics"] > .button')
        .addEventListener('click', e => {
            const button = e.currentTarget;
            setClass(button, 'loading', true);

            Promise.all([
                getEntryStats(),
                getMemberDatabaseUpdates(),
                getIntegrationStats(),
                getInterPro2GoStats(),
                getCitationsStats(),
                getQuartelyStats(),
                getRecentActivity(7, 0)
            ]).then(() => {
                setClass(button, 'hidden', true);
                setClass(button.parentNode.querySelector(':scope > .content'), 'hidden', false);
            });
        });

    let numClicks = 0;
    document.querySelector('a.item[data-tab="statistics"]').addEventListener('click', (e) => {
        numClicks++;
        if (numClicks === 1) {
            setTimeout(() => {
                numClicks = 0;
            }, 1000);
        } else if (numClicks === 5)
            document.querySelector('a.item[data-tab="interproscan"]').className = 'item';
    });

    document.querySelector('.tab[data-tab="interproscan"] > .button')
        .addEventListener('click', e => {
            const button = e.currentTarget;
            const segment = button.parentNode;
            segment.removeChild(button);

            const progressBar = document.querySelector('.tab[data-tab="interproscan"] > .ui.progress');
            setClass(progressBar, 'hidden', false);

            const content = segment.querySelector(':scope > .content');
            getInterProScanAnalyses(progressBar, 10000000)
                .then(() => {
                    setTimeout(() => {
                        segment.removeChild(progressBar);
                        setClass(content, 'hidden', false);

                        // Init checkboxes in "InterProScan" tab
                        $('[data-tab="interproscan"] .checkbox').checkbox({
                            onChange: function () {
                                plotJobTimeChart();
                            }
                        });

                        plotJobTimeChart();
                        plotJobMemoryChart();
                    }, 1000);
                });
        });
});
