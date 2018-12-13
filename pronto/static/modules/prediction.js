import * as ui from "../ui.js";
import {finaliseHeader} from "../header.js";
import {getSignatureComments} from "../comments.js";
import {nvl} from "../utils.js";

function calcPixelSlope(p1, p2, distance) {
    return {
        r: (p2.r - p1.r) / distance,
        g: (p2.g - p1.g) / distance,
        b: (p2.b - p1.b) / distance
    }
}

function calcPixelGradient(startingPixel, distance, slope) {
    return {
        r: startingPixel.r + slope.r * distance,
        g: startingPixel.g + slope.g * distance,
        b: startingPixel.b + slope.b * distance
    }
}

function drawHeatmap(pixels, numRect) {
    const heatmap = document.getElementById('heatmap');

    // Draw heatmap
    const svg = heatmap.querySelector('svg');
    const size = heatmap.offsetWidth;

    svg.setAttribute('width', size.toString());
    svg.setAttribute('height', size.toString());
    const rectSize = Math.floor(size / (numRect + 1));

    let html = '';
    pixels.forEach(p => {
        html += '<rect x="'+ ((p.x + 1) * rectSize) +'" y="'+ ((p.y + 1) * rectSize) +'" width="'+ (rectSize) +'" height="'+ (rectSize) +'" fill="'+ p.c +'"></rect>';
    });

    html += '<text dominant-baseline="hanging" text-anchor="middle" x="'+ ((size + rectSize) / 2) +'" y="0" fill="#333">Candidate</text>';
    for (let x = 0; x <= numRect; ++x) {
        let label = Math.floor(100 - (100 / numRect) * x);
        html += '<text font-size=".8rem" dominant-baseline="hanging" text-anchor="end" x="'+ (rectSize * (x + 1)) +'" y="'+ (rectSize / 2) +'" fill="#333">'+ label +'%</text>';
    }

    html += '<text transform="rotate(-90 0,'+ ((size + rectSize) / 2) +')" dominant-baseline="hanging" text-anchor="middle" x="0" y="'+ ((size + rectSize) / 2) +'" fill="#333">Query</text>';
    for (let y = 1; y <= numRect; ++y) {
        let label = Math.floor(100 - (100 / numRect) * y);
        html += '<text font-size=".8rem" dominant-baseline="auto" text-anchor="end" x="'+ rectSize +'" y="'+ (rectSize * (y + 1)) +'" fill="#333">'+ label +'%</text>';
    }
    svg.innerHTML = html;
}

function findPixel(pixels, x, y) {
    for (let i = 0; i < pixels.length; ++i) {
        if (pixels[i].x === x && pixels[i].y === y)
            return pixels[i].c;
    }

    return null;
}

