import {dimmer} from '../../ui.js';
import {finaliseHeader} from "../../header.js";
import {selector} from "../../signatures.js";

const baseURL = "http://ves-hx2-a0.ebi.ac.uk/bateman/searchsifter/grubbler";
const defaultClassifier = "function";
const defaultEntityCount = 80;

function submitTask(accessions, classifier, entityCount) {
    const extURL = baseURL
        + '/grub/family/' + classifier + '/' + accessions.join(',')
        + '?max_entity_count=' + entityCount;
    return fetch(extURL).then(response => response.json());
}

function getTask(taskID) {
    const extURL = baseURL + '/grub/task/' + taskID;

    return new Promise(((resolve, reject) => {
        const joinTask = () => {
            setTimeout(() => {
                fetch(extURL)
                    .then(response => {
                        if (response.status === 202)
                            joinTask();
                        else
                            resolve(response.json());
                    });
            }, 3000);
        };

        joinTask();
    }));
}

function getLiterature(accessions, classifier, entityCount) {
    dimmer(true);

    const url = new URL(location.href);
    let taskID = url.searchParams.get("task");

    if (taskID === null) {
        submitTask(accessions, classifier, entityCount)
            .then(task => {
                    taskID = task.id;
                    url.searchParams.set("task", taskID);
                    history.replaceState(null, null, url.toString());
                    getTask(taskID)
                        .then(results => {
                            renderLiterature(accessions, results);
                            dimmer(false);
                        });
                }
            )
            .catch(() => {
                const error = document.createElement('div');
                error.className = 'ui error message';
                error.innerHTML = '<div class="header">Service unavailable</div>'
                    + '<p>The literature server is unable to service the request.</p>';

                const segment = document.querySelector('.ui.container.segment');
                segment.removeChild(segment.querySelector('.ui.form'));
                segment.removeChild(segment.querySelector('.ui.table'));
                segment.appendChild(error);
                dimmer(false);
            });
    } else {
        getTask(taskID)
            .then(results => {
                renderLiterature(accessions, results);
                dimmer(false);
            });
    }
}

function splitIfNotNull(val) {
    return val !== null ? val.split(',') : [];
}

