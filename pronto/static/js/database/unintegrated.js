import {updateHeader} from '../ui/header.js'
import * as checkbox from '../ui/checkbox.js'
import * as dimmer from '../ui/dimmer.js'
import * as pagination from '../ui/pagination.js'
import {renderConfidence} from "../ui/signatures.js";


function renderEntry(entry) {
    if (entry === null)
        return '<td colspan="2"></td>'

    return `
        <td class="nowrap">
            <span class="ui circular mini label type ${entry.type}">${entry.type}</span>
            <a href="/entry/${entry.accession}/">${entry.accession} (${entry.name})</a>
        </td>
        <td class="collapsing">${checkbox.createDisabled(entry.checked)}</td>`;
}


function getSignatures() {
    dimmer.on();
    fetch(`/api${location.pathname}${location.search}`)
        .then(response => {
            dimmer.off();
            if (response.ok)
                return response.json();
            throw response.status.toString();
        })
        .then(object => {
            const title = `${object.database.name} (${object.database.version}) unintegrated signatures`;
            document.querySelector('h1.ui.header').innerHTML = title;
            document.title = `${title} | Pronto `;

            for (const [key, value] of Object.entries(object.parameters)) {
                document.querySelector(`input[name="${key}"][value="${value ? value : ''}"]`).checked = true;
            }

            let html = '';
            for (const signature of object.results) {
                html += `<tr>
                         <td rowspan="${signature.targets.length}"><a href="/signature/${signature.accession}/">${signature.accession}</a></td>
                         <td rowspan="${signature.targets.length}" class="right aligned">${signature.proteins.toLocaleString()}</td>`;

                for (let i = 0; i < signature.targets.length; ++i) {
                    const target = signature.targets[i];

                    if (i) html += '<tr>';

                    html += `<td class="nowrap">
                                <span class="ui empty circular label" style="background-color: ${target.database.color};" data-content="${target.database.name}" data-position="left center" data-variation="tiny"></span>
                                <a href="/signature/${target.accession}/">${target.accession}</a>
                             </td>
                             <td class="right aligned">${target.proteins.toLocaleString()}</td>
                             <td class="right aligned">${target.collocations.toLocaleString()}</td>
                             <td class="right aligned">${target.overlaps.toLocaleString()}</td>
                             <td class="center aligned nowrap">${renderConfidence(target)}</td>
                             ${renderEntry(target.entry)}
                             </tr>`;
                }
            }

            const table = document.getElementById('results');
            table.querySelector('tbody').innerHTML = html;

            pagination.render(
                table,
                object.page_info.page,
                object.page_info.page_size,
                object.count,
                (url,) => {
                    history.replaceState(null, document.title, url);
                    getSignatures();
                });

            // Tooltips
            $('[data-content]').popup();
        });
}


document.addEventListener('DOMContentLoaded', () => {
    updateHeader();
    getSignatures();

    $('.message .close')
        .on('click', function() {
            $(this)
                .closest('.message')
                .transition('fade');
        });

    for (const input of document.querySelectorAll('input[type="radio"]')) {
        input.addEventListener('change', (e,) => {
            console.log(e);
            const key = e.currentTarget.name;
            const value = e.currentTarget.value;
            const url = new URL(location.href);

            if (value)
                url.searchParams.set(key, value);
            else if (url.searchParams.has(key))
                url.searchParams.delete(key);

            history.replaceState(null, document.title, url.toString());
            getSignatures();
        });
    }
});
