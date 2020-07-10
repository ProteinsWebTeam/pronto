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

function getComments(accessions) {
    dimmer.on();
    fetchAPI().then(
        (data,) => {
            let html = `<thead>
                        <tr>
                        <th>${data.results.length.toLocaleString()} comments</th>
                        ${accessions.map(acc => `<th>${acc}</th>`).join('')}
                        </tr>
                        </thead>`;

            html += '<tbody>';
            for (const comment of data.results) {
                html += `<tr><td>${comment.value}</td>`;
                for (const acc of accessions) {
                    if (comment.signatures.hasOwnProperty(acc))
                        html += `<td><a target="_blank" href="/signatures/${acc}/proteins/?comment=${comment.id}">${comment.signatures[acc].toLocaleString()}</a></td>`;
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
    const match = location.pathname.match(/\/signatures\/(.+)\/comments\/$/i);
    const accessions = match[1].split("/");
    document.title = "Similarity comments (" + accessions.join(", ") + ") | Pronto";

    selector.init(document.getElementById('signature-selector'));
    for (const accession of accessions) {
        selector.add(accession);
    }
    selector.render().tab("comments");

    updateHeader();
    getComments(accessions);
});
