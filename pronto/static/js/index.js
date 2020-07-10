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
                html += '<tr>'
                    + '<td style="border-left: 5px solid '+ database.color +';" class="collapsing">'
                    + '<a href="'+ database.link +'" target="_blank">'+ database.name +'<i class="external icon"></i></a>'
                    + '</td>'
                    + '<td><span class="ui basic label">'+ database.version +'<span class="detail">'+ database.date +'</span></span></td>'
                    + '<td><a href="/database/' + database.id + '/">'+ database.signatures.total.toLocaleString() +'</a></td>'
                    + '<td>'+ database.signatures.integrated.toLocaleString() +'</td>'
                    + '<td><a href="/database/' + database.id + '/unintegrated/">'+ (database.signatures.total-database.signatures.integrated).toLocaleString() +'</a></td>'
                    + '</tr>';
            }
            document.querySelector("#databases > tbody").innerHTML = html;
            resolve();
        });
    }));
}

function getRecentEntries() {
    return new Promise(((resolve, reject) => {
        fetch('/api/entries/')
        .then(response => response.json())
        .then(object => {
            let html = '';
            for (const entry of object.entries) {
                html += '<tr>'
                    + '<td><span class="ui circular mini label type '+entry.type+'">'+entry.type+'</span>'
                    + '<a href="/entry/'+entry.accession+'/">'+ entry.accession +'</a></td>'
                    + '<td>'+entry.short_name+'</td>'
                    + '<td>'+ entry.date +'</td>'
                    + '<td>'+ entry.author +'</td>'
                    + '<td>'+ entry.signatures +'</td>'
                    + '<td>'+ checkbox.createDisabled(entry.checked) +'</td>'
                    + '</tr>';
            }

            document.querySelector('#recent-entries tbody').innerHTML = html;

            const nEntries = object.entries.length;
            document.querySelector('#recent-entries > p').innerHTML = `<strong>${nEntries}</strong> ${nEntries > 1 ? 'entries' : 'entry'} created since <strong>${object.date}</strong>`;
            $('.message .close')
                .on('click', function() {
                    $(this)
                        .closest('.message')
                        .transition('fade');
                });
            resolve();
        });
    }));
}

document.addEventListener('DOMContentLoaded', () => {
    updateHeader();

    dimmer.on();
    Promise.all([getDatabases(), getRecentEntries()]).then(() => {dimmer.off();});
});
