import * as dimmer from "../ui/dimmer.js";
import {updateHeader} from "../ui/header.js";
import {selector, showProteinsModal} from "../ui/signatures.js";



function getDescriptions(accessions) {
    dimmer.on();

    fetch(`/api${location.pathname}${location.search}`)
        .then(response => response.json())
        .then((data,) => {
                let html = `<thead>
                        <tr>
                        <th>${data.results.length.toLocaleString()} descriptions</th>
                        ${accessions.map(acc => `<th><a href="#!" data-signature="${acc}">${acc}</a></th>`).join('')}
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
