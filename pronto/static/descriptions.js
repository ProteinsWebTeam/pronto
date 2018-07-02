import * as utils from './utils.js';


function getDescriptions(proteinsModal) {
    const url = '/api' + location.pathname + location.search;
    utils.dimmer(true);
    utils.getJSON(url, (obj, status) => {
        // Find the highest protein count
        const maxProt = Math.max(...obj.data.map(descr => {
            return Math.max(...descr.methods.map(method => { return method.count }));
        }));

        // Table header
        let html = '<thead><tr><th>'+ obj.data.length +' descriptions</th>';
        obj.data[0].methods.forEach(method => {
            html += '<th><a href="" data-method="'+ method.accession +'">' + method.accession + '</a></th>';
        });
        html += '</thead>';

        // Table body
        const colors = utils.gradientPuBu;
        html += '</thead><tbody>';
        obj.data.forEach(descr => {
            html += '<tr data-filter="'+ descr.value +'" data-search="description=' + descr.id + '&db='+ obj.database +'">' +
                '<td>'+ descr.value +'</td>';

            descr.methods.forEach(method => {
                if (method.count) {
                    const i = Math.floor(method.count / maxProt * colors.length);
                    const color = colors[Math.min(i, colors.length - 1)];
                    const className = utils.useWhiteText(color) ? 'light' : 'dark';
                    html += '<td class="'+ className +'" style="background-color: '+ color +';"><a href="#" data-method="'+ method.accession +'">' + method.count.toLocaleString() + '</a></td>';
                } else
                    html += '<td></td>';
            });

            html += '</tr>';
        });

        const table = document.querySelector('table');
        table.innerHTML = html + '</tbody>';

        proteinsModal.observe(table.querySelectorAll('th a[data-method]'), (method, filter, search) => {
            const header = '<em>' + method + '</em> proteins';
            proteinsModal.open(method, search, header, true);
        });

        proteinsModal.observe(table.querySelectorAll('td a[data-method]'), (method, filter, search) => {
            const header = '<em>' + method + '</em> proteins<div class="sub header">Description: <em>'+ filter +'</em></div>';
            proteinsModal.open(method, search, header);
        });

        // Update radios
        document.querySelector('input[type=radio][value="'+ obj.database +'"]').checked = true;

        utils.dimmer(false);
    });
}


$(function () {
    const match = location.pathname.match(/^\/methods\/(.+)\/([a-z]+)\/$/);
    if (!match) {
        return;
    }

    const methods = match[1].trim().split('/');
    const methodSelectionView = new utils.MethodsSelectionView(document.getElementById('methods'));
    const proteinsModal = new utils.ProteinsModal();

    // Add current signature
    methods.forEach(method => { methodSelectionView.add(method); });
    methodSelectionView.render();

    // Radio change event
    Array.from(document.querySelectorAll('input[type=radio][name=dbcode]')).forEach(input => {
        input.addEventListener('change', e => {
            const url = location.pathname + utils.encodeParams(
                utils.extendObj(
                    utils.parseLocation(location.search),
                    {db: e.target.value}
                ),
                true
            );
            history.replaceState(null, null, url);
            getDescriptions(proteinsModal);
        });
    });

    utils.setClass(document.querySelector('a[data-page="'+ match[2] +'"]'), 'active', true);
    document.title = 'UniProt descriptions ('+ methods.join(', ') +') | Pronto';
    getDescriptions(proteinsModal);
});