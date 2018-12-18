import {finaliseHeader} from "../../header.js";
import {dimmer, useWhiteText, toRGB} from '../../ui.js';
import {selector, gradientPuBu, proteinViewer} from "../../signatures.js";


function _getComments(proteinsModal) {
    const url = '/api' + location.pathname + location.search;
    utils.dimmer(true);
    utils.getJSON(url, (obj, status) => {
        // Find the highest protein count
        const maxProt = Math.max(...obj.data.map(comment => {
            return Math.max(...comment.methods.map(method => { return method.count }));
        }));

        // Table header
        let html = '<thead><tr><th>'+ obj.data.length +' comments</th>';
        if (obj.data.length) {
            obj.data[0].methods.forEach(method => {
                html += '<th>' + method.accession + '</th>';
            });
        }
        html += '</tr></thead>';

        // Table body
        const colors = utils.gradientPuBu;
        html += '</thead><tbody>';
        obj.data.forEach(comment => {
            html += '<tr data-filter="'+ comment.value +'" data-search="comment=' + comment.id + '&topic='+ obj.meta.topic.id +'">' +
                '<td>'+ comment.value +'</td>';

            comment.methods.forEach(method => {
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

        proteinsModal.observe(table.querySelectorAll('td a[data-method]'), (method, filter, search) => {
            const header = '<em>' + method + '</em> proteins<div class="sub header">Comment: <em>'+ filter +'</em></div>';
            proteinsModal.open(method, search, header);
        });

        // Update select options
        Array.from(document.querySelectorAll('#topics option')).forEach(option => {
            option.selected = parseInt(option.value, 10) === obj.meta.topic.id;
        });

        // Select change event
        $('#topics').dropdown({
            onChange: function(value, text, $selectedItem) {
                const url = location.pathname + utils.encodeParams(
                    utils.extendObj(
                        utils.parseLocation(location.search),
                        {topic: value}
                    ),
                    true
                );
                history.replaceState(null, null, url);
                getComments(proteinsModal);
            }
        });

        utils.dimmer(false);
    });
}

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