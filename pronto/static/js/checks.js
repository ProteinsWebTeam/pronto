import {updateHeader} from "./ui/header.js";
import * as modals from "./ui/modals.js"
import {setClass, escape, unescape, copy2clipboard} from "./ui/utils.js";

function createCard(type, term, addExceptions) {
    let card = `
        <div class="card" data-type="${type}">
        <div class="content">
            <a class="right floated meta"><i class="delete fitted icon"></i></a>
            <code>${escape(term.value)}</code>
            <div class="description">
    `;

    for (const exc of term.exceptions) {
        card += `<div class="ui basic small label" data-exception="${exc.id}">${exc.annotation || exc.entry}<i class="delete icon"></i></div>`;
    }

    card += '</div></div>';

    if (addExceptions)
        card += `<div class="ui bottom attached button"><i class="add icon"></i>Add exception</div>`;

    return card + '</div>'
}

function addTerm(ckType) {
    const modal = document.getElementById('new-term-modal');
    const field = modal.querySelector('.field');
    const input = field.querySelector('input');
    const message = modal.querySelector('.message');

    $(modal)
        .modal({
            onShow: () => {
                setClass(field, 'error', false);
                message.innerHTML = null;
                input.value = null;
            },
            onApprove: () => {
                const body = [
                    `type=${encodeURIComponent(ckType)}`,
                    `term=${encodeURIComponent(input.value)}`
                ]

                fetch('/api/checks/term/', {
                    method: 'PUT',
                    headers: {
                        'Content-type': 'application/x-www-form-urlencoded;charset=UTF-8'
                    },
                    body: body.join('&')
                })
                    .then(response => response.json())
                    .then(result => {
                        if (result.status) {
                            $(modal).modal('hide');
                            getChecks();
                        } else {
                            message.innerHTML = `<div class="header">${result.error.title}</div><p>${result.error.message}</p>`;
                            setClass(field, 'error', true);
                        }
                    });

                return false;
            }
        })
        .modal('show');
}

function addTermException(ckType, ckTerm) {
    const modal = document.getElementById('new-term-exception-modal');
    const field = modal.querySelector('.field');
    const input = field.querySelector('input');
    const message = modal.querySelector('.message');

    modal.querySelector('.header').innerHTML = `Add exception to &ldquo;${escape(ckTerm)}&rdquo;`

    $(modal)
        .modal({
            onShow: () => {
                setClass(field, 'error', false);
                message.innerHTML = null;
                input.value = null;
            },
            onApprove: () => {
                const body = [
                    `type=${encodeURIComponent(ckType)}`,
                    `term=${encodeURIComponent(ckTerm)}`,
                    `exception=${encodeURIComponent(input.value)}`
                ]

                fetch('/api/checks/term/exception/', {
                    method: 'PUT',
                    headers: {
                        'Content-type': 'application/x-www-form-urlencoded;charset=UTF-8'
                    },
                    body: body.join('&')
                })
                    .then(response => response.json())
                    .then(result => {
                        if (result.status) {
                            $(modal).modal('hide');
                            getChecks();
                        } else {
                            message.innerHTML = `<div class="header">${result.error.title}</div><p>${result.error.message}</p>`;
                            setClass(field, 'error', true);
                        }
                    });

                return false;
            }
        })
        .modal('show');
}

function deleteTerm(ckType, ckTerm) {
    modals.ask(
        'Delete term?',
        'This term will not be searched during sanity checks anymore.<br><strong>This action is irreversible.</strong>',
        'Delete',
        () => {
            fetch('/api/checks/term/', {
                method: 'DELETE',
                headers: {
                    'Content-type': 'application/x-www-form-urlencoded;charset=UTF-8'
                },
                body: `type=${encodeURIComponent(ckType)}&term=${encodeURIComponent(ckTerm)}`
            })
                .then(response => response.json())
                .then(result => {
                    if (result.status)
                        getChecks();
                    else
                        modals.error(result.error.title, result.error.message);
                });
        }
    )
}

