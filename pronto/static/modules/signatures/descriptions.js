import {finaliseHeader} from "../../header.js";
import {dimmer, useWhiteText, toRGB} from '../../ui.js';
import {selector, gradientPuBu, proteinViewer} from "../../signatures.js";
import * as config from "../../config.js"

function getDescriptions(accessions) {
    dimmer(true);
    const pathname = location.pathname.match(/(\/signatures\/.+\/)/)[1];
    fetch(config.PREFIX+"/api" + pathname + location.search)
        .then(response => response.json())
        .then(result => {
            // Find the highest protein count
            const maxProt = Math.max(...result.descriptions.map(d => Math.max(...Object.values(d.signatures))));

            // Table header
            let html = '<thead>'
                + '<tr data-params="db='+ result.source_database +'">'
                + '<th>'+ result.descriptions.length.toLocaleString() +' descriptions</th>';

            accessions.map(acc => {
                html += '<th><a href="#" data-accession="'+ acc +'">' + acc + '</a></th>';
            });
            html += '</tr></thead>';

            // Table body
            html += '<tbody>';
            result.descriptions.forEach(d => {
                html += '<tr data-type="Description" data-filter="'+ d.value +'" data-params="description='+ d.id +'&db='+ result.source_database +'">'
                    + '<td>' + d.value + '</td>';

                accessions.forEach(acc => {
                    if (d.signatures.hasOwnProperty(acc)) {
                        const numProt = d.signatures[acc];
                        const i = Math.floor(numProt / (maxProt + 1) * gradientPuBu.length);
                        const color = gradientPuBu[i];
                        const className = useWhiteText(color) ? 'light' : 'dark';
                        html += '<td class="'+ className +'" style="background-color: '+ toRGB(color) +';">'
                            + '<a href="#" data-accession="'+ acc +'">' + numProt.toLocaleString() + '</a>'
                            + '</td>';
                    } else
                        html += '<td></td>';
                });

                html += '</tr>';
            });

            document.querySelector('table').innerHTML = html + '</tbody>';

            // Update radio checkbox (reviewed/unreviewed/any)
            let value;
            if (result.source_database === 'S')
                value = 'S';
            else if (result.source_database === 'T')
                value = 'T';
            else
                value = 'U';
            document.querySelector('input[name=dbcode][value="'+ value +'"]').checked = true;

            proteinViewer.observe(document.querySelectorAll('td a[data-accession]'), true);
            proteinViewer.observe(document.querySelectorAll('th a[data-accession]'), false);

            dimmer(false);
        });
}

$(function () {
    const match = location.pathname.match(/\/signatures\/(.+)\/descriptions\/$/i);
    const accessions = match[1].split("/");
    document.title = "UniProt descriptions (" + accessions.join(", ") + ") | Pronto";
    selector.init(document.getElementById('methods'));
    selector.tab("descriptions");
    accessions.forEach(acc => selector.add(acc));

    // Radio change event
    Array.from(document.querySelectorAll('input[type=radio][name=dbcode]')).forEach(input => {
        input.addEventListener('change', e => {
            const url = new URL(location.href);
            url.searchParams.set("db", e.target.value);
            history.replaceState(null, null, url.toString());
            getDescriptions(accessions);
        });
    });

    finaliseHeader();
    getDescriptions(accessions);
});