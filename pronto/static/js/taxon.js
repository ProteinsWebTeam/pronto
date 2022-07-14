import {waitForTask} from "./tasks.js";
import {initSignaturePopups} from "./ui/comments.js";
import {renderTaskList, updateHeader} from "./ui/header.js";
import {setClass} from "./ui/utils.js";
import * as dimmer from "./ui/dimmer.js";

async function getTaxon(taxonId) {
    dimmer.on();
    const response = await fetch(`/api/taxon/${taxonId}/`);
    const result = await response.json();

    const message = document.getElementById('main-message');
    let enableButton = false;

    if (!result.status) {
        // Taxon does not exist
        message.innerHTML = `
            <div class="header">${result.error.title}</div>
            <p>${result.error.message}</p>
        `;
        message.className = 'ui error message';
        dimmer.off();
        return ;
    }

    if (result.task === null) {
        // Never run
        message.innerHTML = `
            <div class="header">No coverage data for <em>${result.name}</em></div>
            <p>A taxon with ID:${taxonId} has been found, but no coverage data has been calculated yet. Click on the button below to start calculating the coverage.</p>
        `;
        message.className = 'ui info message';
        enableButton = true;
    } else if (result.task.end_time === null) {
        waitForResults(result.task.id);
    } else if (result.task.success) {
        // Success
        message.className = 'ui hidden message';
        enableButton = true;
        renderResults(result.task);
    } else {
        // Failed
        message.innerHTML = `
            <div class="header">Header</div>
            <p>Text</p>
        `;
        message.className = 'ui error message';
        enableButton = true;
    }

    const button = document.getElementById('submit-task');
    button.dataset.id = taxonId;
    setClass(button, 'disabled', !enableButton);
    dimmer.off();
}

async function submitTask(taxonId) {
    document.getElementById('submit-task').disabled = true;

    const response = await fetch(`/api/taxon/${taxonId}/?lowernodes`, {method: 'PUT'});
    const result = await response.json();
    const message = document.getElementById('main-message');

    if (result.status)
        await waitForResults(result.task.id);
    else {
        message.innerHTML = `
            <div class="header">${result.error.title}</div>
            <p>${result.error.message}</p>
        `;
        message.className = 'ui error message';
    }

    document.getElementById('submit-task').disabled = false;
}

