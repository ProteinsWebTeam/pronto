import * as ui from "../ui.js";
import {finaliseHeader} from "../header.js";

// Global variables for SVG
const matchHeight = 10;

function initSVG (svgWidth, rectWidth, proteinLength, numLines, numDiscDomains) {
    const step = Math.pow(10, Math.floor(Math.log(proteinLength) / Math.log(10))) / 2;

    // Create a dummy SVG to compute the length of a text element
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', '100px');
    svg.setAttribute('height', '100px');
    svg.setAttribute('version', '1.1');
    svg.innerHTML = '<g class="ticks"><text x="50" y="50">'+ proteinLength.toLocaleString() +'</text></g>';
    document.body.appendChild(svg);
    const textLength = svg.querySelector('text').getComputedTextLength();
    document.body.removeChild(svg);

    const rectHeight = matchHeight + numDiscDomains * matchHeight * 3 + numLines * matchHeight * 2;
    let content = '<svg width="' + svgWidth + '" height="'+ (rectHeight + 10) +'" version="1.1" baseProfile="full" xmlns="http://www.w3.org/2000/svg">';
    content += '<rect x="0" y="0" height="'+ rectHeight +'" width="'+ rectWidth +'" style="fill: #eee;"/>';
    content += '<g class="ticks">';

    for (let pos = step; pos < proteinLength; pos += step) {
        const x = Math.round(pos * rectWidth / proteinLength);

        if (x + textLength / 2 >= rectWidth)
            break;

        content += '<line x1="'+ x +'" y1="0" x2="'+ x +'" y2="' + rectHeight + '" />';
        content += '<text x="' + x + '" y="'+ rectHeight +'">' + pos.toLocaleString() + '</text>';
    }

    content += '<line x1="'+ rectWidth +'" y1="0" x2="'+ rectWidth +'" y2="' + rectHeight + '" />';
    content += '<text x="' + rectWidth + '" y="'+ rectHeight +'">' + proteinLength.toLocaleString() + '</text>';
    return content + '</g>';
}


function distributeVertically(src) {
    const dst = [];
    src.forEach(feature => {
        let lines = [];

        feature.matches.forEach(fragments => {
            fragments.forEach(fragment => {
                let newLine = true;
                for (let lineFrags of lines) {
                    if (fragment.start > lineFrags[lineFrags.length-1].end) {
                        lineFrags.push(fragment);
                        newLine = false;
                        break;
                    }
                }

                if (newLine)
                    lines.push([fragment]);
            });
        });

        lines.forEach(lineFrags => {
            const newFeature = JSON.parse(JSON.stringify(feature));
            newFeature.matches = lineFrags.map(frag => [frag]);
            dst.push(newFeature);
        });
    });

    return dst;
}

function renderFeatures(svgWidth, rectWidth, proteinLength, features, multiLine = false, labelLink = true) {
    if (!features.length)
        return '<p>None</p>';

    if (multiLine)
        features = distributeVertically(features);

    const numDiscDomains = features.reduce((acc, cur) => {
        // Increase if at least one match has more than one fragment (i.e. discontinuous domain)
        if (cur.matches.filter(fragments => fragments.length > 1).length)
            return acc + 1;
        else
            return acc;
    }, 0);

    let html = initSVG(svgWidth, rectWidth, proteinLength, features.length, numDiscDomains);

    let y = matchHeight;
    features.forEach((feature, i) => {
        if (feature.matches.filter(fragments => fragments.length > 1).length) {
            // has at least one disc domains (need more space for arcs)
            y += matchHeight * 3;
        }

        feature.matches.forEach(fragments => {
            html += '<g class="match">';

            fragments.forEach((fragment, j) => {
                const x = Math.round(fragment.start * rectWidth / proteinLength);
                const w = Math.round((fragment.end - fragment.start) * rectWidth / proteinLength);

                if (j) {
                    // Discontinuous domain: draw arc
                    const px = Math.round(fragments[j-1].end * rectWidth / proteinLength);
                    const x1 = (px + x) / 2;
                    const y1 = y - matchHeight * 6;
                    html += '<path d="M'+ px +' '+ y +' Q '+ [x1, y1, x, y].join(' ') +'" fill="none" stroke="'+ feature.color +'"/>'
                }

                html += '<rect data-start="'+ fragment.start +'" data-end="'+ fragment.end +'" data-id="'+ feature.accession +'" ' +
                    'data-name="'+ (feature.name ? feature.name : '') +'" data-db="'+ feature.database +'" data-link="'+ feature.link +'" x="'+ x +'" y="' + y + '" ' +
                    'width="' + w + '" height="'+ matchHeight +'" rx="1" ry="1" style="fill: '+ feature.color +'"/>';
            });

            html += '</g>';
        });

        if (labelLink)
            html += '<text class="label" x="' + (rectWidth + 10) + '" y="'+ (y + matchHeight / 2) +'"><a href="/prediction/'+ feature.accession +'/">'+ feature.accession +'</a></text>';
        else
            html += '<text class="label" x="' + (rectWidth + 10) + '" y="'+ (y + matchHeight / 2) +'">'+ feature.accession +'</text>';

        y += matchHeight * 2;
    });

    return html + '</svg>';
}


