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

export function setCharsCountdown(input) {
    const maxLength = Number.parseInt(input.getAttribute('maxlength'), 10);
    input.parentNode.querySelector('p').innerHTML = (maxLength - input.value.length) + ' remaining characters';
}

export function toggleErrorMessage(elem, error) {
    if (error === undefined || error === null) {
        setClass(elem, 'hidden', true);
        return;
    }

    elem.innerHTML = `<div class="header">${error.title}</div><p>${error.message}</p>`;
    setClass(elem, 'hidden', false);
}

export function escape(value) {
    return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/ /g, '&nbsp;');
}

export function unescape(value) {
    return value
        .replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&nbsp;/g, ' ');
}

export function copy2clipboard(elem) {
    const input = document.createElement('input');
    input.value = unescape(elem.innerHTML);
    document.body.appendChild(input);
    try {
        input.select();
        document.execCommand('copy');
        elem.className = 'positive';
    } catch (err) {
        console.error(err);
        elem.className = 'negative';
    } finally {
        document.body.removeChild(input);
        setTimeout(() => {
            elem.className = '';
        }, 300);
    }
}