async function waitForResults(taskId) {
    const message = document.getElementById('main-message');
    message.className = 'ui icon info message';
    message.innerHTML = `
        <i class="notched circle loading icon"></i>
        <div class="content">
            <div class="header">Task in progress</div>
            <p>The coverage is being calculated. When complete, results will be displayed below.</p>
        </div>
    `;

    // Update task list
    renderTaskList();

    // Wait for task to complete
    const task = await waitForTask(taskId);
    if (task.success) {
        message.className = 'ui success message';
        message.innerHTML = `
            <div class="header">Task complete</div>
            <p>The coverage has been successfully calculated. Results will be displayed in a few seconds.</p>
        `;

        setTimeout(renderResults, 3000, task);
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

function renderResults(task) {
    const reg = /^(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)$/;
    let m = reg.exec(task.start_time);
    const startTime = new Date(
        Number.parseInt(m[1], 10),
        Number.parseInt(m[2], 10) - 1,
        Number.parseInt(m[3], 10),
        Number.parseInt(m[4], 10),
        Number.parseInt(m[5], 10),
        Number.parseInt(m[6], 10)
    )

    const data = task.result;
    const resultsElem = document.getElementById('results');

    resultsElem.querySelector('h2.ui.header').innerHTML = `
        <em>${data.name}</em>
        <div class="sub header">
            Date: ${startTime.toLocaleString('en-GB', {
        day: 'numeric',
        year: 'numeric',
        month: 'short',
        hour: 'numeric',
        minute: 'numeric'
    })}
        </div>  
    `;

    let html = '';
    if ((new Date() - startTime) / 1000 / 3600 / 24 >= 30) {
        html += `
            <div class="ui warning message">
                <div class="header">Results possibly outdated</div>
                <p>
                    These results are over a month old. UniProt and several member databases may have been updated in the meantime, and many signatures may have been integrated or unintegrated.
                </p>
            </div>
        `;
    }

    const databases = new Map();
    const signatures = data.signatures
        .sort((a, b) => {
            let d = b.proteins.unintegrated_reviewed - a.proteins.unintegrated_reviewed;
            if (d !== 0)
                return d;

            d = b.proteins.unintegrated_all - a.proteins.unintegrated_all;
            if (d !== 0)
                return d;

            return a.name.localeCompare(b.name);
        })
        .map(item => {
            const key = item.database.name;
            if (databases.has(item.database.name))
                databases.get(key).count += 1;
            else
                databases.set(key, { name: key, color: item.database.color, count: 1 });

            return item;
        });

    let menu = '';
    [...databases.values()]
        .sort((a, b) => a.name.localeCompare(b.name))
        .forEach(item => {
            menu += `
                <a data-database="${item.name}" class="item" style="border-left: 2px solid ${item.color};">
                    ${item.name}
                    <div class="ui label">${item.count}</div>
                </a>
            `;
        });

    let dbName = null;
    let minIncr = 0;
    const coverageAll = data.proteins.all > 0 ? data.proteins.integrated_all * 100 / data.proteins.all : 0;
    const coverageRev = data.proteins.reviewed > 0 ? data.proteins.integrated_reviewed * 100 / data.proteins.reviewed : 0;
    const genTableBody = () => {
        let tbody = '';
        signatures.forEach(item => {
            if (dbName !== null && item.database.name !== dbName)
                return;

            const newCov = data.proteins.all > 0 ? (data.proteins.integrated_all + item.proteins.unintegrated_all) * 100 / data.proteins.all : 0;
            if (newCov < coverageAll + minIncr)
                return;

            let btn = '';
            if (item.comments > 0)
                btn = `
                    <a class="ui small basic label" data-accession="${item.accession}">
                        <i class="comments icon"></i>${item.comments}
                    </a>
                `;

            tbody += `
                <tr>
                    <td><a href="/signature/${item.accession}/">${item.accession}</a></td>
                    <td>${item.name !== item.accession ? item.name : ''}</td>
                    <td class="collapsing">${btn}</td>
                    <td class="right aligned">${item.proteins.total_all.toLocaleString()}</td>
                    <td class="right aligned">${item.proteins.total_reviewed.toLocaleString()}</td>
                    <td class="right aligned">${item.proteins.unintegrated_all.toLocaleString()}</td>
                    <td class="right aligned">${item.proteins.unintegrated_reviewed.toLocaleString()}</td>
                </tr>
            `;

        });

        return tbody.length > 0 ? tbody : '<tr><td colspan="7" class="center aligned">No signatures</td></tr>';
    };

    html += `
        <div class="ui relaxed horizontal list">
            <div class="item">
                <div class="content">
                    <div class="header">${data.proteins.all.toLocaleString()}</div>
                    <div class="description">proteins</div>
                </div>
            </div>
            <div class="item">
                <div class="content">
                    <div class="header">${coverageAll.toFixed(2)}%</div>
                    <div class="description">in InterPro</div>
                </div>
            </div>
            <div class="item">
                <div class="content">
                    <div class="header">${data.proteins.reviewed.toLocaleString()}</div>
                    <div class="description">reviewed proteins</div>
                </div>
            </div>
            <div class="item">
                <div class="content">
                    <div class="header">${coverageRev.toFixed(2)}%</div>
                    <div class="description">in InterPro</div>
                </div>
            </div>
            <div class="item">
                <div class="content">
                    <div class="header">${data.signatures.length.toLocaleString()}</div>
                    <div class="description">unintegrated signatures</div>
                </div>
            </div>
            <!--<div class="item">
                <div class="content">
                    <div class="header">
                        <div class="ui fitted checkbox">
                            <input id="only-worth" type="checkbox">
                            <label></label>
                        </div>                    
                    </div>
                    <div class="description">
                        worth integrating only
                        <span data-tooltip="Only shows signatures whose integration would increase the coverage by at least ${minIncr}%.">
                            <i class="question circle icon"></i>
                        </span>
                    </div>
                </div>
            </div>-->
        </div>
        <div class="ui grid">
            <div class="row">
                <div class="four wide column">
                    <div class="ui fluid vertical menu">
                        <a data-database="" class="active item" style="border-left: 2px solid rgba(34, 36, 38, 0.15);">
                            All
                            <div class="ui label">${signatures.length}</div>
                        </a>
                        ${menu}
                    </div>
                </div>
                <div class="twelve wide column">
                    <table class="ui single line table">
                        <thead>
                            <tr class="center aligned">
                                <th rowspan="2">Accession</th>
                                <th rowspan="2">Name</th>
                                <th rowspan="2" class="collapsing"></th>
                                <th colspan="2">Proteins (all clades)</th>
                                <th colspan="2">Unintegrated proteins</th>
                            </tr>
                            <tr class="center aligned">
                                <th class="right aligned">UniProtKB</th>
                                <th class="right aligned">Swiss-Prot</th>
                                <th class="right aligned">UniProtKB</th>
                                <th class="right aligned">Swiss-Prot</th>
                            </tr>
                        </thead>            
                        <tbody>
                            ${genTableBody()}
                        </tbody>        
                    </table>
                </div>
            </div>
        </div>
    `;

    resultsElem.querySelector('.sixteen.wide.column').innerHTML = html;
    initSignaturePopups(resultsElem);

    for (let elem of resultsElem.querySelectorAll('a[data-database]')) {
        elem.addEventListener('click', event => {
            resultsElem.querySelector('a[data-database].active').className = 'item';
            event.currentTarget.className = 'active item';

            const value = event.currentTarget.dataset.database;
            dbName = value !== null && value.length !== 0 ? value : null;
            const tbody = resultsElem.querySelector('tbody');
            tbody.innerHTML = genTableBody();
            initSignaturePopups(tbody);
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    updateHeader();

    const params = new URLSearchParams(location.search);
    if (params.has('id')) {
        getTaxon(params.get('id'));
    }

    document.getElementById('submit-task').addEventListener('click', event => {
        const button = event.currentTarget;
        submitTask(button.dataset.id);
    });

    const useCategories = true;
    const maxResults = 8;
    $('.ui.search')
        .search({
            type: useCategories ? 'category' : 'standard',

            // change search endpoint to a custom endpoint by manipulating apiSettings
            apiSettings: {
                url: '/api/taxon/search/?q={query}',
                onResponse: (response) => {
                    // Sort items by name
                    const items = response.items.sort((a, b) => a.name.localeCompare(b.name));

                    // Function to format results
                    const serverToFomantic = (item) => ({
                        id: item.id,
                        title: item.name,
                        description: item.rank === 'no rank' ? '' : item.rank,
                        url: `/taxon?id=${item.id}`
                    });

                    if (! useCategories)
                        return { results: items.map(serverToFomantic) };

                    const categories = new Map();
                    items.forEach((item, index) => {
                        if (index >= maxResults)
                            return;

                        const key = item.superkingdom;
                        if (categories.has(key))
                            categories.get(key).results.push(serverToFomantic(item));
                        else
                            categories.set(key, {
                                name: key,
                                results: [serverToFomantic(item)]
                            });
                    });

                    return { results: Object.fromEntries(categories) };
                }
            },
            maxResults: maxResults,
            cache: false,
            searchDelay: 300
        });
});