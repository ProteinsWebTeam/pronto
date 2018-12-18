import {finaliseHeader} from "../../header.js";
import {dimmer, useWhiteText, toRGB} from '../../ui.js';
import {selector, gradientPuBu, proteinViewer} from "../../signatures.js";


function getEnzymes(accessions) {
    dimmer(true);
    fetch("/api" + location.pathname + location.search)
        .then(response => response.json())
        .then(result => {
            // Find the highest protein count
            const maxProt = Math.max(...result.entries.map(e => Math.max(...Object.values(e.signatures))));

            // Table header
            let html = '<thead>'
                + '<tr>'
                + '<th>'+ result.entries.length.toLocaleString() +' entries</th>';

            accessions.map(acc => {
                html += '<th>' + acc + '</th>';
            });
            html += '</tr></thead>';

            // Table body
            html += '<tbody>';
            result.entries.forEach(e => {
                html += '<tr data-type="ENZYME entry" data-filter="'+ e.id +'" data-params="ec='+ e.id +'&db='+ result.source_database +'">'
                    + '<td>'
                    + '<a target="_blank" href="//enzyme.expasy.org/EC/'+ e.id +'">'+ e.id +'&nbsp;'
                    + '<i class="external icon"></i>'
                    + '</a>'
                    + '</td>';

                accessions.forEach(acc => {
                    if (e.signatures.hasOwnProperty(acc)) {
                        const numProt = e.signatures[acc];
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
            proteinViewer.observe(document.querySelectorAll('td a[data-accession]'));
            dimmer(false);
        });
}


$(function () {
    const match = location.pathname.match(/^\/signatures\/(.+)\/enzyme\/$/i);
    const accessions = match[1].split("/");
    document.title = "ENZYME entries (" + accessions.join(", ") + ") | Pronto";
    selector.init(document.getElementById('methods'));
    selector.tab("enzyme");
    accessions.forEach(acc => selector.add(acc));

    // Radio change event
    Array.from(document.querySelectorAll('input[type=radio][name=dbcode]')).forEach(input => {
        input.addEventListener('change', e => {
            const url = new URL(location.href);
            url.searchParams.set("db", e.target.value);
            history.replaceState(null, null, url.toString());
            getEnzymes(accessions);
        });
    });

    finaliseHeader();
    getEnzymes(accessions);
});