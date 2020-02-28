import {finaliseHeader, getTasks} from "../header.js"
import {renderCheckbox} from "../ui.js";


function waitForTask() {
    const joinTask = () => {
        setTimeout(() => {
            getTasks().then(tasks => {
                if (tasks.find(t => t.name === "Sanity checks" && t.status !== null) === undefined)
                    joinTask();
                else {
                    getReports();
                    document.querySelector('#sanity-checks .message').className = "ui hidden message";
                }
            });
        }, 3000);
    };

    joinTask();
}


function getReports() {
    fetch(URL_PREFIX + '/api/sanitychecks/runs/')
        .then(response => response.json())
        .then(results => {
            let html = '';
            results.forEach(res => {
                html += '<div class="event">'
                    + '<div class="content">'
                    + '<div class="date">'+ res.date +'</div>'
                    + '<div class="summary">'
                    + '<a class="user">' + res.user + '</a> ran sanity checks'
                    + '</div>'
                    + '<div class="meta"><a href="'+URL_PREFIX+'/sanitychecks/runs/'+ res.id +'/"><i class="file text icon"></i> '+ res.errors +' errors.</a></div>'
                    + '</div>'
                    + '</div>';
            });

            document.querySelector('#sanity-checks .ui.feed').innerHTML = html;
        });
}


$(function () {
    finaliseHeader();

    fetch(URL_PREFIX+'/api/databases/')
        .then(response => response.json())
        .then(databases => {
            let html = '';
            databases.filter(db => db.short_name !== 'mobidblt').forEach(db => {
                html += '<tr>'
                    + '<td style="border-left: 5px solid '+ db.color +';" class="collapsing">'
                    + '<a target="_blank" href="'+ db.home +'">'+ db.name +'&nbsp;<i class="external icon"></i></a>'
                    + '</td>'
                    + '<td><span class="ui basic label">'+ db.version +'<span class="detail">'+ db.date +'</span></span></td>'
                    + '<td><a href="'+URL_PREFIX+'/database/' + db.short_name + '/">'+ db.count_signatures.toLocaleString() +'</a></td>'
                    + '<td>'+ db.count_integrated.toLocaleString() +'</td>'
                    + '<td><a href="'+URL_PREFIX+'/database/' + db.short_name + '/unintegrated/integrated/">'+ db.count_unintegrated.toLocaleString() +'</a></td>'
                    + '</tr>';
            });

            document.querySelector("#databases > tbody").innerHTML = html;
        });

    getReports();

    document.querySelector('#sanity-checks button.primary').addEventListener('click', evt => {
        fetch(URL_PREFIX+'/api/sanitychecks/runs/', {method: 'PUT'})
            .then(response => {
                const elem = document.querySelector('#sanity-checks .message');
                if (response.ok) {
                    elem.className = 'ui success message';
                    elem.innerHTML = '<p>Task successfully submitted.</p>';
                    waitForTask();
                }
                else if (response.status === 401) {
                    elem.className = 'ui error message';
                    elem.innerHTML = '<p>Please <a href="'+URL_PREFIX+'/login/">log in</a> to perform this operation.</p>';
                }
                else if (response.status === 409) {
                    elem.className = 'ui error message';
                    elem.innerHTML = '<p>This task is already running.</p>';
                }

            })
    });

    fetch(URL_PREFIX+'/api/signatures/integrations/')
        .then(response => response.json())
        .then(response => {
            document.getElementById('recent-integrations').innerHTML = '<strong>'+ response.results.length +'</strong> signatures integrated since <strong>'+ response.date +'</strong>.';
        });

    fetch(URL_PREFIX+'/api/entries/')
        .then(response => response.json())
        .then(response => {
            const div = document.getElementById('recent-entries');
            div.querySelector('.title').innerHTML = '<i class="dropdown icon"></i> ' + response.results.length + ' entries recently created';

            let table = '<table class="ui compact table"><thead><tr><th><th>Accession</th><th>Short name</th><th>Creation date</th><th>Author</th><th>Signatures</th><th>Checked</th></tr></thead><tbody>';

            for (const entry of response.results) {
                table += '<tr>'
                    + '<td><span class="ui circular mini label type-'+entry.type+'">'+entry.type+'</span></td>'
                    + '<td><a href="'+ URL_PREFIX +'/entry/'+entry.accession+'/">'+ entry.accession +'</a></td>'
                    + '<td>'+entry.short_name+'</td>' + '<td>'+ entry.date +'</td>'
                    + '<td>'+ entry.author +'</td>'
                    + '<td>'+ entry.num_signatures +'</td>'
                    /*
                    Disable checkboxes (1st arg is null) to force curators
                    to go on the entry page to check/uncheck entries
                     */
                    + '<td>'+ renderCheckbox(null, entry.checked) +'</td>'
                    + '</tr>';
            }

            table += '</tbody></table>';
            div.querySelector('.content').innerHTML = table;

            $(div).accordion();
        });
});