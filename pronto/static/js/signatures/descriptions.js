import * as dimmer from "../ui/dimmer.js";
import {updateHeader} from "../ui/header.js";
import {selector} from "../ui/signatures.js";


function fetchAPI() {
    return new Promise(((resolve, reject) => {
        fetch('/api' + location.pathname + location.search)
            .then(response => {
                response.json()
                    .then(object => {
                        if (response.ok)
                            resolve(object);
                        else
                            reject(object.error);
                    });
            })
    }));
}

function getDescriptions(accessions, reviewOnly) {
    const params = reviewOnly ? '?reviewed&filtermatches' : '?filtermatches';

    dimmer.on();
    fetchAPI().then(
        (data,) => {
            let html = `<thead>
                        <tr>
                        <th>${data.results.length.toLocaleString()} descriptions</th>
                        ${accessions.map(acc => `<th><a target="_blank" href="/signatures/${acc}/proteins/${params}">${acc}</a></th>`).join('')}
                        </tr>
                        </thead>`;

            html += '<tbody>';
            for (const name of data.results) {
                html += `<tr><td>${name.value}</td>`;
                for (const acc of accessions) {
                    if (name.signatures.hasOwnProperty(acc))
                        html += `<td><a target="_blank" href="/signatures/${acc}/proteins/${params}&name=${name.id}">${name.signatures[acc].toLocaleString()}</a></td>`;
                    else
                        html += `<td></td>`;
                }
                html += '</tr>';
            }

            document.getElementById('results').innerHTML = html + '</tbody></table>';
            dimmer.off();
        },
        (error, ) => {
            // todo
            dimmer.off();
        }
    )
}


document.addEventListener('DOMContentLoaded', () => {
    const match = location.pathname.match(/\/signatures\/(.+)\/descriptions\/$/i);
    const accessions = match[1].split("/");
    document.title = "UniProt descriptions (" + accessions.join(", ") + ") | Pronto";

    selector.init(document.getElementById('signature-selector'));
    for (const accession of accessions) {
        selector.add(accession);
    }
    selector.render().tab("descriptions");

    const url = new URL(location.href);
    const checkbox = document.querySelector('input[type=checkbox][name=reviewed]');
    checkbox.checked = url.searchParams.has('reviewed');
    checkbox.addEventListener('change', e => {
        if (e.currentTarget.checked)
            url.searchParams.set('reviewed', '');
        else
            url.searchParams.delete('reviewed');

        history.replaceState(null, document.title, url.toString());
        getDescriptions(accessions, e.currentTarget.checked);
    });

    updateHeader();
    getDescriptions(accessions, checkbox.checked);
});
