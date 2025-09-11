import * as dimmer from "../ui/dimmer.js";
import { updateHeader } from "../ui/header.js";
import { selector } from "../ui/signatures.js";


function getMatrices(accessions) {
    dimmer.on();
    fetch('/api' + location.pathname + location.search)
        .then(response => response.json())
        .then((results,) => {
            const thead = `<thead><tr><th></th>${accessions.map(acc => '<th class="center aligned">' + acc + '</th>').join('')}</tr></thead>`;
            let tbody1 = '';
            let tbody2 = '';

            const signatures = new Map(Object.entries(results.signatures));
            const comparisons = new Map();
            for (const [key, entries] of Object.entries(results.comparisons)) {
                comparisons.set(key, new Map(Object.entries(entries)));
            }


            for (const key1 of accessions) {
                tbody1 += `<tr><td>${key1}</td>`;
                tbody2 += `<tr><td>${key1}</td>`;
                const proteins = signatures.get(key1);

                for (const key2 of accessions) {
                    if (key1 === key2) {
                        tbody1 += `<td class="right aligned">${proteins === undefined ? '' : proteins.toLocaleString()}</td>`;
                        tbody2 += `<td class="right aligned">${proteins === undefined ? '' : proteins.toLocaleString()}</td>`;
                        continue
                    }

                    let val = undefined;
                    if (key1 < key2) {
                        if (comparisons.has(key1))
                            val = comparisons.get(key1).get(key2);
                    } else if (comparisons.has(key2))
                        val = comparisons.get(key2).get(key1);

                    if (val === undefined) {
                        tbody1 += '<td class="right aligned">0</td>';
                        tbody2 += '<td class="right aligned">0</td>';
                    } else {
                        tbody1 += `<td class="right aligned">
                                   <a data-key1="${key1}" data-key2="${key2}">${val.overlaps.toLocaleString()}</a>
                                   </td>`;
                        tbody2 += `<td class="right aligned">
                                   <a data-key1="${key1}" data-key2="${key2}">${val.collocations.toLocaleString()}</a>
                                   </td>`;
                    }
                }

                tbody1 += '</tr>';
                tbody2 += '</tr>';
            }

            document.getElementById('overlaps').innerHTML = thead + `<tbody>${tbody1}</tbody>`;
            document.getElementById('collocations').innerHTML = thead + `<tbody>${tbody2}</tbody>`;

            // Add exclusive-to-signature number of proteins
            let exclusiveTableRows = ''

            Object.entries(results.exclusive).forEach(([signature, count]) => {
            const excludedSignatures = accessions.filter(acc => acc !== signature);
            const linkToSignature =
                count > 0
                ? `<a href="/signatures/${signature}/proteins/?exclude=${excludedSignatures.join(',')}">${signature}</a>`
                : signature;

            exclusiveTableRows += `
                <tr>
                <td>${linkToSignature}</td>
                <td class="right aligned">${count.toLocaleString()}</td>
                </tr>`;
            });

            const exclusiveDiv = document.createElement('div')
            exclusiveDiv.innerHTML = `
                <br>
                <h4 class="ui header">Exclusive proteins</h4>
                        <table class="ui very basic small compact table">
                            <tbody>
                                ${exclusiveTableRows}
                            </tbody>
                        </table>
                <br>
                `
            document.getElementById('details-exclusive').appendChild(exclusiveDiv)

            dimmer.off();

            for (const link of document.querySelectorAll('a[data-key1][data-key2]')) {
                link.href = '#!';
                link.addEventListener('click', e => {
                    e.preventDefault();
                    const key1 = e.currentTarget.dataset.key1;
                    const key2 = e.currentTarget.dataset.key2;

                    const proteins1 = signatures.get(key1);
                    const proteins2 = signatures.get(key2);
                    let values;
                    if (key1 < key2)
                        values = comparisons.get(key1).get(key2);
                    else
                        values = comparisons.get(key2).get(key1);

                    document.getElementById('details-proteins').innerHTML = `
                        <h4 class="ui header">Proteins</h4>
                        <table class="ui very basic small compact table">
                        <tbody>
                            <tr>
                                <td>Overlapping</td>
                                <td class="right aligned">${values.overlaps.toLocaleString()}</td>
                            </tr>
                            <tr>
                                <td>In both signatures</td>
                                <td class="right aligned"><a href="/signatures/${key1}/${key2}/proteins/?matching=2">${values.collocations.toLocaleString()}</a></td>
                            </tr>
                            <tr>
                                <td>In either signatures</td>
                                <td class="right aligned"><a href="/signatures/${key1}/${key2}/proteins/">${(proteins1 + proteins2 - values.collocations).toLocaleString()}</a></td>
                            </tr>
                            <tr>
                                <td>In ${key1}</td>
                                <td class="right aligned"><a href="/signatures/${key1}/proteins/">${proteins1.toLocaleString()}</a></td>
                            </tr>
                            <tr>
                                <td>In ${key1} only</td>
                                <td class="right aligned"><a href="/signatures/${key1}/proteins/?exclude=${key2}">${(proteins1 - values.collocations).toLocaleString()}</a></td>
                            </tr>
                            <tr>
                                <td>In ${key2}</td>
                                <td class="right aligned"><a href="/signatures/${key2}/proteins/">${proteins2.toLocaleString()}</a></td>
                            </tr>
                            <tr>
                                <td>In ${key2} only</td>
                                <td class="right aligned"><a href="/signatures/${key2}/proteins/?exclude=${key1}">${(proteins2 - values.collocations).toLocaleString()}</a></td>
                            </tr>
                        </tbody>
                        </table>
                    `;
                });
            }
        });
}


document.addEventListener('DOMContentLoaded', () => {
    const match = location.pathname.match(/\/signatures\/(.+)\/matrices\/$/i);
    const accessions = match[1].split("/");
    document.title = "Collocations & overlaps (" + accessions.join(", ") + ") | Pronto";

    selector.init(document.getElementById('signature-selector'));
    for (const accession of accessions) {
        selector.add(accession);
    }
    selector.render().tab("matrices");

    updateHeader();
    getMatrices(accessions);
});
