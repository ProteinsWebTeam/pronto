import * as dimmer from "../ui/dimmer.js";
import {updateHeader} from "../ui/header.js";
import {selector} from "../ui/signatures.js";
import { backToTop } from "../ui/backtotop.js";
import * as pagination from "../ui/pagination.js";
import {fetchProtein, genProtHeader, renderMatches} from "../ui/proteins.js";


const svgWidth = 600;
const svgPaddingLeft = 5;
const svgPaddingRight = 30;
const width = svgWidth - svgPaddingLeft - svgPaddingRight;
const copyKey = 'allAccessions';
const pageKey = 'accessions';


function renderProtein(protein, signatures, filterMatches, maxLength) {
    let html = `
        <div class="ui segment">
        <h4 class="ui header">${genProtHeader(protein)}</h4>
        <table class="ui single line very basic compact table"><tbody>
    `;

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

        const _width = Math.floor(protein.length * width / maxLength);
        html += `<td><a href="/signature/${signature.accession}/">${signature.accession}</a></td>
                 <td class="collapsing"><a href="#" data-add-id="${signature.accession}"><i class="cart plus fitted icon"></i></a></td>
                 <td><a target="_blank" href="${signature.link}">${signature.name || signature.accession}<i class="external icon"></i></a></td>
                 <td>
                    <svg width="${svgWidth}" height="30">
                        <line x1="${svgPaddingLeft}" y1="20" x2="${_width}" y2="20" stroke="#888" stroke-width="1px"/>
                        <text x="${svgPaddingLeft + _width + 2}" y="20" class="length">${protein.length}</text>`;

        html += renderMatches(protein.length, signature, _width, svgPaddingLeft);
        html += '</svg></td></tr>';
    }

    html += '</tbody></table></div>';
    return html;
}

function postRendering() {
    for (const elem of document.querySelectorAll('a[data-add-id]')) {
        elem.addEventListener('click', e => {
            e.preventDefault();
            selector.add(elem.dataset.addId).render();
        });
    }

    const tables = document.querySelectorAll('table');
    let i = null;
    let paused = false;
    tables.forEach((table, j) => {
        table.addEventListener('scroll', (event) => {
            if (!paused && (i=== null || i === j)) {
                i = j;
                const sl = event.target.scrollLeft;
                window.requestAnimationFrame(() => {
                    tables.forEach((otherTable, k) => {
                        if (k !== i) {
                            otherTable.scrollLeft = sl;
                        }
                    });

                    i = null;
                    paused = false;
                });
                paused = true;
            }
        });
    });
}

