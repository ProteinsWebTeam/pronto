import {dimmer, renderCheckbox, openErrorModal} from "../ui.js";
import {finaliseHeader, nvl} from "../header.js";
import {getSignatureComments, postSignatureComment} from "../comments.js";
import {selector} from "../signatures.js";
import {checkEntry} from "../events.js";

const PREDICTIONS = new Map([
    ['S', {color: 'green', label: 'Similar'}],
    ['R', {color: 'blue', label: 'Related'}],
    ['C', {color: 'purple', label: 'Child'}],
    ['P', {color: 'violet', label: 'Parent'}],
    [null, {color: 'red', label: 'Dissimilar'}]
]);

function parseParams(name) {
    const value = parseFloat(new URL(location.href).searchParams.get(name));
    return Number.isNaN(value) ? null : value;
}

function initPopup(elem) {
    const title = elem.getAttribute('data-key');
    let content = null;
    if (title === 'collocations')
        content = 'Common proteins';
    else if (title === 'proteins')
        content = 'Overlapping proteins';
    else if (title === 'residues')
        content = 'Overlapping residues';
    else if (title === 'descriptions')
        content = 'Common UniProtKB descriptions';
    else if (title === 'taxa')
        content = 'Common taxonomic origins';
    else if (title === 'terms')
        content = 'Common GO terms';

    $(elem)
        .popup({
            title: title.substr(0, 1).toUpperCase() + title.substr(1),
            content: content,
            position: 'top center',
            variation: 'small'
        });
}

function renderOverlap(accession1, accession2, key) {
    dimmer(true);
    fetch(URL_PREFIX+'/api/signature/'+ accession1 +'/comparison/'+ accession2 +'/'+ key +'/')
        .then(response => response.json())
        .then(results => {
            dimmer(false);
            const modal = document.getElementById('comparison');
            $(modal)
                .modal({
                    // Use onVisible() and not onShow() because we need to modal to actually be visible to compute styles
                    onVisible: function () {
                        const content = this.querySelector('.content');
                        const style = window.getComputedStyle(content, null);
                        const width = content.offsetWidth - parseFloat(style.getPropertyValue('padding-left')) - parseFloat(style.getPropertyValue('padding-right'));

                        const union = (results[accession1] + results[accession2] - results["common"]);
                        const rect1Width = Math.floor(results[accession1] * width / union);

                        const rect2Width = Math.floor(results["common"] * width / union);
                        const rect2X = Math.floor((results[accession1] - results["common"]) * width / union);

                        const rect3Width = Math.floor(results[accession2] * width / union);
                        const rect3X = width - rect3Width;

                        content.innerHTML = '<svg width="' + width + 'px" height="100px">'
                            + '<text dominant-baseline="hanging" text-anchor="start" x="0" y="0" fill="#333">'+ accession1 +' ('+ results[accession1].toLocaleString() +')</text>'
                            + '<rect class="light-blue" x="0" y="20px" width="'+ rect1Width +'px" height="20px"/>'
                            + '<rect class="green" x="'+ rect2X +'px" y="40px"width="'+ rect2Width +'px"  height="20px"/>'
                            + '<rect class="lime" x="'+ rect3X +'px" y="60px"width="'+ rect3Width +'px"  height="20px"/>'
                            + '<text dominant-baseline="hanging" text-anchor="end" x="'+ width +'px" y="80px" fill="#333">'+ accession2 +' ('+ results[accession2].toLocaleString() +')</text>'
                            + '</svg>';
                    }
                })
                .modal('show');
        });
}

function getGlobalPredictionLabel(predictions) {
    let label = PREDICTIONS.get(predictions['proteins']).label;

    if (predictions['proteins'] && predictions['proteins'] === predictions['residues'])
        label += '&nbsp;<i class="yellow star fitted icon"></i>';

    return label;
}

