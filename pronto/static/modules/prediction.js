import {dimmer, renderCheckbox, openErrorModal} from "../ui.js";
import {finaliseHeader, nvl} from "../header.js";
import {getSignatureComments, postSignatureComment} from "../comments.js";
import {selector} from "../signatures.js";
import {checkEntry} from "../events.js";

let ACCESSION = null;
let SIGNATURES = null;
const PREDICTIONS = new Map([
    [0, {color: 'green', label: 'Similar'}],
    [1, {color: 'blue', label: 'Related'}],
    [2, {color: 'purple', label: 'Child'}],
    [3, {color: 'violet', label: 'Parent'}],
    [4, {color: 'red', label: 'Dissimilar'}]
]);

function parseParams(name) {
    const value = parseFloat(new URL(location.href).searchParams.get(name));
    return Number.isNaN(value) ? null : value;
}

function predict(obj, minSimilarity) {
    if (obj.similarity >= minSimilarity)
        return 0;
    else if (obj.query >= minSimilarity) {
        if (obj.target >= minSimilarity)
            return 1;
        else
            return 2;
    } else if (obj.target >= minSimilarity)
        return 3;
    else
        return 4;
}

function predictGlobal(predictions) {
    if (predictions['proteins'] !== 4) {
        const label = PREDICTIONS.get(predictions['proteins']).label;
        if (predictions['residues'] === predictions['proteins'])
            return label + '&nbsp;<i class="yellow fitted star icon"></i>';
        else
            return label;
    }else
        return 'N/A';
}


function refreshTable(minSimilarity) {
    let html = '';

    SIGNATURES.forEach(s => {
        const predictions = {};
        for (let [key, value] of Object.entries(s.similarities)) {
            predictions[key] = predict(value, minSimilarity);
        }

        let circles = '<div class="ui tiny circular labels">';
        let flag;

        // flag = predictions['collocations'];
        // circles += '<span data-key="collocations" class="ui '+ PREDICTIONS.get(flag).color +' label"></span>';

        flag = predictions['proteins'];
        circles += '<span data-key="proteins" class="ui '+ PREDICTIONS.get(flag).color +' label"></span>';

        // flag = predictions['residues'];
        // circles += '<span data-key="residues" class="ui '+ PREDICTIONS.get(flag).color +' label"></span>';

        flag = predictions['descriptions'];
        circles += '<span data-key="descriptions" data-accession="'+ s.accession +'" class="ui '+ PREDICTIONS.get(flag).color +' label"></span>';

        flag = predictions['taxa'];
        circles += '<span data-key="taxa" data-accession="'+ s.accession +'" class="ui '+ PREDICTIONS.get(flag).color +' label"></span>';

        flag = predictions['terms'];
        circles += '<span data-key="terms" data-accession="'+ s.accession +'" class="ui '+ PREDICTIONS.get(flag).color +' label"></span>';
        circles += '</div>';

        html += '<tr>'
            + '<td class="nowrap">'+ predictGlobal(predictions) +'</td><td class="collapsing">'+ circles +'</td>'
            + '<td class="collapsing"><a href="/prediction/'+ s.accession +'/">'+ s.accession +'</a></td>';

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
                    + '<a href="/entry/'+ entryAcc +'/">'+ entryAcc +'</a>'
                    + '</div>'
                    + '</div>';
            });

            html += '<div class="item">'
                + '<div class="content">'
                + '<span class="ui circular mini label type-'+ s.entry.type_code +'">'+ s.entry.type_code +'</span>'
                + '<a href="/entry/'+ s.entry.accession +'/">'+ s.entry.accession +' ('+ s.entry.name +')</a>'
                + '</div>'
                + '</div>'
                + '</td>'
                + '<td class="collapsing">'+ renderCheckbox(s.entry.accession, s.entry.checked) +'</td>';
        } else
            html += '<td></td><td></td>';

        html += '</tr>';

    });

    document.querySelector("tbody").innerHTML = html;

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

    Array.from(document.querySelectorAll('tbody .ui.circular.labels .label[data-key]')).forEach(elem => {
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
    });

    Array.from(document.querySelectorAll('span[data-accession]')).forEach(elem => {
        elem.addEventListener('click', e => {
            dimmer(true);
            const key = e.target.getAttribute('data-key');
            const otherAcc = e.target.getAttribute('data-accession');

            fetch('/api/signature/'+ ACCESSION +'/comparison/'+ otherAcc +'/'+ key +'/')
                .then(response => response.json())
                .then(results => {
                    const modal = document.getElementById('comparison');
                    $(modal)
                        .modal({
                            // Use onVisible() and not onShow() because we need to modal to actually be visible to compute styles
                            onVisible: function () {
                                const content = this.querySelector('.content');
                                const style = window.getComputedStyle(content, null);
                                const width = content.offsetWidth - parseFloat(style.getPropertyValue('padding-left')) - parseFloat(style.getPropertyValue('padding-right'));

                                const union = (results[ACCESSION] + results[otherAcc] - results["common"]);
                                const rect1Width = Math.floor(results[ACCESSION] * width / union);

                                const rect2Width = Math.floor(results["common"] * width / union);
                                const rect2X = Math.floor((results[ACCESSION] - results["common"]) * width / union);

                                const rect3Width = Math.floor(results[otherAcc] * width / union);
                                const rect3X = width - rect3Width;


                                let svg = '<svg width="' + width + 'px" height="100px">'
                                    + '<text dominant-baseline="hanging" text-anchor="start" x="0" y="0" fill="#333">'+ ACCESSION +' ('+ results[ACCESSION].toLocaleString() +')</text>'
                                    + '<rect class="light-blue" x="0" y="20px" width="'+ rect1Width +'px" height="20px"/>'
                                    + '<rect class="green" x="'+ rect2X +'px" y="40px"width="'+ rect2Width +'px"  height="20px"/>'
                                    + '<rect class="lime" x="'+ rect3X +'px" y="60px"width="'+ rect3Width +'px"  height="20px"/>'
                                    + '<text dominant-baseline="hanging" text-anchor="end" x="'+ width +'px" y="80px" fill="#333">'+ otherAcc +' ('+ results[otherAcc].toLocaleString() +')</text>'
                                    + '</svg>';

                                content.innerHTML = svg;
                                dimmer(false);
                            }
                        })
                        .modal('show');

                });
        })
    });
}



