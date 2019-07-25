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
            + '<div class="ui bottom attached small button">'
            + '<i class="add icon"></i>Add exception'
            + '</div>'
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

            ['abbreviation', 'citation', 'punctuation', 'spelling', 'substitution', 'word'].forEach(key => {
                if (map.has(key)) {
                    document.getElementById(key).innerHTML = createCards(key, map.get(key));
                } else
                    document.getElementById(key).innerHTML = '<p>No terms to search</p>';
            });

            ['accession', 'ascii', 'clash', 'gene', 'lowercase', 'underscore'].forEach(key => {
                if (map.has(key)) {
                    document.getElementById(key).innerHTML = createLabels(map.get(key));
                } else
                    document.getElementById(key).innerHTML = '<p>No exceptions</p>';
            });

            document.querySelectorAll('[data-exc-id] i.delete').forEach(elem => {
                elem.addEventListener('click', e => {
                    const exceptionId = e.currentTarget.parentNode.getAttribute('data-exc-id');
                    ui.openConfirmModal(
                        'Delete exception?',
                        'Are you sure to delete a sanity check exception? <strong>This action is irreversible.</strong>',
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
        });
}


$(function () {
    finaliseHeader();
    loadSanityChecks();

    document.querySelectorAll('button[data-type]').forEach(elem => {
        elem.addEventListener('click', e => {
            console.log(e.currentTarget);
        });
    });
});