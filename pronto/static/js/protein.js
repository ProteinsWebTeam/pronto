import * as dimmer from "./ui/dimmer.js"
import {updateHeader} from "./ui/header.js"
import {setClass} from "./ui/utils.js";
import {listenMenu} from "./ui/menu.js";
import {genProtHeader} from "./ui/proteins.js";

// Global variables for SVG
const matchHeight = 10;
let svgWidth;
let rectWidth;

function initSVG (proteinLength, numLines, numDiscDomains) {
    const step = Math.pow(10, Math.floor(Math.log(proteinLength) / Math.log(10))) / 2;

    // Create a dummy SVG to compute the length of a text element
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', '100px');
    svg.setAttribute('height', '100px');
    svg.innerHTML = `<g class="ticks"><text x="50" y="50">${proteinLength.toLocaleString()}</text></g>`;
    document.body.appendChild(svg);
    const textLength = svg.querySelector('text').getComputedTextLength();
    document.body.removeChild(svg);

    const rectHeight = matchHeight + numDiscDomains * matchHeight * 3 + numLines * matchHeight * 2;
    let content = `<svg width="${svgWidth}" height="${rectHeight + 10}">`;
    content += `<rect x="0" y="0" height="${rectHeight}" width="${rectWidth}" style="fill: #eee;"/>`;
    content += '<g class="ticks">';

    for (let pos = step; pos < proteinLength; pos += step) {
        const x = Math.round(pos * rectWidth / proteinLength);

        if (x + textLength >= rectWidth)
            break;

        content += `<line x1="${x}" y1="0" x2="${x}" y2="${rectHeight}" />`;
        content += `<text x="${x}" y="${rectHeight}">${pos.toLocaleString()}</text>`;
    }

    return `${content}
            <line x1="${rectWidth}" y1="0" x2="${rectWidth}" y2="${rectHeight}" />
            <text x="${rectWidth}" y="${rectHeight}">${proteinLength.toLocaleString()}</text>
            </g>`;
}

function distributeVertically(src) {
    const dst = [];
    for (const feature of src) {
        let lines = [];

        for (const fragments of feature.matches) {
            for (const fragment of fragments) {
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
            }
        }

        for (const lineFrags of lines) {
            const newFeature = JSON.parse(JSON.stringify(feature));
            newFeature.matches = lineFrags.map(frag => [frag]);
            dst.push(newFeature);
        }
    }

    return dst;
}

function renderFeatures(proteinLength, features, multiLine = false, labelLink = true) {
    if (!features.length)
        return '<p>No protein matches</p>';

    if (multiLine)
        features = distributeVertically(features);

    const numDiscDomains = features.reduce((acc, cur) => {
        // Increase if at least one match has more than one fragment (i.e. discontinuous domain)
        if (cur.matches.filter(fragments => fragments.length > 1).length)
            return acc + 1;
        else
            return acc;
    }, 0);

    let html = initSVG(proteinLength, features.length, numDiscDomains);

    let y = matchHeight;
    for (const feature of features) {
        if (feature.matches.filter(fragments => fragments.length > 1).length) {
            // has at least one disc domains (need more space for arcs)
            y += matchHeight * 3;
        }

        for (const fragments of feature.matches) {
            html += '<g class="match">';

            for (let i = 0; i < fragments.length; i++) {
                const fragment = fragments[i];
                const x = Math.round(fragment.start * rectWidth / proteinLength);
                const w = Math.round((fragment.end - fragment.start) * rectWidth / proteinLength);

                if (i) {
                    // Discontinuous domain: draw arc
                    const px = Math.round(fragments[i-1].end * rectWidth / proteinLength);
                    const x1 = (px + x) / 2;
                    const y1 = y - matchHeight * 6;
                    html += `<path d="M${px} ${y} Q ${x1} ${y1} ${x} ${y}" fill="none" stroke="${feature.color}"/>`;
                }

                html += `<rect data-start="${fragment.start}" data-end="${fragment.end}" data-id="${feature.accession}" 
                               data-name="${feature.name ? feature.name : ''}" data-db="${feature.database}" 
                               data-link="${feature.link ? feature.link : ''}" x="${x}" y="${y}" width="${w}" height="${matchHeight}" 
                               rx="1" ry="1" style="fill: ${feature.color}"/>`;
            }

            html += '</g>';
        }

        if (labelLink)
            html += `<text class="label" x="${rectWidth+10}" y="${y+matchHeight/2}"><a href="/signature/${feature.accession}/">${feature.accession}</a></text>`;
        else
            html += `<text class="label" x="${rectWidth+10}" y="${y+matchHeight/2}">${feature.accession}</text>`;

        y += matchHeight * 2;
    }

    return html + '</svg>';
}

