import {finaliseHeader} from "../header.js"
import * as ui from "../ui.js";


$(function () {
    finaliseHeader();
    const id = location.pathname.match(/\/interpro\/sanitychecks\/(.+)\/$/)[1];
    fetch('/api/interpro/sanitychecks/' + id + '/')
        .then(response => {
            if (response.ok) {
                response.json().then(obj => {
                    (function () {
                        const elem = document.querySelector('.ui.statistics');
                        elem.querySelectorAll('[data-statistic]').forEach(node => {
                            const key = node.getAttribute('data-statistic');
                            const val = obj[key];
                            if (Number.isInteger(val))
                                node.innerHTML = val.toLocaleString();
                            else
                                node.innerHTML = val.replace(/\s([^\s]+)$/, '<br>$1');
                        });
                        ui.setClass(elem, 'hidden', false);
                    })();

                    let cards = '';
                    for (let [key, value] of Object.entries(obj.errors.abstracts)) {
                        cards += '<div class="card">'
                            + '<div class="content">'
                            + '<div class="header">'+ key +'</div>'
                            + '<a class="meta" href="/entry/'+ value.entry +'/">'+ value.entry +'</a>'
                            + '<div class="description">';

                        for (let [k, v] of Object.entries(value.errors)) {
                            if (typeof v === "boolean")
                                cards += '<div class="ui red label">'+ k +'</div></div>';
                            else
                                for (let err of v) {
                                    cards += '<div class="ui label">'+ k +'<div class="detail">'+ err.count + '&times;'+err.error +'</div></div>';
                                }

                        }

                        cards += '</div></div></div>';  // closing description, content, then card
                    }

                    document.getElementById('abstracts').innerHTML = cards;
                });
            } else {
                ui.setClass(document.querySelector('.error.message'), 'hidden', false);
            }
        });
});