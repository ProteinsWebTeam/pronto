import * as modals from "../ui/modals.js";

function nest(obj, isRoot, accession) {
    let html = '';
    const keys = Object.keys(obj).sort();
    if (keys.length > 0) {
        if (isRoot)
            html += '<div class="ui list">';
        else
            html += '<div class="list">';

        for (const key of keys) {
            const node = obj[key];
            html += `
                <div class="item">
                    <div class="content">
                        <div class="header">
                        <span class="ui mini label circular type ${node.type}">${node.type}</span>`;

            if (node.accession === accession)
                html += `${node.name} (${node.accession})`;
            else {
                html += `<a href="/entry/${node.accession}/">${node.name} (${node.accession})</a>`;

                if (node.deletable) {
                    html += `<i data-id="${node.accession}" class="right floated unlink button icon"></i>`
                }
            }

            html += `</div>${nest(node.children, false, accession)}</div></div>`
        }

        html += '</div>';
    } else if (isRoot)
        html += '<p>This entry has no relationships.</p>';

    return html;
}

function remove(acc1, acc2) {
    modals.ask(
        'Delete relationship?',
        `${acc1} and ${acc2} will not be related anymore.`,
        'Delete',
        () => {
            fetch(`/api/entry/${acc1}/relationship/${acc2}/`, {method: 'DELETE'})
                .then(response => response.json())
                .then(result => {
                    if (result.status) {
                        refresh(acc1).then(() => { $('.ui.sticky').sticky(); });
                    } else
                        modals.error(result.error.title, result.error.message);
                });
        }
    );
}

export function add(accession, other, type) {
    let url;
    if (type === 'parent')
        url = `/api/entry/${other}/relationship/${accession}/`;
    else
        url = `/api/entry/${accession}/relationship/${other}/`;

    fetch(url, {method: 'PUT'})
        .then(response => response.json())
        .then(result => {
            if (result.status) {
                $('#relationships .ui.form').form('clear');
                refresh(accession).then(() => { $('.ui.sticky').sticky(); });
            } else
                modals.error(result.error.title, result.error.message);
        });
}

export function refresh(accession) {
    return fetch(`/api/entry/${accession}/relationships/`)
        .then(response => response.json())
        .then(results => {
            const div = document.querySelector('#relationships > .content');
            div.innerHTML = nest(results, true, accession);

            const relationships = [...div.querySelectorAll('i[data-id]')];

            // Update stats
            for (const elem of document.querySelectorAll('[data-statistic="relationships"]')) {
                elem.innerHTML = relationships.length.toLocaleString();
            }

            for (const elem of relationships) {
                elem.addEventListener('click', (e,) => {
                    remove(accession, e.currentTarget.dataset.id);
                });
            }
        });
}