function getProteins(signatureAccessions) {
    dimmer.on();

    fetch(`/api${location.pathname+location.search}`)
        .then(response => response.json())
        .then((data,) => {
            let elem = document.querySelector('#count .value');
            elem.dataset.count = data.count;
            elem.innerHTML = data.count.toLocaleString();

            elem = document.getElementById('proteins');
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
            if (data.filters.comment)
                filterElem.querySelector('.value').innerHTML = `${data.filters.comment}`;
            else
                filterElem.querySelector('.value').innerHTML = 'N/A';

            filterElem = document.querySelector('[data-filter="description"]');
            if (data.filters.description)
                filterElem.querySelector('.value').innerHTML = `${data.filters.description}`;
            else
                filterElem.querySelector('.value').innerHTML = 'N/A';

            filterElem = document.querySelector('[data-filter="go"]');
            if (data.filters.go)
                filterElem.querySelector('.value').innerHTML = `${data.filters.go}`;
            else
                filterElem.querySelector('.value').innerHTML = 'N/A';

            filterElem = document.querySelector('[data-filter="exclude"]');
            if (data.filters.exclude.length)
                filterElem.querySelector('.value').innerHTML = data.filters.exclude.map(acc => `<span class="ui small basic label">${acc}</span>`).join('');
            else
                filterElem.querySelector('.value').innerHTML = 'N/A';

            filterElem = document.querySelector('[data-filter="taxon"]');
            if (data.filters.taxon)
                filterElem.querySelector('.value').innerHTML = `<em>${data.filters.taxon}</em>`;
            else
                filterElem.querySelector('.value').innerHTML = 'N/A';

            const promises = [];
            const extra = new Map();
            for (const protein of data.results) {
                promises.push(fetchProtein(protein.accession, true));
                extra.set(protein.accession, protein);
            }

            Promise.all(promises).then((proteins) => {
                sessionStorage.removeItem(pageKey);

                if (proteins.length > 0) {
                    const maxLength = Math.max(...Array.from(proteins, p => p.length));
                    const filterMatches = document.querySelector('input[name="filter-matches"]').checked;

                    let html = '';
                    for (const protein of proteins) {
                        for (const [key, value] of Object.entries(extra.get(protein.accession))) {
                            if (protein[key] === undefined)
                                protein[key] = value;
                        }
                        html += renderProtein(protein, signatureAccessions, filterMatches, maxLength);
                    }
                    sessionStorage.setItem(pageKey, JSON.stringify(proteins));
                    elem.innerHTML = html;
                    postRendering();
                } else
                    elem.innerHTML = `
                        <div class="ui warning message">
                        <div class="header">No results found</div>
                        <p>Your query returned no proteins.</p>
                        </div>
                    `;

                dimmer.off()
            });
        });
}

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
            const value = object.results.map(x => x.accession).join(' ');
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
            (async function() {
                let content = 'Accession\tIdentifier\tName\tLength\tSource\tOrganism\n';
                for (let i = 0; i < object.results.length; i += 10) {
                    const promises = [];
                    for (const protein of object.results.slice(i, i+10)) {
                        promises.push(fetchProtein(protein.accession, false));
                    }
                    const rows = [];
                    for await (const obj of promises) {
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

document.addEventListener('DOMContentLoaded', () => {
    const match = location.pathname.match(/\/signatures\/(.+)\/proteins\/$/i);
    const accessions = match[1].split("/");
    document.title = "Proteins (" + accessions.join(", ") + ") | Pronto";

    sessionStorage.clear();

    selector.init(document.getElementById('signature-selector'));
    for (const accession of accessions) {
        selector.add(accession);
    }
    selector.render().tab("proteins");

    const url = new URL(location.href);
    let checkbox = document.querySelector('input[type=checkbox][name=reviewed]');
    if (url.searchParams.get('reviewed') === 'true') {
        checkbox.checked = true;
    } else {
        checkbox.checked = false;
        url.searchParams.delete('reviewed');
        history.replaceState(null, document.title, url.toString());
    }

    checkbox.addEventListener('change', e => {
        const newURL = new URL(location.href);
        if (e.currentTarget.checked)
            newURL.searchParams.set('reviewed', "true");
        else
            newURL.searchParams.delete('reviewed');

        history.replaceState(null, document.title, newURL.toString());
        getProteins(accessions);
    });

    checkbox = document.querySelector('input[type=checkbox][name=dom-orgs]');
    checkbox.checked = url.searchParams.has('domainorganisation');
    checkbox.addEventListener('change', e => {
        const newURL = new URL(location.href);
        if (e.currentTarget.checked)
            newURL.searchParams.set('domainorganisation', '');
        else
            newURL.searchParams.delete('domainorganisation');

        history.replaceState(null, document.title, newURL.toString());
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
        const newURL = new URL(location.href);
        if (filterMatches)
            newURL.searchParams.set('filtermatches', '');
        else
            newURL.searchParams.delete('filtermatches');
        history.replaceState(null, document.title, newURL.toString());

        const proteins = JSON.parse(sessionStorage.getItem(pageKey));
        const maxLength = Math.max(...Array.from(proteins, p => p.length));
        let html = '';
        for (const protein of proteins) {
            html += renderProtein(protein, accessions, filterMatches, maxLength);
        }

        document.getElementById('proteins').innerHTML = html;
        postRendering();
    });

    const matching = Number.parseInt(url.searchParams.get('matching'), 10);
    $('.ui.slider')
        .slider({
            min: 1,
            max: accessions.length,
            start: Number.isInteger(matching) ? matching : accessions.length,
            onChange: function (value) {
                const newURL = new URL(location.href);
                newURL.searchParams.set('matching', value);
                history.replaceState(null, document.title, newURL.toString());
                getProteins(accessions);
            }
        });

    updateHeader();
    backToTop();
    getProteins(accessions);
});
