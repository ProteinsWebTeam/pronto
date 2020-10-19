import {updateHeader} from "./ui/header.js"
import {render} from "./ui/pagination.js"
import * as dimmer from "./ui/dimmer.js"


function callEBISearch(query, page, pageSize) {
    const url = new URL("https://www.ebi.ac.uk/ebisearch/ws/rest/interpro7");
    url.searchParams.set("query", query);
    url.searchParams.set("format", "json");
    url.searchParams.set("fields", "type,name,source_database");
    url.searchParams.set("start", (page-1)*pageSize);
    url.searchParams.set("size", pageSize);

    dimmer.on();
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
                    html += `<tr>
                               <td>
                                 <span class="ui tiny circular label type ${type}">${type}</span>
                                 <a href="/${database.toLowerCase() === 'interpro' ? 'entry' : 'signature'}/${accession}/">${accession}</a>
                               </td>
                               <td>${database}</td>
                               <td>${name}</td>
                             </tr>`;
                });
            } else {
                html = `<tr><td colspan="3" class="center aligned">No results found for <strong>${query}</strong></td></tr>`;
            }

            const table = document.querySelector("#results");
            table.querySelector("tbody").innerHTML = html;
            render(
                table,
                page,
                pageSize,
                result.hitCount,
                (newURL,) => {
                    const params = new URL(newURL).searchParams;
                    const newPage = Number(params.get("page"));
                    callEBISearch(query, newPage, pageSize);
                }
            );
            dimmer.off();
        });
}


document.addEventListener('DOMContentLoaded', () => {
    updateHeader();

    const query = new URLSearchParams(location.search).get('q') || '';

    dimmer.on();
    fetch(`/api/search?q=${query}`)
        .then(response => response.json())
        .then(result => {
            if (result.hit !== null) {
                // Direct hit from Pronto API
                const form = document.createElement("form");
                form.name = "redirectform";
                form.action = `/${result.hit.type}/${result.hit.accession}/`;
                document.body.appendChild(form);
                document.redirectform.submit();
            } else {
                // Fallback to EBI Search
                callEBISearch(query, 1, 20);
            }
        });
});
