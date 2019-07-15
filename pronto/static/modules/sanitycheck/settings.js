import {finaliseHeader} from "../../header.js"
import * as ui from "../../ui.js";


function createCards(checks) {
    let html = '';
    for (let item of checks) {
        const string = item.string.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        html += '<div class="ui card">'
            + '<div class="content">'
            + '<a class="right floated meta"><i class="remove fitted icon"></i></a>'
            + '&ldquo;'+ string +'&rdquo;'
            + '<div class="meta">Created on '+ item.date +'</div>'
            + '<div class="description">';

        for (let exc of item.exceptions) {

            html += '<div class="ui basic small label">'+ (exc.ann_id || exc.entry_acc) +'<i class="delete icon"></i></div>';
        }

        html += '</div></div></div>';
    }
    return html;
}


$(function () {
    finaliseHeader();

    fetch('/api/sanitychecks/checks/')
        .then(response => response.json())
        .then(checks => {
            const map = new Map();
            for (let [key, value] of Object.entries(checks)) {
                map.set(key, value);
            }

            ['abbreviation', 'citation', 'punctuation', 'spelling', 'substitution', 'word'].forEach(key => {
                if (map.has(key)) {
                document.getElementById(key).innerHTML = createCards(map.get(key));
            } else
                document.getElementById(key).innerHTML = '<p>No terms to search</p>';
            });

            // todo: accession, ascii, clash, gene, lowercase, underscore,
        });
});