import {updateHeader} from "./ui/header.js"
import {render} from "./ui/pagination.js"
import * as dimmer from "./ui/dimmer.js"


async function callEBISearch(query, page, pageSize) {
    const url = new URL("https://www.ebi.ac.uk/ebisearch/ws/rest/interpro7");
    url.searchParams.set("query", query);
    url.searchParams.set("format", "json");
    url.searchParams.set("fields", "type,name,source_database");
    url.searchParams.set("start", ((page - 1) * pageSize).toString());
    url.searchParams.set("size", pageSize.toString());

    dimmer.on();
    const response = await fetch(url.toString());
    dimmer.off();

    let html = "";
    let hitCount = 0;
    if (response.ok) {
        const result = await response.json();
        hitCount = result.hitCount;
        if (hitCount) {
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
        }
    }

    if (html.length === 0)
        html = `<tr><td colspan="3" class="center aligned">No results found for <strong>${query}</strong></td></tr>`;

    const table = document.querySelector("#results");
    table.querySelector("tbody").innerHTML = html;
    render(
        table,
        page,
        pageSize,
        hitCount,
        (newURL,) => {
            const params = new URL(newURL).searchParams;
            const newPage = Number(params.get("page"));
            callEBISearch(query, newPage, pageSize);
        }
    );
}


document.addEventListener('DOMContentLoaded', () => {
    updateHeader();

    const query = new URLSearchParams(location.search).get('q') || '';

    dimmer.on();
    fetch(`/api/search/?q=${query}`)
        .then(response => response.json())
        .then(payload => {
            if (payload.results.length === 1) {
                // Direct hit from Pronto API
                const hit = payload.results[0];
                const form = document.createElement("form");
                form.name = "redirectform";
                form.action = `/${hit.type}/${hit.accession}/`;
                document.body.appendChild(form);
                document.redirectform.submit();
            } else if (payload.results.length > 1) {
                let html = "";
                payload.results.forEach((item,) => {
                    html += `<tr>
                               <td><a href="/${item.type}/${item.accession}/">${item.accession}</a></td>
                               <td>${item.database}</td>
                               <td>${item.description}</td>
                             </tr>`;
                });
                document.querySelector("#results tbody").innerHTML = html;
                dimmer.off();
            } else {
                // Fallback to EBI Search
                callEBISearch(query, 1, 20);
            }
        });
});
