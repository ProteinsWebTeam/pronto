import * as modals from "../ui/modals.js";
import * as dimmer from "../ui/dimmer.js";

function unlink(accession, termID) {
    modals.ask(
        'Unlink Go term?',
        `${termID} will not be applied to ${accession} anymore.`,
        'Unlink',
        () => {
            fetch(`/api/entry/${accession}/go/${termID}/`, {method: 'DELETE'})
                .then(response => response.json())
                .then(result => {
                    if (result.status) {
                        refresh(accession).then(() => { $('.ui.sticky').sticky(); });
                    } else
                        modals.error(result.error.title, result.error.message);
                });
        }
    );
}

export function link(accession, termID) {
    fetch(`/api/entry/${accession}/go/${termID}/`, {method: 'PUT'})
        .then(response => response.json())
        .then(result => {
            if (result.status) {
                $('#go-terms .ui.form').form('clear');
                refresh(accession).then(() => { $('.ui.sticky').sticky(); });
            } else
                modals.error(result.error.title, result.error.message);
        });
}

async function fetchConstraints(entryAccession, goID) {
    const response = await fetch(`/api/entry/${entryAccession}/go/${goID}/`);
    return await response.json();
}

async function updateConstraintsLabel(entryAccession, goID) {
    const result = await fetchConstraints(entryAccession, goID);
    if (result.violations.total > 0) {
        document.querySelector(`[data-term="${goID}"]`).classList.remove('basic');
    }
}

function render(accession, terms, divID) {
    const div = document.getElementById(divID);
    if (terms.length === 0) {
        div.innerHTML = 'No GO terms in this category.';
        return;
    }

    let html = '<ul class="ui list">';
    const promises = [];
    for (const term of terms) {
        html += `
            <li class="item">
                <div class="content">
                    <div class="header">
                        <a target="_blank" href="//www.ebi.ac.uk/QuickGo/GTerm?id=${term.id}">${term.id} &mdash; ${term.name}<i class="external icon"></i></a>
        `;

        if (term.taxon_constraints > 0) {
            html += `&nbsp;<span class="ui tiny basic red label button" data-entry="${accession}" data-term="${term.id}">Taxon constraints 
            <span class="detail">${term.taxon_constraints}</span>
            </span>`;
            promises.push(updateConstraintsLabel(accession, term.id));
        }

        if (term.is_obsolete)
            html += '&nbsp;<span class="ui tiny red label">Obsolete</span>';

        if (term.is_secondary)
            html += '&nbsp;<span class="ui tiny yellow label">Secondary</span>';

        html += `<i data-id="${term.id}" class="right floated unlink button icon"></i>
                 </div>
                 <div class="description">${term.definition}</div>
                 </div>
                 </li>`;
    }

    div.innerHTML = html + '</ul>';
    for (const elem of div.querySelectorAll('[data-id]')) {
        elem.addEventListener('click', (e,) => {
            unlink(accession, e.currentTarget.dataset.id);
        });
    }

    for (const elem of div.querySelectorAll('[data-entry]')) {
        elem.addEventListener('click', (e,) => {
            const acc = e.currentTarget.dataset.entry;
            const term = e.currentTarget.dataset.term;

            dimmer.on();
            fetchConstraints(acc, term)
                .then(result => {
                    const signatures = result.signatures.join('/');
                    let html = `<table class="ui definition celled table">
                                    <thead>
                                        <tr>
                                            <th class="normal">Taxon constraint</th>
                                            <th>Swiss-Prot/reviewed proteins - ${result.proteins.reviewed.toLocaleString()}</th>
                                            <th>All proteins - ${result.proteins.total.toLocaleString()}</th>
                                        </tr>
                                    </thead>
                                    <tbody>

                                    <tr>
                                    <td>Violations summary</td>
                                    <td>
                                        <a href="/signatures/${signatures}/proteins/?violate-go=${term}&reviewed&filtermatches">
                                            ${result.violations.reviewed.toLocaleString()}
                                        </a>
                                    </td>
                                    <td>
                                        <a href="/signatures/${signatures}/proteins/?violate-go=${term}&filtermatches">
                                            ${result.violations.total.toLocaleString()}
                                        </a>
                                    </td>
                                    </tr>`;

                    for (const constraint of result.constraint) {
                        const constType = constraint.type === 'never_in_taxon' ? 'Never in' : 'Only in';
                        html += `<tr>
                                <td>${constType} ${constraint.taxon.name}</td>
                                <td>${constraint.matches.reviewed.toLocaleString()}</td>
                                <td>${constraint.matches.total.toLocaleString()}</td>
                                </tr>`;
                    }

                    html += `</tbody>
                            </table>`;

                    const modal = document.getElementById('goconstraint-modal');
                    modal.querySelector('.ui.header').innerHTML = `GO constraints: ${term}`;
                    modal.querySelector('.scrolling.content').innerHTML = html;
                    $(modal).modal('show');
                    dimmer.off();
                });
        });
    }
}

export function refresh(accession) {
    return fetch(`/api/entry/${accession}/go/`)
        .then(response => response.json())
        .then(terms => {
            // Update stats
            for (const elem of document.querySelectorAll('[data-statistic="go"]')) {
                elem.innerHTML = terms.length.toLocaleString();
            }

            render(accession, terms.filter(t => t.category === 'molecular_function'), 'molecular-functions');
            render(accession, terms.filter(t => t.category === 'biological_process'), 'biological-processes');
            render(accession, terms.filter(t => t.category === 'cellular_component'), 'cellular-components');
        });
}
