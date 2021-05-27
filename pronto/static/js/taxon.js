import {waitForTask} from "./tasks.js";
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
            <p>A taxon with ID:${taxonId} has been found, but no coverage data is available. Click on the button above to start calculating the coverage.</p>
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
    const response = await fetch(`/api/taxon/${taxonId}/?lowernodes`, {method: 'PUT'});
    const result = await response.json();
    const message = document.getElementById('main-message');

    if (!result.status) {
        message.innerHTML = `
            <div class="header">${result.error.title}</div>
            <p>${result.error.message}</p>
        `;
        message.className = 'ui error message';
        return;
    }

    waitForResults(result.task.id);
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
    let html = `
        <h2 class="ui header">
            ${data.name}
            <div class="sub header">
                Date: ${startTime.toLocaleString('en-GB', { 
                    day: 'numeric', 
                    year: 'numeric', 
                    month: 'short',  
                    hour: 'numeric', 
                    minute: 'numeric'
                })}
            </div>
        </h2>    
    `;
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

    const getCoverage = (obj) => (obj.integrated * 100 / obj.total);
    const minIncr = 0.005;  // coverage must increase by at least <minIncr>%
    const minCov = getCoverage(data.proteins) + minIncr;
    const databases = new Map();
    const signatures = data.signatures
        .filter((item) => {
            const newCov = (data.proteins.integrated + item.proteins.total) * 100 / data.proteins.total;
            return newCov >= minCov;
        })
        .sort((a, b) => {
            let d = b.proteins.total - a.proteins.total;
            if (d !== 0)
                return d;

            d = b.proteins.reviewed - a.proteins.reviewed;
            if (d !== 0)
                return d;

            return a.name.localeCompare(b.name);
        }).map(item => {
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

    const genTableBody = (dbName = null) => {
        let tbody = '';
        signatures.forEach(item => {
            if (dbName !== null && item.database.name !== dbName)
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
                    <td><a href="/signatures/${item.accession}/proteins/?taxon=${data.id}">${item.accession}</a></td>
                    <td>${item.name !== item.accession ? item.name : ''}</td>
                    <td class="collapsing">${btn}</td>
                    <td class="right aligned">${item.proteins.total.toLocaleString()}</td>
                    <td class="right aligned">${item.proteins.reviewed.toLocaleString()}</td>
                </tr>
            `;

        });

        return tbody;
    };

    html += `
        <div class="ui relaxed horizontal list">
            <div class="item">
                <div class="content">
                    <div class="header">${data.proteins.total.toLocaleString()}</div>
                    <div class="description">proteins with signature matches</div>
                </div>
            </div>
            <div class="item">
                <div class="content">
                    <div class="header">${getCoverage(data.proteins).toFixed(2)}%</div>
                    <div class="description">in InterPro</div>
                </div>
            </div>
            <div class="item">
                <div class="content">
                    <div class="header">${data.proteins.reviewed.total.toLocaleString()}</div>
                    <div class="description">reviewed proteins with signature matches</div>
                </div>
            </div>
            <div class="item">
                <div class="content">
                    <div class="header">${getCoverage(data.proteins.reviewed).toFixed(2)}%</div>
                    <div class="description">in InterPro</div>
                </div>
            </div>
            <div class="item">
                <div class="content">
                    <div class="header">${data.signatures.length.toLocaleString()}</div>
                    <div class="description">unintegrated signatures</div>
                </div>
            </div>
            <div class="item">
                <div class="content">
                    <div class="header">${signatures.length.toLocaleString()}</div>
                    <div class="description">worth integrating
                        <span data-tooltip="Integrating a signature will increase the coverage by at least ${minIncr}%.">
                            <i class="question circle icon"></i>
                        </span>
                    </div>
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
                                <th colspan="2">Unintegrated proteins</th>
                            </tr>
                            <tr class="center aligned">
                                <th class="right aligned">Total</th>
                                <th class="right aligned">Reviewed</th>
                            </tr>
                        </thead>            
                        <tbody>
                            ${genTableBody(null)}
                        </tbody>        
                    </table>
                </div>
            </div>
        </div>
    `;

    const initPopups = (root) => {
        $(root.querySelectorAll('a.label[data-accession]'))
            .popup({
                exclusive: true,
                hoverable: true,
                html: '<i class="notched circle loading icon"></i> Loading&hellip;',
                position: 'left center',
                variation: 'small basic custom',
                onShow: function (elem) {
                    const popup = this;
                    const acc = elem.dataset.accession;
                    fetch(`/api/signature/${acc}/comments/`)
                        .then(response => response.json())
                        .then(payload => {
                            let html = '<div class="ui small comments">';
                            for (let item of payload.results) {
                                if (!item.status)
                                    continue;

                                html += `
                                    <div class="comment">
                                        <a class="author">${item.author}</a>
                                        <div class="metadata"><span class="date">${item.date}</span></div>
                                        <div class="text">${item.text}</div>
                                    </div>
                                `;
                            }
                            popup.html(html + '</div>');
                        });
                }
            });
    };

    const resultsElem = document.getElementById('results');
    resultsElem.innerHTML = html;
    initPopups(resultsElem);

    for (let elem of resultsElem.querySelectorAll('a[data-database]')) {
        elem.addEventListener('click', event => {
            resultsElem.querySelector('a[data-database].active').className = 'item';
            event.currentTarget.className = 'active item';

            const value = event.currentTarget.dataset.database;
            const dbName = value !== null && value.length !== 0 ? value : null;
            const tbody = resultsElem.querySelector('tbody');
            tbody.innerHTML = genTableBody(dbName);
            initPopups(tbody);
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
        button.disabled = true;
        submitTask(button.dataset.id);
    });

    $('.ui.search')
        .search({
            // change search endpoint to a custom endpoint by manipulating apiSettings
            apiSettings: {
                url: '/api/taxon/search/?q={query}',
                onResponse: (response) => {
                    const items = response.items;
                    return {
                        results: items.map(item => ({
                            id: item.id,
                            title: item.name,
                            description: item.rank,
                            url: `/taxon?id=${item.id}`
                        }))
                    };
                }
            },
            cache: false,
            searchDelay: 300
        });
});