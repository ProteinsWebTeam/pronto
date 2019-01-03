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

export function openErrorModal(error) {
    const modal = document.getElementById("error-modal");
    modal.querySelector(".header").innerHTML = error.title || 'Something when wrong';
    modal.querySelector(".content p").innerHTML = error.message;
    $(modal).modal("show");
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

export function renderCheckbox(entryId, isChecked) {
    if (!entryId)
        return '<div class="ui disabled fitted checkbox"><input disabled="disabled" type="checkbox"><label></label></div>';
    else if (isChecked)
        return '<div class="ui checked fitted checkbox"><input name="' + entryId + '" checked="" type="checkbox"><label></label></div>';
    else
        return '<div class="ui fitted checkbox"><input name="' + entryId + '" type="checkbox"><label></label></div>';
}

export function dimmer(show) {
    setClass(document.getElementById('dimmer'), 'active', show);
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

export function useWhiteText(rgb) {
    // Implementation of https://www.w3.org/TR/WCAG20/

    const color = JSON.parse(JSON.stringify(rgb));
    ['r', 'g', 'b'].forEach(k => {
        color[k] /= 255;

        if (color[k] <= 0.03928)
            color[k] /= 12.92;
        else
            color[k] = Math.pow((color[k] + 0.055) / 1.055, 2.4);
    });

    // luminance formula: https://www.w3.org/TR/WCAG20/#relativeluminancedef
    const l = 0.2126 * color.r + 0.7152 * color.g + 0.0722 * color.b;
    return l <= 0.179;
}

export function toRGB(color) {
    return 'rgb('+ color.r +','+ color.g +','+ color.b +')';
}