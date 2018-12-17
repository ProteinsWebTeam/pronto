import {dimmer, setClass, useWhiteText, toRGB} from '../../ui.js';
import {finaliseHeader} from "../../header.js";
import {selector, gradientPuBu, proteinViewer} from "../../signatures.js";

function _getTaxa(proteinsModal) {
    const url = '/api' + location.pathname + location.search;
    utils.dimmer(true);
    utils.getJSON(url, (obj, status) => {

        // Update taxonomic rank tab
        const tab = document.querySelector('a[data-rank].active');
        if (tab) utils.setClass(tab, 'active', false);
        utils.setClass(document.querySelector('a[data-rank="'+ obj.rank +'"]'), 'active', true);

        // Find the highest protein count
        const maxProt = Math.max(...obj.data.map(taxon => {
            return Math.max(...taxon.methods.map(method => { return method.count }));
        }));

        let html = '';
        const filteredByTaxon = obj.taxon.id !== 1;

        // Table header
        if (filteredByTaxon)
        // Override Semantic UI's pointer-events: none
            html += '<thead><tr><th style="pointer-events: auto;"><a class="ui basic label">' + obj.taxon.fullName + '<i class="delete icon"></i></a></th>';
        else
            html += '<thead><tr><th>'+ obj.taxon.fullName +'</th>';

        if (obj.data.length) {
            obj.data[0].methods.forEach(method => {
                html += '<th>'+ method.accession +'</th>';
            });
        } else
            html += '<th>No results found</th>';
        html += '</tr></thead>';

        // Table body
        const colors = utils.gradientPuBu;
        html += '<tbody>';
        obj.data.forEach(taxon => {
            if (taxon.id)
                html += '<tr data-filter="'+ taxon.fullName +'" data-search="taxon='+ taxon.id +'"><td><a href="/methods/'+ taxon.methods.map(method => { return method.accession; }).join('/') +'/taxonomy?rank=' + obj.rank + '&taxon='+ taxon.id + '">'+ taxon.fullName +'</a></td>';
            else
                html += '<tr data-filter="'+ taxon.fullName +'" data-search="notaxon&rank='+ obj.rank +'"><td>'+ taxon.fullName +'</td>';

            taxon.methods.forEach(method => {
                if (method.count) {
                    const i = Math.floor(method.count / maxProt * colors.length);
                    const color = colors[Math.min(i, colors.length - 1)];
                    const className = utils.useWhiteText(color) ? 'light' : 'dark';
                    html += '<td class="'+ className +'" style="background-color: '+ color +';"><a href="#" data-method="'+ method.accession +'">' + method.count.toLocaleString() + '</a></td>';
                } else
                    html += '<td></td>';
            });

            html += '</tr>';
        });

        const table = document.querySelector('table');
        table.innerHTML = html + '</tbody>';

        if (filteredByTaxon) {
            table.querySelector('table a.label i.delete').addEventListener('click', e => {
                const url = location.pathname + utils.encodeParams(
                    utils.extendObj(
                        utils.parseLocation(location.search),
                        {taxon: false}
                    ),
                    true
                );
                history.replaceState(null, null, url);
                getTaxa(proteinsModal);
            });
        }

        proteinsModal.observe(table.querySelectorAll('td a[data-method]'), (method, filter, search) => {
            const header = '<em>' + method + '</em> proteins<div class="sub header">Taxon: <em>'+ filter +'</em></div>';
            proteinsModal.open(method, search, header);
        });

        utils.dimmer(false);
    });
}


function getTaxa(accessions) {
    dimmer(true);
    const url = new URL(location.href);

    fetch("/api" + location.pathname + location.search)
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
            html += '</tr></thead>';

            // Table body
            html += '<tbody>';
            results.taxa.forEach(taxon => {
                if (taxon.id !== null) {
                    url.searchParams.set("taxon", taxon.id);
                    html += '<tr data-label="'+ taxon.name +'" data-key="taxon" data-value="'+ taxon.id +'">'
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

                html += '</tr>';
            });

            document.querySelector('table').innerHTML = html;

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

            proteinViewer.observe(
                document.querySelectorAll('td a[data-accession]'),
                (accession, label, key, value) => {
                    proteinViewer.open(accession, key, value, true);
                }
            );

            dimmer(false);
        });
}


$(function () {
    const match = location.pathname.match(/^\/signatures\/(.+)\/taxonomy\/$/i);
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