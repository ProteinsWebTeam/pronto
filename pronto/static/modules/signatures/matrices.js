import {finaliseHeader} from "../../header.js";
import {dimmer, useWhiteText, toRGB} from '../../ui.js';
import {selector, gradientPuBu} from "../../signatures.js";

function getMatrices(accessions) {
    dimmer(true);
    const pathname = location.pathname.match(/(\/signatures\/.+\/)/)[1];
    fetch("/api" + pathname + location.search)
        .then(response => response.json())
        .then(signatures => {
            // Find the highest protein count
            const maxProt = Math.max(...Object.values(signatures).map(s => s.num_proteins));

            // Table header
            let html1 = '<thead><tr><th></th>';
            let html2 = '<thead><tr><th></th>';
            accessions.map(acc => {
                html1 += '<th class="center aligned">' + acc + '</th>';
                html2 += '<th class="center aligned">' + acc + '</th>';
            });
            html1 += '</tr></thead>';
            html2 += '</tr></thead>';

            // Table body
            html1 += '<tbody>';
            html2 += '<tbody>';
            accessions.forEach(acc1 => {
                html1 += '<tr><td>'+ acc1 +'</td>';
                html2 += '<tr><td>'+ acc1 +'</td>';

                if (!signatures.hasOwnProperty(acc1)) {
                    accessions.forEach(acc2 => {
                        html1 += '<td class="right aligned">0</td>';
                        html2 += '<td class="right aligned">0</td>';
                    });
                    html1 += '</tr>';
                    html2 += '</tr>';
                    return;
                }

                accessions.forEach(acc2 => {
                    if (!signatures[acc1].signatures.hasOwnProperty(acc2)) {
                        html1 += '<td class="right aligned">0</td>';
                        html2 += '<td class="right aligned">0</td>';
                        return;
                    }

                    const diag = acc1 === acc2;
                    const s = signatures[acc1].signatures[acc2];
                    let v, i, color, className;

                    // Overlap
                    v = s.num_overlap;
                    i = Math.floor(v / (maxProt + 1) * gradientPuBu.length);
                    color = gradientPuBu[i];
                    className = useWhiteText(color) ? 'light' : 'dark';
                    if (diag) {
                        html1 += '<td class="right aligned '+ className +'" style="background-color: '+ toRGB(color) +';">'
                            + v.toLocaleString()
                            + '</td>';
                    } else {
                        html1 += '<td class="right aligned '+ className +'" style="background-color: '+ toRGB(color) +';">'
                            + '<a href="#" data-ac1="'+ acc1 +'" data-ac2="'+ acc2 +'">' + v.toLocaleString() + '</a>'
                            + '</td>';
                    }


                    // Collocation
                    v = s.num_coloc;
                    i = Math.floor(v / (maxProt + 1) * gradientPuBu.length);
                    color = gradientPuBu[i];
                    className = useWhiteText(color) ? 'light' : 'dark';
                    if (diag) {
                        html2 += '<td class="right aligned '+ className +'" style="background-color: '+ toRGB(color) +';">'
                            + v.toLocaleString()
                            + '</td>';
                    } else {
                        html2 += '<td class="right aligned '+ className +'" style="background-color: '+ toRGB(color) +';">'
                            + '<a href="#" data-ac1="'+ acc1 +'" data-ac2="'+ acc2 +'">' + v.toLocaleString() + '</a>'
                            + '</td>';
                    }
                });
                html1 += '</tr>';
                html2 += '</tr>';
            });

            document.getElementById('overlap').innerHTML = html1;
            document.getElementById('collocation').innerHTML = html2;

            Array.from(document.querySelectorAll('tbody a[data-ac1]')).forEach(elem => {
                elem.addEventListener('click', e => {
                    e.preventDefault();
                    const acc1 = e.target.getAttribute('data-ac1');
                    const acc2 = e.target.getAttribute('data-ac2');
                    const s1 = signatures[acc1];
                    const s2 = signatures[acc2];
                    const s = signatures[acc1].signatures[acc2];


                    let html = '<h4 class="ui header">Proteins</h4>'
                        + '<table class="ui very basic small compact table">'
                        + '<tbody>'
                        + '<tr>'
                        + '<td>Overlapping</td>'
                        + '<td class="right aligned">'+ s.num_overlap.toLocaleString() +'</td>'
                        + '</tr>'
                        + '<tr>'
                        + '<td>Average overlap</td>'
                        + '<td class="right aligned">'+ Math.floor(s.avg_overlap) +'</td>'
                        + '</tr>'
                        + '<tr>'
                        + '<td>In both signatures</td>'
                        + '<td class="right aligned">'
                        + '<a target="_blank" href="/signatures/'+ acc1 + '/' + acc2 +'/proteins/?db=U&include='+ acc1 + ',' + acc2 +'">'+ s.num_coloc.toLocaleString() +'</a>'
                        + '</td>'
                        + '</tr>'
                        + '<tr>'
                        + '<td>In either signatures</td>'
                        + '<td class="right aligned">'
                        + '<a target="_blank" href="/signatures/'+ acc1 + '/' + acc2 +'/proteins/?db=U&">'+ (s1.num_proteins + s2.num_proteins - s.num_coloc).toLocaleString() +'</a>'
                        + '</td>'
                        + '</tr>'
                        + '<tr>'
                        + '<td>In '+ acc1 +' only</td>'
                        + '<td class="right aligned">'
                        + '<a target="_blank" href="/signatures/'+ acc1 + '/proteins/?db=U&exclude='+ acc2 +'">'+ (s1.num_proteins - s.num_coloc).toLocaleString() +'</a>'
                        + '</td>'
                        + '</tr>'
                        + '<tr>'
                        + '<td>In '+ acc2 +' only</td>'
                        + '<td class="right aligned">'
                        + '<a target="_blank" href="/signatures/'+ acc2 + '/proteins/?db=U&exclude='+ acc1 +'">'+ (s2.num_proteins - s.num_coloc).toLocaleString() +'</a>'
                        + '</td>'
                        + '</tr>'
                        + '<tr>'
                        + '<td>In '+ acc1 +'</td>'
                        + '<td class="right aligned">'
                        + '<a target="_blank" href="/signatures/'+ acc1 + '/proteins/?db=U">'+ s1.num_proteins.toLocaleString() +'</a>'
                        + '</td>'
                        + '</tr>'
                        + '<tr>'
                        + '<td>In '+ acc2 +'</td>'
                        + '<td class="right aligned">'
                        + '<a target="_blank" href="/signatures/'+ acc2 + '/proteins/?db=U">'+ s2.num_proteins.toLocaleString() +'</a>'
                        + '</td>'
                        + '</tr>';

                    document.getElementById('details').innerHTML = html + '</tbody></table>';
                });
            });

            dimmer(false);
        });
}

$(function () {
    const match = location.pathname.match(/\/signatures\/(.+)\/matrices\/$/i);
    const accessions = match[1].split("/");
    document.title = "Overlap/collocation matrices (" + accessions.join(", ") + ") | Pronto";
    selector.init(document.getElementById('methods'));
    selector.tab("matrices");
    accessions.forEach(acc => selector.add(acc));
    finaliseHeader();
    getMatrices(accessions);
});