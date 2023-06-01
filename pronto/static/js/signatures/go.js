import * as dimmer from "../ui/dimmer.js";
import {updateHeader} from "../ui/header.js";
import {selector, showProteinsModal} from "../ui/signatures.js";
import { backToTop } from "../ui/backtotop.js";

function getAspectCode(aspect) {
    switch (aspect) {
        case 'biological_process':
            return 'P';
        case 'molecular_function':
            return 'F';
        default:
            return 'C';
    }
}


function getGoTerms(accessions) {
    dimmer.on();
    fetch('/api' + location.pathname + location.search)
        .then(response => response.json())
        .then((data,) => {
            const sig2ipr = new Map(Object.entries(data.integrated));
            const isPanther = new RegExp('^PTHR');

            const genCell = (acc,) => {
                const span = isPanther.test(acc) ? 3 : 2;
                if (sig2ipr.has(acc))
                    return `<th class="center aligned" colspan="${span}"><span data-tooltip="${sig2ipr.get(acc)}" data-inverted=""><i class="star icon"></i>${acc}</span></th>`;
                else
                    return `<th class="center aligned" colspan="${span}"><i class="star outline icon"></i>${acc}</th>`;
            };

            let html = `<thead>
                        <tr>
                        <th rowspan="2">${data.results.length.toLocaleString()} terms</th>
                        <th class="collapsing center aligned" rowspan="2"><button class="ui primary small fluid compact icon button"><i class="sitemap icon"></i></button></th>
                        ${accessions.map(genCell).join('')}
                        </tr>
                        <tr>`;

            for (let i = 0; i < accessions.length; i++) {
                html += `
                        <th class="collapsing center aligned normal">UNI</th>
                        <th class="collapsing center aligned">REF</th>`;
                if (isPanther.test(accessions[i]))
                    html += `<th class="collapsing center aligned">PTHR</th>`;

            }
            html += `</tr></thead>`;

            html += '<tbody>';

            for (const term of data.results) {
                html += `<tr>
                            <td>
                              <span class="ui small circular label ${term.aspect}">${getAspectCode(term.aspect)}</span>
                              <a target="_blank" href="https://www.ebi.ac.uk/QuickGO/term/${term.id}">${term.id}: ${term.name}<i class="external icon"></i></a>
                            </td>
                            <td class="collapsing center aligned">
                              <div class="ui fitted checkbox">
                                <input name="term" value="${term.id}" type="checkbox">
                                <label></label>
                              </div>
                            </td>`;
                for (const acc of accessions) {
                    if (term.signatures.hasOwnProperty(acc)) {
                        const signature = term.signatures[acc];
                        if (signature['proteins'] > 0) {
                            html += `<td class="collapsing center aligned">
                                        <a href="#!" data-signature="${acc}" data-term="${term.id}">${signature['proteins'].toLocaleString()}</a>
                                    </td>`;
                        } else
                            html += '<td class="collapsing"></td>';

                        if (signature.references > 0) {
                            html += `<td class="collapsing center aligned">
                                       <a data-signature="${acc}" data-term="${term.id}" class="ui basic label"><i class="book icon"></i>${signature.references.toLocaleString()}</a>
                                     </td>`;
                        } else
                            html += '<td class="collapsing"></td>';

                        if (signature.panthergo > 0) {
                            html += `<td class="collapsing center aligned">
                                        <a href="#!" data-signature="${acc}" data-term="${term.id}" data-panther="">${signature.panthergo.toLocaleString()}</a>
                                     </td>`;
                        } else if (isPanther.test(acc))
                            html += '<td class="collapsing"></td>';

                    } else {
                        html += '<td class="collapsing"></td><td class="collapsing"></td>';

                        if (isPanther.test(acc)) {
                            html += '<td class="collapsing"></td>';
                        }
                    }
                }
                html += '</tr>';
            }

            const table = document.getElementById('results');
            table.innerHTML = html + '</tbody>';

            for (const input of document.querySelectorAll(`input[name="aspect"]`)) {
                input.checked = data.aspects.includes(input.value);
            }

            for (const elem of table.querySelectorAll('[data-signature]:not(.label):not([data-panther])')) {
                elem.addEventListener('click', e => {
                    const acc = e.currentTarget.dataset.signature;
                    const termID = e.currentTarget.dataset.term;
                    showProteinsModal(acc, [`go=${termID}`], true);
                });
            }

            // Display GO chart
            table.querySelector('thead button').addEventListener('click', e => {
                const terms = [];
                for (const input of document.querySelectorAll('input[name="term"]:checked')) {
                    terms.push(input.value);
                }

                if (terms.length) {
                    const url = `https://www.ebi.ac.uk/QuickGO/services/ontology/go/terms/${terms.join(',')}/chart`;
                    const modal = document.getElementById('chart-modal');
                    modal.querySelector('.content').innerHTML = '<img class="image" alt="'+ terms.join(',') +'" src="'+ url +'">';
                    setTimeout(function () {
                        $(modal).modal('show');
                    }, 500);
                }
            });

            // Get Pubmed references
            for (const elem of table.querySelectorAll('.label[data-signature]')) {
                elem.addEventListener('click', (e,) => {
                    const acc = e.currentTarget.dataset.signature;
                    const term = e.currentTarget.dataset.term;
                    const url = new URL(`/api/signature/${acc}/go/${term}/`, location.origin);

                    dimmer.on();
                    fetch(url.toString())
                        .then(response => response.json())
                        .then(object => {
                            let html = '';
                            for (const ref of object.results) {
                                html += `<li class="item">
                                           <div class="header">
                                             <a target="_blank" href="//europepmc.org/abstract/MED/${ref.id}">PMID: ${ref.id}<i class="external icon"></i></a>
                                           </div>
                                           <div class="description">${ref.title}&nbsp;${ref.date}</div>
                                         </li>`;
                            }

                            const modal = document.getElementById('references-modal');
                            modal.querySelector('.ui.header').innerHTML = `PubMed references: ${acc}/${term}`;
                            modal.querySelector('.content ul').innerHTML = html;
                            modal.querySelector('.actions a').setAttribute('href', `//www.ebi.ac.uk/QuickGO/term/${term}`);
                            $(modal).modal('show');
                            dimmer.off();
                        });

                });
            }

            // Get PANTHER subfamilies references
            for (const elem of table.querySelectorAll('[data-signature][data-panther]')) {
                elem.addEventListener('click', (e,) => {
                    const acc = e.currentTarget.dataset.signature;
                    const term = e.currentTarget.dataset.term;
                    const url = new URL(`/api/signature/${acc}/go/${term}/subfam`, location.origin);

                    dimmer.on();
                    fetch(url.toString())
                        .then(response => response.json())
                        .then(object => {
                            let html = '';
                            html += `<table class="ui definition celled table">
                                        <thead>
                                            <tr>
                                                <th class="normal">Accession</th>
                                                <th>Proteins (subfamily)</th>
                                                <th>Proteins (family)</th>
                                            </tr>
                                        </thead>
                                        <tbody>`;

                            for (const subfam in object.results) {
                                html += `<tr>
                                            <td>
                                            <a target="_blank" href="//www.pantherdb.org/panther/family.do?clsAccession=${subfam}">${subfam}<i class="external icon"></i></a>
                                            </td>
                                            <td>${object.results[subfam].toLocaleString()}</td>
                                            <td>${object.count.toLocaleString()}</td>
                                         </tr>`;
                            }

                            html += `</tbody>
                                    </table>`;

                            const modal = document.getElementById('panther-modal');
                            modal.querySelector('.ui.header').innerHTML = `PANTHER subfamilies: ${acc}/${term}`;
                            modal.querySelector('.content ul').innerHTML = html;
                            modal.querySelector('.actions a').setAttribute('href', `//www.ebi.ac.uk/QuickGO/term/${term}`);
                            $(modal).modal('show');
                            dimmer.off();
                        });

                });
            }



            dimmer.off();
        });
}


document.addEventListener('DOMContentLoaded', () => {
    const match = location.pathname.match(/\/signatures\/(.+)\/go\/$/i);
    const accessions = match[1].split("/");
    document.title = "GO terms (" + accessions.join(", ") + ") | Pronto";

    selector.init(document.getElementById('signature-selector'));
    for (const accession of accessions) {
        selector.add(accession);
    }
    selector.render().tab("go");

    const checkboxes = document.querySelectorAll('input[name="aspect"]');
    for (const input of checkboxes) {
        input.addEventListener('change', (e,) => {
            const aspects = [];
            for (const input of checkboxes) {
                if (input.checked)
                    aspects.push(input.value);
            }

            const url = new URL(location.href);
            if (url.searchParams.has('aspect'))
                url.searchParams.delete('aspect');

            for (let i = 0; i < aspects.length; i++) {
                if (!i)
                    url.searchParams.set('aspect', aspects[i]);
                else
                    url.searchParams.append('aspect', aspects[i]);
            }


            history.replaceState(null, document.title, url.toString());
            getGoTerms(accessions);
        });
    }

    updateHeader();
    backToTop();
    getGoTerms(accessions);
});
