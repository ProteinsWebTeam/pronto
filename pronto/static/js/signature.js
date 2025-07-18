import * as checkbox from "./ui/checkbox.js"
import * as comments from "./ui/comments.js";
import * as dimmer from "./ui/dimmer.js"
import * as modals from "./ui/modals.js";
import {updateHeader} from "./ui/header.js";
import {selector, renderConfidence} from "./ui/signatures.js";

function getSignature() {
    return new Promise((resolve, reject) => {
        fetch('/api' + location.pathname)
            .then(response => {
                if (response.ok)
                    resolve(response.json());
                else
                    reject(response.status);
            })
    });
}

function getPredictions(accession) {
    fetch(`/api/signature/${accession}/predictions/${location.search}`)
        .then(response => response.json())
        .then(results => {
            dimmer.off();
            let html = '';
            if (results.length > 0) {
                for (const signature of results) {
                    html += `
                    <tr>
                        <td class="capitalize">${signature.relationship || ''}</td>
                        <td class="collapsing center aligned">${renderConfidence(signature)}</td>
                        <td>
                            <span class="ui empty circular label" 
                                  style="background-color: ${signature.database.color};" 
                                  data-content="${signature.database.name}" 
                                  data-position="left center" 
                                  data-variation="tiny"></span>
                            <a href="/signature/${signature.accession}/">${signature.accession}</a>
                        </td>
                        <td class="collapsing"><a target="_blank" href="${signature.database.link}"><i class="external fitted icon"></i></a></td>
                        <td class="collapsing"><a href="#" data-add-id="${signature.accession}"><i class="cart plus fitted icon"></i></a></td>
                        <td class="right aligned">${signature.proteins.toLocaleString()}</td>
                        <td class="right aligned">${signature.collocations.toLocaleString()}</td>
                        <td class="right aligned">${signature.overlaps.toLocaleString()}</td>
                    `;

                    if (signature.entry) {
                        html += '<td class="nowrap"><div class="ui list">';

                        for (const parent of signature.entry.hierarchy) {
                            html += `<div class="item">
                                <div class="content">
                                <i class="angle down icon"></i>
                                <a href="/entry/${parent}">${parent}</a>
                                </div>
                             </div>`;
                        }

                        html += `<div class="item">
                            <div class="content">
                            <span class="ui circular mini label type ${signature.entry.type}">${signature.entry.type}</span>
                            ${signature.entry.llm ? '<i class="magic icon"></i>' : ''}
                            <a href="/entry/${signature.entry.accession}">${signature.entry.accession} (${signature.entry.name})</a>
                            </div>
                         </div>
                         </div>
                         </td>
                         <td>${checkbox.createDisabled(signature.entry.checked)}</td></tr>`;
                    } else
                        html += '<td></td><td></td></tr>';
                }
            } else
                html += '<tr><td colspan="10" class="center aligned">No results for this signature</td></tr>';

            document.querySelector("#predictions tbody").innerHTML = html;

            for (const elem of document.querySelectorAll('tbody a[data-add-id]')) {
                elem.addEventListener('click', e => {
                    e.preventDefault();
                    selector.add(elem.getAttribute('data-add-id')).render();
                });
            }

            document.getElementById('predictions-count').innerHTML = results.length.toLocaleString();

            // Tooltips
            $('[data-content]').popup();
        });
}

