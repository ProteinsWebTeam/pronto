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

export function encodeParams(params, allowNull) {
    const arrParams = [];
    for (let p in params) {
        if (params.hasOwnProperty(p)) {
            if (params[p] === false)
                continue;
            else if (params[p] !== null)
                arrParams.push(p + '=' + params[p]);
            else if (allowNull)
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
        const sub = div.querySelector('.ui.header .sub');
        if (sub) sub.innerHTML = id;

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

                openConfirmModal(
                    'Flag comment?',
                    'This comment will be marked as obsolete, and highlighted in red.',
                    'Flag',
                    function () {
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

export function paginate(element, page, pageSize, count, onClick) {
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

export function openConfirmModal(header, content, approve, onApprove, onDeny) {
    const modal = document.getElementById('confirm-modal');

    modal.querySelector('.header').innerText = header;
    modal.querySelector('.content').innerHTML = '<p>'+ content +'</p>';
    modal.querySelector('.approve').innerText = approve;

    $(modal)
        .modal({
            onApprove: function () {
                if (onApprove) onApprove();
            },
            onDeny: function () {
                if (onDeny) onDeny();
            }
        })
        .modal('show');
}

export function listenMenu(menu) {
    const items = menu.querySelectorAll('a.item');
    Array.from(items).forEach(item => {
        item.addEventListener('click', e => {
            Array.from(items).forEach(i => {
                setClass(i, 'active', i === e.target);
            });
        });
    });
}

export function MethodsSelectionView(root) {
    this.root = root;
    this.methods = [];
    const self = this;

    // Init
    (function () {
        const input = self.root.querySelector('input[type=text]');
        input.addEventListener('keyup', e => {
            if (e.which === 13) {
                let render = false;
                e.target.value.trim().replace(/,/g, ' ').split(' ').forEach(id => {
                    if (id.length && self.methods.indexOf(id) === -1) {
                        self.methods.push(id);
                        render = true;
                    }
                });

                e.target.value = null;
                if (render)
                    self.render();
            }
        });

        Array.from(self.root.querySelectorAll('.links a')).forEach(element => {
            element.addEventListener('click', e => {
                if (!self.methods.length)
                    e.preventDefault();
            });
        });
    })();

    this.clear = function () {
        this.methods = [];
        return this;
    };


    this.add = function(methodId) {
        if (this.methods.indexOf(methodId) === -1)
            this.methods.push(methodId);
        setClass(this.root.querySelector('.ui.input'), 'error', false);
        return this;
    };

    this.render = function () {
        const div = this.root.querySelector('.ui.grid .column:last-child');
        let html = '';
        this.methods.forEach(m => {
            html += '<a class="ui basic label" data-id="' + m + '">' + m + '<i class="delete icon"></i></a>';
        });
        div.innerHTML = html;

        let nodes = div.querySelectorAll('a i.delete');
        for (let i = 0; i < nodes.length; ++i) {
            nodes[i].addEventListener('click', e => {
                const methodAc = e.target.parentNode.getAttribute('data-id');
                const newMethods = [];
                this.methods.forEach(m => {
                    if (m !== methodAc)
                        newMethods.push(m);
                });
                this.methods = newMethods;
                this.render();

                if (!this.methods.length)
                    setClass(this.root.querySelector('.ui.input'), 'error', true);
            });
        }

        Array.from(this.root.querySelectorAll('.links a')).forEach(element => {
            element.setAttribute('href', '/methods/' + this.methods.join('/') + '/' + element.getAttribute('data-page') + '/');
        });
    };

    this.toggle = function (page) {
        Array.from(this.root.querySelectorAll('.links a')).forEach(e => {
            setClass(e, 'active', e.getAttribute('data-page') === page);
        });
    };
}

export const gradientPuBu = [
    '#ffffff',
    '#ece7f2',
    '#d0d1e6',
    '#a6bddb',
    '#74a9cf',
    '#3690c0',
    '#0570b0',
    '#045a8d',
    '#023858'
];

export function useWhiteText(bgHexColor) {
    // Implementation of https://www.w3.org/TR/WCAG20/
    const rgb = hex2rgb(bgHexColor);
    ['r', 'g', 'b'].forEach(k => {
        rgb[k] /= 255;

        if (rgb[k] <= 0.03928)
            rgb[k] /= 12.92;
        else
            rgb[k] = Math.pow((rgb[k] + 0.055) / 1.055, 2.4);
    });

    // luminance formula: https://www.w3.org/TR/WCAG20/#relativeluminancedef
    const l = 0.2126 * rgb.r + 0.7152 * rgb.g + 0.0722 * rgb.b;
    return l <= 0.179;
}


export function hex2rgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
    } : null;
}

export function rgb2hex(c) {
    return '#' + ((1 << 24) + (Math.floor(c.r) << 16) + (Math.floor(c.g) << 8) + Math.floor(c.b)).toString(16).slice(1);
}


$(function () {
    const icon = document.querySelector('.ui.dimmer i.close');
    if (icon) {
        icon.addEventListener('click', () => {
            _processResults = false;
            dimmer(false);
        });
    }
});