function getPredictions(accession) {
    const minCollocation = document.querySelector('tfoot input[type=radio]:checked').value;
    const url = "/api/signature/" + accession + "/predictions/?mincollocation=" + minCollocation;

    dimmer(true);
    fetch(url)
        .then(response => response.json())
        .then(signatures => {
            ACCESSION = accession;
            SIGNATURES = signatures;
            refreshTable(parseFloat(document.getElementById('over-range').value));
            dimmer(false);
        });
}


$(function () {
    const match = location.pathname.match(/\/prediction\/([^\/]+)/i);
    const accession = match[1];
    document.title = accession + " predictions | Pronto";
    finaliseHeader(accession);
    fetch('/api/signature/'+ accession +'/')
        .then(response => {
            if (!response.ok)
                throw Error(response.status.toString());
            return response.json();
        })
        .then(response => {
            selector.init(document.getElementById('methods'), accession);

            if (response.name && response.name !== accession)
                document.querySelector("h1.ui.header .sub").innerHTML = response.name + ' (' + accession + ')';
            else
                document.querySelector("h1.ui.header .sub").innerHTML = accession;

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

            (function () {
                const minSimilarity = parseParams('minsimilarity') || 0.75;
                const slider = document.getElementById('over-range');
                const span = document.getElementById('over-value');
                const labels = Array.from(document.querySelectorAll('tfoot .ui.label[data-content]'));
                labels.forEach(elem => {
                    let content = elem.getAttribute('data-content');
                    content = content.replace('#', minSimilarity.toFixed(2));
                    content = content.replace('$', (minSimilarity*100).toFixed(0));
                    elem.setAttribute('data-content', content);
                });

                slider.value = minSimilarity;
                span.innerHTML = minSimilarity.toFixed(2);
                slider.addEventListener('change', e => {
                    const minSimilarity = parseFloat(e.target.value);
                    span.innerHTML = minSimilarity.toFixed(2);
                    labels.forEach(elem => {
                        let content = elem.getAttribute('data-content');
                        content = content.replace('#', minSimilarity.toFixed(2));
                        content = content.replace('$', (minSimilarity*100).toFixed(0));
                        elem.setAttribute('data-content', content);
                    });

                    const url = new URL(location.href);
                    url.searchParams.set("minsimilarity", minSimilarity);
                    history.replaceState(null, null, url.toString());
                    dimmer(true);
                    refreshTable(minSimilarity);
                    dimmer(false);
                });
                slider.addEventListener('input', evt => {
                    span.innerHTML = (parseFloat(evt.target.value)).toFixed(2);
                });
            })();

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