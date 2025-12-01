import {updateHeader} from "../ui/header.js";
import * as dimmer from "../ui/dimmer.js";
import {initPopups, createPopup, renderCommentLabel} from "../ui/comments.js";
import {render} from "../ui/pagination.js";

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

    ['sprot', 'trembl'].forEach((name,) => {
        const elemId = `#slider-${name}`;
        const filterId = `min-${name}`;
        $(elemId)
            .slider({
                min: 0,
                max: 100,
                start: data.filters[filterId] * 100,
                step: 1,
                smooth: true,
                showThumbTooltip: true,
                tooltipConfig: {
                  position: 'right center',
                  variation: 'visible'
                },
                restrictedLabels: [0, 25, 50, 75, 100],
                onChange: (value) => {
                    const url = new URL(location.href);
                    url.searchParams.set(filterId, (value / 100).toFixed(2));
                    url.searchParams.delete('page');
                    url.searchParams.delete('page_size');
                    history.replaceState(null, document.title, url.toString());
                    refresh();
                }
            });
    });

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
});
