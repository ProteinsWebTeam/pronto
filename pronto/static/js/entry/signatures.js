import * as modals from "../ui/modals.js";

export function integrate(entryAcc, signatureAcc, confirmed) {
    const options = {
        method: 'PUT',
        headers: {
            'Content-type': 'application/x-www-form-urlencoded; charset=UTF-8'
        }
    };

    if (confirmed)
        options.body = 'confirmed';

    fetch(`/api/entry/${entryAcc}/signature/${signatureAcc}/`, options)
        .then(response => response.json())
        .then(result => {
            if (!result.status)
                modals.error(result.error.title, result.error.message);
            else if (result.confirm_for !== undefined) {
                // Ask to confirm
                modals.ask(
                    'Signature already integrated',
                    `${signatureAcc} is integrated in ${result.confirm_for}. Do you want to move ${signatureAcc} from ${result.confirm_for} to ${entryAcc}?`,
                    'Yes',
                    () => {
                        integrate(entryAcc, signatureAcc, true);
                    }
                )
            } else {
                $('#signatures .ui.form').form('clear');
                refresh(entryAcc).then(() => {$('.ui.sticky').sticky();});
            }
        });
}

function unintegrate(entryAcc, signatureAcc) {
    const unirule = document.getElementById('unirule').checked;
    let message;

    if (unirule) {
        message = `<strong>${entryAcc} is used by UniRule.</strong> Do you want to unintegrated ${signatureAcc}?`;
    } else {
        message = `Do you want to unintegrated ${signatureAcc} from ${entryAcc}?`;
    }

    modals.ask(
        'Unintegrate signature?',
        message,
        'Yes',
        () => {
            fetch(`/api/entry/${entryAcc}/signature/${signatureAcc}/`, {method: 'DELETE'})
                .then(response => response.json())
                .then(result => {
                    if (result.status)
                        refresh(entryAcc).then(() => {$('.ui.sticky').sticky();});
                    else
                        modals.error(result.error.title, result.error.message);
                });
        }
    );
}

export function refresh(accession) {
    return fetch(`/api/entry/${accession}/signatures/`)
        .then(response => response.json())
        .then(signatures => {
            // Update stats
            for (const elem of document.querySelectorAll('[data-statistic="signatures"]')) {
                elem.innerHTML = signatures.length;
            }

            let html = '';
            if (signatures.length > 0) {
                for (const signature of signatures) {
                    html += `
                        <tr>
                        <td class="collapsing"><i class="database fitted icon" style="color: ${signature.database.color};"></i></td>
                        <td><a target="_blank" href="${signature.database.link}">${signature.database.name}<i class="external icon"></i></a></td>
                        <td><a href="/signature/${signature.accession}/">${signature.accession}</a></td>
                        <td>${signature.name}</td>
                        <td class="right aligned">${signature.sequences.all.toLocaleString()}</td>
                        <td class="right aligned">${signature.sequences.complete.toLocaleString()}</td>
                        <td class="nowrap">${signature.date}</td>
                        <td class="collapsing"><i data-accession="${signature.accession}" class="unlink fitted button icon"></i></td>
                        </tr>
                    `;
                }

                const accessions = Array.from(signatures, (s,) => s.accession).join('/');
                for (const elem of document.querySelectorAll('a[data-link]')) {
                    elem.href = `/signatures/${accessions}/${elem.dataset.link}`;
                }
            } else {
                html = '<tr><td colspan="7" class="center aligned">No integrated signatures</td></tr>';

                for (const elem of document.querySelectorAll('a[data-link]')) {
                    elem.href = '#';
                }
            }

            const tbody = document.querySelector('#signatures tbody');
            tbody.innerHTML = html;

            for (const elem of tbody.querySelectorAll('[data-accession]')) {
                elem.addEventListener('click', (e,) => {
                    unintegrate(accession, e.currentTarget.dataset.accession);
                });
            }
        });
}