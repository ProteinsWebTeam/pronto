import {updateHeader} from "../ui/header.js";
import * as dimmer from "../ui/dimmer.js";
import {initPopups, createPopup, renderCommentLabel} from "../ui/comments.js";
import {render} from "../ui/pagination.js";
import {
    updateSliders,
    preIntegrate,
    initSliderInputs
} from "./unintagrated-common.js";

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

function getTypesMap() {
    // Builds map of type -> type code using the dropdown in the header used to create new entries
    const select = document.querySelector('#new-entry-info select[name="type"]');
    return new Map(
        Array.from(select.options).map(opt => [opt.text, opt.value])
    );
}

document.addEventListener('DOMContentLoaded', () => {
    updateHeader();
    initSliderInputs();
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

    const types = getTypesMap();

    document
        .querySelector('.ui.form > .ui.button')
        .addEventListener('click', e => preIntegrate(
            new URL(`${location.origin}/api/signatures/unintegrated/specific/?with-annotations=true`),
            (results) => {
                return results
                    .filter(signature => signature.comments === 0 && types.has(signature.type))
                    .map(signature => ([
                        signature.accession,
                        null
                    ]));
            },
            async (signatureAcc,) =>  {
                const state = {
                    ok: false,
                    signature: signatureAcc,
                    entry: null,
                    error: null
                }
                let response = await fetch(`/api/signature/${signatureAcc}/`);
                let data = await response.json();
                if (!response.ok) {
                    state.error = data?.error?.message;
                    return state;
                }

                let typeCode = types.get(data.type);
                if (typeCode === undefined) {
                    state.error = `Cannot integrate signature of type "${data.type}"`;
                    return state;
                }

                if (data.description.match(/(domain|region)$/i)) {
                    typeCode = 'D';
                }

                response = await fetch(
                    '/api/entry/',
                    {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json; charset=utf-8' },
                    body: JSON.stringify({
                        type: typeCode,
                        name: data.description,
                        short_name: data.name,
                        is_llm: false,
                        is_checked: false,
                        automatic: true,
                        signatures: [signatureAcc]
                    })
                });
                data = await response.json();
                if (response.ok) {
                    state.ok = true
                    state.entry = data.accession;
                } else {
                    state.error = data?.error?.message;
                }

                return state;
            }
        ));
});
