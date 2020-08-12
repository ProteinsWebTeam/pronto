import * as dimmer from "../ui/dimmer.js";
import {updateHeader} from "../ui/header.js";
import {selector, showProteinsModal} from "../ui/signatures.js";

async function getComments(acc1, acc2) {
    const response = await fetch(`/api/signatures/${acc1}/${acc2}/comments/`);
    const data = await response.json();

    let diff = 0;
    for (const obj of data.results) {
        if (obj.signatures.hasOwnProperty(acc1) && obj.signatures.hasOwnProperty(acc2)) {
            const val1 = obj.signatures[acc1];
            const val2 = obj.signatures[acc2];
        }
            continue;
        console.warn(`comments`, obj.id, obj.value);
        diff += 1;
    }

    return Promise.resolve(diff === 0);
}

async function getDescriptions(acc1, acc2) {
    const response = await fetch(`/api/signatures/${acc1}/${acc2}/descriptions/?reviewed`);
    const data = await response.json();

    let diff = 0;
    for (const obj of data.results) {
        if (obj.signatures.hasOwnProperty(acc1) && obj.signatures.hasOwnProperty(acc2))
            continue;
        console.warn(`descriptions`, obj.id, obj.value);
        diff += 1;
    }

    return Promise.resolve(diff === 0);
}

async function getGoTerms(acc1, acc2) {
    const response = await fetch(`/api/signatures/${acc1}/${acc2}/go/`);
    const data = await response.json();

    let diff = 0;
    for (const obj of data.results) {
        if (obj.signatures.hasOwnProperty(acc1) && obj.signatures.hasOwnProperty(acc2))
            continue;
        console.warn(`go`, obj.id, obj.name);
        diff += 1;
    }

    return Promise.resolve(diff === 0);
}

async function getTaxonomy(acc1, acc2, domain) {
    const response = await fetch(`/api/signatures/${acc1}/${acc2}/taxonomy/${domain}/`);
    const data = await response.json();

    let diff = 0;
    for (const obj of data.results) {
        if (obj.signatures.hasOwnProperty(acc1) && obj.signatures.hasOwnProperty(acc2))
            continue;
        console.warn(`taxonomy/${domain}`, obj.id, obj.name);
        diff += 1;
    }

    return Promise.resolve(diff === 0);
}


document.addEventListener('DOMContentLoaded', () => {
    // todo
    const acc1 = 'PF06792';
    const acc2 = 'cd15488';

    dimmer.on();
    const promises = [
        getComments(acc1, acc2),
        getDescriptions(acc1, acc2),
        getGoTerms(acc1, acc2),
        getTaxonomy(acc1, acc2, 'superkingdom'),
        getTaxonomy(acc1, acc2, 'kingdom')
    ];

    Promise.all(promises).then(results => {
        console.log(results)
        dimmer.off();
    });
});
