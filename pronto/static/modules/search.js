import * as utils from '../utils.js';

function renderHits(query, results) {
    const table = document.querySelector('table');
    let html = '';

    if (results.count) {
        results.hits.forEach(entry => {
            html += '<tr>' +
                '<td><span class="ui tiny type-'+ entry.type +' circular label">'+ entry.type +'</span>&nbsp;<a href="/entry/'+ entry.id +'/">'+ entry.id +'</a></td>' +
                '<td>'+ entry.name +'</td>' +
                '</tr>';
        });
    } else {
        html += '<tr><td colspan="2">No hits found by EBI Search</td></tr>';
    }

    table.querySelector('tbody').innerHTML = html;

    utils.paginate(
        table,
        results.page,
        results.pageSize,
        results.count,
        '/api/search/' + utils.encodeParams({q: query, nodb: null}, true),
        (url => {
            utils.dimmer(true);
            utils.getJSON(url, (results, status) => {
                renderHits(query, results.ebisearch);
                utils.dimmer(false);
            });
        })
    );
}

$(function () {
    renderHits(query, ebisearch);
});