function deleteException(exceptionID) {
    modals.ask(
        'Delete exception?',
        'More errors could be reported when running sanity checks.<br><strong>This action is irreversible.</strong>',
        'Delete',
        () => {
            fetch('/api/checks/exception/', {
                method: 'DELETE',
                headers: {
                    'Content-type': 'application/x-www-form-urlencoded;charset=UTF-8'
                },
                body: `id=${encodeURIComponent(exceptionID)}`
            })
                .then(response => response.json())
                .then(result => {
                    if (result.status)
                        getChecks();
                    else
                        modals.error(result.error.title, result.error.message);
                });
        }
    )
}

function addException(ckType, excType) {
    const modal = document.getElementById('new-exception-modal');
    const fields = [...modal.querySelectorAll('.field')];
    const field1 = fields[0];
    const field2 = fields[1];

    setClass(field1, 'error', false);
    setClass(field2, 'error', false);

    if (excType === 'g') {
        field1.querySelector('label').innerHTML = 'Term';
        field1.querySelector('input').placeholder = 'Term to authorize';
        setClass(field2, 'hidden', true);
    } else if (excType === 'p') {
        field1.querySelector('label').innerHTML = 'Entry #1';
        field1.querySelector('input').placeholder = 'Entry accession #1';
        field2.querySelector('label').innerHTML = 'Entry #2';
        field2.querySelector('input').placeholder = 'Entry accession #2';
        setClass(field2, 'hidden', false);
    } else if (excType === 's') {
        field1.querySelector('label').innerHTML = 'Entry';
        field1.querySelector('input').placeholder = 'Entry accession';
        setClass(field2, 'hidden', true);
    }

    const message = modal.querySelector('.message');
    message.innerHTML = null;
    for (const field of fields) {
        field.querySelector('input').value = null;
    }

    $(modal)
        .modal({
            onApprove: () => {
                const body = [
                    `type=${encodeURIComponent(ckType)}`,
                    `value1=${encodeURIComponent(field1.querySelector('input').value)}`,
                    `value2=${encodeURIComponent(field2.querySelector('input').value)}`,
                ]

                fetch('/api/checks/exception/', {
                    method: 'PUT',
                    headers: {
                        'Content-type': 'application/x-www-form-urlencoded;charset=UTF-8'
                    },
                    body: body.join('&')
                })
                    .then(response => response.json())
                    .then(result => {
                        if (result.status) {
                            $(modal).modal('hide');
                            getChecks();
                        } else {
                            message.innerHTML = `<div class="header">${result.error.title}</div><p>${result.error.message}</p>`;
                            setClass(field1, 'error', true);
                            setClass(field2, 'error', true);
                        }
                    });

                return false;
            }
        })
        .modal('show');
}

