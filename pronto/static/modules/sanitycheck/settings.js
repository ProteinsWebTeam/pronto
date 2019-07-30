import {finaliseHeader} from "../../header.js"
import * as ui from "../../ui.js";


function createCards(checkType, checks) {
    let html = '';
    for (let item of checks) {
        const string = item.string.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        html += '<div class="ui card" data-type="'+ checkType +'" data-string="'+ item.string +'">'
            + '<div class="content">'
            + '<a class="right floated meta"><i class="delete fitted icon"></i></a>'
            + '&ldquo;'+ string +'&rdquo;'
            + '<div class="meta">Created on '+ item.date +'</div>'
            + '<div class="description">';

        for (let exc of item.exceptions) {
            html += '<div class="ui basic small label" data-exc-id="'+ exc.id +'">'+ (exc.ann_id || exc.entry_acc) +'<i class="delete icon"></i></div>';
        }

        html += '</div>'    // close description
            + '</div>'      // close content
            + '<button class="ui bottom attached small button">'
            + '<i class="add icon"></i>Add exception'
            + '</button>'
            + '</div>';     // close card
    }
    return html;
}


function createLabels(checks) {
    let html = '';
    for (let item of checks) {
        for (let exc of item.exceptions) {
            let acc = null;
            let err;

            html += '<div class="ui basic label" data-exc-id="'+ exc.id +'">';
            if (exc.ann_id || exc.entry_acc) {
                acc = exc.ann_id || exc.entry_acc;
                html += '<a class="header" href="/search/?q='+ acc +'">'+ acc +'</a>';
            } else
                html += exc.string;

            if (exc.entry_acc2)
                html += '<a class="detail" href="/search/?q='+ exc.entry_acc2 +'">'+ exc.entry_acc2 +'</a>';
            else if (acc != null && exc.string !== null)
                html += '<div class="detail">'+ exc.string +'</div>';

            html += '<i class="delete icon"></i></div>';
        }
    }
    return html;
}

function loadSanityChecks() {
    fetch('/api/sanitychecks/checks/')
        .then(response => response.json())
        .then(checks => {
            const map = new Map();
            for (let [key, value] of Object.entries(checks)) {
                map.set(key, value);
            }

            ['invalid_abbr', 'invalid_citation', 'invalid_punct', 'misspelling', 'bad_subst', 'illegal_word'].forEach(key => {
                if (map.has(key)) {
                    document.getElementById(key).innerHTML = createCards(key, map.get(key));
                } else
                    document.getElementById(key).innerHTML = '<p>No terms to search</p>';
            });

            ['acc_in_name', 'non_ascii', 'similar_name', 'gene_symbol', 'lowercase_name', 'underscore_in_name'].forEach(key => {
                if (map.has(key)) {
                    document.getElementById(key).innerHTML = createLabels(map.get(key));
                } else
                    document.getElementById(key).innerHTML = '<p>No exceptions</p>';
            });

            document.querySelectorAll('.ui.label[data-exc-id] i.delete').forEach(elem => {
                elem.addEventListener('click', e => {
                    const exceptionId = e.currentTarget.parentNode.getAttribute('data-exc-id');
                    ui.openConfirmModal(
                        'Delete exception?',
                        'Are you sure to delete this sanity check exception? <strong>This action is irreversible.</strong>',
                        'Delete',
                        () => {
                            fetch('/api/sanitychecks/exception/'+ exceptionId +'/', {method: 'DELETE'})
                                .then(response => response.json())
                                .then(result => {
                                    if (result.status)
                                        loadSanityChecks();
                                    else
                                        ui.openErrorModal(result);
                                });
                        }
                    );
                });
            });

            document.querySelectorAll('.ui.card[data-type] .meta i.delete').forEach(elem => {
                elem.addEventListener('click', e => {
                    const card = e.currentTarget.closest('.ui.card');
                    const ckType = card.getAttribute('data-type');
                    const ckString = encodeURI(card.getAttribute('data-string'));

                    ui.openConfirmModal(
                        'Delete term?',
                        'Are you sure to delete this term? It will not be searched any more. <strong>This action is irreversible.</strong>',
                        'Delete',
                        () => {
                            fetch('/api/sanitychecks/term/'+ ckType +'/?str=' + ckString, {method: 'DELETE'})
                                .then(response => response.json())
                                .then(result => {
                                    if (result.status)
                                        loadSanityChecks();
                                    else
                                        ui.openErrorModal(result);
                                });
                        }
                    );
                });
            });


            document.querySelectorAll('.ui.card[data-type] button.bottom').forEach(elem => {
                elem.addEventListener('click', e => {
                    const card = e.currentTarget.closest('.ui.card');
                    const ckType = card.getAttribute('data-type');
                    const ckString = card.getAttribute('data-string');
                    addTermOrException(ckType, ckString);
                });
            });

            $('.ui.sticky').sticky({offset: 50});
            $('section')
                .visibility({
                    observeChanges: false,
                    once: false,
                    offset: 50,
                    onTopPassed: function () {
                        const section = this;
                        const sections = Array.from(document.querySelectorAll('section'));
                        const index = sections.findIndex((element,) => element === section);
                        const item = document.querySelector('.ui.sticky .item:nth-child('+ (index+1) +')');
                        const activeItem = document.querySelector('.ui.sticky .item.active');
                        if (item !== activeItem) {
                            ui.setClass(activeItem, 'active', false);
                            ui.setClass(item, 'active', true);
                        }
                    },
                    onTopPassedReverse: function () {
                        const activeItem = document.querySelector('.ui.sticky .item.active');
                        const prevItem = activeItem.previousElementSibling;
                        if (prevItem) {
                            ui.setClass(activeItem, 'active', false);
                            ui.setClass(prevItem, 'active', true);
                        }
                    }
                });
        });
}

