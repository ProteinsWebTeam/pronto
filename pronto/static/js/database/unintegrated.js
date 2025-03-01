import { updateHeader } from '../ui/header.js'
import * as checkbox from '../ui/checkbox.js'
import * as comments from '../ui/comments.js';
import * as dimmer from '../ui/dimmer.js'
import * as modals from '../ui/modals.js'
import * as pagination from '../ui/pagination.js'
import { renderConfidence } from "../ui/signatures.js";
import { backToTop } from "../ui/backtotop.js";


function renderEntry(entry) {
    if (entry === null)
        return '<td colspan="2"></td>'

    return `
        <td class="nowrap">
            <span class="ui circular mini label type ${entry.type}">${entry.type}</span>
            <a href="/entry/${entry.accession}/">${entry.accession}</a> 
    
        </td>
        <td class="collapsing">${checkbox.createDisabled(entry.checked)}</td>`;
}

function getSignatures() {
    dimmer.on();
    fetch(`/api${location.pathname}${location.search}`)
        .then(response => {
            dimmer.off();
            if (response.ok)
                return response.json();
            throw response.status.toString();
        })
        .then(object => {
            const title = `${object.database.name} (${object.database.version}) unintegrated signatures`;
            document.querySelector('h1.ui.header').innerHTML = title;
            document.title = `${title} | Pronto `;

            let sortBy = null;
            let sortOrder = null;
            for (const [key, value] of Object.entries(object.parameters)) {
                if (key === "sort-by") {
                    sortBy = value;
                    continue;
                } else if (key === "sort-order") {
                    sortOrder = value;
                    continue;
                }

                const inputs = document.querySelectorAll(`input[name="${key}"]`);
                for (const node of inputs) {
                    node.checked = node.value === (value !== null ? value : "");
                }
            }

            let html = '';
            if (object.count > 0) {
                for (const signature of object.results) {
                    html += `
                        <tr data-id="${signature.accession}">
                        <td class="collapsing" rowspan="${signature.targets.length || 1}">
                            <a href="/signature/${signature.accession}/">${signature.accession}</a>
                    `;

                    if (signature.comments > 0) {
                        html += `
                            <a class="ui small basic label">
                                <i class="comments icon"></i> ${signature.comments}
                            </a>`;
                    }

                    html += `
                        </td>
                        <td rowspan="${signature.targets.length || 1}" class="right aligned">
                            ${signature.proteins.toLocaleString()}
                        </td>
                        <td rowspan="${signature.targets.length || 1}" class="right aligned">
                            ${signature.single_domain_proteins.toLocaleString()}
                        </td>                        
                    `;

                    if (signature.targets.length) {
                        signature.targets.forEach((target, i) => {
                            if (i)
                                html += '<tr>';

                            html += `
                                <td class="nowrap">
                                    <span class="ui empty circular label" 
                                          style="background-color: ${target.database.color};" 
                                          data-content="${target.database.name}" 
                                          data-position="left center" 
                                          data-variation="tiny"></span>
                                    <a href="/signature/${target.accession}/">${target.accession}</a>
                                 </td>
                                 <td class="right aligned">${target.proteins.toLocaleString()}</td>
                                 <td class="right aligned">${target.collocations.toLocaleString()}</td>
                                 <td class="right aligned">${target.overlaps.toLocaleString()}</td>
                                 <td class="capitalize">${target.relationship}</td>
                                 <td class="center aligned nowrap">${renderConfidence(target, true)}</td>
                                 ${renderEntry(target.entry)}
                                </tr>
                            `;
                        });
                    } else {
                        html += '<td class="disabled" colspan="8"></td></tr>'
                    }
                }
            } else {
                html = '<tr><td class="center aligned" colspan="11">No matching signatures found</td></tr>'
            }

            const table = document.getElementById('results');
            const cell = table.querySelector('thead tr:first-child th:first-child');
            if (object.count > 1)
                cell.innerHTML = `${object.count.toLocaleString()} signatures`;
            else
                cell.innerHTML = `${object.count} signature`;

            table.querySelector('tbody').innerHTML = html;

            pagination.render(
                table,
                object.page_info.page,
                object.page_info.page_size,
                object.count,
                (url, ) => {
                    history.replaceState(null, document.title, url);
                    getSignatures();
                });

            for (const elem of document.querySelectorAll('a.small.basic.label')) {
                elem.addEventListener('click', e => {
                    const accession = e.target.closest('tr').getAttribute('data-id');
                    const div = document.querySelector('.ui.sticky .ui.comments');
                    comments.getSignatureComments(accession, 2, div);
                });
            }

            if (sortBy !== null && sortOrder !== null) {
                for (const th of table.querySelectorAll('th[data-sort-by]')) {
                    if (th.dataset.sortBy === sortBy) {
                        th.dataset.sortOrder = sortOrder;
                        th.querySelector("i").className = `button icon sort ${sortOrder === "asc" ? "up" : "down"}`;
                    } else {
                        th.dataset.sortOrder = "";
                        th.querySelector("i").className = "button icon sort";
                    }
                }
            }

            // Tooltips
            $('[data-content]').popup();
        });
}


