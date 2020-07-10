import {updateHeader} from '../ui/header.js'
import * as checkbox from '../ui/checkbox.js'
import * as comments from '../ui/comments.js';
import * as dimmer from '../ui/dimmer.js'
import * as modals from '../ui/modals.js'
import * as pagination from '../ui/pagination.js'
import * as searchbox from '../ui/searchbox.js'


function getSignatures() {
    dimmer.on();
    fetch(`/api${location.pathname}signatures/${location.search}`)
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

            let html = '';
            if (object.count) {
                for (const signature of object.results) {
                    html += '<tr data-id="'+ signature.accession +'">' +
                        '<td><a href="/signature/'+ signature.accession +'/">'+ signature.accession +'</a></td>';

                    if (signature.entry !== null) {
                        html += '<td>'
                            + '<span class="ui circular mini label type '+ signature.entry.type +'">'+ signature.entry.type +'</span>'
                            + '<a href="/entry/'+ signature.entry.accession +'/">'+ signature.entry.accession +'</a>'
                            + '</td>'
                            + '<td class="collapsing">'
                            + checkbox.createDisabled(signature.entry.checked)
                            + '</td>';
                    } else {
                        html += '<td></td>'
                            + '<td class="collapsing">'
                            + checkbox.createDisabled(false)
                            + '</td>';
                    }

                    html += '<td class="right aligned">'+ signature.proteins.then +'</td>' +
                        '<td class="right aligned">'+ signature.proteins.now +'</td>' +
                        '<td class="right aligned">'+ (signature.proteins.then && signature.proteins.now ? Math.floor(signature.proteins.now / signature.proteins.then * 1000) / 10 : '') +'</td>';

                    // Comment row
                    html += '<td class="ui comments"><div class="comment"><div class="content">';
                    if (signature.latest_comment) {
                        html += '<a class="author">' + signature.latest_comment.author + '&nbsp;</a>' +
                            '<div class="metadata"><span class="date">' + signature.latest_comment.date + '</span></div>' +
                            '<div class="text">' + (signature.latest_comment.text.length < 40 ? signature.latest_comment.text : signature.latest_comment.text.substr(0, 40) + '&hellip;')  + '</div>';
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
                (url,) => {
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
