import * as utils from '../utils.js';


function getGoTerms(proteinsModal) {
    const url = '/api' + location.pathname + location.search;
    utils.dimmer(true);
    utils.getJSON(url, (obj, status) => {
        // Find the highest protein count
        const maxProt = Math.max(...obj.data.map(comment => {
            return Math.max(...comment.methods.map(method => { return method.count }));
        }));

        // Table header
        let html = '<thead><tr><th>'+ obj.data.length +' terms</th>';
        if (obj.data.length) {
            html += '<th class="center aligned"><button class="ui fluid very compact blue icon button"><i class="sitemap icon"></i></button></th>';
            obj.data[0].methods.forEach(method => {
                html += '<th colspan="2" class="center aligned">' + method.accession + '</th>';
            });
        }
        html += '</tr></thead>';

        // Table body
        const colors = utils.gradientPuBu;
        html += '</thead><tbody>';
        obj.data.forEach(term => {
            html += '<tr data-filter="'+ term.id +'" data-search="term=' + term.id + '">' +
                '<td class="nowrap">' +
                '<span class="ui circular small label aspect-'+ term.aspect +'">'+ term.aspect +'</span>' +
                '<a target="_blank" href="https://www.ebi.ac.uk/QuickGO/term/'+ term.id +'">'+ term.id + ':&nbsp;' + term.value +'&nbsp;<i class="external icon"></i></a>' +
                '</td><td class="collapsing center aligned">'+ utils.renderCheckbox(term.id, false) +'</td>';

            term.methods.forEach(method => {
                if (method.count) {
                    const i = Math.floor(method.count / maxProt * colors.length);
                    const color = colors[Math.min(i, colors.length - 1)];
                    const className = utils.useWhiteText(color) ? 'light' : 'dark';
                    html += '<td class="'+ className +'" style="background-color: '+ color +';"><a href="#" data-method="'+ method.accession +'">' + method.count.toLocaleString() + '</a></td>';

                    if (method.references)
                        html += '<td class="collapsing"><a data-term="'+ term.id +'" data-method-ref="'+ method.accession +'" class="ui basic label"><i class="book icon"></i>&nbsp;'+ method.references.toLocaleString() +'</a></td>';
                    else
                        html += '<td class="collapsing"></td>';

                } else
                    html += '<td colspan="2"></td>';
            });

            html += '</tr>';
        });

        const table = document.querySelector('table');
        table.innerHTML = html + '</tbody>';

        proteinsModal.observe(table.querySelectorAll('td a[data-method]'), (method, filter, search) => {
            const header = '<em>' + method + '</em> proteins<div class="sub header">GO term: <em>'+ filter +'</em></div>';
            proteinsModal.open(method, search, header);
        });

        // Update checkboxes
        Array.from(document.querySelectorAll('input[type=checkbox][name=aspect]')).forEach(input => {
            input.checked = obj.meta.aspects.indexOf(input.value) !== -1;
        });

        // Display GO references
        Array.from(table.querySelectorAll('a[data-term][data-method-ref]')).forEach(element => {
            element.addEventListener('click', e => {
                e.preventDefault();
                const term = e.target.getAttribute('data-term');
                const method = e.target.getAttribute('data-method-ref');
                utils.dimmer(true);
                utils.getJSON('/api/method/' + method + '/references/' + term + '/', (data, status) => {
                    const modal = document.getElementById('go-references-modal');
                    let html = '';

                    if (data.count) {
                        data.results.forEach(ref => {
                            html += '<li class="item">' +
                                '<div class="header"><a target="_blank" href="http://europepmc.org/abstract/MED/'+ ref.id +'">'+ ref.id +'&nbsp;<i class="external icon"></i></a></div><div class="description">'+ utils.nvl(ref.title, '') + ' ' + utils.nvl(ref.date, '') +'</div></li>';
                        });
                    } else {
                        html = '<div class="ui negative message"><div class="header">No references found</div><p>This entry does not have any references in the literature.</p></div>';
                    }

                    modal.querySelector('.ui.header').innerHTML = '<i class="book icon"></i>' + term + ' / ' + method;
                    modal.querySelector('.content ol').innerHTML = html;
                    modal.querySelector('.actions a').setAttribute('href', 'https://www.ebi.ac.uk/QuickGO/term/' + term);
                    utils.dimmer(false);
                    $(modal).modal('show');
                });
            });
        });

        // Display GO chart
        table.querySelector('thead button').addEventListener('click', e => {
            const terms = [];
            Array.from(table.querySelectorAll('input[type=checkbox]:checked')).forEach(input => {
                terms.push(input.name);
            });

            if (terms.length) {
                const modal = document.getElementById('go-chart-modal');
                modal.querySelector('.content').innerHTML = '<img class="image" alt="'+ terms.join(',') +'" src="https://www.ebi.ac.uk/QuickGO/services/ontology/go/terms/' + terms.join(',') + '/chart">';
                setTimeout(function () {
                    $(modal).modal('show');
                }, 500);
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

    // Checkbox change event
    Array.from(document.querySelectorAll('input[type=checkbox][name=aspect]')).forEach((input, i, array) => {
        input.addEventListener('change', e => {
            const aspects = [];
            array.forEach(cbox => {
                if (cbox.checked)
                    aspects.push(cbox.value);
            });

            const url = location.pathname + utils.encodeParams(
                utils.extendObj(
                    utils.parseLocation(location.search),
                    {aspect: aspects.length ? aspects.join(',') : false}
                )
            );
            history.replaceState(null, null, url);
            getGoTerms(proteinsModal);
        });
    });

    utils.setClass(document.querySelector('a[data-page="'+ match[2] +'"]'), 'active', true);
    document.title = 'GO terms ('+ methods.join(', ') +') | Pronto';
    getGoTerms(proteinsModal);
});