document.addEventListener('DOMContentLoaded', () => {
    const div = document.querySelector('#integrated + div');
    svgWidth = div.offsetWidth;
    rectWidth = svgWidth - 200;

    const tooltip = {
        element: document.getElementById('tooltip'),
        isInit: false,
        active: false,
        lockedOn: null,

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
            if (this.lockedOn !== null)  return;
            this.active = false;
            setTimeout(() => {
                this._hide();
            }, 500);
        },
        update: function (id, name, start, end, dbName, link) {
            if (this.lockedOn !== id)
                this.lockedOn = null;

            let content = `<div class="header">${start.toLocaleString()} - ${end.toLocaleString()}</div>`;

            if (name.length)
                content += `<div class="meta">${name}&nbsp;&ndash;&nbsp;${dbName}</div>`;
            else
                content += `<div class="meta">${dbName}</div>`;

            if (link.length)
                content += `<div class="description"><a target="_blank" href="${link}">${id}&nbsp;<i class="external icon"></i></div>`;
            else
                content += `<div class="description">${id}</div>`;

            this.element.querySelector('.content').innerHTML = content;
        },
        lock: function (id) {
            this.lockedOn = id;
        },
        unlock: function () {
            this.lockedOn = null;
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

    updateHeader();

    dimmer.on();
    fetch(`/api${location.pathname}?matches&lineage`)
        .then(response => {
            if (!response.ok)
                throw Error();
            return response.json();
        })
        .then(protein => {
            document.title = `${protein.name} (${protein.accession}) | Pronto`;
            document.querySelector('h1.ui.header').innerHTML = genProtHeader(protein);

            if (!protein.is_fragment)
                setClass(document.querySelector('.ui.warning'), 'hidden', true);

            const entries = new Map();
            const unintegrated = [];
            const extra = [];
            for (const signature of protein.signatures) {
                if (!signature.is_signature)
                    // Only non-signatures don't have a sign_acc
                    extra.push(signature);
                else if (signature.entry === null)
                    unintegrated.push(signature);
                else if (entries.has(signature.entry.accession))
                    entries.get(signature.entry.accession).push(signature);
                else
                    entries.set(signature.entry.accession, [signature]);
            }

            // Integrated signatures
            let html = '';
            if (entries.size) {
                for (const key of [...entries.keys()].sort((a, b) => a.localeCompare(b))) {
                    const signatures = entries.get(key);
                    const entry = signatures[0].entry;
                    html += `<h3 class="ui header">
                            <span class="ui tiny type ${entry.type} circular label">${entry.type}</span>
                            <a href="/entry/${entry.accession}/">${entry.accession}</a>
                            <div class="sub header">${entry.name}</div>
                         </h3>`;

                    html += renderFeatures(protein.length, signatures);
                }
            } else
                html += '<p>No protein matches</p>';

            // Integrated signatures
            document.querySelector('#integrated + div').innerHTML = html;

            // Unintegrated signatures
            document.querySelector('#unintegrated + div').innerHTML = renderFeatures(protein.length, unintegrated);

            // Extra features
            document.querySelector('#others + div').innerHTML = renderFeatures(protein.length, extra, true, false);

            // Lineage
            html = '';
            for (const organism of protein.organism.lineage) {
                html += `
                    <div class="item">
                    <i class="angle down icon"></i>
                    <div class="content">${organism}</div>
                    </div>                
                `;
            }
            document.querySelector('#lineage + .ui.list').innerHTML = html;

            for (const rect of document.querySelectorAll('rect[data-id]')) {
                rect.addEventListener('mouseenter', e => {
                    const target = e.currentTarget;

                    tooltip.update(
                        target.dataset.id,
                        target.dataset.name,
                        parseInt(target.dataset.start, 10),
                        parseInt(target.dataset.end, 10),
                        target.dataset.db,
                        target.dataset.link
                    );
                    tooltip.show(target.getBoundingClientRect());
                });

                rect.addEventListener('click', e => {
                    tooltip.lock(e.currentTarget.dataset.id);
                });

                rect.addEventListener('mouseleave', e => {
                    tooltip.hide();
                });
            }

        })
        .finally(() => {
            $(document.querySelector('.ui.sticky')).sticky({
                context: document.querySelector('.twelve.column')
            });
            listenMenu(document.querySelector('.ui.vertical.menu'));

            dimmer.off();
        });
});
