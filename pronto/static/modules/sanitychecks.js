import {finaliseHeader} from "../header.js"
import * as ui from "../ui.js";


function getErrors(runId) {
    fetch('/api/interpro/sanitychecks/' + runId + '/')
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
                        if (err.resolved)
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
                                cards += '<div class="ui basic small label">'+ label +'</div></div>';
                            else
                                for (let err of errors) {
                                    if (err.count > 1) {
                                        cards += '<div class="ui basic small label">'
                                            + label
                                            + '<div class="detail">' + err.count + '&times;' + err.error + '</div>'
                                            + '</div>';
                                    } else {
                                        cards += '<div class="ui basic small label">'
                                            + label
                                            + '<div class="detail">' + err.error + '</div>'
                                            + '</div>';
                                    }
                                }

                        }

                        // Close description and content
                        cards += '</div></div>';

                        if (!err.resolved) {
                            // Add button to resolve error
                            cards += '<div class="extra content"><div class="right floated" data-id="'+ err.id +'"><i class="check icon"></i>Resolve</div></div>';
                        }

                        // Close card
                        cards += '</div>';
                    }


                    document.querySelector('.ui.cards').innerHTML = cards;

                    Array.from(document.querySelectorAll('[data-id]')).forEach(elem => {
                        elem.addEventListener('click', e => {
                            const errId = e.currentTarget.getAttribute('data-id');
                            return fetch('/api/interpro/sanitychecks/' + runId + '/' + errId + '/', {method: "POST"})
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
    const runId = location.pathname.match(/\/interpro\/sanitychecks\/(.+)\/$/)[1];
    getErrors(runId);
});