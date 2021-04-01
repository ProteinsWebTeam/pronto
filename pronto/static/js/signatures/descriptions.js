import * as dimmer from "../ui/dimmer.js";
import {updateHeader} from "../ui/header.js";
import {selector, showProteinsModal} from "../ui/signatures.js";



function getDescriptions(accessions) {
    dimmer.on();

    fetch(`/api${location.pathname}${location.search}`)
        .then(response => response.json())
        .then((data,) => {
                const sig2ipr = new Map(Object.entries(data.integrated));
                const genCell = (acc,) => {
                    if (sig2ipr.has(acc))
                        return `<th class="center aligned"><a href="#!" data-signature="${acc}" data-tooltip="${sig2ipr.get(acc)}" data-inverted=""><i class="star icon"></i>${acc}</a></th>`;
                    else
                        return `<th class="center aligned"><a href="#!" data-signature="${acc}"><i class="star outline icon"></i>${acc}</a></th>`;
                };

                let html = `<thead>
                        <tr>
                        <th>${data.results.length.toLocaleString()} descriptions</th>
                        ${accessions.map(genCell).join('')}
                        </tr>
                        </thead>`;

                html += '<tbody>';
                for (const name of data.results) {
                    html += `<tr><td>${name.value}</td>`;
                    for (const acc of accessions) {
                        if (name.signatures.hasOwnProperty(acc))
                            html += `<td><a href="#!" data-signature="${acc}" data-name="${name.id}">${name.signatures[acc].toLocaleString()}</a></td>`;
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
                        const name = e.currentTarget.dataset.name;

                        const params = [];
                        if ((new URLSearchParams(location.search).has('reviewed')))
                            params.push('reviewed');

                        let showMatches = false;
                        if (name !== undefined && name.length > 0) {
                            params.push(`name=${name}`);
                            showMatches = true;
                        }

                        showProteinsModal(acc, params, showMatches);
                    });
                }

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
        getDescriptions(accessions);
    });

    updateHeader();
    getDescriptions(accessions);
});
