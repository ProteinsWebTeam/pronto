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

