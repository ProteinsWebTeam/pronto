import { updateHeader } from '../ui/header.js'
import * as checkbox from '../ui/checkbox.js'
import * as comments from '../ui/comments.js';
import * as dimmer from '../ui/dimmer.js'
import * as modals from '../ui/modals.js'
import * as pagination from '../ui/pagination.js'
import * as searchbox from '../ui/searchbox.js'


function fmtSignature(s) {
    let html = `
        <span class="ui circular mini label type ${s.type.code}">
            ${s.type.code}
        </span>
    `;

    if (s.name !== null) {
        html += `
            <a href="/signature/${s.accession}/">
                ${s.accession} &middot; ${s.name}
            </a>
        `;
    } else {
        html += `
            <a href="/signature/${s.accession}/">
                ${s.accession}
            </a>
        `;
    }
    return html;
}

function fmtEntry(e) {
    if (e !== null) {
        return `
            <td class="nowrap">
                <span class="ui circular mini label type ${e.type.code}">${e.type.code}</span>
                <a href="/entry/${e.accession}/">${e.accession} &middot; ${e.short_name}</a>
            </td>
            <td class="collapsing">${checkbox.createDisabled(e.checked)}</td>        
        `;
    } else {
        return `
            <td></td>
            <td class="collapsing">${checkbox.createDisabled(false)}</td>        
        `;
    }
}


function getSignatures() {
    dimmer.on();
    const url = new URL(`/api${location.pathname}signatures/`, location.origin);
    const searchParams = new URLSearchParams(location.search);
    for (const [key, value] of searchParams.entries()) {
        url.searchParams.set(key, value);
    }
    url.searchParams.set('details', '');

    fetch(url.toString())
        .then(response => {
            dimmer.off();
            if (response.ok)
                return response.json();
            throw response.status.toString();
        })
        .then(object => {
            const title = `${object.database.name} (${object.database.version})`;
            document.querySelector('h1.ui.header').innerHTML = title;
            document.title = title + ' | Pronto';

            const renderCommentText = (text) => {
                if (text.length < 40)
                    return text;
                return text.substr(0, 40) + '&hellip;';
            };

            let html = '';
            if (object.count) {
                for (const signature of object.results) {
                    html += `<tr data-id="${signature.accession}">
                             <td class="nowrap">${fmtSignature(signature)}</td>
                             ${fmtEntry(signature.entry)}
                    `;

                    let change = '';
                    if (signature.proteins.then > 0 && signature.proteins.now > 0) {
                        change = (signature.proteins.now - signature.proteins.then) / signature.proteins.then * 100;
                        if (change >= 1)
                            change = `+${Math.ceil(change)}%`;
                        else if (change <= -1)
                            change = `${Math.floor(change)}%`;
                        else
                            change = '';
                    }

                    html += `
                        <td class="right aligned">${signature.proteins.then.toLocaleString()}</td>
                        <td class="right aligned">${signature.proteins.now.toLocaleString()}</td>
                        <td class="right aligned">${change}</td>

                        <td class="ui comments"><div class="comment"><div class="content">
                    `;

                    // Comment row
                    if (signature.latest_comment) {
                        html += `
                            <a class="author">${signature.latest_comment.author}</a>
                            <div class="metadata"><span class="date">${signature.latest_comment.date}</span></div>
                            <div class="text">${renderCommentText(signature.latest_comment.text)}</div>
                        `;
                    }
                    html += '<div class="actions"><a class="reply">Leave a comment</a></div></div></div></td></tr>';
                }
            } else
                html = '<tr><td class="center aligned" colspan="7">No matching signatures found</td></tr>';

            const table = document.getElementById("signatures");
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
        })
        .catch(status => {
            // todo: show error
        })
}


document.addEventListener('DOMContentLoaded', () => {
    updateHeader();
    getSignatures();

    const url = new URL(location.href);
    const radios = document.querySelectorAll('input[type=radio]');

    for (const radio of radios) {
        radio.addEventListener('change', e => {
            if (radio.value)
                url.searchParams.set(radio.name, radio.value);
            else
                url.searchParams.delete(radio.name);
            history.replaceState(null, null, url.toString());
            getSignatures();
        });
    }

    for (const key of new Set(Array.from(radios, x => x.name))) {
        if (url.searchParams.has(key))
            document.querySelector(`input[type=radio][name="${key}"][value="${url.searchParams.get(key)}"]`).checked = true;
    }

    searchbox.init(
        document.querySelector('#signatures thead input'),
        url.searchParams.get("search"),
        (value, ) => {
            url.searchParams.delete("page");
            if (value !== null)
                url.searchParams.set("search", value);
            else
                url.searchParams.delete("search");

            history.replaceState(null, null, url.toString());
            getSignatures();
        }
    );

    $('.message .close')
        .on('click', function() {
            $(this)
                .closest('.message')
                .transition('fade');
        });

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
});
