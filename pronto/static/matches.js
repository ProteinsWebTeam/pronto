import * as utils from './utils.js';

const svgWidth = 700;

function getMatches(methodSelectionView) {
    const url = '/api' + location.pathname + location.search;
    const params = utils.parseLocation(location.search);
    utils.dimmer(true);
    utils.getJSON(url, (obj, status) => {

        // Check radio
        document.querySelector('input[name=dbcode][value='+ obj.database +']').checked = true;

        // Update number of groups/proteins
        document.querySelector('.statistic .value').innerHTML = obj.count.toLocaleString();

        const maxLength = Math.max(...obj.data.map(protein => { return protein.length }));

        let html = '';
        obj.data.forEach(protein => {
            // URL for uncondensed view
            const url = location.pathname + utils.encodeParams(utils.extendObj(params, {code: protein.code, page: null, pageSize: null}), false);

            html += '<div class="ui segment">' +
                '<span class="ui red ribbon label">' + (protein.isReviewed ? '<i class="star icon"></i>&nbsp;' : '') + protein.id + '</a></span>' +
                '<a target="_blank" href="'+ protein.link +'">'+ protein.description +'&nbsp;<i class="external icon"></i></a>' +
                '<div><div class="ui horizontal list">' +
                '<div class="item">' +
                '<div class="content">' +
                '<div class="ui sub header">Proteins</div><a href="'+ url +'" ">'+ protein.count.toLocaleString() +'</a>' +
                '</div>' +
                '</div>' +
                '<div class="item">' +
                '<div class="content">' +
                '<div class="ui sub header">Organism</div><em>'+ protein.organism +'</em>' +
                '</div>' +
                '</div>' +
                '</div></div>';

            html += '<table class="ui very basic compact table"><tbody>';

            protein.methods.forEach((method, j) => {
                html += method.isSelected ? '<tr class="selected">' : '<tr>';

                if (method.entryId)
                    html += '<td class="nowrap"><a href="/entry/'+ method.entryId +'">'+ method.entryId +'</a></td>';
                else
                    html += '<td></td>';

                if (method.link)
                    html += '<td class="nowrap"><a target="_blank" href="'+ method.link +'">'+ method.id + '&nbsp;<i class="external icon"></i></a></td>';
                else
                    html += '<td>'+ method.id + '</td>';

                html += '<td class="collapsing"><a href="#" data-add-id="'+ method.id +'"><i class="cart plus icon"></i></a></td>';

                html += '<td>'+ (method.name !== null ? method.name : '') + '</td>' +
                    '<td>'+ (method.isCandidate ? '&nbsp;<i class="checkmark box icon"></i>' : '') +'</td>';

                const paddingLeft = 5;
                const paddingRight = 30;
                const width = Math.floor(protein.length * (svgWidth - (paddingLeft + paddingRight)) / maxLength);

                html += '<td><svg class="matches" width="' + svgWidth + '" height="30" version="1.1" baseProfile="full" xmlns="http://www.w3.org/2000/svg">' +
                    '<line x1="'+ paddingLeft +'" y1="20" x2="'+width+'" y2="20" stroke="#888" stroke-width="1px" />' +
                    '<text x="'+ (paddingLeft + width + 2) +'" y="20" class="length">'+ protein.length +'</text>';

                method.matches.forEach(match => {
                    const x = Math.round(match.start * width / protein.length) + paddingLeft;
                    const w = Math.round((match.end - match.start) * width / protein.length);
                    html += '<g><rect x="'+ x +'" y="15" width="'+ w +'" height="10" rx="1" ry="1" style="fill: '+ (method.color !== null ? method.color : '#bbb') +';"/>' +
                        '<text x="'+ x +'" y="10" class="position">'+ match.start +'</text>' +
                        '<text x="'+ (x + w) +'" y="10" class="position">'+ match.end +'</text></g>'
                });

                html += '</svg></td></tr>';
            });

            html += '</tbody></table></div>';
        });

        document.querySelector('.segments').innerHTML = html;

        // Pagination
        utils.paginate(
            document.querySelector('.ui.vertical.segment'),
            obj.page,
            obj.pageSize,
            obj.count,
            (url, ) => {
                history.replaceState(null, null, url);
                getMatches(methodSelectionView);
            }
        );

                // Adding/removing signatures
        Array.from(document.querySelectorAll('tbody a[data-add-id]')).forEach(elem => {
            elem.addEventListener('click', e => {
                e.preventDefault();
                methodSelectionView.add(elem.getAttribute('data-add-id')).render();
            });
        });

        utils.dimmer(false);
    });
}


$(function () {
    utils.setClass(document.querySelector('a[data-page="matches"]'), 'active', true);

    const pathName = location.pathname;

    const match = pathName.match(/^\/methods\/(.+)\/matches\/$/);
    if (!match) {
        return;
    }

    const methods = match[1].trim().split('/');

    const methodSelectionView = new utils.MethodsSelectionView(document.getElementById('methods'));

    getMatches(methodSelectionView);

    // Radio events
    Array.from(document.querySelectorAll('input[type=radio]')).forEach(radio => {
        radio.addEventListener('change', e => {
            if (e.target.checked) {
                const params = utils.parseLocation(location.search);
                const url = location.pathname + utils.encodeParams(utils.extendObj(params, {db: e.target.value}), false);
                history.replaceState(null, null, url);
                getMatches();
            }
        });
    });

    // Add current signature
    methods.forEach(method => { methodSelectionView.add(method); });
    methodSelectionView.render();
});