function _getPredictions(methodID, overlapThreshold, pixels, numRect, getComments, methodSelectionView) {
    utils.dimmer(true);

    const params = utils.extendObj(utils.parseLocation(location.search), {overlap: overlapThreshold});
    const url = '/api/method/' + methodID + '/prediction/' + utils.encodeParams(params);
    utils.getJSON(url, (data, status) => {
        // Update header
        document.querySelector('h1.ui.header .sub').innerText = methodID;

        // Render table
        let html = '';
        data.results.forEach(m => {
            const qRatio = Math.min(m.nProts / m.nProtsQuery, 1);
            const cRatio = Math.min(m.nProts / m.nProtsCand, 1);
            let x = numRect - Math.floor(cRatio * numRect);
            let y = numRect - Math.floor(qRatio * numRect);

            const c1 = findPixel(
                pixels,
                x < numRect ? x : x - 1,
                y < numRect ? y : y - 1
            );

            const qBlob = Math.min(m.nBlobs / m.nBlobsQuery, 1);
            const cBlob = Math.min(m.nBlobs / m.nBlobsCand, 1);
            x = numRect - Math.floor(cBlob * numRect);
            y = numRect - Math.floor(qBlob * numRect);

            const c2 = findPixel(
                pixels,
                x < numRect ? x : x - 1,
                y < numRect ? y : y - 1
            );

            html += '<tr '+ (m.id === methodID ? 'class="active"' : '') +'>' +
                '<td>'+ utils.nvl(m.relation, '') +'</td>' +
                '<td><a href="/method/'+ m.id +'/">' + m.id + '</a></td>' +
                '<td class="collapsing">'+ (m.dbLink ? '<a target="_blank" href="'+ m.dbLink +'"><i class="external icon"></i></a>' : '') +'</td>' +
                '<td class="collapsing"><a href="#" data-add-id="'+ m.id +'"><i class="cart plus icon"></i></a></td>' +
                // '<td>'+ m.dbShort +'</td>' +
                '<td>'+ m.nProtsCand.toLocaleString() +'</td>' +
                '<td>'+ m.nBlobsCand.toLocaleString() +'</td>' +
                '<td class="'+ (utils.useWhiteText(c1) ? 'light' : 'dark') +'" style="background-color: '+ c1 +';">'+ m.nProts.toLocaleString() +'</td>' +
                '<td class="'+ (utils.useWhiteText(c2) ? 'light' : 'dark') +'" style="background-color: '+ c2 +';">'+ m.nBlobs.toLocaleString() +'</td>';

            if (m.entryId) {
                html += '<td class="nowrap"><div class="ui list">';

                m.entryHierarchy.forEach(e => {
                    html += '<div class="item"><div class="content"><i class="angle down icon"></i><a href="/entry/'+ e +'/">' + e + '</a></div></div>';
                });

                html += '<div class="item"><div class="content"><span class="ui circular mini label type-'+ m.entryType +'">'+ m.entryType +'</span><a href="/entry/'+ m.entryId +'/">' + m.entryId + '</a></div></div></td>';
                html += '<td>' + m.entryName + '</td>';
            } else
                html += '<td></td><td></td>';

            html += '<td>'+ utils.renderCheckbox(m.entryId, m.isChecked) +'</td>';
        });

        document.querySelector('tbody').innerHTML = html;

        utils.dimmer(false);

        // Get comments
        if (getComments) {
            utils.getComments(document.querySelector('.ui.comments'), 'method', methodID, 2, function () {
                drawHeatmap(pixels, numRect);
            });
        }

        // (Un)check entries
        Array.from(document.querySelectorAll('tbody input[type=checkbox]')).forEach(input => {
            input.addEventListener('change', e => {
                utils.openConfirmModal(
                    (input.checked ? 'Check' : 'Uncheck') + ' entry?',
                    '<strong>' + input.name + '</strong> will be marked as ' + (input.checked ? 'checked' : 'unchecked'),
                    (input.checked ? 'Check' : 'Uncheck'),
                    function () {
                        utils.post('/api/entry/' + input.name + '/check/', {
                            checked: input.checked ? 1 : 0
                        }, data => {
                            if (data.status) {
                                const cboxes = document.querySelectorAll('input[type=checkbox][name="'+ input.name +'"]');
                                for (let i = 0; i < cboxes.length; ++i)
                                    cboxes[i].checked = input.checked;
                            } else {
                                const modal = document.getElementById('error-modal');
                                modal.querySelector('.content p').innerHTML = data.message;
                                $(modal).modal('show');
                            }
                        });
                    },
                    function () {
                        input.checked = !input.checked;
                    }
                );
            });
        });

        // Adding/removing signatures
        Array.from(document.querySelectorAll('tbody a[data-add-id]')).forEach(elem => {
            elem.addEventListener('click', e => {
                e.preventDefault();
                methodSelectionView.add(elem.getAttribute('data-add-id')).render();
            });
        });

        // Add current signature
        methodSelectionView.add(methodID).render();
    });
}


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


function getPredictions(accession) {
    fetch("/api/signature/" + accession + "/predictions/")
        .then(response => response.json())
        .then(signatures => {
            let html = "";
            signatures.forEach(s => {
                let queryRatio = Math.min(s.n_proteins / s.query.n_proteins, 1);
                let candidateRatio = Math.min(s.n_proteins / s.candidate.n_proteins, 1);
                let x = overlapHeatmap.size - Math.floor(queryRatio * overlapHeatmap.size);
                let y = overlapHeatmap.size - Math.floor(candidateRatio * overlapHeatmap.size);

                if (x >= overlapHeatmap.size)
                    x = overlapHeatmap.size - 1;

                if (y >= overlapHeatmap.size)
                    y = overlapHeatmap.size - 1;

                const c1 = overlapHeatmap.getPixel(x, y);

                queryRatio = Math.min(s.n_overlaps / s.query.n_matches, 1);
                candidateRatio = Math.min(s.n_overlaps / s.candidate.n_matches, 1);
                x = overlapHeatmap.size - Math.floor(queryRatio * overlapHeatmap.size);
                y = overlapHeatmap.size - Math.floor(candidateRatio * overlapHeatmap.size);

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
                    + '<td>' + s.candidate.n_proteins.toLocaleString() + '</td>'
                    + '<td>' + s.candidate.n_matches.toLocaleString() + '</td>';

                if (useWhiteText(c1))
                    html += '<td class="light" style="background-color: '+ toRGB(c1) +'">';
                else
                    html += '<td class="dark" style="background-color: '+ toRGB(c1) +'">';
                html += s.n_proteins.toLocaleString() + '</td>';

                if (useWhiteText(c2))
                    html += '<td class="light" style="background-color: '+ toRGB(c2) +'">';
                else
                    html += '<td class="dark" style="background-color: '+ toRGB(c2) +'">';
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
                        + '<td>'+ ui.renderCheckbox(s.entry.accession, s.entry.checked) +'</td>'
                        + '</tr>';
                }
            });

            document.querySelector("tbody").innerHTML = html;
        });
}


