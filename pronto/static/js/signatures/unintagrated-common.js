import {sleep} from "../tasks.js";
import * as dimmer from "../ui/dimmer.js";
import * as modals from "../ui/modals.js"

export function initSliderInputs() {
    ['sprot', 'trembl'].forEach(name => {
        const input = document.getElementById(`input-${name}`);
        input.addEventListener('change', event => {
            const value = Number.parseInt(event.currentTarget.value, 10);
            const sliderId = `#slider-${name}`;
            $(sliderId).slider('set value', value, true);
        });
    });
}

export function updateSliders(data, refresh) {
    ['sprot', 'trembl'].forEach((name,) => {
        const sliderId = `#slider-${name}`;
        const filterId = `min-${name}`;
        const input = document.getElementById(`input-${name}`);
         input.value = (data.filters[filterId] * 100).toFixed(0);
        $(sliderId)
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

export async function preIntegrate(apiUrl, filterFn, actionFn) {
    dimmer.on();
    const url = new URL(location.href);
    url.searchParams.set('page', '1');
    url.searchParams.set('page_size', '1000000');

    for (const [param, value] of url.searchParams.entries()) {
        if (!apiUrl.searchParams.has(param))
            apiUrl.searchParams.set(param, value);
    }

    const response = await fetch(apiUrl);
    const data = await response.json();
    dimmer.off();

    if (!response.ok) {
        modals.error(data.error.title, data.error.message);
        return;
    }

    const signatures = filterFn(data.results);
    if (signatures.length > 0) {
        modals.ask(
            'Bulk integration',
            `You are about to integrate <strong>${signatures.length} signatures</strong>. You need to be logged in to perform this operation.`,
            'Integrate',
            () => {
                integrate(signatures, actionFn)
            }
        );
    } else {
        modals.error('No signatures to integrate', 'We did not find any signature eligible to be integrated.');
    }
}

export async function integrate(signatures, actionFn) {
    const modal = document.getElementById('progress-model');
    modal.querySelector('.content').innerHTML = `
        <div class="ui progress" data-value="0" data-total="${signatures.length}">
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
    $(modal).modal({closable: false}).modal('show');
    $(progress).progress();

    await sleep(2000);

    let successes = 0;
    for (const [signatureAcc, entryAcc] of signatures) {
        const response = await actionFn(signatureAcc, entryAcc);
        const node = document.createElement('tr');
        let icon = '<i class="green check circle icon"></i>';
        if (response.ok)
            successes++;
        else
            icon = `<span data-tooltip="${response.error || 'Unknown error'}"><i class="red exclamation circle icon"></i></span>`;

        let entry = 'N/A';
        if (response.entry)
            entry = `<a href="/entry/${response.entry}/" target="_blank">${response.entry}</a>`;

        node.innerHTML = `
            <td>
                <a href="/signature/${response.signature}/" target="_blank">${response.signature}</a>
            </td>
            <td>
                ${icon}
                ${entry}
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