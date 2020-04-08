import {dimmer, setClass, useWhiteText, toRGB} from '../../ui.js';
import {finaliseHeader} from "../../header.js";
import {selector, gradientPuBu, proteinViewer} from "../../signatures.js";

function getTaxa(accessions) {
    dimmer(true);
    const url = new URL(location.href);

    const pathname = location.pathname.match(/(\/signatures\/.+\/)/)[1];
    fetch(URL_PREFIX+"/api" + pathname + location.search)
        .then(response => response.json())
        .then(results => {
            // Update tab
            const tab = document.querySelector('a[data-rank].active');
            if (tab) setClass(tab, "active", false);
            setClass(document.querySelector('a[data-rank="'+ results.rank +'"]'), 'active', true);

            // Find the highest count
            const maxProt = Math.max(...results.taxa.map(taxon => Math.max(...Object.values(taxon.signatures))));

            let html = '<thead><tr>';

            // Table header (when filtering by taxon)
            if (results.taxon.id !== null) {
                // Override Semantic UI's pointer-events: none
                html += '<th style="pointer-events: auto;">'
                    + '<a class="ui basic label">'+ results.taxon.name +'&nbsp;'
                    + '<i class="delete icon"></i>'
                    + '</a>'
                    + '</th>';
            } else
                html += '<th></th>';

            accessions.map(acc => {
                html += '<th>' + acc + '</th>';
            });
            html += '<th></th></tr></thead>';
            html += '</tr></thead>';

            // Table body
            html += '<tbody>';
            results.taxa.forEach(taxon => {
                if (taxon.id !== null) {
                    url.searchParams.set("taxon", taxon.id);
                    html += '<tr data-type="Taxon" data-filter="'+ taxon.name +'" data-params="taxon='+ taxon.id +'">'
                        + '<td>'
                        + '<a href="'+ url.toString() +'">'+ taxon.name +'</a>'
                        + '</td>';
                } else {
                    html += '<tr><td>'+ taxon.name +'</td>';
                }

                accessions.forEach(acc => {
                    if (taxon.signatures.hasOwnProperty(acc)) {
                        const numProt = taxon.signatures[acc];
                        const i = Math.floor(numProt / (maxProt + 1) * gradientPuBu.length);
                        const color = gradientPuBu[i];
                        const className = useWhiteText(color) ? 'light' : 'dark';
                        html += '<td class="'+ className +'" style="background-color: '+ toRGB(color) +';">'
                            + '<a href="#" data-accession="'+ acc +'">' + numProt.toLocaleString() + '</a>'
                            + '</td>';
                    } else
                        html += '<td></td>';
                });

                html += '<td class="collapsing"><i class="fitted object ungroup button icon" data-taxon="'+ taxon.id +'"></i></td></tr>';
                html += '</tr>';
            });

            document.querySelector('.ui.container.vertical.segment table').innerHTML = html + '</tbody>';

            (function () {
                const icon = document.querySelector('table a.label i.delete');
                if (icon) {
                    icon.addEventListener('click', e => {
                        const url = new URL(location.href);
                        url.searchParams.delete('taxon');
                        history.replaceState(null, null, url.toString());
                        getTaxa(accessions);
                    })
                }
            })();

            proteinViewer.observe(document.querySelectorAll('td a[data-accession]'), true);

            Array.from(document.querySelectorAll('i.ungroup.button.icon')).forEach(icon => {
                icon.addEventListener('click', e => {
                    e.preventDefault();
                    proteinViewer.open(accessions, 'common', null, '/taxonomy/' + results.rank + '/' + e.target.getAttribute('data-taxon') + '/')
                        .then(() => {
                            const row = e.target.closest('tr');
                            const type = row.getAttribute('data-type');
                            const filter = row.getAttribute('data-filter');
                            proteinViewer.setTitle('Common proteins<div class="sub header">'+ type +': <em>'+ filter +'</em></div>');
                        });
                });
            });

            dimmer(false);
        });
}

$(function () {
    const match = location.pathname.match(/\/signatures\/(.+)\/taxonomy\/$/i);
    const accessions = match[1].split("/");
    document.title = "Taxonomic origins (" + accessions.join(", ") + ") | Pronto";
    selector.init(document.getElementById('methods'));
    selector.tab("taxonomy");
    accessions.forEach(acc => selector.add(acc));

    // Tab change event
    Array.from(document.querySelectorAll('.tabular.menu .item[data-rank]')).forEach(item => {
        item.addEventListener('click', e => {
            const url = new URL(location.href);
            url.searchParams.set("rank", item.getAttribute('data-rank'));
            history.replaceState(null, null, url.toString());
            getTaxa(accessions);
        });
    });

    finaliseHeader();
    getTaxa(accessions);
});