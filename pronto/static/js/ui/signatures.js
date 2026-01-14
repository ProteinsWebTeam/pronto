import { setClass } from "./utils.js";
import { fetchProtein, renderMatches, setLinkToUniProt, setLinkToStructurePrediction } from "./proteins.js";
import * as pagination from "./pagination.js";
import * as dimmer from "./dimmer.js";

export const selector = {
    elem: null,
    signatures: [],
    init: function(elem) {
        this.elem = elem;
        const input = this.elem.querySelector('input[type=text]');
        const self = this;

        input.addEventListener('keyup', e => {
            if (e.which === 13) {
                let render = false;
                e.target.value.trim().replace(/,/g, ' ').split(' ').forEach(accession => {
                    if (accession.length && !self.signatures.includes(accession)) {
                        self.signatures.push(accession);
                        render = true;
                    }
                });

                e.target.value = null;
                if (render)
                    self.render();
            }
        });
        return this;
    },
    add: function(accession) {
        if (accession.length && !this.signatures.includes(accession)) {
            this.signatures.push(accession);
        }
        return this;
    },
    render: function() {
        const div = this.elem.querySelector('.ui.grid .column:last-child');

        let html = '';
        this.signatures.forEach(accession => {
            html += '<a class="ui basic label" data-id="' + accession + '">' + accession + '<i class="delete icon"></i></a>';
        });
        div.innerHTML = html;

        for (const elem of div.querySelectorAll('a i.delete')) {
            elem.addEventListener('click', e => {
                if (this.signatures.length === 1)
                    return; // Always have at least one signature selected

                const accession = e.currentTarget.parentNode.dataset.id;
                this.signatures = this.signatures.filter(item => item !== accession);
                this.render();
            });
        }

        // const params = [];
        // for (let [key, value] of new URL(location.href).searchParams.entries()) {
        //     if (key !== 'page' && key !== 'page_size')
        //         params.push(`${key}=${value}`);
        // }

        for (const elem of this.elem.querySelectorAll('.links a')) {
            // elem.setAttribute('href', `/signatures/${this.signatures.join('/')}/${elem.dataset.link}/?${params.join('&')}`);
            elem.setAttribute('href', `/signatures/${this.signatures.join('/')}/${elem.dataset.link}`);
        }
        return this;
    },
    tab: function(tabName) {
        for (const elem of this.elem.querySelectorAll('.links a')) {
            setClass(elem, 'active', elem.dataset.name === tabName);
        }
        return this;
    }
};

export function renderConfidence(signature, force) {
    if (signature.relationship === null) {
        if (force) {
            return `<i class="star outline fitted icon"></i>
                    <i class="star outline fitted icon"></i>
                    <i class="star outline fitted icon">`;
        }
        return '';
    }

    let html = '<i class="star fitted icon"></i>';
    if (signature.relationship === signature.residues.relationship) {
        html += '<i class="star fitted icon"></i>';

        const key = signature.relationship === 'similar' ? 'similarity' : 'containment';
        if (signature.residues[key] >= 0.90)
            html += '<i class="star fitted icon"></i>';
        else
            html += '<i class="star outline fitted icon"></i>';
    } else
        html += '<i class="star outline fitted icon"></i><i class="star outline fitted icon"></i>';

    return html;
}

export function showProteinsModal(accession, params, getMatches, allAccessions) {
    const modal = document.getElementById('proteins-modal');
    let linkElem = modal.querySelector('thead .right.menu a:first-of-type');
    linkElem.innerHTML = 'Proteins';
    linkElem.href = `/signatures/${accession}/proteins/?${params.join('&')}`;

    linkElem = modal.querySelector('thead .right.menu a:nth-of-type(2)');
    linkElem.innerHTML = `Proteins matching ${accession} only`;
    const otherAccessions = allAccessions.filter((acc) => acc !== accession);
    linkElem.href = `/signatures/${accession}/proteins/?${params.join('&')}&exclude=${otherAccessions.join(',')}`;

    // To exclude ALL other signatures, not only the other signatures being compared
    // linkElem.href = `/signatures/${accession}/proteins/?${params.join('&')}&exclude-others`;

    params.push('page_size=20');
    params.push('page=1');
    params.push('reviewed-first');

    let url = `/api/signatures/${accession}/proteins/?${params.join('&')}`;
    getProteins(accession, url, getMatches).then(() => {
        $(modal).modal('show');
    })
}


async function getProteins(accession, url, getMatches) {
    dimmer.on();
    const response = await fetch(url);
    const object = await response.json();

    const promises = [];
    for (const protein of object.results) {
        promises.push(fetchProtein(protein.accession, getMatches));
    }

    const proteins = await Promise.all(promises);

    const svgWidth = 400;
    const svgPaddingLeft = 5;
    const svgPaddingRight = 20;
    const width = svgWidth - svgPaddingLeft - svgPaddingRight;

    const maxLength = Math.max(...Array.from(proteins, p => p.length));

    let html = '';
    for (const protein of proteins) {
        const _width = Math.floor(protein.length * width / maxLength);
        const signature = protein.signatures.filter(s => s.accession === accession)[0];
        html += `
            <tr>
            <td class="nowrap" data-external-uniprot="${protein.accession}"></td>
            <td class="collapsing" data-external-structure="${protein.accession}"></td>
        `;

        html += `
            <td>${protein.identifier}</td>
            <td>${protein.name}</td>
        `;

        if (getMatches) {
            html += `
                <td><em>${protein.organism.name}</em></td>
                <td>
                    <svg width="${svgWidth}" height="30">
                    <line x1="${svgPaddingLeft}" y1="20" x2="${_width}" y2="20" stroke="#888" stroke-width="1px"/>
                    <text x="${svgPaddingLeft + _width + 2}" y="20" class="length">${protein.length}</text>
                    ${renderMatches(protein.length, signature, _width, svgPaddingLeft)}
                    </svg>
                </td>
                </tr>
            `;
        } else
            html += `<td colspan="2"><em>${protein.organism.name}</em></td></tr>`;

        setLinkToUniProt(protein,
            (p) => `<i class="${!p.is_reviewed ? 'outline ' : ''}star icon"></i>`,
            (p) => p.is_spurious ? '<span class="ui red text"> <i class="warning icon"></i ></span>' : null);
        setLinkToStructurePrediction(protein.accession)
    }

    const modal = document.getElementById('proteins-modal');
    const tbody = modal.querySelector('tbody');
    tbody.innerHTML = html;

    pagination.render(
        tbody.parentNode,
        object.page_info.page,
        object.page_info.page_size,
        object.count,
        (url) => {
            getProteins(accession, url, getMatches);
        },
        new URL(url, location.origin)
    );
    dimmer.off();
    return Promise.resolve();
}