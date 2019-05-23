import {finaliseHeader} from "../header.js"
import * as ui from "../ui.js";

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
                        + '<a href="/'+ (database.toLowerCase() === "interpro" ? "entry" : "prediction") +'/'+ accession +'/">'+ accession +'</a>'
                        + '</td>'
                        + '<td>'+ database +'</td>'
                        + '<td>'+ name +'</td>'
                        + '</tr>';
                });
            } else {
                html = '<tr><td colspan="3" class="center aligned">No results found for <strong>'+ query +'</strong></td></tr>';
            }

            const table = document.querySelector("#search-results");
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
    const url = new URL(location.href);
    let query = url.searchParams.get("q");
    if (!query || !query.length) {
        query = "ESR1";
        url.searchParams.set("q", query);
        history.replaceState(null, null, url.toString());
    }

    document.querySelector("header input[name=q]").value = query;
    document.title = "Search '"+ query +"' | Pronto";

    finaliseHeader();
    ui.dimmer(true);
    fetch("/api/search/" + location.search)
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