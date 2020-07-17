import * as dimmer from "../ui/dimmer.js";
import {updateHeader} from "../ui/header.js";
import {selector} from "../ui/signatures.js";
import {setClass} from "../ui/utils.js";
import * as pagination from "../ui/pagination.js";
import {genProtHeader} from "../ui/proteins.js";


const svgWidth = 700;
const svgPaddingLeft = 5;
const svgPaddingRight = 30;
const width = svgWidth - svgPaddingLeft - svgPaddingRight;
const copyKey = 'proteinAccessions';


function fetchMatches(proteinAccession) {
    return fetch(`/api/protein/${proteinAccession}/?matches`)
        .then(response => response.json())
        .then(protein => {
            sessionStorage.setItem(proteinAccession, JSON.stringify(protein));
        });
}


function renderMatches(proteinAccession, signatures, filterMatches) {
    const protein = JSON.parse(sessionStorage.getItem(proteinAccession));

    let html = `<h4 class="ui header">${genProtHeader(protein)}</h4>
                        <table class="ui single line very basic compact table"><tbody>`;

    for (const signature of protein.signatures) {
        if (signatures.includes(signature.accession)) {
            if (filterMatches)
                html += '<tr>';
            else
                html += '<tr class="active">';
        }
        else if (filterMatches)
            continue
        else
            html += '<tr>';

        if (signature.entry === null)
            html += '<td></td>';
        else {
            html += `<td>
                       <span class="ui mini circular label type ${signature.entry.type}">${signature.entry.type}</span>
                       <a href="/entry/${signature.entry.accession}/">${signature.entry.accession}</a>
                     </td>`;
        }

        html += `<td><a href="/signature/${signature.accession}/">${signature.accession}</a></td>
                 <td class="collapsing"><a href="#" data-add-id="${signature.accession}"><i class="cart plus fitted icon"></i></a></td>
                 <td><a target="_blank" href="${signature.link}">${signature.name}<i class="external icon"></i></a></td>
                 <td>
                    <svg width="${svgWidth}" height="30">
                        <line x1="${svgPaddingLeft}" y1="20" x2="${width}" y2="20" stroke="#888" stroke-width="1px"/>
                        <text x="${svgPaddingLeft + width + 2}" y="20" class="length">${protein.length}</text>`;

        for (const fragments of signature.matches) {
            for (let i = 0; i < fragments.length; i++) {
                const frag = fragments[i];
                const x = Math.round(frag.start * width / protein.length) + svgPaddingLeft;
                const w = Math.round((frag.end - frag.start) * width / protein.length);

                html += '<g>';
                if (i) {
                    // Discontinuous domain: draw arc
                    const px = Math.round(fragments[i-1].end * width / protein.length) + svgPaddingLeft;
                    html += `<path d="M${px} 15 Q ${(px+x)/2} 0 ${x} 15" fill="none" stroke="${signature.color}"/>`
                }

                html += `<rect x="${x}" y="15" width="${w}" height="10" rx="1" ry="1" style="fill: ${signature.color};" />
                         <text x="${x}" y="10" class="position">${frag.start}</text>
                         <text x="${x+w}" y="10" class="position">${frag.end}</text>
                         </g>`;
            }
        }

        html += '</svg></td></tr>';
    }

    html += '</tbody></table>';
    document.querySelector(`#proteins [data-id="${proteinAccession}"]`).innerHTML = html;
}


async function getProteins(signatureAccessions) {
    dimmer.on();

    fetch(`/api${location.pathname+location.search}`)
        .then(response => response.json())
        .then((data,) => {
            let elem = document.querySelector('#count .value');
            elem.dataset.count = data.count;
            elem.innerHTML = data.count.toLocaleString();

            let html = '';
            for (const protein of data.results) {
                html += `<div data-id="${protein}" class="ui segment"></div>`;
            }

            elem = document.getElementById('proteins');
            elem.innerHTML = html;

            pagination.render(
                elem.parentNode,
                data.page_info.page,
                data.page_info.page_size,
                data.count,
                (url,) => {
                    history.replaceState(null, document.title, url);
                    getProteins(signatureAccessions);
                }
            );

            let filterElem;
            filterElem = document.querySelector('[data-filter="comment"]');
            if (data.filters.comment) {
                filterElem.querySelector('.value').innerHTML = `${data.filters.comment}`;
                setClass(filterElem, 'hidden', false);

            } else
                setClass(filterElem, 'hidden', true);

            filterElem = document.querySelector('[data-filter="description"]');
            if (data.filters.description) {
                filterElem.querySelector('.value').innerHTML = `${data.filters.description}`;
                setClass(filterElem, 'hidden', false);

            } else
                setClass(filterElem, 'hidden', true);

            filterElem = document.querySelector('[data-filter="go"]');
            if (data.filters.go) {
                filterElem.querySelector('.value').innerHTML = `${data.filters.go}`;
                setClass(filterElem, 'hidden', false);

            } else
                setClass(filterElem, 'hidden', true);

            filterElem = document.querySelector('[data-filter="exclude"]');
            if (data.filters.exclude.length) {
                filterElem.querySelector('.value').innerHTML = data.filters.exclude.map(acc => `<span class="ui small basic label">${acc}</span>`).join('');
                setClass(filterElem, 'hidden', false);
            } else
                setClass(filterElem, 'hidden', true);

            filterElem = document.querySelector('[data-filter="taxon"]');
            if (data.filters.taxon) {
                filterElem.querySelector('.value').innerHTML = `<em>${data.filters.taxon}</em>`;
                setClass(filterElem, 'hidden', false);
            } else
                setClass(filterElem, 'hidden', true);

            // Remove all stored data (except accessions for the 'copy' button)
            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                if (key !== copyKey)
                    sessionStorage.removeItem(key);
            }

            const filterMatches = document.querySelector('input[name="filter-matches"]').checked;
            const promises = [];
            for (const protein of data.results) {
                promises.push(fetchMatches(protein).then(() => renderMatches(protein, signatureAccessions, filterMatches)));
            }

            Promise.all(promises).then(() => {
                for (const elem of document.querySelectorAll('a[data-add-id]')) {
                    elem.addEventListener('click', e => {
                        e.preventDefault();
                        selector.add(elem.dataset.addId).render();
                    });
                }

                dimmer.off()
            });
        });
}