function getChecks() {
    fetch('/api/checks/')
        .then(response => response.json())
        .then(checks => {
            let menuHTML = '';
            let mainHTML = '';

            for (let i = 0; i < checks.length; i++) {
                const ck = checks[i];
                const ckID = ck.type.replace(/_/g, '-');
                menuHTML += `<a href="#${ckID}" class="item ${i === 0 ? 'active' : ''}">${ck.name}</a>`;

                mainHTML += `
                    <div id="${ckID}" class="ui vertical basic segment">
                    <h2 class="ui header">${ck.name}
                    <div class="sub header">${ck.description}</div>
                    </h2>                
                `;

                if (ck.add_terms) {
                    mainHTML += `<button data-type="${ck.type}" data-new-term class="ui basic compact secondary button"><i class="add icon"></i>Add term</button>`;

                    if (ck.terms.length > 0) {
                        mainHTML += '<div class="ui four cards">';
                        for (const term of ck.terms)
                            mainHTML += createCard(ck.type, term, ck.add_exceptions.length > 0);
                        mainHTML += '</div>';
                    }
                } else if (ck.add_exceptions.length > 0) {
                    mainHTML += `<button data-type="${ck.type}" data-new-exception="${ck.add_exceptions}" class="ui basic compact secondary button"><i class="add icon"></i>Add exception</button>`;

                    if (ck.exceptions.length > 0) {
                        mainHTML += '<div>';
                        for (const exc of ck.exceptions) {
                            if (ck.add_exceptions === 'g')
                                mainHTML += `<div class="ui basic small label" data-exception="${exc.id}"><code>${escape(exc.term)}</code><i class="delete icon"></i></div>`;
                            else if (ck.add_exceptions === 'p') {
                                mainHTML += `
                                    <div class="ui basic small label" data-exception="${exc.id}">
                                        <code>${escape(exc.entry)}</code>
                                        <div class="detail">${exc.term || exc.entry2}</div>
                                        <i class="delete icon"></i>
                                    </div>
                               `;
                            } else if (ck.add_exceptions === 's')
                                mainHTML += `<div class="ui basic small label" data-exception="${exc.id}"><code>${escape(exc.entry)}</code><i class="delete icon"></i></div>`;
                        }
                        mainHTML += '</div>';
                    }
                }

                mainHTML += '</div>';
            }

            document.querySelector('.sticky > .menu').innerHTML = menuHTML;

            const main = document.querySelector('.thirteen.column');
            main.innerHTML = mainHTML;

            // Copy terms to clipboard
            for (const elem of main.querySelectorAll('code')) {
                elem.addEventListener('click', e => copy2clipboard(e.currentTarget));
            }

            // Adding a term to check
            for (const elem of main.querySelectorAll('[data-new-term]')) {
                elem.addEventListener('click', e => {
                    const ckType = e.currentTarget.dataset.type;
                    addTerm(ckType);
                });
            }

            // Add an exception to a term
            for (const elem of main.querySelectorAll('.card > .bottom.button')) {
                elem.addEventListener('click', e => {
                    const card = e.currentTarget.closest('.card');
                    const ckType = card.dataset.type;
                    const code = card.querySelector('code');
                    const ckTerm = unescape(code.innerHTML);
                    addTermException(ckType, ckTerm);
                });
            }

            // Deleting a term
            for (const elem of main.querySelectorAll('.card > .content > .meta > .icon')) {
                elem.addEventListener('click', e => {
                    const card = e.currentTarget.closest('.card');
                    const ckType = card.dataset.type;
                    const code = card.querySelector('code');
                    const ckTerm = unescape(code.innerHTML);
                    deleteTerm(ckType, ckTerm);
                });
            }

            // Adding an exception (not to a term)
            for (const elem of main.querySelectorAll('[data-new-exception]')) {
                elem.addEventListener('click', e => {
                    const ckType = e.currentTarget.dataset.type;
                    const excType = e.currentTarget.dataset.newException;
                    addException(ckType, excType);
                });
            }

            // Deleting an exception
            for (const elem of main.querySelectorAll('[data-exception] .icon')) {
                elem.addEventListener('click', e => {
                    const excID = e.currentTarget.closest('[data-exception]').dataset.exception;
                    deleteException(excID);
                });
            }

            $('.ui.sticky').sticky({offset: 50});
            const segments = [...main.querySelectorAll('.ui.basic.vertical.segment')];
            $(segments)
                .visibility({
                    observeChanges: false,
                    once: false,
                    offset: 50,
                    onTopPassed: function () {
                        const segment = this;
                        const index = segments.findIndex((element,) => element === segment);
                        const item = document.querySelector('.ui.sticky .item:nth-child('+ (index+1) +')');
                        const activeItem = document.querySelector('.ui.sticky .item.active');
                        if (item !== activeItem) {
                            setClass(activeItem, 'active', false);
                            setClass(item, 'active', true);
                        }
                    },
                    onTopPassedReverse: function () {
                        const activeItem = document.querySelector('.ui.sticky .item.active');
                        const prevItem = activeItem.previousElementSibling;
                        if (prevItem) {
                            setClass(activeItem, 'active', false);
                            setClass(prevItem, 'active', true);
                        }
                    }
                });
        });
}

document.addEventListener('DOMContentLoaded', () => {
    updateHeader();
    getChecks();
});