document.addEventListener('DOMContentLoaded', () => {
    const accession = location.pathname.match(/\/signature\/(.+)\//)[1];
    updateHeader(accession);

    const input = document.querySelector('input[name="all"]');
    input.checked = (new URLSearchParams(location.search)).has('all');
    input.addEventListener('change', e => {
        const url = new URL(location.href);
        if (e.currentTarget.checked)
            url.searchParams.set('all', '');
        else
            url.searchParams.delete('all');

        history.replaceState(null, document.title, url.toString());
        dimmer.on();
        getPredictions(accession);
    });

    dimmer.on();
    getSignature().then(
        (result,) => {
            const accession = result.accession;
            document.title = `${accession} | Pronto`;

            selector.init(document.getElementById('signature-selector'))
                .add(accession)
                .render();

            // Update page header
            let html = `<a href="${result.database.link}" target="_blank">`;

            if (result.name && result.name !== accession)
                html += result.name + ' (' + accession + ')';
            else
                html += accession;
            html += '<i class="external icon"></i></a>';

            if (result.entry) {
                html += '&nbsp;&middot;&nbsp;';
                if (result.entry.hierarchy.length > 0) {
                    const parent = result.entry.hierarchy[result.entry.hierarchy.length-1];
                    html += `<a href="/entry/${parent.accession}">${parent.accession}</a>
                             <i class="fitted right chevron icon"></i>`;
                }

                html += `<span class="ui small circular label type ${result.entry.type}">${result.entry.type}</span>
                         ${result.entry.llm ? '<i class="magic icon"></i>' : ''}
                         <a href="/entry/${result.entry.accession}/">${result.entry.accession}</a>`;
            }

            document.querySelector("h1.ui.header .sub").innerHTML = html;

            // Update table header
            html = `<th colspan="2"></th>
                    <th>${accession}</th>
                    <th class="collapsing"><a target="_blank" href="${result.database.link}"><i class="external fitted icon"></i></a></th>
                    <th class="collapsing"><a href="#" data-add-id="${accession}"><i class="cart plus fitted icon"></i></a></th>
                    <th class="right aligned">${result.proteins.complete.toLocaleString()}</th>
                    <th></th>
                    <th></th>`;

            if (result.entry) {
                html += '<th class="nowrap"><div class="ui list">';

                for (let i = 0; i < result.entry.hierarchy.length; i++) {
                    const node = result.entry.hierarchy[i];
                    html += `<div class="item">
                                <div class="content">
                                <i class="angle right icon"></i>
                                <a href="/entry/${node.accession}">${node.accession}</a>
                                </div>
                             </div>`;
                }

                html += `<div class="item">
                            <div class="content">
                            <span class="ui circular mini label type ${result.entry.type}">${result.entry.type}</span>
                            ${result.entry.llm ? '<i class="magic icon"></i>' : ''}
                            <a href="/entry/${result.entry.accession}">${result.entry.accession} (${result.entry.name})</a>
                            </div>
                         </div>
                         </div>
                         </th>
                         <th>${checkbox.createDisabled(result.entry.checked)}</th>`;
            } else
                html += '<th></th><th></th>';

            let node = document.createElement('tr');
            node.innerHTML = html;
            document.querySelector("#predictions thead").appendChild(node);

            // Events on thead
            document.querySelector('thead a[data-add-id]').addEventListener('click', e => {
                e.preventDefault();
                selector.add(e.currentTarget.getAttribute('data-add-id'));
            });

            // Get comments
            comments.getSignatureComments(accession, 2, document.querySelector(".ui.comments"));

            // Even listener to post comments
            const button = document.querySelector('.ui.comments form button');
            button.addEventListener('click', e => {
                e.preventDefault();
                const form = e.target.closest('form');
                const accession = form.getAttribute('data-id');
                const textarea = form.querySelector('textarea');

                comments.postSignatureComment(accession, textarea.value.trim())
                    .then(object => {
                        if (object.status) {
                            comments.getSignatureComments(accession, null, e.target.closest(".ui.comments"));
                        } else
                            modals.error(object.error.title, object.error.message);
                    });
            });

            comments.addKeyPressEventListener(
                button.closest('form').querySelector('textarea'),
                button
            )

            if (result.abstract || result.llm_abstract) {
                let abstract;
                let isLLM = false;
                if (result.abstract) {
                    abstract = result.abstract;
                } else {
                    abstract = result.llm_abstract;
                    isLLM = true;
                }

                const pub2pmid = new Map(result.references.map((r) => ([r.id, r.pmid])));
                const descriptionElement = document.getElementById('description');
                descriptionElement.innerHTML = abstract.replaceAll(
                    /\[+cite:(PUB\d+)\]+/g,
                    (match, p1) => {
                        const pmid = pub2pmid.get(p1);
                        if (pmid) {
                            return `[<a href="http://europepmc.org/abstract/MED/${pmid}/" target="_blank">PMID:${pmid}<i class="external icon"></i></a>]`;
                        }
                        return '';
                    }
                );

                if (isLLM) {
                    descriptionElement.parentNode.querySelector('h4').innerHTML = '<i class="normal fitted magic icon"></i> Description';
                }
            }

            document.getElementById('counters').innerHTML = `
                <tbody>
                    <tr>
                        <td>Proteins</td>
                        <td class="right aligned">${result.proteins.total.toLocaleString()}</td>
                    </tr>
                    <tr>
                        <td>Complete proteins</td>
                        <td class="right aligned">${result.proteins.complete.toLocaleString()}</td>
                    </tr>               
                    <tr>
                        <td>Swiss-Prot proteins</td>
                        <td class="right aligned">${result.proteins.reviewed.total.toLocaleString()}</td>
                    </tr>
                    <tr>
                        <td>Complete Swiss-Prot proteins</td>
                        <td class="right aligned">${result.proteins.reviewed.complete.toLocaleString()}</td>
                    </tr>
                </tbody>
            `;

            getPredictions(accession);
        },
        (status,) => {
            // todo: show error
        }
    );

    $('.message .close')
        .on('click', function() {
            $(this)
                .closest('.message')
                .transition('fade');
        });
});
