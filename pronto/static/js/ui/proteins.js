export function genLink(accession, reviewed) {
    if (reviewed)
        return `//sp.sib.swiss/uniprot/${accession}`;
    return `//www.uniprot.org/uniprotkb/${accession}/entry`
}

export function fetchProtein(proteinAccession, matches) {
    let url = `/api/protein/${proteinAccession}/`;
    if (matches)
        url += '?matches'

    return fetch(url)
        .then(response => response.json())
        .then(protein => protein);
}

export async function hasAlphaFold(accession) {
    const response = await fetch(`https://alphafold.ebi.ac.uk/api/prediction/${accession}`);
    return response.status === 200;
}

export function genProtHeader(protein) {
    let html = `
        ${protein.name}
        <div class="sub header">
            ${protein.accession} (${protein.identifier})
            &mdash;
            <a target="_blank" href="${genLink(protein.accession, protein.is_reviewed)}">${protein.is_reviewed ? 'reviewed' : 'unreviewed'}<i class="external icon"></i></a>
            &mdash;
            <span data-alphafold="${protein.accession}"></span>
    `;

    hasAlphaFold(protein.accession).then((hasAF) => {
        if (hasAF) {
            const wait = (ms) => {
                setTimeout(() => {
                    const span = document.querySelector(`[data-alphafold="${protein.accession}"]`);
                    if (span !== null) {
                        span.innerHTML = `
                            <a target="_blank" href="https://alphafold.ebi.ac.uk/entry/${protein.accession}">Alphafold<i class="external icon"></i></a> 
                            &mdash;
                        `;
                    } else {
                        wait(500);
                    }
                }, ms);
            };

            wait(0);
        }
    });

    html +=`
            Organism: <em>${protein.organism.name}</em>
            &mdash;
            Length: ${protein.length} AA
            ${protein.is_spurious ? '&mdash; <span class="ui red text"><i class="warning icon"></i >Spurious protein</span>' : ''}
    `;

    if (protein.md5 !== undefined && protein.count !== undefined) {
        const url = new URL(location.pathname, location.origin);
        url.searchParams.set('md5', protein.md5);

        const params = new URLSearchParams(location.search);
        for (const [key, value] of params.entries()) {
            if (key !== 'page' && key !== 'page_size' && key !== 'domainorganisation')
                url.searchParams.set(key, value);
        }

        html += `
            &mdash;
            <a href="${url.toString()}">${protein.count.toLocaleString()} proteins</a> with this architecture 
        `;
    }

    return html + '</div>';
}

export function renderMatches(proteinLength, signature, width, paddingLeft) {
    let html = '';
    for (const fragments of signature.matches) {
        for (let i = 0; i < fragments.length; i++) {
            const frag = fragments[i];
            const x = Math.round(frag.start * width / proteinLength) + paddingLeft;
            const w = Math.round((frag.end - frag.start) * width / proteinLength);

            html += '<g>';
            if (i) {
                // Discontinuous domain: draw arc
                const px = Math.round(fragments[i - 1].end * width / proteinLength) + paddingLeft;
                html += `<path d="M${px} 15 Q ${(px + x) / 2} 0 ${x} 15" fill="none" stroke="${signature.color}"/>`
            }

            html += `<rect x="${x}" y="15" width="${w}" height="10" rx="1" ry="1" style="fill: ${signature.color};" />
                    <text x="${x}" y="10" class="position">${frag.start}</text>
                    <text x="${x + w}" y="10" class="position">${frag.end}</text>
                    </g>`;
        }
    }
    return html;
}