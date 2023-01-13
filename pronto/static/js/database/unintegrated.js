import { updateHeader } from '../ui/header.js'
import * as checkbox from '../ui/checkbox.js'
import * as comments from '../ui/comments.js';
import * as dimmer from '../ui/dimmer.js'
import * as modals from '../ui/modals.js'
import * as pagination from '../ui/pagination.js'
import { renderConfidence } from "../ui/signatures.js";


function renderEntry(entry) {
    if (entry === null)
        return '<td colspan="2"></td>'

    return `
        <td class="nowrap">
            <span class="ui circular mini label type ${entry.type}">${entry.type}</span>
            <a href="/entry/${entry.accession}/">${entry.accession}</a> 
    
        </td>
        <td class="collapsing">${checkbox.createDisabled(entry.checked)}</td>`;
    // <a>(${entry.name})</a>
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

            for (const [key, value] of Object.entries(object.parameters)) {
                document.querySelector(`input[name="${key}"][value="${value ? value : ''}"]`).checked = true;
            }

            const renderCommentText = (text) => {
                if (text.length < 30)
                    return text;
                return text.substr(0, 30) + '&hellip;';
            };

            let html = '';
            if (object.count > 0) {
                for (const signature of object.results) {
                    html += `<tr data-id="${signature.accession}">
                         <td rowspan="${signature.targets.length}"><a href="/signature/${signature.accession}/">${signature.accession}</a></td>
                         <td rowspan="${signature.targets.length}" class="right aligned">${signature.proteins.toLocaleString()}</td>
                         <td rowspan="${signature.targets.length}" class="ui comments"><div class="comment"><div class="content">`;
                    if (signature.comments > 0) {
                        html += `
                                <a class="author">${signature.latest_comment.author}</a>
                                <div class="metadata"><span class="date">${signature.latest_comment.date}</span></div>
                                <div class="text">${renderCommentText(signature.latest_comment.text)}</div>
                            `;
                    }
                    html += '<div class="actions"><a class="reply">Leave a comment</a></div></div></div></td>';


                    for (let i = 0; i < signature.targets.length; ++i) {
                        const target = signature.targets[i];

                        if (i) html += '<tr>';

                        html += `<td class="nowrap">
                                <span class="ui empty circular label" style="background-color: ${target.database.color};" data-content="${target.database.name}" data-position="left center" data-variation="tiny"></span>
                                <a href="/signature/${target.accession}/">${target.accession}</a>
                             </td>
                             <td class="right aligned">${target.proteins.toLocaleString()}</td>
                             <td class="right aligned">${target.collocations.toLocaleString()}</td>
                             <td class="right aligned">${target.overlaps.toLocaleString()}</td>
                             <td class="center aligned nowrap">${renderConfidence(target)}</td>
                             ${renderEntry(target.entry)}
                             </tr>`;
                    }
                }
            } else {
                html = '<tr><td class="center aligned" colspan="9">No matching signatures found</td></tr>'
            }

            const table = document.getElementById('results');
            const cell = table.querySelector('thead tr:first-child th:first-child');
            if (object.count > 1)
                cell.innerHTML = `${object.count} unintegrated signatures`;
            else
                cell.innerHTML = `${object.count} unintegrated signature`;

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

            for (const elem of document.querySelectorAll('.comment .reply')) {
                elem.addEventListener('click', e => {
                    const accession = e.target.closest('tr').getAttribute('data-id');
                    const div = document.querySelector('.ui.sticky .ui.comments');
                    comments.getSignatureComments(accession, 2, div);
                });
            }

            // Tooltips
            $('[data-content]').popup();
        });
}


document.addEventListener('DOMContentLoaded', () => {
    updateHeader();
    getSignatures();

    $('.message .close')
        .on('click', function() {
            $(this)
                .closest('.message')
                .transition('fade');
        });

    for (const input of document.querySelectorAll('input[type="radio"]')) {
        input.addEventListener('change', (e, ) => {
            const key = e.currentTarget.name;
            const value = e.currentTarget.value;
            const url = new URL(location.href);

            if (value)
                url.searchParams.set(key, value);
            else if (url.searchParams.has(key))
                url.searchParams.delete(key);

            history.replaceState(null, document.title, url.toString());
            getSignatures();
        });
    }

    document.querySelector('.ui.comments form button').addEventListener('click', e => {
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

    const col_headers = document.querySelectorAll('th[data-sort-by]');
    col_headers.forEach(node => {
        node.addEventListener("click", e => {
            const sortBy = node.getAttribute("data-sort-by");
            var sortOrder = node.getAttribute("data-sort-order")
            const url = new URL(location.href);
            var otherEl = "";

            if (sortBy === "accession")
                otherEl = "proteins"
            else
                otherEl = "accession"

            if (sortOrder === "asc") {
                node.setAttribute("data-sort-order", "desc");
                document.getElementById(`${sortBy}-btn`).className = "button icon sort up";
                sortOrder = "desc";
            }
            else {
                node.setAttribute("data-sort-order", "asc");
                document.getElementById(`${sortBy}-btn`).className = "button icon sort down";
                sortOrder = "asc";
            }
            document.getElementById(`${otherEl}-btn`).className = "button icon sort before";
            document.getElementById(otherEl).setAttribute("data-sort-order", "none");

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
});
