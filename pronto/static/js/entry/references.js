import * as modals from "../ui/modals.js";
import { toggleErrorMessage } from "../ui/utils.js";

export function refresh(accession) {
    return fetch(`/api/entry/${accession}/references/`)
        .then(response => response.json())
        .then(references => {

            const elem = document.querySelector('#supp-references .content');
            const suppRefsActions = document.querySelector('#supp-refs-actions')

            if (!references.length) {
                elem.innerHTML = '<p>This entry has no additional references.</p>';

                // Move to parent element to keep style the same
                document.querySelectorAll('.supp-refs-unlink').forEach(e => {
                    const temp = e.cloneNode(true)
                    suppRefsActions.appendChild(temp)
                    temp.style.display = 'none'
                    e.remove()
                })
                return;
            }

            document.querySelectorAll('#supp-refs-actions .supp-refs-unlink').forEach(e => {
                const temp = e.cloneNode(true)

                // Move in button group again
                const buttonGroup = document.querySelector('#supp-refs-actions .ui.action.input')
                buttonGroup.appendChild(temp)
                temp.style.display = 'inline'
                e.remove()
            })
            
            // Unlink all supp. references on click
            const unlinkBtn = document.querySelector('#unlink-all-btn')
            if (unlinkBtn) {
                unlinkBtn.addEventListener('click', e => {
                    const errMsg = document.querySelector('#edit-entry .ui.message');
                    toggleErrorMessage(errMsg, null);
                    modals.ask(
                        'Unlink supplementary references',
                        `Do you want to unlink all the supplementary references?`,
                        'Unlink all',
                        () => {
                            let url = `/api/entry/${accession}/unlink-references/`;
                            fetch(url, {
                                headers: {
                                    'Content-Type': 'application/json',
                                },
                                method: 'PATCH',
                                body: JSON.stringify({
                                    "pub_ids": references.map((ref) => ref.id)
                                })
                            })
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

            }

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
                            fetch(`/api/entry/${accession}/unlink-references/`,
                                {
                                    headers: {
                                        'Content-Type': 'application/json',
                                    },
                                    method: 'PATCH',
                                    body: JSON.stringify({
                                        "pub_ids": [pubId]
                                    })
                                })
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