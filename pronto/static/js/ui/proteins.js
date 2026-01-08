import {sleep} from "../tasks.js";

function toInterPro(accession) {
    return `https://ebi.ac.uk/interpro/protein/${accession}`
}

export function fetchProtein(proteinAccession, matches) {
    let url = `/api/protein/${proteinAccession}/`;
    if (matches)
        url += '?matches'

    return fetch(url)
        .then(response => response.json())
        .then(protein => protein);
}

export async function setLinkToUniProt(protein, textPrefixFn, afterLinkFn) {
    const link = await isOnInternalSwissProt(protein.accession) ?
        `//sp.swiss-prot.ch/uniprot/${protein.accession}` :
        `//www.uniprot.org/uniprotkb/${protein.accession}/entry`;

    let text = textPrefixFn ? textPrefixFn(protein) : '';
    text += protein.is_reviewed ? 'reviewed' : 'unreviewed';

    const after = afterLinkFn ? afterLinkFn(protein) : null;
    setLink(`[data-external-uniprot="${protein.accession}"]`, link, text, after);
}

async function setLink(selectors, href, text, afterLink) {
    let elem = document.querySelector(selectors);
    while (elem === null) {
        await sleep(500);
        elem = document.querySelector(selectors);
    }

    elem.innerHTML = `
        ${elem.tagName.toLowerCase() === 'td' ? '' : '&mdash;'}
        <a target="_blank" href="${href}">
            ${text}<i class="external icon"></i>
        </a>
        ${afterLink ?? ''}
    `;
}

export async function setLinkToStructurePrediction(accession) {
    const selector = `[data-external-structure="${accession}"]`;

    // Check AlphaFold DB
    let response = await fetch(`https://alphafold.ebi.ac.uk/api/prediction/${accession}`);
    if (response.status === 200) {
        const link = `//alphafold.ebi.ac.uk/entry/${accession}`;
        setLink(selector, link, 'AlphaFold', null);
        return;
    }

    // Check BFVD
    response = await fetch(`https://bfvd.foldseek.com/api/${accession}`);
    if (response.status === 200) {
        const payload = await response.json()
        // Find representative accession for the current protein accession
        const reprAccession = payload[0]['rep_accession'];
        if (reprAccession !== null && reprAccession !== undefined) {
            const link = `//bfvd.foldseek.com/cluster/${accession}`;
            setLink(selector, link, 'BFVD', null);
        }
    }
}

async function isOnInternalSwissProt(accession) {
    try {
        const response = await fetch(`//sp.swiss-prot.ch/uniprot/${accession}`, {
            method: 'HEAD',
            signal: AbortSignal.timeout(500)
        });
        return response.ok
    } catch (e) {
        return false;
    }
}


export function genProtHeader(protein) {

    const matchesProteinPage =
    window.location.href.includes(`protein/${protein.accession}`);

    const interproLink = matchesProteinPage
    ? `&mdash; <a target="_blank" href="${toInterPro(protein.accession)}">
        InterPro<i class="external icon"></i>
        </a>`
    : '';

    let html = `
        ${protein.name}
        <div class="sub header">
            ${protein.accession}
            &mdash;
            ${protein.identifier}
            <span data-external-uniprot="${protein.accession}"></span>
            ${interproLink}
            <span data-external-structure="${protein.accession}"></span>
    `;
    setLinkToUniProt(protein);
    setLinkToStructurePrediction(protein.accession);

    html += `
            &mdash;
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