import * as modals from "../ui/modals.js";

export function refresh(accession) {
    return fetch(`/api/entry/${accession}/references/`)
        .then(response => response.json())
        .then(references => {
            const elem = document.querySelector('#supp-references .content');
            if (!references.length) {
                elem.innerHTML = '<p>This entry has no additional references.</p>';
                return;
            }

            let html = '<p>The following publications were not referred to in the description, but provide useful additional information.</p><ul class="ui list">';
            references.sort((a, b) => a.year - b.year);
            for (const pub of references) {
                html += `
                    <li id="${pub.id}" class="item">
                        <div><strong>${pub.title}</strong>
                        <i data-id="${pub.id}" class="right floated unlink button icon"></i>
                        </div>
                        <div>${pub.authors}</div>
                        <div><em>${pub.journal}</em> ${pub.year}, ${pub.volume}, ${pub.pages}</div>
                        <div class="ui horizontal link list">
                `;

                if (pub.doi) {
                    html += `<span class="item"><a target="_blank" href="${pub.doi}">View article<i class="external icon"></i></a></span>`
                }

                if (pub.pmid) {
                    html += `<span class="item">Europe PMC: <a target="_blank" href="//europepmc.org/abstract/MED/${pub.pmid}/">${pub.pmid}<i class="external icon"></i></a></span>`;
                }

                html += '</div></li>'
            }

            elem.innerHTML = html + '</ul>';

            for (const item of elem.querySelectorAll('[data-id]')) {
                item.addEventListener('click', (e,) => {
                    const pubId = e.currentTarget.dataset.id;
                    modals.ask(
                        'Delete reference?',
                        'This reference will not be associated to this entry anymore.',
                        'Delete',
                        () => {
                            fetch(`/api/entry/${accession}/reference/${pubId}/`, {method: 'DELETE'})
                                .then(response => response.json())
                                .then(result => {
                                    if (result.status)
                                        refresh(accession).then(() => { $('.ui.sticky').sticky(); });
                                    else
                                        modals.error(result.error.title, result.error.message);
                                });
                        }
                    );
                });
            }
        });
}