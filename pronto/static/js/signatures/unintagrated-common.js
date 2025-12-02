import {sleep} from "../tasks.js";
import * as dimmer from "../ui/dimmer.js";
import * as modals from "../ui/modals.js"

export function updateSliders(data, refresh) {
    ['sprot', 'trembl'].forEach((name,) => {
        const elemId = `#slider-${name}`;
        const filterId = `min-${name}`;
        const input = document.getElementById(`input-${name}`);
         input.value = (data.filters[filterId] * 100).toFixed(0);
        $(elemId)
            .slider({
                min: 0,
                max: 100,
                start: data.filters[filterId] * 100,
                step: 1,
                smooth: true,
                // showThumbTooltip: true,
                // tooltipConfig: {
                //   position: 'bottom center',
                //   variation: 'grey visible'
                // },
                restrictedLabels: [0, 25, 50, 75, 100],
                onMove: (value) => {
                    input.value = value.toFixed(0);
                },
                onChange: (value) => {
                    input.value = value.toFixed(0);
                    const url = new URL(location.href);
                    url.searchParams.set(filterId, (value / 100).toFixed(2));
                    url.searchParams.delete('page');
                    url.searchParams.delete('page_size');
                    history.replaceState(null, document.title, url.toString());
                    refresh();
                }
            });
    });
}

export async function initIntegrate(apiUrl, filterFn, actionFn) {
    dimmer.on();
    const url = new URL(location.href);
    url.searchParams.delete('page');
    url.searchParams.set('page_size', '1000000');
    const fullApiUrl = `${apiUrl.replace(/\/+$/, '')}/${url.search}`;
    const response = await fetch(fullApiUrl);
    const data = await response.json();
    dimmer.off();

    if (!response.ok) {
        modals.error(data.error.title, data.error.message);
        return;
    }

    const signatures = filterFn(data.results);

    if (signatures.length === 0)
        return;

    modals.ask(
        'Bulk integration',
        `You are about to integrate <strong>${signatures.length} signatures</strong>. You need to be logged in to perform this operation.`,
        'Integrate',
        () => {
            integrate(signatures, actionFn)
        }
    );
}

export async function integrate(signatures, actionFn) {
    const modal = document.getElementById('progress-model');
    modal.querySelector('.content').innerHTML = `
        <div class="ui progress" data-value="1" data-total="${signatures.length}">
            <div class="bar">
                <div class="progress"></div>
            </div>
            <div class="label">Integrating signatures</div>
        </div>
        <table class="ui basic table">
            <thead>
                <tr>
                    <th>Signature</th>
                    <th>Entry</th>
                </tr>
            </thead>
            <tbody></tbody>
        </table>
    `;

    const progress = modal.querySelector('.ui.progress');
    const tbody = modal.querySelector('tbody');
    modal.querySelector('.close.icon').classList.add('hidden');
    $(modal).modal('show');
    $(progress).progress();

    await sleep(2000);

    let successes = 0;
    for (const [signatureAcc, entryAcc] of signatures) {
        const response = await actionFn(signatureAcc, entryAcc);
        const node = document.createElement('tr');
        let icon;
        if (response.ok) {
            successes++;
            icon = '<i class="green check circle icon"></i>';
        } else {
            icon = `<span data-tooltip="${response.error}"><i class="red exclamation circle icon"></i></span>`;
        }
        node.innerHTML = `
            <td>
                <a href="/signature/${response.signature}/" target="_blank">${response.signature}</a>
            </td>
            <td>
                ${icon}
                <a href="/entry/${response.entry}/" target="_blank">${response.entry}</a>
            </td>`;
        tbody.insertBefore(node, tbody.firstChild);
        $(progress).progress('increment');
    }

    if (successes === signatures.length) {
        progress.querySelector('.label').innerText = `${successes} signatures integrated!`;
    } else {
        progress.querySelector('.label').innerText = `${signatures.length - successes} signatures failed to be integrated!`;
        progress.classList.add('error');
    }

    modal.querySelector('.close.icon').classList.remove('hidden');
}