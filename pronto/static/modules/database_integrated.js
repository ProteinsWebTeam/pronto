import {finaliseHeader, nvl} from "../header.js"
import * as ui from "../ui.js";
import {checkEntry} from '../events.js';
import {getSignatureComments, postSignatureComment} from "../comments.js";

function getSignatures() {
    ui.dimmer(true);
    const pathname = location.pathname.match(/(\/database\/.+\/)/)[1];
    fetch(URL_PREFIX+"/api" + pathname + location.search)
        .then(response => response.json())
        .then(results => {
            if (!results.database) {
                // TODO: show error
                return;
            }

            const title = results.database.name + ' (' + results.database.version + ') signatures';
            document.querySelector('h1.ui.header').innerHTML = title;
            document.title = title + ' | Pronto';

            let html = '';
            if (results.signatures.length) {
                results.signatures.forEach(signature => {
                    html += '<tr data-id="'+ signature.accession +'">' +
                        '<td><a href="'+URL_PREFIX+'/prediction/'+ signature.accession +'/">'+ signature.accession +'</a></td>';

                    if (signature.entry !== null) {
                        html += '<td>'
                            + '<span class="ui circular mini label type-'+ signature.entry.type +'">'+ signature.entry.type +'</span>'
                            + '<a href="'+URL_PREFIX+'/entry/'+ signature.entry.accession +'/">'+ signature.entry.accession +'</a>'
                            + '</td>'
                            + '<td class="collapsing">'
                            + ui.renderCheckbox(signature.entry.accession, signature.entry.checked)
                            + '</td>';
                    } else {
                        html += '<td></td>'
                            + '<td class="collapsing">'
                            + ui.renderCheckbox(null, null)
                            + '</td>';
                    }

                    html += '<td class="right aligned">'+ nvl(signature.count_now, '') +'</td>' +
                        '<td class="right aligned">'+ nvl(signature.count_then, '') +'</td>' +
                        '<td class="right aligned">'+ (signature.count_now && signature.count_then ? Math.floor(signature.count_now / signature.count_then * 1000) / 10 : '') +'</td>';

                    // Comment row
                    html += '<td class="ui comments"><div class="comment"><div class="content">';
                    if (signature.latest_comment) {
                        html += '<a class="author">' + signature.latest_comment.author + '&nbsp;</a>' +
                            '<div class="metadata"><span class="date">' + signature.latest_comment.date + '</span></div>' +
                            '<div class="text">' + (signature.latest_comment.text.length < 40 ? signature.latest_comment.text : signature.latest_comment.text.substr(0, 40) + '&hellip;')  + '</div>';
                    }
                    html += '<div class="actions"><a class="reply">Leave a comment</a></div></div></div></td></tr>';
                });
            } else
                html = '<tr><td class="center aligned" colspan="7">No matching signatures found</td></tr>';

            const table = document.getElementById("table-signatures");
            table.querySelector('tbody').innerHTML = html;

            ui.paginate(
                table,
                results.page_info.page,
                results.page_info.page_size,
                results.count,
                (url,) => {
                    history.replaceState(null, null, url);
                    getSignatures();
                });

            Array.from(document.querySelectorAll('tbody input[type=checkbox]')).forEach(input => {
                input.addEventListener('change', e => checkEntry(input));
            });

            Array.from(document.querySelectorAll('.comment .reply')).forEach(elem => {
                elem.addEventListener('click', e => {
                    const accession = e.target.closest('tr').getAttribute('data-id');
                    const div = document.querySelector('.ui.sticky .ui.comments');
                    getSignatureComments(accession, 2, div);
                });
            });

            ui.dimmer(false);
        });
}


$(function () {
    finaliseHeader();
    getSignatures();

    const url = new URL(location.href);
    ui.initSearchBox(
        document.querySelector("thead input"),
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

     Array.from(document.querySelectorAll('input[type=radio]')).forEach(radio => {
        radio.addEventListener('change', e => {
            if (radio.value)
                url.searchParams.set(radio.name, radio.value);
            else
                url.searchParams.delete(radio.name);
            history.replaceState(null, null, url.toString());
            getSignatures();
        });
    });

     ["integrated", "checked", "commented"].forEach(key => {
         if (url.searchParams.has(key))
             document.querySelector("input[type=radio][name="+ key +"][value='"+ url.searchParams.get(key) +"']").checked = true;
     });

    document.querySelector('.ui.comments form button').addEventListener('click', e => {
        e.preventDefault();
        const form = e.target.closest('form');
        const accession = form.getAttribute('data-id');
        const textarea = form.querySelector('textarea');

        postSignatureComment(accession, textarea.value.trim())
            .then(result => {
                if (result.status)
                    getSignatureComments(accession, 2, e.target.closest(".ui.comments"));
                 else
                    ui.openErrorModal(result.error);
            });
    });
});