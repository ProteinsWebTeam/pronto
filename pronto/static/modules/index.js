import {finaliseHeader, getTasks} from "../header.js"


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
    fetch('/api/interpro/sanitychecks/')
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
                    + '<div class="meta"><a href="/interpro/sanitychecks/'+ res.id +'/"><i class="file text icon"></i> '+ res.errors +' errors.</a></div>'
                    + '</div>'
                    + '</div>';
            });

            document.querySelector('#sanity-checks .ui.feed').innerHTML = html;
        });
}


$(function () {
    finaliseHeader();

    fetch('/api/interpro/databases/')
        .then(response => response.json())
        .then(databases => {
            let html = '';
            databases.forEach(db => {
                html += '<tr>'
                    + '<td class="collapsing">'
                    + '<a target="_blank" href="'+ db.home +'">'+ db.name +'&nbsp;<i class="external icon"></i></a>'
                    + '</td>'
                    + '<td><span class="ui basic label">'+ db.version +'<span class="detail">'+ db.date +'</span></span></td>'
                    + '<td><a href="/database/' + db.short_name + '/">'+ db.count_signatures.toLocaleString() +'</a></td>'
                    + '<td>'+ db.count_integrated.toLocaleString() +'</td>'
                    + '<td><a href="/database/' + db.short_name + '/unintegrated/integrated/">'+ db.count_unintegrated.toLocaleString() +'</a></td>'
                    + '</tr>';
            });

            document.querySelector("#databases > tbody").innerHTML = html;
        });

    getReports();

    document.querySelector('#sanity-checks button.primary').addEventListener('click', evt => {
        fetch('/api/interpro/sanitychecks/', {method: 'PUT'})
            .then(response => {
                const elem = document.querySelector('#sanity-checks .message');
                if (response.ok) {
                    elem.className = 'ui success message';
                    elem.innerHTML = '<p>Task successfully submitted.</p>';
                    waitForTask();
                }
                else if (response.status === 401) {
                    elem.className = 'ui error message';
                    elem.innerHTML = '<p>Please <a href="/login/">log in</a> to perform this operation.</p>';
                }
                else if (response.status === 409) {
                    elem.className = 'ui error message';
                    elem.innerHTML = '<p>This task is already running.</p>';
                }

            })
    });
});