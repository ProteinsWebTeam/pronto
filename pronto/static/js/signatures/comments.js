import * as dimmer from "../ui/dimmer.js";
import {updateHeader} from "../ui/header.js";
import {selector, showProteinsModal} from "../ui/signatures.js";

function getComments(accessions) {
    dimmer.on();
    fetch('/api' + location.pathname + location.search)
        .then(response => response.json())
        .then((data,) => {
            const sig2ipr = new Map(Object.entries(data.integrated));
            const genCell = (acc,) => {
                if (sig2ipr.has(acc))
                    return `<th class="center aligned"><span data-tooltip="${sig2ipr.get(acc)}" data-inverted=""><i class="star icon"></i>${acc}</span></th>`;
                else
                    return `<th class="center aligned"><i class="star outline icon"></i>${acc}</th>`;
            };

            let html = `<thead>
                        <tr>
                        <th>${data.results.length.toLocaleString()} comments</th>
                        ${accessions.map(genCell).join('')}
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
                    showProteinsModal(acc, [`comment=${comment}`], true, accessions);
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
