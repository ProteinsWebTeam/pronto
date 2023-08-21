import * as dimmer from "../ui/dimmer.js";
import {updateHeader} from "../ui/header.js";
import {render} from "../ui/pagination.js";
import {selector} from "../ui/signatures.js";

document.addEventListener('DOMContentLoaded', () => {
    const match = location.pathname.match(/\/signatures\/(.+)\/structures\/$/i);
    const accessions = match[1].split("/");
    document.title = "Structures (" + accessions.join(", ") + ") | Pronto";

    selector.init(document.getElementById('signature-selector'));
    for (const accession of accessions) {
        selector.add(accession);
    }
    selector.render().tab("structures");

    updateHeader();
    getStructures(accessions);
});

async function getStructures(accessions) {
    dimmer.on();

    const response = await fetch(`/api${location.pathname}`);
    const payload = await response.json();

    const sig2ipr = new Map(Object.entries(payload.integrated));
    const genCell = (acc,) => {
        if (sig2ipr.has(acc))
            return `<th class="center aligned"><span data-tooltip="${sig2ipr.get(acc)}" data-inverted=""><i class="star icon"></i>${acc}</span></th>`;
        else
            return `<th class="center aligned"><i class="star outline icon"></i>${acc}</th>`;
    };

    let html = `
        <thead>
            <tr>
                <th>${payload.results.length.toLocaleString()} proteins</th>
                ${accessions.map(genCell).join('')}
            </tr>
        </thead>
    `;

    html += '<tbody>';
    for (const protein of payload.results) {
        let className = protein.is_reviewed ? "star" : "star outline";
        html += `<tr><td><i class="${className} icon"></i>${protein.accession} (${protein.identifier})</td>`;
        for (const acc of accessions) {
            const structures = protein.signatures[acc]?.length;
            if (structures !== undefined)
                html += `<td><a href="#!" data-signature="${acc}" data-protein="${protein.accession}">${structures.toLocaleString()}</a></td>`;
            else
                html += `<td></td>`;
        }
        html += '</tr>';
    }

    const table = document.getElementById('results');
    table.innerHTML = html + '</tbody>';

    for (const elem of table.querySelectorAll('[data-signature]')) {
        elem.addEventListener('click', e => {
            const signatureAcc = e.currentTarget.dataset.signature;
            const proteinAcc = e.currentTarget.dataset.protein;
            const structures = payload
                .results
                .find((p) => p.accession === proteinAcc)
                .signatures[signatureAcc]
                .sort((a, b) => a.localeCompare(b));

            showStructures(structures, 1, 50)
                .then(() => {
                        $("#structures-modal").modal('show');
                    }
                );
        });
    }

    dimmer.off();
}

async function showStructures(identifiers, page, pageSize) {
    const start = (page - 1) * pageSize;
    const end = page * pageSize;
    const items = identifiers.slice(start, end);
    const results = await getStructuresFromPDBe(items);

    let body = '';

    for (const pdbId of items) {
        const pdbInfo = results.get(pdbId);
        if (pdbInfo === undefined)
            body += '<tr><td colspan="3">Missing</td></tr>';
        else {
            const methods = pdbInfo.experimental_method;
            const rowspan = methods.length || 1;

            body += `
                <tr>
                    <td rowspan="${rowspan}" class="nowrap">
                        <a target="_blank" href="https://www.ebi.ac.uk/pdbe/entry/pdb/${pdbId}">
                            ${pdbId}
                            <i class="external icon"></i>
                        </a>
                    </td>
                    <td rowspan="${rowspan}">${pdbInfo.title}</td>
                    <td class="nowrap">${methods.length ? methods[0] : ''}</td>
                </tr>
            `;

            for (const method of methods.slice(1)) {
                body += `<tr><td class="nowrap">${method}</td></tr>`;
            }
        }
    }

    const table = document.getElementById("structures-modal");
    table.querySelector("tbody").innerHTML = body;

    render(table, page, pageSize, identifiers.length, (url) => {
        const params = new URL(url).searchParams;
        showStructures(identifiers, Number.parseInt(params.get("page")), Number.parseInt(params.get("page_size")));
    });
}

async function getStructuresFromPDBe(identifiers) {
    const response = await fetch("https://www.ebi.ac.uk/pdbe/api/pdb/entry/summary/", {
        "body": identifiers.join(","),
        "method": "POST",
        "mode": "cors"
    });
    const payload =  await response.json();
    return new Map(
        Object
            .entries(payload)
            .filter(([key, value]) => value.length === 1)
            .map(([key, value]) => [key, value[0]])
    );
}