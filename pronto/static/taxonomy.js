import * as utils from './utils.js';

function getTaxa(proteinsModal) {
    const url = '/api' + location.pathname + location.search;
    utils.dimmer(true);
    utils.getJSON(url, (obj, status) => {

        // Update taxonomic rank tab
        const tab = document.querySelector('a[data-rank].active');
        if (tab) utils.setClass(tab, 'active', false);
        utils.setClass(document.querySelector('a[data-rank="'+ obj.rank +'"]'), 'active', true);

        // Find the highest protein count
        const maxProt = Math.max(...obj.data.map(taxon => {
            return Math.max(...taxon.methods.map(method => { return method.count }));
        }));

        let html = '';
        const filteredByTaxon = obj.taxon.id !== 1;

        // Table header
        if (filteredByTaxon)
            // Override Semantic UI's pointer-events: none
            html += '<thead><tr><th style="pointer-events: auto;"><a class="ui basic label">' + obj.taxon.fullName + '<i class="delete icon"></i></a></th>';
        else
            html += '<thead><tr><th>'+ obj.taxon.fullName +'</th>';

        if (obj.data.length) {
            obj.data[0].methods.forEach(method => {
                html += '<th><a href="" data-method="'+ method.accession +'">' + method.accession + '</a></th>';
            });
        } else
            html += '<th>No results found</th>';
        html += '</tr></thead>';

        obj.data[0].methods.forEach(method => {
            html += '<th>' + method.accession + '</th>';
        });
        html += '</thead>';

        // Table body
        const colors = utils.gradientPuBu;
        html += '<tbody>';
        obj.data.forEach(taxon => {
            if (taxon.id)
                html += '<tr data-filter="'+ taxon.fullName +'" data-search="taxon='+ taxon.id +'"><td><a href="/methods/'+ taxon.methods.map(method => { return method.accession; }).join('/') +'/taxonomy?rank=' + obj.rank + '&taxon='+ taxon.id + '">'+ taxon.fullName +'</a></td>';
            else
                html += '<tr data-filter="'+ taxon.fullName +'" data-search="notaxon&rank='+ obj.rank +'"><td>'+ taxon.fullName +'</td>';

            taxon.methods.forEach(method => {
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

        if (filteredByTaxon) {
            table.querySelector('table a.label i.delete').addEventListener('click', e => {
                const url = location.pathname + utils.encodeParams(
                    utils.extendObj(
                        utils.parseLocation(location.search),
                        {taxon: false}
                    ),
                    true
                );
                history.replaceState(null, null, url);
                getTaxa(proteinsModal);
            });
        }

        proteinsModal.observe(table.querySelectorAll('td a[data-method]'), (method, filter, search) => {
            const header = '<em>' + method + '</em> proteins<div class="sub header">Organism: <em>'+ filter +'</em></div>';
            proteinsModal.open(method, search, header);
        });

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

    // Tab change event
    const items = Array.from(document.querySelectorAll('.tabular.menu .item[data-rank]'));
    items.forEach(item => {
        item.addEventListener('click', e => {
            const url = location.pathname + utils.encodeParams(
                utils.extendObj(
                    utils.parseLocation(location.search),
                    {rank: item.getAttribute('data-rank')}
                ),
                true
            );
            history.replaceState(null, null, url);
            getTaxa(proteinsModal);
        });
    });

    // Toggle change event
    const input = document.querySelector('input[name=notaxon]');
    input.addEventListener('change', e => {
        const url = location.pathname + utils.encodeParams(
            utils.extendObj(
                utils.parseLocation(location.search),
                {notaxon: e.target.checked ? null : false}
            ),
            true
        );
        history.replaceState(null, null, url);
        getTaxa(proteinsModal);
    });

    // Set check status based on URL
    input.checked = (utils.parseLocation(location.search).notaxon !== undefined);

    utils.setClass(document.querySelector('a[data-page="'+ match[2] +'"]'), 'active', true);
    document.title = 'Taxonomic origins ('+ methods.join(', ') +') | Pronto';
    getTaxa(proteinsModal);
});