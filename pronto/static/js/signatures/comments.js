import * as dimmer from "../ui/dimmer.js";
import {updateHeader} from "../ui/header.js";
import {selector, showProteinsModal} from "../ui/signatures.js";

function getComments(accessions) {
    dimmer.on();
    fetch('/api' + location.pathname + location.search)
        .then(response => response.json())
        .then((data,) => {
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
                        html += `<td><a href="#!" data-signature="${acc}" data-comment="${comment.id}">${comment.signatures[acc].toLocaleString()}</a></td>`;
                    else
                        html += `<td></td>`;
                }
                html += '</tr>';
            }

            const table = document.getElementById('results');
            table.innerHTML = html + '</tbody>';

            for (const elem of table.querySelectorAll('[data-signature]')) {
                elem.addEventListener('click', e => {
                    const acc = e.currentTarget.dataset.signature;
                    const comment = e.currentTarget.dataset.comment;
                    showProteinsModal(acc, [`comment=${comment}`], true);
                });
            }

            dimmer.off();
        });
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