document.addEventListener('DOMContentLoaded', () => {
    const match = location.pathname.match(/\/signatures\/(.+)\/proteins\/$/i);
    const accessions = match[1].split("/");
    document.title = "Proteins (" + accessions.join(", ") + ") | Pronto";

    selector.init(document.getElementById('signature-selector'));
    for (const accession of accessions) {
        selector.add(accession);
    }
    selector.render().tab("proteins");

    const url = new URL(location.href);
    let checkbox = document.querySelector('input[type=checkbox][name=reviewed]');
    checkbox.checked = url.searchParams.has('reviewed');
    checkbox.addEventListener('change', e => {
        if (e.currentTarget.checked)
            url.searchParams.set('reviewed', '');
        else
            url.searchParams.delete('reviewed');

        history.replaceState(null, document.title, url.toString());
        getProteins(accessions);
    });

    document.getElementById('copy-btn').addEventListener('click', e => {
        e.preventDefault();
        copyProteins();
    });

    document.getElementById('download-btn').addEventListener('click', e => {
        e.preventDefault();
        downloadProteins();
    });

    checkbox = document.querySelector('input[type=checkbox][name=filter-matches]');
    checkbox.checked = url.searchParams.has('filtermatches')
    checkbox.addEventListener('change', e => {
        e.preventDefault();
        const filterMatches = e.currentTarget.checked;
        for (const elem of document.querySelectorAll('#proteins [data-id]')) {
            renderMatches(elem.dataset.id, accessions, filterMatches);
        }
    });

    updateHeader();
    getProteins(accessions);
});

function copyProteins() {
    const btn = document.getElementById('copy-btn');
    const copy2clipboard = (value) => {
        const input = document.createElement('input');
        input.value = value;
        document.body.appendChild(input);
        try {
            input.select();
            document.execCommand('copy');
            btn.className = 'ui green tertiary button';
        } catch (err) {
            console.error(err);
            btn.className = 'ui red tertiary button';
        } finally {
            document.body.removeChild(input);
            setTimeout(() => {
                btn.className = 'ui tertiary button';
            }, 3000);
        }
    };

    const value = sessionStorage.getItem(copyKey);
    if (value !== null) {
        copy2clipboard(value);
        return;
    }

    btn.className = 'ui disabled loading tertiary button';
    const url = new URL(location.href);
    url.searchParams.set('page_size', '0');
    fetch(`/api${url.pathname}${url.search}`)
        .then(response => response.json())
        .then(object => {
            const value = object.results.join(' ');
            sessionStorage.setItem(copyKey, value);
            copy2clipboard(value);
        });
}

function downloadProteins() {
    const modal = document.getElementById('progress-modal');
    const progress = modal.querySelector('.progress');
    $(progress).progress({
        value: 0,
        total: Number.parseInt(document.querySelector('#count .value').dataset.count, 10),
        text : {
            percent: '{percent}%',
            active  : '{value} of {total} proteins downloaded',
            success : '{total} proteins downloaded!'
        }
    });
    $(modal).modal({
        closable: false
    }).modal('show');

    const url = new URL(location.href);
    url.searchParams.set('page_size', '0');
    fetch(`/api${url.pathname}${url.search}`)
        .then(response => response.json())
        .then(object => {

            const getProteinInfo = (accession) => {
                return fetch(`/api/protein/${accession}/`).then(response => response.json());
            };

            (async function() {
                let content = 'Accession\tIdentifier\tName\tLength\tSource\tOrganism\n';
                for (let i = 0; i < object.results.length; i += 10) {
                    const chunk = object.results.slice(i, i+10);
                    const promises = Array.from(chunk, getProteinInfo);
                    const rows = [];
                    for await (let obj of promises) {
                        $(progress).progress('increment');
                        rows.push([
                            obj.accession,
                            obj.identifier,
                            obj.name,
                            obj.length,
                            obj.is_reviewed ? 'UniProtKB/Swiss-Prot' : 'UniProtKB/TrEMBL',
                            obj.organism.name
                        ]);
                    }
                    // Sort protein by accession
                    rows.sort((a, b) => a[0].localeCompare(b[0]));
                    for (const row of rows) {
                        content += row.join('\t') + '\n';
                    }
                }

                const blob = new Blob([content], {type: 'text/tab-separated-values;charset=utf-8;'});

                const link = document.createElement("a");
                link.href = URL.createObjectURL(blob);
                link.download = 'proteins.tsv';
                link.style.display = 'none';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                $(modal).modal('hide');
            })();
        });
}
