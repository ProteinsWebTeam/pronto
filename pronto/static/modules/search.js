import {finaliseHeader} from "../header.js"
import * as ui from "../ui.js";

function renderHits(query, results) {
    const table = document.querySelector('table');
    let html = '';

    if (results.count) {
        results.hits.forEach(entry => {
            html += '<tr>' +
                '<td><span class="ui tiny type-'+ entry.type +' circular label">'+ entry.type +'</span>&nbsp;<a href="/entry/'+ entry.id +'/">'+ entry.id +'</a></td>' +
                '<td>'+ entry.name +'</td>' +
                '</tr>';
        });
    } else {
        html += '<tr><td colspan="2">No hits found by EBI Search</td></tr>';
    }

    table.querySelector('tbody').innerHTML = html;

    utils.paginate(
        table,
        results.page,
        results.pageSize,
        results.count,
        '/api/search/' + utils.encodeParams({q: query, nodb: null}, true),
        (url => {
            utils.dimmer(true);
            utils.getJSON(url, (results, status) => {
                renderHits(query, results.ebisearch);
                utils.dimmer(false);
            });
        })
    );
}


function callEBISearch(query, page, pageSize) {
    const url = new URL("https://www.ebi.ac.uk/ebisearch/ws/rest/interpro7");
    url.searchParams.set("query", query);
    url.searchParams.set("format", "json");
    url.searchParams.set("fields", "type,name,source_database");
    url.searchParams.set("start", (page-1)*pageSize);
    url.searchParams.set("size", pageSize);

    fetch(url.toString())
        .then(response => response.json())
        .then(result => {
            let html = "";
            if (result.hitCount) {
                result.entries.forEach(entry => {
                    const accession = entry.id;
                    const type = entry.fields.type[0].charAt(0).toUpperCase();
                    const database = entry.fields.source_database[0];
                    const name = entry.fields.name[0];
                    html += '<tr>'
                        + '<td>'
                        + '<span class="ui tiny circular label type-'+ type +'">'+ type +'</span>'
                        + '<a href="/'+ (database.toLowerCase() === "interpro" ? "entry" : "method") +'/'+ accession +'/">'+ accession +'</a>'
                        + '</td>'
                        + '<td>'+ database +'</td>'
                        + '<td>'+ name +'</td>'
                        + '</tr>';
                });
            } else {
                html = '<tr><td colspan="3">No hits found by EBI Search</td></tr>';
            }

            const table = document.querySelector("table");
            table.querySelector("tbody").innerHTML = html;
            ui.paginate(table, page, pageSize, result.hitCount, (newHref, ) => {
                const newURL = new URL(newHref);
                const newPage = Number(newURL.searchParams.get("page"));
                ui.dimmer(true);
                callEBISearch(query, newPage, pageSize);
            });
            ui.dimmer(false);
        });
}


$(function () {
    const query = new URL(location.href).searchParams.get("q");
    document.querySelector("header input[name=q]").value = query;

    finaliseHeader();
    ui.dimmer(true);
    fetch("/api" + location.pathname + location.search)
        .then(response => response.json())
        .then(result => {
            if (result.hit !== null) {
                // Direct hit from Pronto API
                const form = document.createElement("form");
                form.name = "nevergonnagiveyouup";  // ;)
                form.action = "/" + result.hit.type + "/" + result.hit.accession + "/";
                document.body.appendChild(form);
                document.nevergonnagiveyouup.submit();
            } else {
                // Fallback to EBI Search
                callEBISearch(query, 1, 20);
            }
        });
});