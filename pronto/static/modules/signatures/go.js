import {finaliseHeader} from "../../header.js";
import {dimmer, renderCheckbox, toRGB, useWhiteText} from '../../ui.js';
import {gradientPuBu, proteinViewer, selector} from "../../signatures.js";

function getGoTerms(accessions) {
    dimmer(true);
    const pathname = location.pathname.match(/(\/signatures\/.+\/)/)[1];
    fetch(URL_PREFIX+"/api" + pathname + location.search)
        .then(response => response.json())
        .then(result => {
            // Find the highest protein count
            const maxProt = Math.max(...result.terms.map(t => Math.max(...Object.values(t.signatures).map(s => s.num_proteins))));

            // Table header
            let html = '<thead>'
                + '<tr>'
                + '<th>'+ result.terms.length.toLocaleString() +' terms</th>'
                + '<th class="center aligned">'
                + '<button class="ui fluid very compact blue icon button">'
                + '<i class="sitemap icon"></i>'
                + '</button>'
                + '</th>';

            accessions.map(acc => {
                html += '<th colspan="2" class="center aligned">' + acc + '</th>';
            });
            html += '</tr></thead>';

            // Table body
            html += '<tbody>';
            result.terms.forEach(t => {
                html += '<tr data-type="GO term" data-filter="'+ t.name +'" data-params="go='+ t.id +'">'
                    + '<td>'
                    + '<span class="ui circular small label aspect-'+ t.aspect +'">'+ t.aspect +'</span>'
                    + '<a target="_blank" href="//www.ebi.ac.uk/QuickGO/term/'+ t.id +'">'
                    + t.id + ':&nbsp;'+ t.name +'&nbsp;'
                    + '<i class="external icon"></i>'
                    + '</a>'
                    + '</td>'
                    + '<td class="collapsing center aligned">'+ renderCheckbox(t.id, false) +'</td>';

                accessions.forEach(acc => {
                    if (t.signatures.hasOwnProperty(acc)) {
                        const numProt = t.signatures[acc].num_proteins;
                        const numRefs = t.signatures[acc].num_references;
                        const i = Math.floor(numProt / (maxProt + 1) * gradientPuBu.length);
                        const color = gradientPuBu[i];
                        const className = useWhiteText(color) ? 'light' : 'dark';
                        html += '<td class="'+ className +'" style="background-color: '+ toRGB(color) +';">'
                            + '<a href="#" data-accession="'+ acc +'">' + numProt.toLocaleString() + '</a>'
                            + '</td>';

                        if (numRefs) {
                            html += '<td class="collapsing">'
                                + '<a data-ref-id="'+ t.id +'" data-ref-ac="'+ acc +'" class="ui basic label">'
                                + '<i class="book icon"></i>&nbsp;'+ numRefs.toLocaleString()
                                + '</a>'
                                + '</td>';
                        } else
                            html += '<td></td>';
                    } else
                        html += '<td></td><td></td>';
                });

                html += '</tr>';
            });

            const table = document.querySelector('table');
            table.innerHTML = html + '</tbody>';

            // Update checkboxes
            Array.from(document.querySelectorAll('input[type=checkbox][name=aspect]')).forEach(input => {
                input.checked = result.aspects.includes(input.value);
            });

            // Display GO references
            Array.from(table.querySelectorAll('a[data-ref-id]')).forEach(elem => {
                elem.addEventListener('click', e => {
                    e.preventDefault();
                    const goID = e.target.getAttribute('data-ref-id');
                    const accession = e.target.getAttribute('data-ref-ac');
                    dimmer(true);
                    fetch(URL_PREFIX+'/api/signature/' + accession + '/references/' + goID +'/')
                        .then(response => response.json())
                        .then(references => {


                            let html = '';
                            references.forEach(ref => {
                                html += '<li class="item">'
                                    + '<div class="header">'
                                    + '<a target="_blank" href="//europepmc.org/abstract/MED/'+ ref.id +'">PMID:'+ ref.id +'&nbsp;'
                                    + '<i class="external icon"></i>'
                                    + '</a>'
                                    + '</div>'
                                    + '<div class="description">'+ ref.title +'&nbsp;'+ ref.date +'</div>'
                                    + '</li>';
                            });

                            const modal = document.getElementById('go-references-modal');
                            modal.querySelector('.ui.header').innerHTML = 'PubMed references for ' + goID + ' and ' + accession;
                            modal.querySelector('.content ol').innerHTML = html;
                            modal.querySelector('.actions a').setAttribute('href', 'https://www.ebi.ac.uk/QuickGO/term/' + goID);
                            $(modal).modal('show');
                            dimmer(false);
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
                    const url = 'https://www.ebi.ac.uk/QuickGO/services/ontology/go/terms/' + terms.join(',') + '/chart';
                    const modal = document.getElementById('go-chart-modal');
                    modal.querySelector('.content').innerHTML = '<img class="image" alt="'+ terms.join(',') +'" src="'+ url +'">';
                    setTimeout(function () {
                        $(modal).modal('show');
                    }, 500);
                }
            });

            proteinViewer.observe(table.querySelectorAll('td a[data-accession]'));
            dimmer(false);
        });
}

$(function () {
    const match = location.pathname.match(/\/signatures\/(.+)\/go\/$/i);
    const accessions = match[1].split("/");
    document.title = "GO terms (" + accessions.join(", ") + ") | Pronto";
    selector.init(document.getElementById('methods'));
    selector.tab("go");
    accessions.forEach(acc => selector.add(acc));

    // Checkbox change event
    Array.from(document.querySelectorAll('input[type=checkbox][name=aspect]')).forEach((input, i, array) => {
        input.addEventListener('change', e => {
            const aspects = [];
            array.forEach(cbox => {
                if (cbox.checked)
                    aspects.push(cbox.value);
            });

            const url = new URL(location.href);
            if (aspects.length)
                url.searchParams.set('aspects', aspects.join(','));
            else
                url.searchParams.delete('aspects');

            history.replaceState(null, null, url.toString());
            getGoTerms(accessions);
        });
    });

    finaliseHeader();
    getGoTerms(accessions);
});