function genLinkTag(accession, isReviewed) {
    if (isReviewed)
        return `<a target="_blank" href="//sp.isb-sib.ch/uniprot/${accession}">reviewed<i class="external icon"></i></a>`;
    else
        return `<a target="_blank" href="//uniprot.org/uniprot/${accession}">unreviewed<i class="external icon"></i></a>`;
}

export function genProtHeader(protein) {
    return `${protein.name}
            <div class="sub header">
            ${protein.accession} (${genLinkTag(protein.accession, protein.is_reviewed)})
            &mdash;
            Organism: <em>${protein.organism}</em>
            &mdash;
            Length: ${protein.length} AA
            </div>`;
}