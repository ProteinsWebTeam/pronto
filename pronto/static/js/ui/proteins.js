export function genLink(accession, reviewed) {
    if (reviewed)
        return `//sp.isb-sib.ch/uniprot/${accession}`;
    return `//www.uniprot.org/uniprot/${accession}`
}

export function fetchProtein(proteinAccession, matches) {
    let url = `/api/protein/${proteinAccession}/`;
    if (matches)
        url += '?matches'

    return fetch(url)
        .then(response => response.json())
        .then(protein => protein);
}

export function genProtHeader(protein) {
    return `${protein.name}
            <div class="sub header">
            ${protein.accession} (${protein.identifier})
            &mdash;
            <a target="_blank" href="${genLink(protein.accession, protein.is_reviewed)}">${protein.is_reviewed ? 'reviewed' : 'unreviewed'}<i class="external icon"></i></a>
            &mdash;
            Organism: <em>${protein.organism.name}</em>
            &mdash;
            Length: ${protein.length} AA
            </div>`;
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
                    const px = Math.round(fragments[i-1].end * width / proteinLength) + paddingLeft;
                    html += `<path d="M${px} 15 Q ${(px+x)/2} 0 ${x} 15" fill="none" stroke="${signature.color}"/>`
                }

                html += `<rect x="${x}" y="15" width="${w}" height="10" rx="1" ry="1" style="fill: ${signature.color};" />
                         <text x="${x}" y="10" class="position">${frag.start}</text>
                         <text x="${x+w}" y="10" class="position">${frag.end}</text>
                         </g>`;
            }
        }
    return html;
}