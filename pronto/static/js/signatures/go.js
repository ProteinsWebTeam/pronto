import * as dimmer from "../ui/dimmer.js";
import {updateHeader} from "../ui/header.js";
import {selector} from "../ui/signatures.js";


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
    fetchAPI().then(
        (data,) => {
            let html = `<thead>
                        <tr>
                        <th>${data.results.length.toLocaleString()} terms</th>
                        <th class="collapsing center aligned"><button class="ui primary small fluid compact icon button"><i class="sitemap icon"></i></button></th>
                        ${accessions.map(acc => `<th class="center aligned" colspan="2">${acc}</th>`).join('')}
                        </tr>
                        </thead>`;

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
                        html += `<td class="collapsing center aligned">
                                    <a target="_blank" href="/signatures/${acc}/proteins/?go=${term.id}">${signature['proteins'].toLocaleString()}</a>
                                 </td>`;
                        if (signature['references']) {
                            html += `<td class="collapsing center aligned">
                                       <a data-signature="${acc}" data-term="${term.id}" class="ui basic label"><i class="book icon"></i>${signature['references'].toLocaleString()}</a>
                                     </td>`;
                        } else
                            html += '<td></td>';

                    } else
                        html += '<td></td><td></td>';
                }
                html += '</tr>';
            }

            document.getElementById('results').innerHTML = html + '</tbody></table>';

            for (const input of document.querySelectorAll(`input[name="aspect"]`)) {
                input.checked = data.aspects.includes(input.value);
            }

            // Display GO chart
            document.querySelector('#results thead button').addEventListener('click', e => {
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
            for (const elem of document.querySelectorAll('#results [data-signature]')) {
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

            dimmer.off();
        },
        (error, ) => {
            // todo
            dimmer.off();
        }
    )
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
    getGoTerms(accessions);
});