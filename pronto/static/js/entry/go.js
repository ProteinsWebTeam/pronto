import * as modals from "../ui/modals.js";

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

function render(accession, terms, divID) {
    const div = document.getElementById(divID);
    if (terms.length === 0) {
        div.innerHTML = 'No GO terms in this category.';
        return;
    }

    let html = '<ul class="ui list">';
    for (const term of terms) {
        html += `
            <li class="item">
                <div class="content">
                    <div class="header">
                        <a target="_blank" href="//www.ebi.ac.uk/QuickGo/GTerm?id=${term.id}">${term.id} &mdash; ${term.name}<i class="external icon"></i></a>
        `;

        if (term.taxon_constraints > 0) {
            html += `&nbsp;<a target="_blank" href="https://www.ebi.ac.uk/QuickGO/term/${term.id}#termTaxonConstraints" class="ui tiny red label">Taxon constraints <span class="detail">${term.taxon_constraints}</span></a>`;
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
