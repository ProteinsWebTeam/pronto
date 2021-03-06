import * as modals from './modals.js';
import * as utils from './utils.js';

export function getEntryComments(accession, max, div, callback) {
    getComments('entry', accession, max, div, callback);
}

export function getSignatureComments(accession, max, div, callback) {
    getComments('signature', accession, max, div, callback);
}

export function postEntryComment(accession, text) {
    return postComment('entry', accession, text);
}

export function postSignatureComment(accession, text) {
    return postComment('signature', accession, text);
}

function getComments(type, accession, max, div, callback) {
    const url = new URL(`/api/${type}/${accession}/comments/`, location.origin);
    if (max)
        url.searchParams.set("max", max);

    fetch(url.toString())
        .then(response => response.json())
        .then(object => {
            const sub = div.querySelector('.ui.header .sub');
            if (sub) sub.innerHTML = accession;

            let html = "";
            for (const comment of object.results) {
                if (comment.status) {
                    html += `
                        <div class="comment" data-id="${comment.id}">
                            <div class="content">
                                <a class="author">${comment.author}</a>
                                <div class="metadata">
                                    <span class="date">${comment.date}</span>
                                    <a><i class="delete icon"></i></a>
                                </div>
                                <div class="text">${comment.text}</div>
                            </div>
                        </div>
                    `;
                } else {
                    html += `
                        <div class="negative comment" data-id="${comment.id}">
                            <div class="content">
                                <a class="author">${comment.author}</a>
                                <div class="metadata">
                                    <span class="date">${comment.date}</span>
                                </div>
                                <div class="text">${comment.text}</div>
                            </div>
                        </div>
                    `;
                }
            }

            if (object.results.length < object.count)
                html += '<div class="actions"><a>View more comments</a></div>';

            div.querySelector('.comments-content').innerHTML = html;

            const form = div.querySelector('form');
            form.setAttribute('data-id', accession);

            const textarea = form.querySelector('textarea');
            utils.setClass(textarea.parentNode, 'error', false);
            textarea.value = null;

            const action = div.querySelector('.comments-content .actions a');
            if (action) {
                action.addEventListener('click', e => {
                    e.preventDefault();
                    getComments(type, accession, null, div, callback);
                });
            }

            Array.from(div.querySelectorAll('.comment .metadata a')).forEach(element => {
                element.addEventListener('click', e => {
                    e.preventDefault();
                    const id = e.target.closest('.comment').getAttribute('data-id');

                    modals.ask(
                        "Deprecate comment?",
                        "This comment will be marked as obsolete.",
                        "Deprecate",
                        () => {
                            fetch(`/api/${type}/${accession}/comment/${id}/`, { method: "DELETE" })
                                .then(response => response.json())
                                .then(result => {
                                    if (result.status)
                                        getComments(type, accession, max, div, callback);
                                    else
                                        modals.error(result.error.title, result.error.message);
                                });
                        }
                    );
                });
            });

            const sticky = div.closest('.sticky');
            if (sticky) {
                utils.setClass(sticky, 'hidden', false);
                $(sticky).sticky({context: div.querySelector('table')});
            }

            if (callback) callback();
        });
}


function postComment(type, accession, text) {
    return fetch(`/api/${type}/${accession}/comment/`, {
        method: "PUT",
        headers: {
            "Content-Type": "application/json; charset=utf-8"
        },
        body: JSON.stringify({text: text})
    })
        .then(response => response.json());

}
