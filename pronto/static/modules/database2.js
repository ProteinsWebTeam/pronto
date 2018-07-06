import * as utils from '../utils.js';


function getMethods() {
    const url = location.pathname + location.search;

    utils.dimmer(true);
    utils.getJSON('/api' + url, (data, status) => {
        utils.dimmer(false);

        if (!data.database) {
            // TODO: show error
            return;
        }

        const title = data.database.name + ' (' + data.database.version + ') unintegrated signatures';
        document.querySelector('h1.ui.header').innerHTML = title;
        document.title = title + ' | Pronto';

        let html = '';
        if (data.results.length) {
            data.results.forEach(m => {
                html += '<tr data-id="'+ m.id +'">' +
                    '<td><a href="/method/'+ m.id +'">'+ m.id +'</a></td>' +
                    '<td class="nowrap"><div class="ui list">';

                m.addTo.forEach(pred => {
                    html += '<div class="item">';

                    if (pred.type !== null)
                        html += '<div class="content"><span class="ui circular mini label type-'+ pred.type +'">'+ pred.type +'</span><a href="/entry/'+ pred.id +'">'+ pred.id +'</a></div></div>';
                    else
                        html += '<div class="content"><span class="ui circular mini label">&nbsp;</span><a href="/method/'+ pred.id +'">'+ pred.id +'</a></div></div>';
                });

                html += '</div></td>' +
                    '<td>'+ m.parents.join(', ') +'</td>' +
                    '<td>'+ m.children.join(', ') +'</td></tr>';
            });
        } else
            html = '<tr><td class="center aligned" colspan="4">No matching entries found</td></tr>';

        document.querySelector('tbody').innerHTML = html;

        utils.paginate(
            document.querySelector('table'),
            data.pageInfo.page,
            data.pageInfo.pageSize,
            data.count,
            null,
            (url, ) => {
                history.replaceState(null, null, url);
                getMethods();
            }
        );
    });
}


$(function () {
    getMethods();

    const params = utils.parseLocation(location.search);
    utils.initInput(document.querySelector('table input'), params.search, value => {
        const pathName = location.pathname;
        const newParams = utils.extendObj(
            utils.parseLocation(location.search),
            {search: value, page: 1}
        );

        history.pushState(null, null, pathName + utils.encodeParams(newParams));
        getMethods();
    });

    Array.from(document.querySelectorAll('input[type=radio]')).forEach(radio => {
        radio.addEventListener('change', e => {
            const obj = {};
            obj[radio.name] = radio.value;
            const pathName = location.pathname;
            const params = utils.extendObj(
                utils.parseLocation(location.search),
                obj
            );
            history.replaceState(null, null, pathName + utils.encodeParams(params));
            getMethods();
        });
    });

    for (let k in params) {
        if (params.hasOwnProperty(k)) {
            let radio = document.querySelector('input[type=radio][name='+k+'][value="'+params[k]+'"]');
            if (radio) radio.checked = true;
        }
    }
});