document.addEventListener('DOMContentLoaded', () => {
    updateHeader()
    getSignatures();
    backToTop();

    $('.message .close')
        .on('click', function() {
            $(this)
                .closest('.message')
                .transition('fade');
        });

    const inputs = document.querySelectorAll('.ui.form input');
    for (const input of inputs) {
        input.addEventListener('change', (e, ) => {
            const type = e.currentTarget.type;
            const key = e.currentTarget.name;
            const value = e.currentTarget.value;
            const checked = e.currentTarget.checked;
            const url = new URL(location.href);

            if (value && (type === "radio" || (type === "checkbox" && checked)))
                url.searchParams.set(key, value);
            else
                url.searchParams.delete(key);

            url.searchParams.delete('page');
            url.searchParams.delete('page_size');

            history.replaceState(null, document.title, url.toString());
            getSignatures();
        });
    }

    const url = new URL(location.href);
    for (const input of inputs) {
        const key = input.name;

        if (url.searchParams.has(key)) {
            const value = url.searchParams.get(key);

            let selector = null;
            if (input.type === "checkbox") {
                selector = `input[type="checkbox"][name="${key}"]`;
            } else if (value === input.value) {
                selector = `input[type="radio"][name="${key}"][value="${value}"]`;
            }

            if (selector !== null)
                document.querySelector(selector).checked = true;
        }
    }

    document.querySelector('.ui.comments form button')
        .addEventListener('click', e => {
            e.preventDefault();
            const form = e.target.closest('form');
            const accession = form.getAttribute('data-id');
            const textarea = form.querySelector('textarea');

            comments.postSignatureComment(accession, textarea.value.trim())
                .then(object => {
                    if (object.status) {
                        comments.getSignatureComments(accession, 2, e.target.closest(".ui.comments"));
                        getSignatures();
                    } else
                        modals.error(object.error.title, object.error.message);
                });
        });

    const colHeaders = document.querySelectorAll('th[data-sort-by]');
    colHeaders.forEach(node => {
        node.addEventListener("click", e => {
            const sortBy = node.dataset.sortBy;
            let sortOrder = node.dataset.sortOrder;

            const url = new URL(location.href);

            if (sortOrder === "asc") {
                node.querySelector("i").className = "button icon sort down";
                sortOrder = "desc";
            }
            else {
                node.querySelector("i").className = "button icon sort up";
                sortOrder = "asc";
            }

            node.dataset.sortOrder = sortOrder;

            colHeaders.forEach(otherNode => {
                if (otherNode !== node) {
                    otherNode.dataset.sortOrder = '';
                    otherNode.querySelector("i").className = "button icon sort";
                }
            });

            const keySort = "sort-by";
            const keyOrder = "sort-order";

            if (sortBy)
                url.searchParams.set(keySort, sortBy);
            else if (url.searchParams.has(keySort))
                url.searchParams.delete(keySort);

            if (sortOrder)
                url.searchParams.set(keyOrder, sortOrder);
            else if (url.searchParams.has(keyOrder))
                url.searchParams.delete(keyOrder);

            history.replaceState(null, document.title, url.toString());
            getSignatures();
        });
    });

    let sortCol = null;
    let sortOrder = null;
    for (const [key, value] of [...new URLSearchParams(location.search).entries()]) {
        if (key === 'sort-by') {
            sortCol = value;
            continue
        } else if (key === 'sort-order') {
            sortOrder = value;
            continue;
        }

        // const inputs = document.querySelectorAll(`input[name="${key}"]`);
        // for (const node of inputs){
        //     if (node.type === "radio" || node.type === "checkbox") {
        //         node.checked = node.value === value;
        //     }
        // }
    }
});
