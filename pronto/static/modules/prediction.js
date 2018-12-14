import {dimmer, renderCheckbox, openErrorModal} from "../ui.js";
import {finaliseHeader} from "../header.js";
import {getSignatureComments, postSignatureComment} from "../comments.js";
import {nvl} from "../utils.js";
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

function useWhiteText(color) {
    // Implementation of https://www.w3.org/TR/WCAG20/

    const copy = JSON.parse(JSON.stringify(color));
    ['r', 'g', 'b'].forEach(k => {
        copy[k] /= 255;

        if (copy[k] <= 0.03928)
            copy[k] /= 12.92;
        else
            copy[k] = Math.pow((copy[k] + 0.055) / 1.055, 2.4);
    });

    // luminance formula: https://www.w3.org/TR/WCAG20/#relativeluminancedef
    const l = 0.2126 * copy.r + 0.7152 * copy.g + 0.0722 * copy.b;
    return l <= 0.179;
}

function toRGB(color) {
    return 'rgb('+ color.r +','+ color.g +','+ color.b +')';
}

function getOverlap() {
    let overlap = parseFloat(new URL(location.href).searchParams.get("overlap"));
    return Number.isNaN(overlap) ? null : overlap;
}

function getPredictions(accession) {
    let url = "/api/signature/" + accession + "/predictions/";
    let overlap = getOverlap();
    if (overlap !== null)
        url += "?overlap=" + overlap;

    dimmer(true);
    fetch(url)
        .then(response => response.json())
        .then(signatures => {
            let html = "";
            signatures.forEach(s => {
                let queryRatio = Math.min(s.n_proteins / s.query.n_proteins, 1);
                let candidateRatio = Math.min(s.n_proteins / s.candidate.n_proteins, 1);
                let x = overlapHeatmap.size - Math.floor(candidateRatio * overlapHeatmap.size);
                let y = overlapHeatmap.size - Math.floor(queryRatio * overlapHeatmap.size);

                if (x >= overlapHeatmap.size)
                    x = overlapHeatmap.size - 1;

                if (y >= overlapHeatmap.size)
                    y = overlapHeatmap.size - 1;

                const c1 = overlapHeatmap.getPixel(x, y);

                queryRatio = Math.min(s.n_overlaps / s.query.n_matches, 1);
                candidateRatio = Math.min(s.n_overlaps / s.candidate.n_matches, 1);
                x = overlapHeatmap.size - Math.floor(candidateRatio * overlapHeatmap.size);
                y = overlapHeatmap.size - Math.floor(queryRatio * overlapHeatmap.size);

                if (x >= overlapHeatmap.size)
                    x = overlapHeatmap.size - 1;

                if (y >= overlapHeatmap.size)
                    y = overlapHeatmap.size - 1;

                const c2 = overlapHeatmap.getPixel(x, y);

                if (s.accession === accession)
                    html += '<tr class="active">';
                else
                    html += '<tr>';

                html += '<td>'+ nvl(s.relation, "") +'</td>'
                    + '<td>'
                    + '<a href="/prediction/'+ s.accession +'/">'+ s.accession +'</a>'
                    + '</td>';

                if (s.link !== null) {
                    html += '<td class="collapsing">'
                        + '<a target="_blank" href="'+ s.link +'">'
                        + '<i class="external icon"></i>'
                        + '</a>'
                        + '</td>';
                } else
                    html += '<td></td>';

                html += '<td class="collapsing">'
                    + '<a href="#" data-add-id="'+ s.accession +'">'
                    + '<i class="cart plus icon"></i>'
                    + '</a>'
                    + '</td>'
                    + '<td class="right aligned">' + s.candidate.n_proteins.toLocaleString() + '</td>'
                    + '<td class="right aligned">' + s.candidate.n_matches.toLocaleString() + '</td>';

                if (useWhiteText(c1))
                    html += '<td class="light right aligned" style="background-color: '+ toRGB(c1) +'">';
                else
                    html += '<td class="dark right aligned" style="background-color: '+ toRGB(c1) +'">';
                html += s.n_proteins.toLocaleString() + '</td>';

                if (useWhiteText(c2))
                    html += '<td class="light right aligned" style="background-color: '+ toRGB(c2) +'">';
                else
                    html += '<td class="dark right aligned" style="background-color: '+ toRGB(c2) +'">';
                html += s.n_overlaps.toLocaleString() + '</td>';

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
                        + '<a href="/entry/'+ s.entry.accession +'/">'+ s.entry.accession +'</a>'
                        + '</div>'
                        + '</div>'
                        + '</td>'
                        + '<td>'+ s.entry.name +'</td>'
                        + '<td>'+ renderCheckbox(s.entry.accession, s.entry.checked) +'</td>'
                        + '</tr>';
                } else
                    html += '<td></td><td></td><td></td>';
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

            dimmer(false);
        });
}


$(function () {
    const match = location.pathname.match(/^\/prediction\/([^\/]+)/i);
    const accession = match[1];
    selector.init(document.getElementById('methods'), accession);
    document.title = accession + " predictions | Pronto";
    document.querySelector("h1.ui.header .sub").innerHTML = accession;

    overlapHeatmap.calcPixels();
    overlapHeatmap.render();

    // Init Semantic-UI elements
    $('[data-content]').popup();

    (function () {
        const overlap = getOverlap() || 0.3;
        const slider = document.getElementById('over-range');
        const span = document.getElementById('over-value');

        slider.value = overlap;
        span.innerHTML = (overlap * 100).toFixed(0);
        slider.addEventListener('change', e => {
            const overlap = parseFloat(e.target.value);
            span.innerHTML = (overlap * 100).toFixed(0);
            const url = new URL(location.href);
            url.searchParams.set("overlap", overlap);
            history.replaceState(null, null, url.toString());
            getPredictions(accession);
        });
        slider.addEventListener('input', evt => {
            span.innerHTML = (parseFloat(evt.target.value) * 100).toFixed(0);
        });
    })();

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
                    openErrorModal(result.message);
            });
    });

    finaliseHeader();
    getPredictions(accession);
    getSignatureComments(accession, 2, document.querySelector('.ui.comments'));
});