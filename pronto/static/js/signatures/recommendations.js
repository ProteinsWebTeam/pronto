import {updateHeader} from "../ui/header.js";
import * as dimmer from "../ui/dimmer.js";
import {createDisabled} from "../ui/checkbox.js";
import {render} from "../ui/pagination.js";

function renderEntry(entry) {
    if (entry === null)
        return '<td colspan="2"></td>';

    return `
        <td>
            <span class="ui circular mini label type ${entry.type}">${entry.type}</span>
            <a href="/entry/${entry.accession}/">${entry.accession} (${entry.name})</a>
        </td>
        <td class="collapsing">${createDisabled(entry.checked)}</td>
    `;
}

async function refresh() {
    dimmer.on();
    const response = await fetch(`/api/signatures/recommendations/${location.search}`);
    const data = await response.json();
    let html = `
        <table class="ui small celled very compact table">
        <thead>
            <tr><th colspan="5"><div class="ui secondary menu"><span class="item"></span></div></th></tr>
            <tr>
            <th class="center aligned">Signature #1</th>
            <th colspan="2" class="center aligned">Entry</th>
            <th class="center aligned">Signature #2</th>
            <th class="center aligned">Similarity</th>
            </tr>
        </thead>
        <tbody>
    `;
    for (const obj of data.results) {
        if (obj.query.entry === null && obj.target.entry !== null) {
            // Ensure only query is integrated
            const tmp = obj.query;
            obj.query = obj.target;
            obj.target = tmp;
        }

        html += `
            <tr>
            <td>
                <span class="ui empty circular label" style="background-color: ${obj.query.database.color};" data-content="${obj.query.database.name}" data-position="left center" data-variation="tiny"></span>
                <a href="/signature/${obj.query.accession}/">${obj.query.accession}</a>
            </td>
            ${renderEntry(obj.query.entry)}
            <td>
                <span class="ui empty circular label" style="background-color: ${obj.target.database.color};" data-content="${obj.target.database.name}" data-position="left center" data-variation="tiny"></span>
                <a href="/signature/${obj.target.accession}/">${obj.target.accession}</a>
            </td>
            <td class="right aligned">${obj.similarity.toFixed(4)}</td>
            </tr>
        `;
    }

    html += `
        </tbody>
        <tfoot>
        <tr><th colspan="7"><div class="ui right floated pagination menu"></div></th></tr>
        </tfoot>
    `;

    const elem = document.getElementById('results');
    elem.innerHTML = html;

    // Tooltips
    $('[data-content]').popup();

    render(
        elem.querySelector('table'),
        data.page_info.page,
        data.page_info.page_size,
        data.count,
        (url => {
            history.pushState(null, document.title, url);
            refresh();
        })
    );

    dimmer.off();
}

document.addEventListener('DOMContentLoaded', () => {
    updateHeader();
    document.title = 'Highly similar signatures | Pronto';
    document.querySelector('h1.ui.header').innerHTML = 'Highly similar signatures';

    const params = document.getElementById('params');
    params.innerHTML = `
        <p class="justified aligned">
            This page presents pairs of similar signatures, that is signatures whose matches significantly overlap. The similarity between two signatures is determined by evaluating how many residues in UniProtKB are matched by both signatures.<br>Pairs of signatures where both signatures are integrated are not shown.
            
        </p>
        <div class="ui warning message">
            <i class="close icon"></i>
            <div class="header">Checkboxes are read-only</div>
            <p>To check or uncheck an entry, please visit the entry page.</p>
        </div>
        <div class="ui toggle checkbox">
          <input type="checkbox" name="nopanthersf">
          <label>Ignore PANTHER subfamilies</label>
        </div>    
        <div class="ui toggle checkbox">
          <input type="checkbox" name="nocommented">
          <label>Ignore commented candidates</label>
        </div>    
    `;

    $(params.querySelectorAll('.message .close'))
        .on('click', function() {
            $(this)
                .closest('.message')
                .transition('fade');
        });

    for (let input of params.querySelectorAll('input')) {
        input.addEventListener('change', e => {
            const key = e.currentTarget.name;
            const checked = e.currentTarget.checked;
            const url = new URL(location.href, location.origin);

            if (checked)
                url.searchParams.set(key, '');
            else if (url.searchParams.has(key))
                url.searchParams.delete(key);

            history.pushState(null, document.title, url.toString());
            refresh();
        });
    }

    refresh();
});
