import {finaliseHeader} from "../../header.js";
import {dimmer, useWhiteText, toRGB} from '../../ui.js';
import {selector, gradientPuBu, proteinViewer} from "../../signatures.js";

function getComments(accessions) {
    dimmer(true);
    fetch("/api" + location.pathname + location.search)
        .then(response => response.json())
        .then(comments => {
            // Find the highest protein count
            const maxProt = Math.max(...comments.map(c => Math.max(...Object.values(c.signatures))));

            // Table header
            let html = '<thead>'
                + '<tr>'
                + '<th>'+ comments.length.toLocaleString() +' similarity comments</th>';

            accessions.map(acc => {
                html += '<th>' + acc + '</th>';
            });
            html += '</tr></thead>';

            // Table body
            html += '<tbody>';
            comments.forEach(c => {
                html += '<tr data-type="Similarity" data-filter="'+ c.value +'" data-params="comment='+ c.id +'&topic=34">'
                    + '<td>' + c.value + '</td>';

                accessions.forEach(acc => {
                    if (c.signatures.hasOwnProperty(acc)) {
                        const numProt = c.signatures[acc];
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
            proteinViewer.observe(document.querySelectorAll('td a[data-accession]'));
            dimmer(false);
        });
}

$(function () {
    const match = location.pathname.match(/^\/signatures\/(.+)\/similarity\/$/i);
    const accessions = match[1].split("/");
    document.title = "Similarity comments (" + accessions.join(", ") + ") | Pronto";
    selector.init(document.getElementById('methods'));
    selector.tab("similarity");
    accessions.forEach(acc => selector.add(acc));
    finaliseHeader();
    getComments(accessions);
});