function renderLiterature(accessions, results) {
    const url = new URL(location.href);
    const filteredEntities = splitIfNotNull(url.searchParams.get('filter-entities'));
    const filteredSignatures = splitIfNotNull(url.searchParams.get('filter-signatures'));

    // Add buttons for filters
    (function () {
        let html = '';
        if (filteredEntities.length) {
            filteredEntities.forEach(term => {
                html += '<a class="ui basic small red label">'+ term +'<i data-term="'+ term +'" class="delete icon"></i></a>';
            });
        } else
            html = 'None';

        document.getElementById("entity-filters").innerHTML = html;
    })();

    // Use a deep copy to be able to reuse the results (as we may overwrite some objects)
    const filteredResults = JSON.parse(JSON.stringify(results))
        .filter(pub => {
            // Keep only publications with at least one non-filtered terms
            const matches = {};
            let n = 0;
            Object.entries(pub.matches)
                .forEach(pair => {
                    // pair: array [key, value]
                    const key = pair[0];
                    const val = pair[1];

                    if (!filteredEntities.includes(val.term)) {
                        // term is not excluded
                        matches[key] = val;
                        n += 1;
                    }
                });

            pub.matches = matches;  // keep only non-filtered terms
            return n > 0;
        })
        // Keep only publications associated to every checked signatures
        .filter(pub => filteredSignatures.every(accession => pub.families.hasOwnProperty(accession)));

    //console.log(filteredResults);

    // Table header
    let html = '<thead>'
        + '<tr>'
        + '<th>'+ filteredResults.length +' literature matches</th>'
        + '<th>Proteins</th>';

    accessions.forEach(acc => {
        html += '<th>';
        if (accessions.length > 1) {
            if (filteredSignatures.includes(acc)) {
                html += '<div class="ui checked checkbox">'
                    + '<input type="checkbox" tabindex="0" class="hidden" data-method="'+ acc +'" checked>';
            } else {
                html += '<div class="ui checkbox">'
                    + '<input type="checkbox" tabindex="0" class="hidden" data-method="'+ acc +'">';
            }
            html += '<label>'+ acc +'</label>'
                + '</div>';
        } else
            html += acc;
        html += '</th>';
    });
    html += '</thead><tbody>';

    // Table body
    filteredResults.forEach(pub => {
        html += '<tr>'
            + '<td>'
            + '<a href="' + pub.url +'" target="_blank">' + pub.title + '&nbsp;<i class="external icon"></i></a>'
            + '</td>'
            + '<td>'
            + '<div class="ui divided items">';

        Object.entries(pub.upids_by_entity).forEach(pair => {
            const entity = pair[0];
            const proteinNames = pair[1];
            const match = pub.matches[entity];

            if (match) {
                const literatureContext = 2;
                const delta = literatureContext - Math.min(literatureContext, match.sindex);
                const paragraph = match.paragraph.slice(
                    Math.max(0, match.sindex - literatureContext),
                    match.sindex + literatureContext
                );

                html += '<div class="item">'
                    + '<div class="content">'
                    + '<div class="meta">'
                    + '<a class="ui basic label literature-match">'
                    + match.term + '<i data-term="'+ match.term +'" class="filter icon"></i>'
                    + '</a>'
                    + '<div class="ui popup">'
                    + '<p>';

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

                html += '</p></div></div>';  // close paragraph, popup, and meta

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
        html += '</div></td>';  // close items, then cell

        accessions.forEach(acc => {
            if (pub.families.hasOwnProperty(acc))
                html += '<td class="center aligned" style="background-color: rgba(129,199,132,' + (pub.score + 0.1) + ')"><i class="large checkmark icon"></i></td>';
            else
                html += '<td></td>';
        });
        html += '</tr>';
    });

    document.querySelector('table').innerHTML = html + '</tbody>';

    $('.literature-match').popup({
        hoverable: true,
        position: "top center"
    });

    $("table .ui.checkbox").checkbox({
        onChange: function() {
            const methodAc = this.dataset.method;
            const i = filteredSignatures.indexOf(methodAc);

            if (this.checked && i === -1)
                filteredSignatures.push(methodAc);
            else if (!this.checked && i !== -1)
                filteredSignatures.splice(i, 1);
            else
                return;

            if (filteredSignatures.length)
                url.searchParams.set('filter-signatures', filteredSignatures.join(','));
            else
                url.searchParams.delete('filter-signatures');

            history.replaceState(null, null, url.toString());
            renderLiterature(accessions, results);
        }
    });

    Array.from(document.querySelectorAll(".literature-match i")).forEach(icon => {
        icon.addEventListener("click", e => {
            const term = e.target.dataset.term;
            if (!filteredEntities.includes(term))
                filteredEntities.push(term);

            if (filteredEntities.length)
                url.searchParams.set('filter-entities', filteredEntities.join(','));
            else
                url.searchParams.delete('filter-entities');

            history.replaceState(null, null, url.toString());
            renderLiterature(accessions, results);
        });
    });

    Array.from(document.querySelectorAll("#entity-filters i")).forEach(icon => {
        icon.addEventListener("click", e => {
            const term = e.target.dataset.term;
            const i = filteredEntities.indexOf(term);
            filteredEntities.splice(i, 1);

            if (filteredEntities.length)
                url.searchParams.set('filter-entities', filteredEntities.join(','));
            else
                url.searchParams.delete('filter-entities');

            history.replaceState(null, null, url.toString());
            renderLiterature(accessions, results);
        });
    });
}

$(function () {
    const match = location.pathname.match(/^\/signatures\/(.+)\/literature\/$/i);
    const accessions = match[1].split("/");
    document.title = "Literature (" + accessions.join(", ") + ") | Pronto";
    selector.init(document.getElementById('methods'));
    selector.tab("literature");
    accessions.forEach(acc => selector.add(acc));

    const url = new URL(location.href);
    let classifier = url.searchParams.get("classifier") || defaultClassifier;
    let entityCount = Number.parseInt(url.searchParams.get("entity-count"), 10);
    if (Number.isNaN(entityCount))
        entityCount = defaultEntityCount;

    Array.from(document.querySelectorAll("input[name=classifier]")).forEach(input => {
        input.addEventListener("change", e => {
            classifier = e.target.value;
            url.searchParams.set("classifier", classifier);
            url.searchParams.delete("task");
            history.replaceState(null, null, url.toString());
            getLiterature(accessions, classifier, entityCount);
        });

        input.checked = input.value === classifier;
    });

    Array.from(document.querySelectorAll("input[name=entity-count]")).forEach(input => {
        input.addEventListener("change", e => {
            entityCount = Number.parseInt(e.target.value, 10);
            url.searchParams.set("entity-count", entityCount);
            url.searchParams.delete("task");
            history.replaceState(null, null, url.toString());
            getLiterature(accessions, classifier, entityCount);
        });

        input.checked = Number.parseInt(input.value, 10) === entityCount;
    });

    finaliseHeader();
    getLiterature(accessions, classifier, entityCount);
});