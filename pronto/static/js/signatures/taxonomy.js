import * as dimmer from "../ui/dimmer.js";
import {updateHeader} from "../ui/header.js";
import {selector} from "../ui/signatures.js";


function fetchAPI() {
    dimmer.on();
    return new Promise(((resolve, reject) => {
        fetch('/api' + location.pathname + location.search)
            .then(response => {
                response.json()
                    .then(object => {
                        if (response.ok)
                            resolve(object);
                        else
                            reject(object.error);
                        dimmer.off()
                    });
            })
    }));
}


function getTaxonomyCounts(accessions, rank) {
    const tabs = document.querySelectorAll('[data-rank]');
    for (const tab of tabs) {
        if (tab.dataset.rank === rank)
            tab.className = 'active item';
        else
            tab.className = 'item';
    }

    fetchAPI()
        .then(
            (data,) => {
                let html = `<thead>
                            <tr>
                            <th>${data.taxon.id === null ? '' : `<div class="ui basic label">${data.taxon.name}<i class="delete icon"></i></div>`}</th>
                            ${accessions.map(acc => `<th>${acc}</th>`).join('')}
                            </tr>
                            </thead>
                            <tbody>`;


                for (const node of data.results) {
                    html += `<tr><td><a href="#!" data-id="${node.id}">${node.name}</a></td>`;

                    for (const acc of accessions) {
                        if (node.signatures.hasOwnProperty(acc))
                            html += `<td><a target="_blank" href="/signatures/${acc}/proteins/?taxon=${node.id}">${node.signatures[acc].toLocaleString()}</a></td>`;
                        else
                            html += '<td></td>';
                    }
                }

                const table = document.getElementById('results');
                table.innerHTML = html + '</tbody>';

                for (const elem of table.querySelectorAll('[data-id]')) {
                    elem.addEventListener('click', e => {
                        e.preventDefault();
                        const url = new URL(location.href);
                        url.searchParams.set('taxon', e.currentTarget.dataset.id);
                        history.replaceState(null, document.title, url.toString());
                        getTaxonomyCounts(accessions, rank);
                    });
                }

                const icon = table.querySelector('thead .ui.label i.delete.icon');
                if (icon) {
                    icon.addEventListener('click', e => {
                        const url = new URL(location.href);
                        url.searchParams.delete('taxon');
                        history.replaceState(null, document.title, url.toString());
                        getTaxonomyCounts(accessions, rank);
                    });
                }

            },
            (error,) => {
                console.error(error);  // todo
            }
        );
}


document.addEventListener('DOMContentLoaded', () => {
    const match = location.pathname.match(/\/signatures\/(.+)\/taxonomy\/(\w+)\/$/i);
    const accessions = match[1].split("/");
    const rank = match[2];
    document.title = "Taxonomic origins (" + accessions.join(", ") + ") | Pronto";

    selector.init(document.getElementById('signature-selector'));
    for (const accession of accessions) {
        selector.add(accession);
    }
    selector.render().tab("taxonomy");

    updateHeader();

    for (const tab of document.querySelectorAll('[data-rank]')) {
        tab.addEventListener('click', e => {
            const url = new URL(location.href);

            const rank = tab.dataset.rank;
            const newURL = new URL(`/signatures/${accessions.join('/')}/taxonomy/${rank}/`, location.origin);

            if (url.searchParams.has('taxon'))
                newURL.searchParams.set('taxon', url.searchParams.get('taxon'));

            history.replaceState(null, document.title, newURL.toString());
            getTaxonomyCounts(accessions, rank);
        });
    }

    getTaxonomyCounts(accessions, rank);
});