function getPredictions(accession) {
    const minCollocation = document.querySelector('tfoot input[type=radio]:checked').value;
    const url = URL_PREFIX + "/api/signature/" + accession + "/predictions/?mincollocation=" + minCollocation;

    dimmer(true);
    fetch(url)
        .then(response => response.json())
        .then(signatures => {
            let html = '';

            document.getElementById('predictions-count').innerHTML = signatures.length.toLocaleString();

            if (signatures.length) {
                signatures.forEach(s => {
                    const circles = '<div class="ui tiny circular labels">'
                        + '<span data-key="proteins" class="ui '+ PREDICTIONS.get(s.predictions['proteins']).color +' label"></span>'
                        + '<span data-key="descriptions" data-accession="'+ s.accession +'" class="ui '+ PREDICTIONS.get(s.predictions['descriptions']).color +' label"></span>'
                        +'<span data-key="taxa" data-accession="'+ s.accession +'" class="ui '+ PREDICTIONS.get(s.predictions['taxa']).color +' label"></span>'
                        + '<span data-key="terms" data-accession="'+ s.accession +'" class="ui '+ PREDICTIONS.get(s.predictions['terms']).color +' label"></span>'
                        + '</div>';

                    html += '<tr>'
                        + '<td class="nowrap">'+ getGlobalPredictionLabel(s.predictions) +'</td><td class="collapsing">'+ circles +'</td>'
                        + '<td class="collapsing"><a href="'+URL_PREFIX+'/prediction/'+ s.accession +'/">'+ s.accession +'</a></td>';

                    if (s.link !== null) {
                        html += '<td class="collapsing">'
                            + '<a target="_blank" href="'+ s.link +'">'
                            + '<i class="external icon"></i>'
                            + '</a>'
                            + '</td>';
                    } else
                        html += '<td></td>';

                    html += '<td class="collapsing">'
                        + '<a href="#" data-add-id="'+ s.accession +'"><i class="cart plus icon"></i></a>'
                        + '</td>'
                        + '<td class="collapsing right aligned">' + s.proteins.toLocaleString() + '</td>'
                        + '<td class="collapsing right aligned">'+ s.common_proteins.toLocaleString() +'</td>'
                        + '<td class="collapsing right aligned">'+ s.overlap_proteins.toLocaleString() +'</td>';

                    if (s.entry.accession !== null) {
                        html += '<td class="nowrap">'
                            + '<div class="ui list">';

                        s.entry.hierarchy.forEach(entryAcc => {
                            html += '<div class="item">'
                                + '<div class="content">'
                                + '<i class="angle down icon"></i>'
                                + '<a href="'+URL_PREFIX+'/entry/'+ entryAcc +'/">'+ entryAcc +'</a>'
                                + '</div>'
                                + '</div>';
                        });

                        html += '<div class="item">'
                            + '<div class="content">'
                            + '<span class="ui circular mini label type-'+ s.entry.type_code +'">'+ s.entry.type_code +'</span>'
                            + '<a href="'+URL_PREFIX+'/entry/'+ s.entry.accession +'/">'+ s.entry.accession +' ('+ s.entry.name +')</a>'
                            + '</div>'
                            + '</div>'
                            + '</td>'
                            + '<td class="collapsing">'+ renderCheckbox(s.entry.accession, s.entry.checked) +'</td>';
                    } else
                        html += '<td></td><td></td>';

                    html += '</tr>';
                });
            } else
                html += '<tr><td colspan="10" class="center aligned">No predictions found for this signature</td></tr>';

            document.querySelector("#table-predictions tbody").innerHTML = html;

            // Adding/removing signatures
            Array.from(document.querySelectorAll('tbody a[data-add-id]')).forEach(elem => {
                elem.addEventListener('click', e => {
                    e.preventDefault();
                    selector.add(elem.getAttribute('data-add-id'));
                });
            });

            Array.from(document.querySelectorAll('tbody input[type=checkbox]')).forEach(input => {
                input.addEventListener('change', e => checkEntry(input));
            });

            Array.from(document.querySelectorAll('tbody .ui.circular.labels .label[data-key]')).map(initPopup);

            Array.from(document.querySelectorAll('span[data-accession]')).forEach(elem => {
                elem.addEventListener('click', e => {
                    renderOverlap(
                        accession,
                        e.target.getAttribute('data-accession'),
                        e.target.getAttribute('data-key')
                    );
                })
            });

            dimmer(false);
        });
}


