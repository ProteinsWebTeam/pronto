import {finaliseHeader} from "../../header.js"
import * as ui from "../../ui.js";


function getErrors(runId) {
    fetch(URL_PREFIX+'/api/sanitychecks/runs/' + runId + '/')
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

                    let html = '';
                    for (let err of run.errors) {
                        if (err.resolved_by)
                            html += '<div class="green card"><div class="content">';
                        else
                            html += '<div class="red card"><div class="content">';

                        if (err.ann_id) {
                            html += '<a class="header" target="_blank" href="'+URL_PREFIX+'/entry/' + err.entry_ac + '/">'
                                + err.ann_id
                                + '&nbsp;<i class="external icon"></i>'
                                +'</a>';
                        } else {
                            html += '<a class="header" target="_blank" href="'+URL_PREFIX+'/entry/' + err.entry_ac + '/">'
                                + err.entry_ac
                                + '&nbsp;<i class="external icon"></i>'
                                +'</a>';
                        }

                        html += '<div class="description">';
                        let numErrors = 0;
                        let acceptExceptions = true;
                        for (let [label, object] of Object.entries(err.errors)) {
                            if (!object.accept_exceptions)
                                acceptExceptions = false;

                            if (typeof object.errors === "boolean") {
                                numErrors++;
                                html += '<div class="ui basic label">'+ label +'</div>';
                            }
                            else
                                for (let error of object.errors) {
                                    numErrors++;
                                    if (error.count > 1) {
                                        html += '<div class="ui basic label">'
                                            + label
                                            + '<div class="detail">' + error.count + '&times;&ldquo;' + error.error + '&rdquo;</div>'
                                            + '</div>';
                                    } else {
                                        html += '<div class="ui basic label">'
                                            + label
                                            + '<div class="detail">&ldquo;' + error.error + '&rdquo;</div>'
                                            + '</div>';
                                    }
                                }

                        }

                        html += '</div>'   // close description
                            + '</div>'      // close content
                            + '<div class="extra content">';

                        if (err.resolved_by)
                            html += '<div class="right floated">'
                                + '<i class="check icon"></i>'
                                + 'Resolved by ' + err.resolved_by.split(/\s/)[0]
                                + '</div>';
                        else {
                            if (numErrors === 1 && acceptExceptions)
                                html += '<span data-id="'+ err.id +'" data-add-exception>Add exception ' + '&amp; resolve</span>';
                            html += '<div class="right floated" data-id="'+ err.id +'">Resolve</div>';
                        }

                        // close extra content, then card
                        html += '</div></div>';
                    }

                    document.querySelector('.ui.cards').innerHTML = html;

                    let raisedCard = null;
                    const cards = Array.from(document.querySelectorAll('.card'));
                    cards.forEach(elem => {
                        elem.addEventListener('click', e => {
                            const thisCard = e.currentTarget;

                            if (raisedCard === thisCard) {
                                cards.forEach(card => {
                                    ui.setClass(card, 'unselected', false);
                                });
                                raisedCard = null;
                            } else {
                                cards.forEach(card => {
                                    ui.setClass(card, 'unselected', card !== thisCard);
                                });
                                raisedCard = thisCard;
                            }
                        });
                    });

                    Array.from(document.querySelectorAll('[data-id]')).forEach(elem => {
                        elem.addEventListener('click', e => {
                            const errId = e.currentTarget.getAttribute('data-id');
                            let url = URL_PREFIX + '/api/sanitychecks/runs/' + runId + '/' + errId + '/';

                            if (e.currentTarget.hasAttribute('data-add-exception'))
                                url += '?exception';

                            return fetch(url, {method: "POST"})
                                .then(response => {
                                    if (response.ok) {
                                        getErrors(runId);
                                        return null;
                                    }

                                    return response.json();
                                })
                                .then(response => {
                                    if (response !== null)
                                        console.log(response);
                                        ui.openErrorModal({title: response.error.title, message: response.error.message});
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
});