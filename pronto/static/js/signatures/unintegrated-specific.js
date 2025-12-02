import {updateHeader} from "../ui/header.js";
import * as dimmer from "../ui/dimmer.js";
import {initPopups, createPopup, renderCommentLabel} from "../ui/comments.js";
import {render} from "../ui/pagination.js";
import {updateSliders} from "./unintagrated-common.js";

async function refresh() {
    dimmer.on();
    const response = await fetch(`/api/signatures/unintegrated/specific/${location.search}`);
    const data = await response.json();

    if (!response.ok) {
        document.getElementById('results').innerHTML = `
            <div class="ui error message">
                <div class="header">${data.error.title}</div>
                ${data.error.message}
            </div>
        `;
        dimmer.off();
        return;
    }

    if (data.filters['with-annotations'] !== null) {
        const value = data.filters['with-annotations'] ? 'true' : 'false';
        document.querySelector(`input[name="with-annotations"][value="${value}"]`).checked = true;
    } else {
        document.querySelector('input[name="with-annotations"][value=""]').checked = true;
    }

    updateSliders(data, refresh);

    let html = `      
        <table class="ui celled structured small compact table">
        <thead>
            <tr><th colspan="7"><div class="ui secondary menu"><span class="item"></span></div></th></tr>
            <tr>
                <th rowspan="2" colspan="3">Signature</th>
                <th colspan="2" class="center aligned">Swiss-Prot</th>
                <th colspan="2" class="center aligned">TrEMBL</th>
            </tr>
            <tr>
                <th class="right aligned">Proteins</th>
                <th class="right aligned">Overlap fraction</th>
                <th class="right aligned">Proteins</th>
                <th class="right aligned">Overlap fraction</th>
            </tr>
        </thead>
        <tbody>
    `;

    const renderProteinsLink = (accession, numProteins, isReviewed) => {
        if (numProteins === 0) return 0;
        return `<a href="/signatures/${accession}/proteins?reviewed=${isReviewed ? 'true' : 'false'}">
                    ${numProteins.toLocaleString()}
                </a>`;
    };

    if (data.results.length > 0) {
        for (const obj of data.results) {
            html += `
                <tr>
                <td>
                    <span class="ui empty circular label" style="background-color: ${obj.database.color};" data-content="${obj.database.name}" data-position="left center" data-variation="tiny"></span>
                    <a href="/signature/${obj.accession}/?all">${obj.accession}</a>
                </td>
                <td>${obj.name ?? ''}</td>
                <td class="collapsing">${renderCommentLabel(obj)}</td>
                <td class="right aligned">${renderProteinsLink(obj.accession, obj.proteins.reviewed, true)}</td>
                <td class="right aligned">${(obj.proteins.overlapping.fraction_reviewed * 100).toFixed(2)}%</td>
                <td class="right aligned">${renderProteinsLink(obj.accession, obj.proteins.unreviewed, false)}</td>
                <td class="right aligned">${(obj.proteins.overlapping.fraction_unreviewed * 100).toFixed(2)}%</td>
                </tr>
            `;
        }
    } else {
        html += '<tr><td colspan="7" class="center aligned">No results found</td></tr>';
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

    // Comment pop-ups
    initPopups({
        element: elem,
        position: 'right center',
        buildUrl: (accession) => `/api/signature/${accession}/comments/`,
        createPopup: createPopup
    });

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
    refresh();

    document.querySelectorAll('.ui.form input[name="with-annotations"]').forEach((input) => {
        input.addEventListener('change', e => {
            const value = e.currentTarget.value;
            const url = new URL(location.href);
            url.searchParams.set('with-annotations', value);
            url.searchParams.delete('page');
            url.searchParams.delete('page_size');
            history.replaceState(null, null, url.toString());
            refresh();
        });
    });
});
