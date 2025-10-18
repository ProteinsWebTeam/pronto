import {updateHeader} from "../ui/header.js";
import * as dimmer from "../ui/dimmer.js";
import {createDisabled} from "../ui/checkbox.js";
import {initPopups, createPopup, renderCommentLabel} from "../ui/comments.js";
import {render} from "../ui/pagination.js";

function renderEntry(entry) {
    return `
        <td>
            <span class="ui circular mini label type ${entry.type}">${entry.type}</span>
            <a href="/entry/${entry.accession}/">${entry.accession} &ndash; ${entry.short_name}</a>
        </td>
        <td class="collapsing">${createDisabled(entry.checked)}</td>
    `;
}

function renderSignatureLink(s) {
    let html = `<span class="ui empty circular label" style="background-color: ${s.database.color};" data-content="${s.database.name}" data-position="left center" data-variation="tiny"></span>`
    if (s.name !== null)
        html += `<a href="/signature/${s.accession}/">${s.accession} &ndash; ${s.name}</a>`;
    else
        html += `<a href="/signature/${s.accession}/">${s.accession}</a>`;
    return html;
}

function renderProteinsLink(accession, numProteins, isReviewed) {
    if (numProteins === 0) return 0;
    return `<a href="/signatures/${accession}/proteins?reviewed=${isReviewed ? 'true' : 'false'}">
                ${numProteins.toLocaleString()}
            </a>`;
}

async function refresh() {
    dimmer.on();
    const response = await fetch(`/api/signatures/unintegrated/similar/${location.search}`);
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

    let html = `
        <strong>Minimum similarity:</strong>
        <div class="ui sib label">
          Swiss-Prot
          <div class="detail">&ge; ${(data.filters['min-sprot'] * 100).toFixed(0)}%</div>
        </div>
        <div class="ui uniprot label">
          TrEMBL
          <div class="detail">&ge; ${(data.filters['min-trembl'] * 100).toFixed(0)}%</div>
        </div>        
        <table class="ui celled structured small compact table">
        <thead>
            <tr><th colspan="11"><div class="ui secondary menu"><span class="item"></span></div></th></tr>
            <tr>
                <th colspan="4" class="center aligned">Candidate</th>
                <th colspan="5" class="center aligned">Target</th>
                <th colspan="2" class="center aligned">Similarity</th>
            </tr>
                <th colspan="2"></th>
                <th class="center aligned">Swiss-Prot</th>
                <th class="center aligned">TrEMBL</th>
                <th></th>
                <th class="center aligned">Swiss-Prot</th>
                <th class="center aligned">TrEMBL</th>    
                <th colspan="2" class="center aligned">Entry</th>
                <th class="center aligned">Swiss-Prot</th>
                <th class="center aligned">TrEMBL</th>
        </thead>
        <tbody>
    `;

    for (const obj of data.results) {
        const rowSpan = obj.targets.length;
        html += `
            <tr>
            <td rowspan="${rowSpan}">${renderSignatureLink(obj)}</td>
            <td rowspan="${rowSpan}" class="collapsing">${renderCommentLabel(obj)}</td>
            <td rowspan="${rowSpan}" class="right aligned">${renderProteinsLink(obj.accession, obj.proteins.reviewed, true)}</td>
            <td rowspan="${rowSpan}" class="right aligned">${renderProteinsLink(obj.accession, obj.proteins.unreviewed, false)}</td>
        `;

        for (let i = 0; i < obj.targets.length; i++) {
            const target = obj.targets[i];
            if (i > 0) html += '<tr>'
            html += `
                <td>${renderSignatureLink(target)}</td>
                <td class="right aligned">${renderProteinsLink(target.accession, target.proteins.reviewed, true)}</td>
                <td class="right aligned">${renderProteinsLink(target.accession, target.proteins.unreviewed, false)}</td>
                ${renderEntry(target.entry)}
                <td class="right aligned">${(target.proteins.overlapping.fraction_reviewed * 100).toFixed(1)}%</td>
                <td class="right aligned">${(target.proteins.overlapping.fraction_unreviewed * 100).toFixed(1)}%</td>
                </tr>                
            `;
        }
    }

    html += `
        </tbody>
        <tfoot>
        <tr><th colspan="11"><div class="ui right floated pagination menu"></div></th></tr>
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
    document.title = 'Similar signatures | Pronto';
    document.querySelector('h1.ui.header').innerHTML = 'Similar signatures';

    const params = document.getElementById('params');
    params.innerHTML = `
        <p class="justified aligned">
            This page lists unintegrated signatures that are potential candidates 
            for integration into existing InterPro entries.
            Candidates are identified based on their similarity to at least 
            one integrated signature from another member database.<br>
            Similarity between two signatures is measured by comparing 
            their hits on protein sequences: a sequence is considered <em>overlapped</em> 
            when the regions matched by both signatures cover at least 80% 
            of each other’s residues. The overall similarity between signatures is then derived 
            from the proportion of shared overlapped sequences in Swiss-Prot and TrEMBL.
        </p>
    `;

    refresh();
});
