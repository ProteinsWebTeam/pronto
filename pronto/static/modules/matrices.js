import * as utils from '../utils.js';


function getMatrices() {
    const url = '/api' + location.pathname + location.search;
    utils.dimmer(true);
    utils.getJSON(url, (obj, status) => {
        // Find the highest protein count
        const maxProt = Math.max(...obj.data.map(method => { return method.count; }));

        // Table header
        let html1 = '<thead><tr><th></th>';
        let html2 = '<thead><tr><th></th>';
        obj.data.forEach(method => {
            html1 += '<th>' + method.accession + '</th>';
            html2 += '<th>' + method.accession + '</th>';
        });
        html1 += '</thead>';
        html2 += '</thead>';

        // Table body
        const colors = utils.gradientPuBu;
        html1 += '<tbody>';
        html2 += '<tbody>';
        obj.data.forEach((method, i, array) => {
            html1 += '<tr><td>' + method.accession + '</td>';
            html2 += '<tr><td>' + method.accession + '</td>';

            method.data.forEach((counts, j, _array) => {
                let x, color, className;

                // Overlap matrix
                x = Math.floor(counts.over / maxProt * colors.length);
                color = colors[Math.min(x, colors.length - 1)];
                className = utils.useWhiteText(color) ? 'light' : 'dark';

                if (counts.over && method.accession !== array[j].accession)
                    html1 += '<td class="'+ className +'" style="background-color: '+ color +'"><a data-i="'+ i +'" data-j="'+ j +'" href="#">' + counts.over + '</a></td>';
                else
                    html1 += '<td class="'+ className +'" style="background-color: '+ color +'">' + counts.over + '</td>';

                // Collocation matrix
                x = Math.floor(counts.coloc / maxProt * colors.length);
                color = colors[Math.min(x, colors.length - 1)];
                className = utils.useWhiteText(color) ? 'light' : 'dark';

                if (counts.coloc && method.accession !== array[j].accession)
                    html2 += '<td class="'+ className +'" style="background-color: '+ color +'"><a data-i="'+ i +'" data-j="'+ j +'" href="#">' + counts.coloc + '</a></td>';
                else
                    html2 += '<td class="'+ className +'" style="background-color: '+ color +'">' + counts.coloc + '</td>';
            });

            html1 += '</tr>';
            html2 += '</tr>';
        });

        document.getElementById('overlap').innerHTML = html1;
        document.getElementById('collocation').innerHTML = html2;

        const details = document.getElementById('details');
        details.innerHTML = null;

        Array.from(document.querySelectorAll('tbody a[data-i][data-j]')).forEach(elem => {
            elem.addEventListener('click', e => {
                e.preventDefault();
                const i = parseInt(e.target.getAttribute('data-i'), 10);
                const j = parseInt(e.target.getAttribute('data-j'), 10);

                let html = '<h4 class="ui header">Proteins</h4><table class="ui very basic small compact table"><tbody>';
                html += '<tr><td>Overlapping</td><td class="right aligned">'+ obj.data[i].data[j].over +'</td></tr>';
                html += '<tr><td>Average overlap</td><td class="right aligned">'+ Math.floor(obj.data[i].data[j].avgOver) +'</td></tr>';
                html += '<tr><td>In both signatures</td><td class="right aligned"><a target="_blank" href="/methods/'+ obj.data[i].accession + '/' + obj.data[j].accession +'/matches/?force='+ obj.data[i].accession + ',' + obj.data[j].accession +'">'+ obj.data[i].data[j].coloc +'</a></td></tr>';
                html += '<tr><td>In either signatures</td><td class="right aligned"><a target="_blank" href="/methods/'+ obj.data[i].accession + '/' + obj.data[j].accession +'/matches/">'+ (obj.data[i].data[i].coloc + obj.data[j].data[j].coloc - obj.data[i].data[j].coloc) +'</a></td></tr>';
                html += '<tr><td>In '+ obj.data[i].accession +' only</td><td class="right aligned"><a target="_blank" href="/methods/'+ obj.data[i].accession + '/matches/?exclude='+ obj.data[j].accession +'">'+ (obj.data[i].data[i].coloc - (obj.data[i].data[j] !== null ? obj.data[i].data[j].coloc : 0)) +'</a></td></tr>';
                html += '<tr><td>In '+ obj.data[j].accession +' only</td><td class="right aligned"><a target="_blank" href="/methods/'+ obj.data[j].accession + '/matches/?exclude='+ obj.data[i].accession +'">'+ (obj.data[j].data[j].coloc - (obj.data[i].data[j] !== null ? obj.data[i].data[j].coloc : 0)) +'</a></td></tr>';
                html += '<tr><td>In '+ obj.data[i].accession +'</td><td class="right aligned"><a target="_blank" href="/methods/'+ obj.data[i].accession + '/matches/">'+ obj.data[i].data[i].coloc +'</a></td></tr>';
                html += '<tr><td>In '+ obj.data[j].accession +'</td><td class="right aligned"><a target="_blank" href="/methods/'+ obj.data[j].accession + '/matches/">'+ obj.data[j].data[j].coloc +'</a></td></tr>';

                details.innerHTML = html + '</tbody></table>';
                console.log(details);
            });
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

    // Add current signature
    methods.forEach(method => { methodSelectionView.add(method); });
    methodSelectionView.render();

    utils.setClass(document.querySelector('a[data-page="'+ match[2] +'"]'), 'active', true);
    document.title = 'Match matrices ('+ methods.join(', ') +') | Pronto';
    getMatrices();
});