import {finaliseHeader, getTasks} from "../header.js"


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

    document.querySelector('#sanity-checks button.primary').addEventListener('click', evt => {
        fetch('/api/sanitychecks/')
            .then(response => {
                const elem = document.querySelector('#sanity-checks .message');
                if (response.ok) {
                    getTasks();
                    elem.className = 'ui success message';
                    elem.innerHTML = '<p>Task successfully submitted.</p>';
                }
                else {
                    elem.className = 'ui error message';
                    elem.innerHTML = '<p>This task is already running.</p>';
                }
            })
            // .then(response => response.json())
            // .then(result => {
            //
            // });
    });
});