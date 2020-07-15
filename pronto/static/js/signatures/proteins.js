import * as dimmer from "../ui/dimmer.js";
import {updateHeader} from "../ui/header.js";
import {selector} from "../ui/signatures.js";
import {setClass} from "../ui/utils.js";
import * as pagination from "../ui/pagination.js";
import {genProtHeader} from "../ui/proteins.js";

function fetchAPI() {
    return new Promise(((resolve, reject) => {
        fetch('/api' + location.pathname + location.search)
            .then(response => {
                response.json()
                    .then(object => {
                        if (response.ok)
                            resolve(object);
                        else
                            reject(object.error);
                    });
            })
    }));
}

const svgWidth = 700;
const svgPaddingLeft = 5;
const svgPaddingRight = 30;
const width = svgWidth - svgPaddingLeft - svgPaddingRight;


function getProtein(proteinAccession, signatures) {
    return fetch(`/api/protein/${proteinAccession}/?matches`)
        .then(response => response.json())
        .then(protein => {
            let html = '';

            for (const signature of protein.signatures) {
                if (signatures.includes(signature.accession))
                    html += '<tr class="active">';
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

            const elem = document.querySelector(`#proteins [data-id="${protein.accession}"] tbody`);
            elem.innerHTML = html;
            return protein.accession;
        });
}

function getProteins(signatureAccessions) {
    dimmer.on();

    fetchAPI()
        .then(
            (data,) => {
                document.querySelector('#count .value').innerHTML = data.count.toLocaleString();

                let html = '';
                for (const protein of data.results) {
                    html += `<div data-id="${protein.accession}" class="ui segment">
                             <h4 class="ui header">${genProtHeader(protein)}</h4>
                             <table class="ui single line very basic compact table"><tbody></tbody></table>
                             </div>`;
                }

                const elem = document.getElementById('proteins');
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



                const promises = [];
                for (const protein of data.results) {
                    promises.push(getProtein(protein.accession, signatureAccessions));
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

            },
            (error,) => {
                dimmer.off();
                console.error(error);  // todo
            }
        );
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
    const params = new URLSearchParams(url.search);
    params.set('page', '1');
    params.set('page_size', '0');
    params.set('file', '');

    const checkbox = document.querySelector('input[type=checkbox][name=reviewed]');
    const dlButton = document.querySelector('#count a');

    checkbox.checked = url.searchParams.has('reviewed');
    dlButton.href = new URL(`/api${location.pathname}?${params.toString()}`,location.origin).toString();

    checkbox.addEventListener('change', e => {
        if (e.currentTarget.checked) {
            url.searchParams.set('reviewed', '');
            params.set('reviewed', '');
        } else {
            url.searchParams.delete('reviewed');
            params.delete('reviewed');
        }

        dlButton.href = new URL(`/api${location.pathname}?${params.toString()}`,location.origin).toString();
        console.log(dlButton.href);

        history.replaceState(null, document.title, url.toString());
        getProteins(accessions);
    });

    updateHeader();
    getProteins(accessions);
});
