let _processResults = true;

export function getJSON(url, callback) {
    _processResults = true;
    let xhr = new XMLHttpRequest();
    xhr.onload = function () {
        if (_processResults)
            callback(JSON.parse(this.responseText), xhr.status);
    };
    xhr.open('GET', url, true);
    xhr.send();
}

export function cancelQuery() {
    _processResults = false;
}

export function parseLocation(url) {
    let search;
    if (url) {
        const i = url.indexOf('?');
        search = i !== -1 ? url.substr(i) : '';
    } else
        search = location.search;

    let params = {};
    if (search.length) {
        const arr = search.substr(1).split('&');
        arr.forEach(function (p) {
            if (p.trim()) {
                const pArr = p.trim().split('=');
                params[pArr[0]] = pArr.length > 1 ? pArr[1] : null;
            }
        })
    }

    return params
}

export function initInput(input, initValue, callback) {
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

export function nvl(expr1, expr2, expr3) {
    if (expr1 !== null && expr1 !== undefined)
        return expr3 ? expr3 : expr1;
    else
        return expr2;
}

export  function renderCheckbox(entryId, isChecked) {
    if (!entryId)
        return '<div class="ui disabled fitted checkbox"><input disabled="disabled" type="checkbox"><label></label></div>';
    else if (isChecked)
        return '<div class="ui checked fitted checkbox"><input name="' + entryId + '" checked="" type="checkbox"><label></label></div>';
    else
        return '<div class="ui fitted checkbox"><input name="' + entryId + '" type="checkbox"><label></label></div>';
}

export function encodeParams(params, allowEmpty) {
    const arrParams = [];
    for (let p in params) {
        if (params.hasOwnProperty(p)) {
            if (params[p] !== null)
                arrParams.push(p + '=' + params[p]);
            else if (allowEmpty)
                arrParams.push(p);
        }
    }

    return arrParams.length ? '?' + arrParams.join('&') : '';
}

export function extendObj(original, options) {
    const obj = Object.assign({}, original);
    for (let prop in options) {
        if (options.hasOwnProperty(prop))
            obj[prop] = options[prop];
    }

    return obj;
}

export function setClass(element, className, active) {
    const classes = element.className.trim().split(' ');
    const hasClass = classes.indexOf(className) !== -1;

    if (active && !hasClass)
        element.className = classes.join(' ') + ' ' + className;
    else if (!active && hasClass) {
        let newClasses = [];
        for (let i = 0; i < classes.length; ++i) {
            if (classes[i] !== className)
                newClasses.push(classes[i]);
        }
        element.className = newClasses.join(' ');
    }
}

export function dimmer(show) {
    setClass(document.getElementById('dimmer'), 'active', show);
}

export function post(url, params, callback) {
    let xhr = new XMLHttpRequest();
    xhr.onload = function () {
        callback(JSON.parse(this.responseText))
    };
    xhr.open('POST', url, true);
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
    let postVars = [];
    for (let key in params) {
        if (params.hasOwnProperty(key))
            postVars.push(key + '=' + params[key])
    }
    xhr.send(postVars.join('&'));
}

export function deletexhr(url, params, callback) {
    let xhr = new XMLHttpRequest();
    xhr.onload = function () {
        callback(JSON.parse(this.responseText))
    };
    xhr.open('DELETE', url, true);
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
    let postVars = [];
    for (let key in params) {
        if (params.hasOwnProperty(key))
            postVars.push(key + '=' + params[key])
    }
    xhr.send(postVars.join('&'));
}

export function getComments(div, type, id, size, callback) {
    getJSON('/api/'+ type +'/' + id + '/comments/' + encodeParams({size: size}), data => {
        // Sub header
        document.querySelector('.ui.header .sub').innerHTML = id;

        let html = '';
        data.results.forEach(comment => {
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

        if (data.results.length < data.count)
            html += '<div class="actions"><a>View more comments</a></div>';

        div.querySelector('.comments-content').innerHTML = html;

        const form = div.querySelector('form');
        form.setAttribute('data-id', id);

        const textarea = form.querySelector('textarea');
        setClass(textarea.parentNode, 'error', false);
        textarea.value = null;

        const action = div.querySelector('.comments-content .actions a');
        if (action) {
            action.addEventListener('click', e => {
                e.preventDefault();
                getComments(div, type, id, null, callback);
            });
        }

        Array.from(div.querySelectorAll('.comment .metadata a')).forEach(element => {
            element.addEventListener('click', e => {
                e.preventDefault();

                const commentId = e.target.closest('.comment').getAttribute('data-id');
                const modal = document.getElementById('confirm-modal');

                modal.querySelector('.content').innerHTML = '<p>Flag this comment as invalid? This action <strong>cannot</strong> be undone.</p>';

                $(modal)
                    .modal({
                        onApprove: function () {
                            deletexhr('/api/' + type + '/' + id + '/comment/' + commentId + '/', {
                                status: 0
                            }, data => {
                                if (data.status)
                                    getComments(div, type, id, size, callback);
                                else {
                                    const modal = document.getElementById('error-modal');
                                    modal.querySelector('.content p').innerHTML = data.message;
                                    $(modal).modal('show');
                                }
                            });
                        },
                        onDeny: function () {}
                    })
                    .modal('show');
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

export function paginate(table, page, pageSize, count, onClick) {
    const lastPage = Math.ceil(count / pageSize);
    const pathName = location.pathname;
    const params = parseLocation(location.search);
    let html = '';

    const genLink = function(page) {
        return pathName + encodeParams(extendObj(params, {page: page, pageSize: pageSize}))
    };

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

    const pagination = table.querySelector('.pagination');
    pagination.innerHTML = html;
    table.querySelector('thead span').innerHTML = (count ? (page - 1) * pageSize + 1 : 0) + ' - ' + Math.min(page * pageSize, count) + ' of ' + count.toLocaleString() + ' entries';

    const elements = pagination.querySelectorAll('a[href]');
    for (let i  = 0; i < elements.length; ++i) {
        elements[i].addEventListener('click', e => {
            e.preventDefault();
            onClick(elements[i].href);
        });
    }
}
