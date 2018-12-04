import {finaliseHeader} from "../header.js"


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
                    + '<td><a href="/database/' + db.short_name + '/unintegrated/">'+ db.count_unintegrated.toLocaleString() +'</a></td>'
                    + '</tr>';
            });

            document.querySelector("table > tbody").innerHTML = html;
        });
});