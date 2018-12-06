import {deletexhr, setClass} from "./utils.js";

export function openConfirmModal(header, content, approve, onApprove, onDeny) {
    const modal = document.getElementById("confirm-modal");

    modal.querySelector(".header").innerText = header;
    modal.querySelector(".content").innerHTML = "<p>"+ content +"</p>";
    modal.querySelector(".approve").innerText = approve;

    $(modal)
        .modal({
            onApprove: function () {
                if (onApprove) onApprove();
            },
            onDeny: function () {
                if (onDeny) onDeny();
            }
        })
        .modal("show");
}

export function openErrorModal(message) {
    const modal = document.getElementById("error-modal");
    modal.querySelector(".content p").innerHTML = message;
    $(modal).modal("show");
}

export function checkEntry(input) {
    // Expects input.name to be the entry accession
    openConfirmModal(
        (input.checked ? "Check" : "Uncheck") + " entry?",
        "<strong>" + input.name + "</strong> will be marked as " + (input.checked ? "checked" : "unchecked"),
        (input.checked ? "Check" : "Uncheck"),
        () => {
            fetch("/api/entry/" + input.name + "/check/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json; charset=utf-8",
                },
                body: JSON.stringify({
                    checked: input.checked ? 1 : 0
                })
            }).then(response => response.json())
                .then(result => {
                    if (result.status) {
                        Array.from(document.querySelectorAll("input[type=checkbox][name="+input.name+"]")).forEach(cbox => {
                            cbox.checked = input.checked;
                        });
                    } else {
                        openErrorModal(result.message);
                        input.checked = !input.checked;
                    }
                });
        },
        () => {
            input.checked = !input.checked;
        }
    );

}

export function paginate(element, page, pageSize, count, onClick, url) {
    const newURL = new URL(url === undefined ? location.href : url);
    newURL.searchParams.set("page_size", pageSize);

    const genLink = function (page) {
        newURL.searchParams.set("page", page);
        return newURL.toString();
    };

    const lastPage = Math.ceil(count / pageSize);
    let html = '';
    if (page === 1)
        html += '<a class="icon disabled item"><i class="left chevron icon"></i></a><a class="active item">1</a>';
    else
        html += '<a class="icon item" href="'+ genLink(page-1)  +'"><i class="left chevron icon"></i></a><a class="item" href="'+ genLink(1)  +'">1</a>';

    let ellipsisBefore = false;
    let ellipsisAfter = false;
    for (let i = 2; i < lastPage; ++i) {
        if (i === page)
            html += '<a class="active item">'+ i +'</a>';
        else if (Math.abs(i - page) === 1)
            html += '<a class="item" href="'+ genLink(i) +'">'+ i +'</a>';
        else if (i < page && !ellipsisBefore) {
            html += '<div class="disabled item">&hellip;</div>';
            ellipsisBefore = true;
        } else if (i > page && !ellipsisAfter) {
            html += '<div class="disabled item">&hellip;</div>';
            ellipsisAfter = true;
        }
    }

    if (lastPage > 1) {
        if (page === lastPage)
            html += '<a class="active item">'+ lastPage +'</a>';
        else
            html += '<a class="item" href="'+ genLink(lastPage)  +'">'+ lastPage +'</a>'
    }

    if (page === lastPage || !lastPage)
        html += '<a class="icon disabled item"><i class="right chevron icon"></i></a>';
    else
        html += '<a class="icon item" href="'+ genLink(page + 1)  +'"><i class="right chevron icon"></i></a>';

    const pagination = element.querySelector('.pagination');
    pagination.innerHTML = html;

    if (onClick) {
        Array.from(pagination.querySelectorAll('a[href]')).forEach(elem => {
            elem.addEventListener('click', e => {
                e.preventDefault();
                onClick(elem.href);
            });
        });
    }

    const span = element.querySelector('thead span');
    if (span)
        span.innerHTML = (count ? (page - 1) * pageSize + 1 : 0) + ' - ' + Math.min(page * pageSize, count) + ' of ' + count.toLocaleString() + ' entries';
}

export function initSearchBox(input, initValue, callback) {
    let value = initValue;
    let counter = 0;

    if (value) input.value = value;

    input.addEventListener('keydown', e => {
        ++counter;
    });

    input.addEventListener('keyup', e => {
        setTimeout(() => {
            if (!--counter && value !== e.target.value) {
                value = e.target.value;
                callback(value.length ? value : null);
            }
        }, 350);
    });
}

function getComments(type, accession, max, div, callback) {
    const url = new URL("/api/"+ type +"/" + accession + "/comments/", location.origin);
    if (max)
        url.searchParams.set("max", max);

    fetch(url.toString())
        .then(response => response.json())
        .then(result => {
            const sub = div.querySelector('.ui.header .sub');
            if (sub) sub.innerHTML = accession;

            let html = "";
            result.comments.forEach(comment => {
                if (comment.status)
                    html += '<div class="comment" data-id="'+ comment.id +'">' +
                        '<div class="content">' +
                        '<a class="author">'+ comment.author +'</a>' +
                        '<div class="metadata">' +
                        '<span class="date">'+ comment.date +'</span>' +
                        '<a><i class="remove icon"></i></a>' +
                        '</div>' +
                        '<div class="text">'+ comment.text +'</div></div></div>';
                else
                    html += '<div class="negative comment" data-id="'+ comment.id +'">' +
                        '<div class="content">' +
                        '<a class="author">'+ comment.author +'</a>' +
                        '<div class="metadata">' +
                        '<span class="date">'+ comment.date +'</span>' +
                        '</div>' +
                        '<div class="text">'+ comment.text +'</div></div></div>';
            });

            if (result.comments.length < result.count)
                html += '<div class="actions"><a>View more comments</a></div>';

            div.querySelector('.comments-content').innerHTML = html;

            const form = div.querySelector('form');
            form.setAttribute('data-id', accession);

            const textarea = form.querySelector('textarea');
            setClass(textarea.parentNode, 'error', false);
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

                    openConfirmModal(
                        "Flag comment?",
                        "This comment will be marked as obsolete, and highlighted in red",
                        "Flag",
                        () => {
                            fetch("/api/"+ type +"/" + accession + "/comment/" + id + "/", {
                                method: "DELETE"
                            }).then(response => response.json())
                                .then(result => {
                                    if (result.status)
                                        getComments(type, accession, max, div, callback);
                                    else
                                        openErrorModal(result.message);
                                });
                        }
                    );
                });
            });

            const sticky = div.closest('.sticky');
            if (sticky) {
                setClass(sticky, 'hidden', false);
                $(sticky).sticky({context: div.querySelector('table')});
            }

            if (callback) callback();

        });
}


export function getEntryComments(accession, max, div, callback) {
    getComments("entry", accession, max, div, callback);
}

export function getSignatureComments(accession, max, div, callback) {
    getComments("signature", accession, max, div, callback);
}

function postComment(type, accession, text) {
    return fetch("/api/" + type + "/" + accession + "/comment/", {
        method: "PUT",
        headers: {
            "Content-Type": "application/json; charset=utf-8"
        },
        body: JSON.stringify({text: text})
    })
        .then(response => response.json());

}

export function postSignatureComment(accession, text) {
    return postComment("signature", accession, text);
}

export function postEntryComment(accession, text) {
    return postComment("entry", accession, text);
}