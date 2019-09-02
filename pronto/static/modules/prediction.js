import {dimmer, renderCheckbox, openErrorModal, useWhiteText, toRGB} from "../ui.js";
import {finaliseHeader, nvl} from "../header.js";
import {getSignatureComments, postSignatureComment} from "../comments.js";
import {selector} from "../signatures.js";
import {checkEntry} from "../events.js";

const overlapHeatmap = {
    colors: {
        topLeft: {r: 108, g: 167, b: 93},
        topRight: {r: 147, g: 114, b: 198},
        bottomLeft: {r: 191, g: 130, b: 59},
        bottomRight: {r: 204, g: 85, b: 111},
    },
    size: 5,
    pixels: [],
    calcSlope: function (p1, p2) {
        return {
            r: (p2.r - p1.r) / this.size,
            g: (p2.g - p1.g) / this.size,
            b: (p2.b - p1.b) / this.size
        }
    },
    calcGradient: function (p, distance, slope) {
        return {
            r: p.r + slope.r * distance,
            g: p.g + slope.g * distance,
            b: p.b + slope.b * distance
        }
    },
    calcPixels: function () {
        const top = this.calcSlope(this.colors.topLeft, this.colors.topRight);
        const bottom = this.calcSlope(this.colors.bottomLeft, this.colors.bottomRight);

        // Interpolate from left to right, then from top to bottom
        for (let x = 0; x < this.size; ++x) {
            const p1 = this.calcGradient(this.colors.topLeft, x, top);
            const p2 = this.calcGradient(this.colors.bottomLeft, x, bottom);

            for (let y = 0; y < this.size; ++y) {
                const vertical = this.calcSlope(p1, p2);
                this.pixels.push({
                    x: x,
                    y: y,
                    c: this.calcGradient(p1, y, vertical)
                });
            }
        }
    },
    getPixel: function (x, y) {
        const p = this.pixels.find((e,) => e.x === x && e.y === y);
        return p === undefined ? null : p.c;
    },
    render: function () {
        const element = document.getElementById('heatmap');
        const svg = element.querySelector('svg');
        const size = element.offsetWidth;
        svg.setAttribute('width', size.toString());
        svg.setAttribute('height', size.toString());
        const rectSize = Math.floor(size / (this.size + 1));
        let html = '';
        this.pixels.forEach(p => {
            html += '<rect x="'+ ((p.x + 1) * rectSize) +'" y="'+ ((p.y + 1) * rectSize) +'" width="'+ (rectSize) +'" height="'+ (rectSize) +'" fill="'+ toRGB(p.c) +'"></rect>';
        });

        html += '<text dominant-baseline="hanging" text-anchor="middle" x="'+ ((size + rectSize) / 2) +'" y="0" fill="#333">Candidate</text>';

        for (let x = 0; x <= this.size; ++x) {
            let label = Math.floor(100 - (100 / this.size) * x);
            html += '<text font-size=".8rem" dominant-baseline="hanging" text-anchor="end" x="'+ (rectSize * (x + 1)) +'" y="'+ (rectSize / 2) +'" fill="#333">'+ label +'%</text>';
        }

        html += '<text transform="rotate(-90 0,'+ ((size + rectSize) / 2) +')" dominant-baseline="hanging" text-anchor="middle" x="0" y="'+ ((size + rectSize) / 2) +'" fill="#333">Query</text>';

        for (let y = 1; y <= this.size; ++y) {
            let label = Math.floor(100 - (100 / this.size) * y);
            html += '<text font-size=".8rem" dominant-baseline="auto" text-anchor="end" x="'+ rectSize +'" y="'+ (rectSize * (y + 1)) +'" fill="#333">'+ label +'%</text>';
        }
        svg.innerHTML = html;
    }
};

function parseParams(name) {
    const value = parseFloat(new URL(location.href).searchParams.get(name));
    return Number.isNaN(value) ? null : value;
}

