import * as checkbox from './ui/checkbox.js'
import * as dimmer from "./ui/dimmer.js"
import {updateHeader} from "./ui/header.js"

function getDatabases() {
    return new Promise(((resolve, reject) => {
        fetch('/api/databases/')
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
                document.querySelector('.segment[data-tab="databases"] tbody').innerHTML = html;
                resolve();
            });
    }));
}

function getRecentEntries() {
    return new Promise(((resolve, reject) => {
        fetch('/api/entries/news/')
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

                const tab = document.querySelector('.segment[data-tab="recent-entries"]');
                tab.querySelector('tbody').innerHTML = html;
                tab.querySelector(':scope > p').innerHTML = `<strong>${object.entries.length}</strong> ${object.entries.length > 1 ? 'entries' : 'entry'} created since <strong>${object.date}</strong>.`;

                document.querySelector('.item[data-tab="recent-entries"] .label').innerHTML = object.entries.length.toString();
                resolve();
            });
    }));
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

            const tab = document.querySelector('.segment[data-tab="unchecked-entries"]');
            tab.querySelector('tbody').innerHTML = html;

            document.querySelector('.item[data-tab="unchecked-entries"] .label').innerHTML = entries.length.toString();
        });
}

document.addEventListener('DOMContentLoaded', () => {
    updateHeader();

    dimmer.on();
    const promises = [
        getDatabases(),
        getRecentEntries(),
        getUncheckedEntries()
    ];

    Promise.all(promises)
        .then(() => {
            $(document.querySelectorAll('.message .close'))
                .on('click', function() {
                    $(this)
                        .closest('.message')
                        .transition('fade');
                });

            $('.tabular.menu .item').tab();
            dimmer.off();
        });
});
