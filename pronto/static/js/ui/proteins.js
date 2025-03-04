export function genLink(accession, reviewed) {
    if (reviewed)
        return `//sp.swiss-prot.ch/uniprot/${accession}`;
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

export function structureTypeToURL(urlType, structureType, accession) {
    const structureTypeToUrlMap = {
        "api": {
            "alphafold": `https://alphafold.ebi.ac.uk/api/prediction/${accession}`,
            "bfvd": `https://bfvd.foldseek.com/api/${accession}`,
        },
        "browser": {
            "alphafold": `https://alphafold.ebi.ac.uk/entry/${accession}`,
            "bfvd": `https://bfvd.foldseek.com/cluster/${accession}`
        }
    }

    return structureTypeToUrlMap[urlType][structureType]
}

export async function setExternalStructureLink(type, accession) {

    const wait = (ms) => {
        setTimeout(() => {
            const htmlElement = document.querySelector(`[data-external-structure="${accession}"]`);
            if (htmlElement !== null) {
                if (type){
                    const linkContent = type === "alphafold" ? "Alphafold" : "BFVD" 
                    htmlElement.innerHTML = `
                    <a target="_blank" href=${structureTypeToURL("browser", type, accession)}>
                        ${linkContent}<i class="external icon"></i>
                    </a>
                    ${htmlElement.tagName.toLowerCase() === "td" ? '' : '&mdash;'}`
                }
                else {
                    htmlElement.innerHTML = `No predicted structure`;
                }
            } else {
                wait(500);
            }
        }, ms);
    };
    wait(0);
}

export async function hasExternalStructure(accession, type) {

    const url = structureTypeToURL("api", type, accession)
    const response = await fetch(url);

    // Find representative accession for the current signature accession
    if (type === "bfvd") {
        const bfvdData = await response.json()
        return bfvdData[0]["rep_accession"] ? true : false
    }

    return response.status === 200;
}

export async function getExternalStructureSources(accession) {
    hasExternalStructure(accession, "alphafold").then((hasAF) => { 
        if (hasAF) setExternalStructureLink("alphafold", accession) 
        else {
            hasExternalStructure(accession, "bfvd").then((hasBFVD) => {
                if (hasBFVD) {
                    setExternalStructureLink("bfvd", accession)
                }
                else setExternalStructureLink(null, accession)
            })
        }
    })
}

export function genProtHeader(protein) {
    let html = `
        ${protein.name}
        <div class="sub header">
            ${protein.accession}
            &mdash;
            ${protein.identifier}
            &mdash;
            <a target="_blank" href="${genLink(protein.accession, protein.is_reviewed)}">${protein.is_reviewed ? 'reviewed' : 'unreviewed'}<i class="external icon"></i></a>
            &mdash;
            <span data-external-structure="${protein.accession}"></span>
    `;

    getExternalStructureSources(protein.accession)

    html += `
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

            html += renderFragment(frag, width, proteinLength, 15, signature.color, {
                previousFragment: i > 0 ? fragments[i-1] : null,
                paddingLeft: paddingLeft,
                addPositions: true,
                arcFactor: 0
            })
        }
    }
    return html;
}


export function renderFragment(fragment, width, proteinLength, y, color,
                        {
                            previousFragment = null,
                            paddingLeft = 0,
                            addPositions = false,
                            accession = null,
                            name = null,
                            database = null,
                            link = null,
                            matchHeight = 10,
                            arcFactor = 1
                        }
) {
    const x = Math.round(fragment.start * width / proteinLength) + paddingLeft;
    const w = Math.round((fragment.end - fragment.start) * width / proteinLength);

    let html = '<g>';
    if (fragment.status === 'S') {
        html += `<path 
                    d="M${x},${y} L${x+w},${y} L${x+w},${y+matchHeight} L${x},${y+matchHeight}Z" fill="${color}"
                    data-start="${fragment.start}"
                    data-end="${fragment.end}"
                    data-id="${accession || ''}"
                    data-name="${name || ''}"
                    data-db="${database || ''}"
                    data-link="${link || ''}"/>`;
    } else {
        if (previousFragment !== null) {
            // Draw arc
            const px = Math.round(previousFragment.end * width / proteinLength) + paddingLeft;
            const x1 = (px + x) / 2;
            const y1 = (y - matchHeight * 6) * arcFactor;
            html += `<path d="M${px} ${y} Q ${x1} ${y1} ${x} ${y}" fill="none" stroke="${color}"/>`;
        }

        const da = (matchHeight * Math.sqrt(2)) / 2;
        const db = Math.sqrt(Math.pow(da, 2) - Math.pow(matchHeight / 2, 2));

        let pathCmd = '';
        if (fragment.status === 'N' || fragment.status === 'NC') {
            pathCmd += `M${x+db} ${y+(matchHeight/2)} L${x} ${y} L${x+w} ${y}`;
        } else {
            pathCmd += `M${x} ${y} L${x+w} ${y}`;
        }

        if (fragment.status === 'C' || fragment.status === 'NC') {
            pathCmd += `L${x+w-db} ${y+(matchHeight/2)} L${x+w} ${y+matchHeight} L${x} ${y+matchHeight}`;
        } else {
            pathCmd += `L${x+w} ${y+matchHeight} L${x} ${y+matchHeight}`;
        }

        html += `<path 
                    d="${pathCmd}Z" fill="${color}"
                    data-start="${fragment.start}"
                    data-end="${fragment.end}"
                    data-id="${accession || ''}"
                    data-name="${name || ''}"
                    data-db="${database || ''}"
                    data-link="${link || ''}"/>`;
    }

    if (addPositions) {
        html += `
            <text x="${x}" y="10" class="position">${fragment.start}</text>
            <text x="${x + w}" y="10" class="position">${fragment.end}</text>
        `;
    }

    return html + '</g>';
}