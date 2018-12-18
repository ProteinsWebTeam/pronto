import {finaliseHeader} from "../../header.js";
import {dimmer, useWhiteText, toRGB} from '../../ui.js';
import {selector, gradientPuBu, proteinViewer} from "../../signatures.js";


function _getDescriptions(proteinsModal) {
    const url = '/api' + location.pathname + location.search;
    utils.dimmer(true);
    utils.getJSON(url, (obj, status) => {
        // Find the highest protein count
        const maxProt = Math.max(...obj.data.map(descr => {
            return Math.max(...descr.methods.map(method => { return method.count }));
        }));

        // Table header
        let html = '<thead><tr data-search="db='+ obj.database +'"><th>'+ obj.data.length +' descriptions</th>';
        if (obj.data.length) {
            obj.data[0].methods.forEach(method => {
                html += '<th><a href="" data-method="'+ method.accession +'">' + method.accession + '</a></th>';
            });
        }
        html += '</tr></thead>';

        // Table body
        const colors = utils.gradientPuBu;
        html += '</thead><tbody>';
        obj.data.forEach(descr => {
            html += '<tr data-type data-filter="'+ descr.value +'" data-search="description=' + descr.id + '&db='+ obj.database +'">' +
                '<td>'+ descr.value +'</td>';

            descr.methods.forEach(method => {
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

        proteinsModal.observe(table.querySelectorAll('th a[data-method]'), (method, filter, search) => {
            const header = '<em>' + method + '</em> proteins';
            proteinsModal.open(method, search, header, true);
        });

        proteinsModal.observe(table.querySelectorAll('td a[data-method]'), (method, filter, search) => {
            const header = '<em>' + method + '</em> proteins<div class="sub header">Description: <em>'+ filter +'</em></div>';
            proteinsModal.open(method, search, header);
        });

        // Update radios
        document.querySelector('input[type=radio][value="'+ obj.database +'"]').checked = true;

        utils.dimmer(false);
    });
}


function getDescriptions(accessions) {
    dimmer(true);
    const url = new URL(location.href);

    fetch("/api" + location.pathname + location.search)
        .then(response => response.json())
        .then(result => {
            console.log(result);

            // Find the highest protein count
            const maxProt = Math.max(...result.descriptions.map(d => Math.max(...Object.values(d.signatures))));

            // Table header
            let html = '<thead>'
                + '<tr>'
                + '<th>'+ result.descriptions.length.toLocaleString() +' descriptions</th>';

            accessions.map(acc => {
                html += '<th>' + acc + '</th>';
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

            proteinViewer.observe(document.querySelectorAll('td a[data-accession]'));

            dimmer(false);
        });
}


$(function () {
    const match = location.pathname.match(/^\/signatures\/(.+)\/descriptions\/$/i);
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