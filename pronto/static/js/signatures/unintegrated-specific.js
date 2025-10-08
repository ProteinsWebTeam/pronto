import {updateHeader} from "../ui/header.js";
import * as dimmer from "../ui/dimmer.js";
import {initPopups, createPopup, renderCommentLabel} from "../ui/comments.js";
import {render} from "../ui/pagination.js";

async function refresh() {
    dimmer.on();
    const response = await fetch(`/api/signatures/unintegrated/specific/${location.search}`);
    const data = await response.json();
    let html = `
        <strong>Overlap limits:</strong>
        <div class="ui sib label">
          Swiss-Prot
          <div class="detail">&le; ${(data.filters['max-sprot'] * 100).toFixed(0)}%</div>
        </div>
        <div class="ui uniprot label">
          TrEMBL
          <div class="detail">&le; ${(data.filters['max-trembl'] * 100).toFixed(0)}%</div>
        </div>        
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
    document.title = 'Highly specific signatures | Pronto';
    document.querySelector('h1.ui.header').innerHTML = 'Highly specific signatures';

    const params = document.getElementById('params');
    params.innerHTML = `
        <p class="justified aligned">
            This page lists signatures whose matches rarely overlap with those of other signatures. 
            Specificity is quantified as the fraction of proteins whose hits overlap 
            with hits from any other signature. 
            Signatures with low overlap fractions are considered highly specific and 
            are suitable candidates for integration into new InterPro entries with minimal risk of conflict.
        </p>
    `;

    // Maximum overlap tolerated in Swiss-Prot
    // Maximum overlap tolerated in TrEMBL

    // for (let input of params.querySelectorAll('input')) {
    //     input.addEventListener('change', e => {
    //         const key = e.currentTarget.name;
    //         const checked = e.currentTarget.checked;
    //         const url = new URL(location.href, location.origin);
    //
    //         if (checked)
    //             url.searchParams.set(key, '');
    //         else if (url.searchParams.has(key))
    //             url.searchParams.delete(key);
    //
    //         history.pushState(null, document.title, url.toString());
    //         refresh();
    //     });
    // }

    refresh();
});
