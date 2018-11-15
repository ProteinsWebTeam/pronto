import * as utils from '../utils.js';

const baseURL = "http://ves-hx2-a0.ebi.ac.uk/bateman/searchsifter/grubbler";

function joinTask(methods, taskID) {
    let url = baseURL + "/grub/task/" + taskID;

    const join = function () {
        setTimeout(function () {
            utils.getJSON(url, (obj, status) => {
                if (status === 202)
                    join();
                else
                    renderLiterature(methods, obj);
            });
        }, 1000);
    }();
}


function renderLiterature(methods, results) {
    const url = utils.parseLocation();
    const filteredEntities = url["filter-entities"] ? url["filter-entities"].split(',') : [];
    const filteredMethods = url["filter-methods"] ? url["filter-methods"].split(',') : [];

    results = results.filter(pub => {
        const matches = {};
        let n = 0;
        Object.keys(pub.matches)
            .filter(key => !filteredEntities.includes(pub.matches[key].term))
            .forEach(key => {
                matches[key] = pub.matches[key];
                n += 1;
            });

        pub.matches = matches;
        return n;
    }).filter(pub => filteredMethods.every(accession => pub.families.hasOwnProperty(accession)));

    let html = '<thead><tr><th>'+ results.length +' possible literature matches</th><th>Proteins</th>';
    methods.forEach(methodAc => {
        html += '<th>';
        if (methods.length > 1) {
            html += '<div class="ui checkbox">'
                + '<input type="checkbox" class="hidden" data-id="'+ methodAc +'">'
                + '<label>'+ methodAc +'</label>'
                + '</div>';
        } else
            html += methodAc;
        html += '</th>';
    });
    html += '</thead><tbody>';

    results.forEach(pub => {
        html += '<tr>'
            + '<td><a href="' + pub.url +'" target="_blank">' + pub.title + '</a></td>'
            + '<td>';

        let divider = '';
        Object.keys(pub.upids_by_entity).forEach(entity => {
            html += divider;

            let proteinNames = pub.upids_by_entity[entity];
            let match = pub.matches[entity];
            if (match) {
                const proteins = new Map();
                html += '<a class="ui label literature-match" data-match="' + match.term + '">' + match.term + '<i class="delete icon"></i></a> ';
                html += '<div class="ui flowing popup top center transition hidden">';
                html += '<div class="ui left aligned one wide">';
                html += '<p>';

                const literatureContext = 2;
                const delta = literatureContext - Math.min(literatureContext, match.sindex);
                const paragraph = match.paragraph.slice(
                    Math.max(0, match.sindex - literatureContext),
                    match.sindex + literatureContext
                );

                paragraph.forEach((sentence, i) => {
                    if (i !== (literatureContext - delta))
                        html += '<span class="literature-context-sentence">';
                    else {
                        html += '<span class="literature-match-sentence">';
                        const [start, end] = match.coordinates;
                        const before = sentence.slice(0, start);
                        const match_text = sentence.slice(start, end + 1);
                        const after = sentence.slice(end + 1, sentence.length);
                        sentence = before + '<span class="literature-match-phrase">' + match_text + '</span>' + after;
                    }
                    html += sentence;
                    html += '</span>';
                });

                html += '</p></div>'
                    + '</div>';

                proteinNames.forEach(name => {
                    const prefix = name.split('_')[0];
                    if (proteins.has(prefix)) {
                        proteins.get(prefix).push(name);
                    } else {
                        proteins.set(prefix, [name]);
                    }
                });
                Array.from(proteins).slice(0, 5).forEach(protein => {
                    const [prefix, names] = protein;
                    if (names.length > 1)
                        html += '<p><a href="//www.uniprot.org/uniprot/' + names[0] + '" target="_blank">' + prefix + '</a></p>';
                    else
                        html += '<p><a href="//www.uniprot.org/uniprot/' + names[0] + '" target="_blank">' + names[0] + '</a></p>';
                });
                if (proteins.size > 10) {
                    html += '<p>and ' + (proteins.size - 10) + ' more.</p>';
                }
                divider = '<div class="ui divider"></div>'
            }
        });
        html += '</td>';
        methods.forEach(methodAc => {

            console.log(methodAc in pub.families);
            if (pub.families.hasOwnProperty(methodAc))
                html += '<td style="background-color: rgba(255,150,150,' + (pub.score + 0.1) + ')">&checkmark;</td>';
            else
                html += '<td></td>';
        });
        html += '</tr>';

    });

    html += '</tbody>';
    const table = document.querySelector('table');
    table.innerHTML = html;
    utils.dimmer(false);
}


function getLiterature(methods) {
    const url = utils.parseLocation();

    utils.dimmer(true);
    if (url.task)
        joinTask(methods, url.task);
    else {
        const entityCount = url["entity-count"] ? url["entity-count"] : 80;
        let grubblerURL = baseURL;

        if (url.classifier)
            grubblerURL += "/grub/family/"
                + url.classifier + '/'
                + methods.join(',')
                + '?max_entity_count='
                + entityCount;
        else
            grubblerURL += "/grub/family/function/"
                + methods.join(',')
                + '?max_entity_count='
                + entityCount;

        utils.getJSON(grubblerURL, (obj, status) => {
            joinTask(methods, obj.id);
        });
    }
}

$(function () {
    const match = location.pathname.match(/^\/methods\/(.+)\/([a-z]+)\/$/);
    if (!match) {
        return;
    }

    const methods = match[1].trim().split('/');
    const methodSelectionView = new utils.MethodsSelectionView(document.getElementById('methods'));

    // Add current signature
    methods.forEach(method => { methodSelectionView.add(method); });
    methodSelectionView.render();

    utils.setClass(document.querySelector('a[data-page="'+ match[2] +'"]'), 'active', true);
    document.title = 'Literature ('+ methods.join(', ') +') | Pronto';

    getLiterature(methods);
});