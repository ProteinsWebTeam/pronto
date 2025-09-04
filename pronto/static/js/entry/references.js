import * as modals from "../ui/modals.js";
import { toggleErrorMessage } from "../ui/utils.js";

export function refresh(accession) {
    return fetch(`/api/entry/${accession}/references/`)
        .then(response => response.json())
        .then(references => {
            const elem = document.querySelector('#supp-references .content');
            if (!references.length) {
                elem.innerHTML = '<p>This entry has no additional references.</p>';
                document.querySelectorAll('.supp-refs-unlink').forEach(e => e.remove())
                return;
            }
            
            // Unlink all references
            document.querySelector('.supp-refs-actions').innerHTML += `
                <div class="supp-refs-unlink ui horizontal divider">&nbsp;</div>
                <button id="unlink-all-btn" class="supp-refs-unlink ui red button">Unlink all</button>
            `

            document.querySelector('#unlink-all-btn').addEventListener('click', e => {
                const errMsg = document.querySelector('#edit-entry .ui.message');
                toggleErrorMessage(errMsg, null);
                modals.ask(
                    'Unlink supplementary references',
                    `Do you want to unlink all the supplementary references?`,
                    'Unlink all',
                    () => {
                        let url = `/api/entry/${accession}/references/`;
                        fetch(url, { method: 'DELETE' })
                            .then(response => response.json())
                            .then(result => {
                                if (result.status) {
                                    refresh(accession).then(() => { $('.ui.sticky').sticky(); });
                                } else
                                    toggleErrorMessage(errMsg, result.error);
                            });
                    }
                );
            })

            let html = '<p>The following publications were not referred to in the description, but provide useful additional information.</p><ul class="ui list">';
            references.sort((a, b) => a.year - b.year);
            for (const pub of references) {
                let details = '';
                if (pub.volume && pub.issue && pub.pages)
                    details = `, ${pub.volume}(${pub.issue}):${pub.pages}`;

                html += `
                    <li id="${pub.id}" class="item">
                        <div><strong>${pub.title}</strong>
                        <i data-id="${pub.id}" class="right floated unlink button icon"></i>
                        </div>
                        <div>${pub.authors}</div>
                        <div><em>${pub.journal}</em> ${pub.year}${details}</div>
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
                            fetch(`/api/entry/${accession}/reference/${pubId}/`, { method: 'DELETE' })
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