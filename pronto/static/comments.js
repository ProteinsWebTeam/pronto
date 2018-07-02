import * as utils from './utils.js';


function getComments(proteinsModal) {
    const url = '/api' + location.pathname + location.search;
    utils.dimmer(true);
    utils.getJSON(url, (obj, status) => {
        // Find the highest protein count
        const maxProt = Math.max(...obj.data.map(comment => {
            return Math.max(...comment.methods.map(method => { return method.count }));
        }));

        // Table header
        let html = '<thead><tr><th>'+ obj.data.length +' comments</th>';
        if (obj.data.length) {
            obj.data[0].methods.forEach(method => {
                html += '<th>' + method.accession + '</th>';
            });
        }
        html += '</tr></thead>';

        // Table body
        const colors = utils.gradientPuBu;
        html += '</thead><tbody>';
        obj.data.forEach(comment => {
            html += '<tr data-filter="'+ comment.value +'" data-search="comment=' + comment.id + '&topic='+ obj.meta.topic.id +'">' +
                '<td>'+ comment.value +'</td>';

            comment.methods.forEach(method => {
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

        proteinsModal.observe(table.querySelectorAll('td a[data-method]'), (method, filter, search) => {
            const header = '<em>' + method + '</em> proteins<div class="sub header">Comment: <em>'+ filter +'</em></div>';
            proteinsModal.open(method, search, header);
        });

        // Update select options
        Array.from(document.querySelectorAll('#topics option')).forEach(option => {
            option.selected = parseInt(option.value, 10) === obj.meta.topic.id;
        });

        // Select change event
        $('#topics').dropdown({
            onChange: function(value, text, $selectedItem) {
                const url = location.pathname + utils.encodeParams(
                    utils.extendObj(
                        utils.parseLocation(location.search),
                        {topic: value}
                    ),
                    true
                );
                history.replaceState(null, null, url);
                getComments(proteinsModal);
            }
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

    utils.setClass(document.querySelector('a[data-page="'+ match[2] +'"]'), 'active', true);
    document.title = 'Swiss-Prot comments ('+ methods.join(', ') +') | Pronto';
    getComments(proteinsModal);
});