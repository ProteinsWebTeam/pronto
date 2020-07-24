import {updateHeader} from "./ui/header.js";
import {setClass, escape, unescape} from "./ui/utils.js";

function createCard(type, term, addExceptions) {
    let card = `
        <div class="card">
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
                    mainHTML += `<button data-add="${ck.type}" data-type="term" class="ui basic compact secondary button"><i class="add icon"></i>Add term</button><div class="ui four cards">`;

                    for (const term of ck.terms)
                        mainHTML += createCard(ck.type, term, ck.add_exceptions);

                    mainHTML += '</div>';
                } else if (ck.add_exceptions) {
                    mainHTML += `<button data-add="${ck.type}" data-type="exception" ${ck.use_global_exceptions ? 'data-global' : ''} class="ui basic compact secondary button"><i class="add icon"></i>Add exception</button>`;
                }

                mainHTML += '</div>';
            }

            document.querySelector('.sticky > .menu').innerHTML = menuHTML;

            const main = document.querySelector('.thirteen.column');
            main.innerHTML = mainHTML;

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