function getPredictions(accession) {
    const params = [];
    const minSimilarity = parseParams('minsimilarity');
    if (minSimilarity !== null)
        params.push('minsimilarity=' + minSimilarity);

    if (document.querySelector('tfoot .checkbox input').checked)
        params.push('mincollocation=0.5');
    else
        params.push('mincollocation=0');

    const url = "/api/signature/" + accession + "/predictions2/?" + params.join('&');

    dimmer(true);
    fetch(url)
        .then(response => response.json())
        .then(signatures => {
            let html = '';

            signatures.forEach(s => {
                const predictions = new Map();
                let numTypes = 0;
                for (let value of Object.values(s.predictions)) {
                    numTypes++;
                    if (value === null)
                        continue;
                    else if (predictions.has(value))
                        predictions.set(value, predictions.get(value)+1);
                    else
                        predictions.set(value, 1);
                }

                let prediction = null;
                for (let [pred, count] of predictions.entries()) {
                    if (count > numTypes/2) {
                        prediction = pred;
                        break;
                    }
                }

                let circles = '<div class="ui tiny circular labels">';
                ['proteins', 'residues', 'descriptions', 'taxa', 'terms'].forEach(key => {
                    const value = s.predictions[key];
                    let labelClass;
                    if (value === 'Similar to')
                        labelClass = 'ui green label';
                    else if (value === 'Relates to')
                        labelClass = 'ui blue label';
                    else if (value === 'Parent of')
                        labelClass = 'ui violet label';
                    else if (value === 'Child of')
                        labelClass = 'ui purple label';
                    else
                        labelClass = 'ui red label';

                    if (key === 'proteins' || key === 'residues')
                        circles += '<span data-key="'+ key +'" class="'+ labelClass +'"></span>';
                    else
                        circles += '<span data-accession="'+ s.accession +'" data-key="'+ key +'" class="'+ labelClass +'"></span>';
                });
                circles += '</div>';

                html += '<tr>'
                    + '<td>'+ (prediction === null ? 'N/A' : prediction) +'</td><td class="collapsing">'+ circles +'</td>'
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
                if (title === 'descriptions')
                    content = 'Common UniProtKB descriptions';
                else if (title === 'proteins')
                    content = 'Overlapping proteins';
                else if (title === 'residues')
                    content = 'Overlapping residues';
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

                    fetch('/api/signature/'+ accession +'/comparison/'+ otherAcc +'/'+ key +'/')
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

                                        const union = (results[accession] + results[otherAcc] - results["common"]);
                                        const rect1Width = Math.floor(results[accession] * width / union);

                                        const rect2Width = Math.floor(results["common"] * width / union);
                                        const rect2X = Math.floor((results[accession] - results["common"]) * width / union);

                                        const rect3Width = Math.floor(results[otherAcc] * width / union);
                                        const rect3X = width - rect3Width;


                                        let svg = '<svg width="' + width + 'px" height="100px">'
                                            + '<text dominant-baseline="hanging" text-anchor="start" x="0" y="0" fill="#333">'+ accession +' ('+ results[accession].toLocaleString() +')</text>'
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
                            //console.log(window)
                            //console.log(modal.querySelector('.content').getC);

                        });
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
    fetch('/api/signature/'+ accession +'/')
        .then(response => {
            if (!response.ok)
                throw Error();
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

            const toggle = document.querySelector('tfoot .ui.toggle.checkbox');
            $(toggle).checkbox('set checked');
            $(toggle).checkbox({
                onChange: function () {
                    getPredictions(accession);
                }
            });

            (function () {
                const minSimilarity = parseParams('minsimilarity') || 0.75;
                const slider = document.getElementById('over-range');
                const span = document.getElementById('over-value');

                slider.value = minSimilarity;
                span.innerHTML = minSimilarity.toFixed(2);
                slider.addEventListener('change', e => {
                    const minSimilarity = parseFloat(e.target.value);
                    span.innerHTML = minSimilarity.toFixed(2);
                    const url = new URL(location.href);
                    url.searchParams.set("minsimilarity", minSimilarity);
                    history.replaceState(null, null, url.toString());
                    getPredictions(accession);
                });
                slider.addEventListener('input', evt => {
                    span.innerHTML = (parseFloat(evt.target.value)).toFixed(2);
                });
            })();

            getSignatureComments(accession, 2, document.querySelector('.ui.comments'));
            getPredictions(accession);
        })
        .catch(error => {
            document.querySelector('.ui.container.segment').innerHTML = '<div class="ui error message">'
                + '<div class="header">Signature not found</div>'
                + '<p><strong>'+ accession +'</strong> is not a valid member database signature accession.</p>'
                + '</div>';
        });
});