$(function () {
    ui.dimmer(true);

    // Get page width for SVG
    const div = document.querySelector('#integrated + div');
    const svgWidth = div.offsetWidth;
    const rectWidth = svgWidth - 200;

    const tooltip = {
        element: document.getElementById('tooltip'),
        isInit: false,
        active: false,

        show: function(rect) {
            this.active = true;
            this.element.style.display = 'block';
            this.element.style.top = Math.round(rect.top - this.element.offsetHeight + window.scrollY - 5).toString() + 'px';
            this.element.style.left = Math.round(rect.left + rect .width / 2 - this.element.offsetWidth / 2).toString() + 'px';

        },
        _hide: function () {
            if (!this.active)
                this.element.style.display = 'none';
        },
        hide: function () {
            this.active = false;
            setTimeout(() => {
                this._hide();
            }, 500);
        },
        update: function (id, name, start, end, dbName, link) {
            let content = '<div class="header">' + start.toLocaleString() + ' - ' + end.toLocaleString() +'</div>';

            if (name.length)
                content += '<div class="meta">'+ name +'&nbsp;&ndash;&nbsp;'+ dbName +'</div>';
            else
                content += '<div class="meta">'+ dbName +'</div>';

            content += '<div class="description"><a target="_blank" href="'+ link +'">'+ id +'&nbsp;<i class="external icon"></i></div>';

            this.element.querySelector('.content').innerHTML = content;
        },
        init: function () {
            if (this.isInit)
                return;

            this.isInit = true;

            this.element.addEventListener('mouseenter', e => {
                this.active = true;
            });

            this.element.addEventListener('mouseleave', e => {
                this.hide();
            });

            this.element.querySelector('.close').addEventListener('click', e => {
                this.element.style.display = 'none';
            });
        }
    };

    tooltip.init();

    finaliseHeader();

    const proteinAcc = location.pathname.match(/\/protein\/([a-z0-9]+)\/$/i)[1];
    fetch("/api/protein/" + proteinAcc + "/")
        .then(response => {
            ui.dimmer(false);
            if (response.status === 200)
                return response.json();
            else {
                document.querySelector('.ui.container.segment').innerHTML = '<div class="ui error message">'
                    + '<div class="header">Protein not found</div>'
                    + '<strong>'+ proteinAcc +'</strong> is not a valid UniProtKB accession.'
                    + '</div>';
                return null;
            }
        })
        .then(protein => {
            if (protein === null) return;
            document.title = protein.description + " (" + protein.accession + ") | Pronto";

            // Header
            (function () {
                document.querySelector("h1.ui.header").innerHTML = protein.description + " (" + protein.identifier + ")"
                    + '<div class="sub header">'
                    + '<a target="_blank" href="'+ protein.link +'">'
                    + (protein.is_reviewed ? '<i class="star icon"></i>&nbsp;' : '') + protein.accession
                    + '&nbsp;<i class="external icon"></i>'
                    + '</a>'
                    + '</div>';
            })();

            // Statistics
            document.getElementById("organism").innerText = (function () {
                const words = protein.taxon.full_name.split(' ');
                return words[0].charAt(0) + '. ' + words.slice(1).join(' ');
            })();
            document.getElementById("length").innerText = protein.length.toLocaleString();
            document.getElementById("entries").innerText = protein.entries.length;
            document.getElementById("signatures").innerText = (function () {
                const reducer = (acc, cur) => acc + cur.signatures.length;
                return protein.unintegrated.length + protein.entries.reduce(reducer, 0);
            })();


            // Warning message about the sequence being a fragment
            if (!protein.is_fragment)
                ui.setClass(document.querySelector(".ui.warning.message"), "hidden", true);

            // Integrated signatures
            (function () {
                const entries = protein.entries;
                entries.sort((a, b) => {
                    const codes = ["H", "F", "D"];
                    const i = codes.indexOf(a.type_code);
                    const j = codes.indexOf(b.type_code);

                    if (i === j)
                        return a.accession.localeCompare(b.accession);
                    else if (i === -1)
                        return 1;
                    else if (j === -1)
                        return -1;
                    else
                        return i - j;
                });

                let html = '';
                entries.forEach(entry => {
                    html += '<h3 class="ui header">'
                        + '<span class="ui tiny type-'+ entry.type_code +' circular label">'+ entry.type_code +'</span>&nbsp;'
                        + '<a href="/entry/'+ entry.accession +'/">'+ entry.accession +'</a>'
                        + '<div class="sub header">'+ entry.name +'</div>'
                        + '</h3>';

                    html += renderFeatures(svgWidth, rectWidth, protein.length, entry.signatures);
                });

                document.querySelector('#integrated + div').innerHTML = html;
            })();

            // Unintegrated signatures
            document.querySelector('#unintegrated + div').innerHTML = renderFeatures(svgWidth, rectWidth, protein.length, protein.unintegrated);

            // Disordered regions
            document.querySelector('#disordered-regions + div').innerHTML = renderFeatures(svgWidth, rectWidth, protein.length, protein.mobidblite, true, false);

            Array.from(document.querySelectorAll('rect[data-id]')).forEach(rect => {
                rect.addEventListener('mouseenter', e => {
                    const target = e.target;

                    tooltip.update(
                        target.getAttribute('data-id'),
                        target.getAttribute('data-name'),
                        parseInt(target.getAttribute('data-start'), 10),
                        parseInt(target.getAttribute('data-end'), 10),
                        target.getAttribute('data-db'),
                        target.getAttribute('data-link')
                    );
                    tooltip.show(target.getBoundingClientRect());
                });

                rect.addEventListener('mouseleave', e => {
                    tooltip.hide();
                });
            });

            $(document.querySelector('.ui.sticky')).sticky({
                context: document.querySelector('.twelve.column')
            });

            ui.listenMenu(document.querySelector('.ui.vertical.menu'));
        });
});