$(function () {
    overlapHeatmap.calcPixels();

    finaliseHeader();
    const match = location.pathname.match(/^\/prediction\/([^\/]+)/i);
    const accession = match[1];
    getSignatureComments(accession, 2, document.querySelector('.ui.comments'));
    getPredictions(accession);




    return;

    // const pathName = location.pathname;
    //
    // const match = pathName.match(/^\/method\/([^\/]+)/i);
    // if (!match) {
    //     return;
    // }

    const methodID = match[1];
    let params = utils.parseLocation(location.search);

    // Compute gradient
    const heatmap = document.getElementById('heatmap');
    const colors = heatmap.getAttribute('data-colors').split(',');
    const numRect = parseInt(heatmap.getAttribute('data-size'), 10);
    const pixels = [];
    const topLeft = utils.hex2rgb(colors[0]);
    const topRight = utils.hex2rgb(colors[1]);
    const bottomLeft = utils.hex2rgb(colors[2]);
    const bottomRight = utils.hex2rgb(colors[3]);

    // Color slopes
    const leftToRightTop = calcPixelSlope(topLeft, topRight, numRect);
    const leftToRightBottom = calcPixelSlope(bottomLeft, bottomRight, numRect);

    // Interpolate from left to right, then top to bottom
    for (let x = 0; x < numRect; ++x) {
        let p1 = calcPixelGradient(topLeft, x, leftToRightTop);
        let p2 = calcPixelGradient(bottomLeft, x, leftToRightBottom);

        for (let y = 0; y < numRect; ++y) {
            let topToBottom = calcPixelSlope(p1, p2, numRect);
            let p = calcPixelGradient(p1, y, topToBottom);
            pixels.push({
                x: x,  // origin is top left corner, but we want the bottom right corner
                y: y,
                c: utils.rgb2hex(p)
            });
        }
    }

    // Adding comments
    document.querySelector('.ui.comments form button').addEventListener('click', e => {
        e.preventDefault();
        const form = e.target.closest('form');
        const textarea = form.querySelector('textarea');

        utils.post('/api/method/'+ methodID +'/comment/', {
            comment: textarea.value.trim()
        }, data => {
            utils.setClass(textarea.closest('.field'), 'error', !data.status);

            if (!data.status) {
                const modal = document.getElementById('error-modal');
                modal.querySelector('.content p').innerHTML = data.message;
                $(modal).modal('show');
            } else
                utils.getComments(document.querySelector('.ui.comments'), 'method', methodID, 2, function () {
                    drawHeatmap(pixels, numRect);
                });
        });
    });

    // Range event
    const slider = document.getElementById('over-range');
    const span = document.getElementById('over-value');
    let overlapThreshold;

    if (params.overlap !== undefined) {
        overlapThreshold = params.overlap;
        slider.value = overlapThreshold;
    } else
        overlapThreshold = parseFloat(slider.value);

    span.innerHTML = (overlapThreshold * 100).toFixed(0);
    slider.addEventListener('change', evt => {
        overlapThreshold = parseFloat(evt.target.value);
        span.innerHTML = (overlapThreshold * 100).toFixed(0);
        const params = utils.extendObj(utils.parseLocation(location.search), {overlap: overlapThreshold});
        history.replaceState(null, null, location.pathname + utils.encodeParams(params));
        getPredictions(methodID, overlapThreshold, pixels, numRect, false, msv);
    });
    slider.addEventListener('input', evt => {
        span.innerHTML = (parseFloat(evt.target.value) * 100).toFixed(0);
    });

    // Init Semantic-UI elements
    $('[data-content]').popup();

    // Instantiate selection view
    const msv = new utils.MethodsSelectionView(document.getElementById('methods'));

    getPredictions(methodID, overlapThreshold, pixels, numRect, true, msv);
});