function addTermOrException(ckType, ckString) {
    const modal = document.getElementById('new-term-modal');
    const message = modal.querySelector('.message');
    const label1 = modal.querySelector('#label-1');
    const label2 = modal.querySelector('#label-2');

    ui.setClass(message, 'hidden', true);

    const isTerm = ['invalid_abbr', 'invalid_citation', 'invalid_punct', 'misspelling', 'bad_subst', 'illegal_word'].includes(ckType);
    if (isTerm && ckString === null) {
        // New term
        modal.querySelector('.header').innerHTML = 'Add term';
        label1.querySelector('label').innerHTML = 'New term to check';
        label1.querySelector('input').placeholder = 'Term to check';
        ui.setClass(label2, 'hidden', true);
    }
    else if (isTerm) {
        // New exception for existing term
        modal.querySelector('.header').innerHTML = 'Add exception for &ldquo;' + ckString + '&rdquo;';
        label1.querySelector('label').innerHTML = 'Entry or abstract';
        label1.querySelector('input').placeholder = 'Entry accession or abstract ID';
        ui.setClass(label2, 'hidden', true);
    }
    else {
        // New exception for a type of check that does not require terms
        modal.querySelector('.header').innerHTML = 'Add exception';
        if (ckType === 'acc_in_name' || ckType === 'similar_name') {
            label1.querySelector('label').innerHTML = 'Entry #1';
            label1.querySelector('input').placeholder = 'Entry accession #1';
            label2.querySelector('label').innerHTML = 'Entry #2';
            label2.querySelector('input').placeholder = 'Entry accession #2';
            ui.setClass(label2, 'hidden', false);
        } else if (ckType === 'non_ascii') {
            label1.querySelector('label').innerHTML = 'Abstract';
            label1.querySelector('input').placeholder = 'Abstract ID';
            label2.querySelector('label').innerHTML = 'Non-ASCII character';
            label2.querySelector('input').placeholder = 'Non-ASCII character';
            ui.setClass(label2, 'hidden', false);
        } else if (ckType === 'underscore_in_name') {
            label1.querySelector('label').innerHTML = 'Entry';
            label1.querySelector('input').placeholder = 'Entry accession';
            ui.setClass(label2, 'hidden', true);
        } else {
            label1.querySelector('label').innerHTML = 'Term';
            label1.querySelector('input').placeholder = 'Term to authorize';
            ui.setClass(label2, 'hidden', true);
        }
    }

    $(modal)
        .modal({
            onShow: function() {
                label1.querySelector('input').value = null;
                label2.querySelector('input').value = null;
            },
            onApprove: function () {
                const options = {method: 'PUT'};

                if (isTerm && ckString === null) {
                    // New term
                    const term = encodeURI(label1.querySelector('input').value);
                    fetch('/api/sanitychecks/term/' + ckType + '/?term=' + term, options)
                        .then(response => response.json())
                        .then(result => {
                            if (result.status) {
                                $(modal).modal('hide');
                                loadSanityChecks();
                            } else {
                                message.innerHTML = '<div class="header">' + result.error.title + '</div><p>'+ result.error.message +'</p>';
                                ui.setClass(message, 'hidden', false);
                            }
                        });
                } else {
                    options.headers = {'Content-Type': 'application/json; charset=utf-8'};
                    options.body = JSON.stringify({
                        value1: label1.querySelector('input').value,
                        value2: label2.querySelector('input').value,
                        term: ckString
                    });
                    fetch('/api/sanitychecks/exception/' + ckType + '/', options)
                        .then(response => response.json())
                        .then(result => {
                            if (result.status) {
                                $(modal).modal('hide');
                                loadSanityChecks();
                            } else {
                                message.innerHTML = '<div class="header">' + result.error.title + '</div><p>'+ result.error.message +'</p>';
                                ui.setClass(message, 'hidden', false);
                            }
                        });
                }

                return false;
            }
        })
        .modal('show');
}


$(function () {
    finaliseHeader();
    loadSanityChecks();

    document.querySelectorAll('button[data-type]').forEach(elem => {
        elem.addEventListener('click', e => {
            const ckType = e.currentTarget.getAttribute('data-type');
            addTermOrException(ckType, null);
        });
    });
});