$(function () {
    const match = location.pathname.match(/\/prediction\/([^\/]+)/i);
    const accession = match[1];
    document.title = accession + " predictions | Pronto";
    finaliseHeader(accession);
    fetch(URL_PREFIX+'/api/signature/'+ accession +'/')
        .then(response => {
            if (!response.ok)
                throw Error(response.status.toString());
            return response.json();
        })
        .then(response => {
            selector.init(document.getElementById('methods'), accession);

            // Update page header
            let html = '';
            if (response.link)
                html += '<a href="'+ response.link +'" target="_blank">';

            if (response.name && response.name !== accession)
                html += response.name + ' (' + accession + ')';
            else
                html += accession;

            if (response.link)
                html += '&nbsp;<i class="external fitted icon"></i></a>';

            html += ' &mdash; ' + response.num_sequences.toLocaleString() +' proteins';

            if (response.entry.accession) {
                html += '&nbsp;&mdash;&nbsp;';

                if (response.entry.parent) {
                    html += '<a href="'+URL_PREFIX+'/entry/'+response.entry.parent+'/">'+response.entry.parent+'</a>&nbsp;'
                        + '<i class="fitted right chevron icon"></i>&nbsp;';
                }

                html += '<span class="ui small circular label type-'+ response.entry.type +'" style="margin-left: 0 !important;">'+ response.entry.type +'</span>'
                    + '<a href="'+URL_PREFIX+'/entry/'+ response.entry.accession +'/">'
                    + response.entry.accession
                    + '</a>'
                    + (response.entry.checked ? '<i class="checkmark icon"></i>' : '');
            }

            document.querySelector("h1.ui.header .sub").innerHTML = html;

            // Update table header (a curator requested to have the signature in the prediction table...)
            html = '<th colspan="2"></th><th class="collapsing"><a href="'+URL_PREFIX+'/prediction/'+ accession +'/">'+ accession +'</a></a></th>';
            if (response.link) {
                html += '<th class="collapsing">'
                    + '<a target="_blank" href="'+ response.link +'">'
                    + '<i class="external icon"></i>'
                    + '</a>'
                    + '</th>';
            } else
                html += '<th></th>';

            html += '<th class="collapsing"><a href="#" data-add-id="'+ accession +'"><i class="cart plus icon"></i></a></th>'
                + '<th class="collapsing right aligned">' + response.num_sequences.toLocaleString() + '</th>'
                + '<th></th>'
                + '<th></th>';

            if (response.entry.accession !== null) {
                html += '<th class="nowrap">'
                    + '<div class="ui list">';

                if (response.entry.parent) {
                    html += '<div class="item">'
                        + '<div class="content">'
                        + '<i class="angle down icon"></i>'
                        + '<a href="'+URL_PREFIX+'/entry/'+ response.entry.parent +'/">'+ response.entry.parent +'</a>'
                        + '</div>'
                        + '</div>';
                }

                html += '<div class="item">'
                    + '<div class="content">'
                    + '<span class="ui circular mini label type-'+ response.entry.type +'">'+ response.entry.type +'</span>'
                    + '<a href="'+URL_PREFIX+'/entry/'+ response.entry.accession +'/">'+ response.entry.accession +'</a>'
                    + '</div>'
                    + '</div>'
                    + '</th>'
                    + '<th class="collapsing">'+ renderCheckbox(response.entry.accession, response.entry.checked) +'</th>';
            } else
                html += '<th></th><th></th>';

            let node = document.createElement('tr');
            node.innerHTML = html;
            document.querySelector("#table-predictions thead").appendChild(node);

            // Events on thead
            document.querySelector('thead a[data-add-id]').addEventListener('click', e => {
                e.preventDefault();
                selector.add(e.currentTarget.getAttribute('data-add-id'));
            });
            node = document.querySelector('thead input[type=checkbox]');
            if (node)
                node.addEventListener('change', e => checkEntry(e.currentTarget));

            document.querySelector('.ui.comments form button').addEventListener('click', e => {
                e.preventDefault();
                const form = e.target.closest('form');
                const accession = form.getAttribute('data-id');
                const textarea = form.querySelector('textarea');

                postSignatureComment(accession, textarea.value.trim())
                    .then(result => {
                        if (result.status)
                            getSignatureComments(accession, 2, e.target.closest(".ui.comments"));
                        else
                            openErrorModal(result);
                    });
            });

            // Init Semantic-UI elements
            $('[data-content]').popup();

            Array.from(document.querySelectorAll('tfoot input[type=radio]')).forEach(elem => {
                elem.addEventListener('change', (e,) => {
                    getPredictions(accession);
                });
            });

            getSignatureComments(accession, 2, document.querySelector('.ui.comments'));
            getPredictions(accession);
        })
        .catch(error => {
            if (error.message === '404') {
                document.querySelector('.ui.container.segment').innerHTML = '<div class="ui error message">'
                    + '<div class="header">Signature not found</div>'
                    + '<p><strong>'+ accession +'</strong> is not a valid member database signature accession.</p>'
                    + '</div>';
            } else {
                document.querySelector('.ui.container.segment').innerHTML = '<div class="ui error message">'
                    + '<div class="header">'+ error.name +'</div>'
                    + '<p>'+ error.message +'</p>'
                    + '</div>';
            }
        });
});