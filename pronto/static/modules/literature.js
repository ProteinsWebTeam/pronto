import * as utils from '../utils.js';

function getLiterature(methods) {
    let grubblerURL = "http://ves-hx2-a0.ebi.ac.uk/bateman/searchsifter/grubbler";
    const url = utils.parseLocation();
    if (url.task)
        grubblerURL += "/grub/task/" + url.task;
    else if (url.classifier)
        grubblerURL += "/grub/family/" + url.classifier + '/' + methods.join(',') + '?max_entity_count=80';
    else {
        grubblerURL += "/grub/family/function/" + methods.join(',') + '?max_entity_count=80';
    }
}

$(function () {
    const match = location.pathname.match(/^\/methods\/(.+)\/([a-z]+)\/$/);
    if (!match) {
        return;
    }

    const methods = match[1].trim().split('/');
    const methodSelectionView = new utils.MethodsSelectionView(document.getElementById('methods'));

    // Add current signature
    methods.forEach(method => { methodSelectionView.add(method); });
    methodSelectionView.render();

    utils.setClass(document.querySelector('a[data-page="'+ match[2] +'"]'), 'active', true);
    document.title = 'Literature ('+ methods.join(', ') +') | Pronto';

    getLiterature(methods);
});