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
        }, 3000);
    };

    join();
}


function renderLiterature(methods, results) {
    const url = utils.parseLocation();
    const filteredEntities = url["filter-entities"] ? url["filter-entities"].split(',') : [];
    const filteredMethods = url["filter-methods"] ? url["filter-methods"].split(',') : [];

    (function () {
        let html = "";
        filteredEntities.forEach(term => {
            html += '<a class="ui basic small red label">'+ term +'<i data-term="'+ term +'" class="delete icon"></i></a>';
        });
        document.getElementById("entity-filters").innerHTML = html;
    })();

    // Deep copy
    const filteredResults = JSON.parse(JSON.stringify(results)).filter(pub => {
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

    let html = '<thead><tr><th>'+ filteredResults.length +' literature matches</th><th>Proteins</th>';
    methods.forEach(methodAc => {
        html += '<th>';
        if (methods.length > 1) {
            if (filteredMethods.includes(methodAc)) {
                html += '<div class="ui checked checkbox">'
                + '<input type="checkbox" tabindex="0" class="hidden" data-method="'+ methodAc +'" checked>';
            } else {
                html += '<div class="ui checkbox">'
                + '<input type="checkbox" tabindex="0" class="hidden" data-method="'+ methodAc +'">';
            }
            html += '<label>'+ methodAc +'</label>'
                + '</div>';
        } else
            html += methodAc;
        html += '</th>';
    });
    html += '</thead><tbody>';

    filteredResults.forEach(pub => {
        html += '<tr>'
            + '<td><a href="' + pub.url +'" target="_blank">' + pub.title + '</a></td>'
            + '<td>'
            + '<div class="ui divided items">';

        Object.keys(pub.upids_by_entity).forEach(entity => {
            let proteinNames = pub.upids_by_entity[entity];
            let match = pub.matches[entity];
            if (match) {
                const literatureContext = 2;
                const delta = literatureContext - Math.min(literatureContext, match.sindex);
                const paragraph = match.paragraph.slice(
                    Math.max(0, match.sindex - literatureContext),
                    match.sindex + literatureContext
                );

                html += '<div class="item">'
                    + '<div class="content">'
                    + '<div class="meta">' +
                    '<a class="ui basic label literature-match">'+ match.term +'<i data-term="'+ match.term +'" class="delete icon"></i></a>'
                    + '<div class="ui popup"><p>';

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
                    html += '</span> ';
                });

                html += '</p></div></div>';  // close popup, then meta

                const proteins = new Map();
                proteinNames.forEach(name => {
                    const prefix = name.split('_')[0];
                    if (proteins.has(prefix)) {
                        proteins.get(prefix).push(name);
                    } else {
                        proteins.set(prefix, [name]);
                    }
                });

                html += '<div class="ui horizontal bulleted link list">';
                Array.from(proteins).slice(0, 5).forEach(protein => {
                    const [prefix, names] = protein;
                    if (names.length > 1)
                        html += '<a class="item" href="//www.uniprot.org/uniprot/' + names[0] + '" target="_blank">' + prefix;
                    else
                        html += '<a class="item" href="//www.uniprot.org/uniprot/' + names[0] + '" target="_blank">' + names[0];

                    html += '&nbsp;<i class="external icon"></i></a>';
                });

                html += '</div>';
                if (proteins.size > 10)
                    html += '<div class="extra">and '+ (proteins.size - 10) +' more.</div>';
                html += '</div></div>';  // close content, then item
            }
        });
        html += '</div></td>';
        methods.forEach(methodAc => {
            if (pub.families.hasOwnProperty(methodAc))
                html += '<td class="center aligned" style="background-color: rgba(129,199,132,' + (pub.score + 0.1) + ')"><i class="large checkmark icon"></i></td>';
            else
                html += '<td></td>';
        });
        html += '</tr>';

    });

    html += '</tbody>';
    const table = document.querySelector('table');
    table.innerHTML = html;
    $('.literature-match').popup({
        hoverable: true,
        position: "top center"
    });

    $(".ui.checkbox").checkbox({
        onChange: function() {
            const methodAc = this.dataset.method;
            const i = filteredMethods.indexOf(methodAc);

            if (this.checked && i === -1)
                filteredMethods.push(methodAc);
            else if (!this.checked && i !== -1)
                filteredMethods.splice(i, 1);
            else
                return;

            const url = location.pathname + utils.encodeParams(
                utils.extendObj(
                    utils.parseLocation(location.search),
                    {"filter-methods": filteredMethods.length ? filteredMethods.join(',') : false}
                )
            );

            history.replaceState(null, null, url);
            renderLiterature(methods, results);
        }
    });

    Array.from(document.querySelectorAll(".literature-match i")).forEach(icon => {
        icon.addEventListener("click", e => {
            const term = e.target.dataset.term;
            if (!filteredEntities.includes(term))
                filteredEntities.push(term);

            const url = location.pathname + utils.encodeParams(
                utils.extendObj(
                    utils.parseLocation(location.search),
                    {"filter-entities": filteredEntities.length ? filteredEntities.join(',') : false}
                )
            );

            history.replaceState(null, null, url);
            renderLiterature(methods, results);
        });
    });

    Array.from(document.querySelectorAll("#entity-filters i")).forEach(icon => {
        icon.addEventListener("click", e => {
            const term = e.target.dataset.term;
            const i = filteredEntities.indexOf(term);
            filteredEntities.splice(i, 1);

            const url = location.pathname + utils.encodeParams(
                utils.extendObj(
                    utils.parseLocation(location.search),
                    {"filter-entities": filteredEntities.length ? filteredEntities.join(',') : false}
                )
            );

            history.replaceState(null, null, url);
            renderLiterature(methods, results);
        });
    });

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
            history.replaceState(null, null, location.pathname + utils.encodeParams(
                utils.extendObj(
                    utils.parseLocation(location.search),
                    {task: obj.id}
                )
            ));
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