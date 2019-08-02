import {finaliseHeader} from "../../header.js"
import * as ui from "../../ui.js";


function getErrors(runId) {
    fetch('/api/sanitychecks/runs/' + runId + '/')
        .then(response => {
            if (response.ok) {
                response.json().then(run => {
                    (function () {
                        const elem = document.querySelector('.ui.statistics');
                        elem.querySelectorAll('[data-statistic]').forEach(node => {
                            const key = node.getAttribute('data-statistic');
                            const val = run[key];
                            if (Number.isInteger(val))
                                node.innerHTML = val.toLocaleString();
                            else
                                node.innerHTML = val.replace(/\s([^\s]+)$/, '<br>$1');
                        });
                        ui.setClass(elem, 'hidden', false);
                    })();

                    let cards = '';
                    for (let err of run.errors) {
                        if (err.resolved_by)
                            cards += '<div class="green card"><div class="content">';
                        else
                            cards += '<div class="red card"><div class="content">';

                        if (err.ann_id) {
                            cards += '<div class="header">' + err.ann_id + '</div>'
                                + '<a class="meta" href="/entry/' + err.entry_ac + '/">'+ err.entry_ac +'</a>';
                        } else
                            cards += '<a class="header" href="/entry/' + err.entry_ac + '/">' + err.entry_ac + '</a>';

                        cards += '<div class="description">';
                        for (let [label, errors] of Object.entries(err.errors)) {
                            if (typeof errors === "boolean")
                                cards += '<div class="ui basic small label">'+ label +'</div>';
                            else
                                for (let err of errors) {
                                    if (err.count > 1) {
                                        cards += '<div class="ui basic small label">'
                                            + label
                                            + '<div class="detail">' + err.count + '&times;&ldquo;' + err.error + '&rdquo;</div>'
                                            + '</div>';
                                    } else {
                                        cards += '<div class="ui basic small label">'
                                            + label
                                            + '<div class="detail">&ldquo;' + err.error + '&rdquo;</div>'
                                            + '</div>';
                                    }
                                }

                        }

                        cards += '</div>'   // close description
                            + '</div>'      // close content
                            + '<div class="extra content">';

                        if (err.resolved_by)
                            cards += '<div class="right floated">Resolved by ' + err.resolved_by.split(/\s/)[0] + '</div>';
                        else
                            cards += '<div class="right floated" data-id="'+ err.id +'"><i class="check icon"></i>Resolve</div>';

                        // close extra content, then card
                        cards += '</div></div>';
                    }

                    document.querySelector('.ui.cards').innerHTML = cards;

                    Array.from(document.querySelectorAll('[data-id]')).forEach(elem => {
                        elem.addEventListener('click', e => {
                            const errId = e.currentTarget.getAttribute('data-id');
                            return fetch('/api/sanitychecks/runs/' + runId + '/' + errId + '/', {method: "POST"})
                                .then(response => {
                                    if (response.ok)
                                        getErrors(runId);
                                    else if (response.status === 401)
                                        ui.openErrorModal({title: 'Access denied', message: 'Please <a href="/login/">log in</a> to perform this operation.'});
                                    else if (response.status === 404)
                                        ui.openErrorModal({title: 'Not found', message: 'This error does not exist.'});
                                    else
                                        ui.openErrorModal({title: 'Something went wrong', message: 'An unexpected error occurred. No details available.'});
                                });
                        });
                    });
                });
            } else {
                ui.setClass(document.querySelector('.error.message'), 'hidden', false);
                ui.setClass(document.querySelector('.ui.statistics'), 'hidden', true);
                ui.setClass(document.querySelector('.ui.cards'), 'hidden', true);
            }
        });
}


$(function () {
    finaliseHeader();
    const runId = location.pathname.match(/\/sanitychecks\/runs\/(.+)\/$/)[1];
    getErrors(runId);
    $('#help-modal').modal('attach events', '#show-help', 'show');
    console.log(1);
});