import {finaliseHeader} from "../../header.js";
import {paginate} from "../../ui.js";
import {selector} from "../../signatures.js";
import {dimmer} from "../../ui.js";

function getProteins() {
    const url = new URL(location.href);
    dimmer(true);
    const pathname = location.pathname.match(/(\/signatures\/.+\/)/)[1];
    fetch(URL_PREFIX+"/api" + pathname + location.search)
        .then(response => response.json())
        .then(response => {

            // Update radio for database (SwissProt/TrEMBL/Any)
            if (response.source_database)
                document.querySelector('input[name=dbcode][value='+ response.source_database +']').checked = true;
            else
                document.querySelector('input[name=dbcode][value=U]').checked = true;

            let html;

            // Set statistic counts
            html = '<div class="ui horizontal statistic">'
                + '<div class="value">'+ response.num_proteins.toLocaleString() +'</div>'
                + '<div class="label">proteins</div>'
                + '</div>';

            if (url.searchParams.get("md5") === null) {
                // Display the number of different structures
                html += '<div class="ui horizontal statistic">'
                + '<div class="value">'+ response.num_structures.toLocaleString() +'</div>'
                + '<div class="label">structures</div>'
                + '</div>';
            }

            document.querySelector('.ui.statistics').innerHTML = html;

            // Find longest protein
            const maxLength = Math.max(...response.proteins.map(p => { return p.length }));

            html = '';
            response.proteins.forEach(protein => {
                url.searchParams.set("md5", protein.md5);
                url.searchParams.delete("page");

                // Header of the protein
                html += '<div class="ui segment">'
                    + '<span class="ui red ribbon label">';

                if (protein.reviewed)
                    html += '<i class="star icon"></i>&nbsp;';

                html += protein.accession + '</span>'
                    + '<a target="_blank" href="'+ protein.link +'">'+ protein.name +'&nbsp;'
                    + '<i class="external icon"></i>'
                    + '</a>';

                // Wrap horizontal list in div otherwise it's inline with ribbon
                html += '<div>'
                    + '<div class="ui horizontal list">';

                if (protein.num_similar) {  // neither null or 0
                    html += '<div class="item">'
                        + '<div class="content">'
                        + '<div class="ui sub header">Similar proteins</div>'
                        + '<a href="' + url.toString() + '">' + protein.num_similar.toLocaleString() + '</a>'
                        + '</div>'
                        + '</div>';
                }

                html += '<div class="item">'
                    + '<div class="content">'
                    + '<div class="ui sub header">Organism</div>'
                    + '<em>'+ protein.taxon +'</em>'
                    + '</div>'
                    + '</div>'
                    + '</div>'
                    + '</div>';

                // Matches
                html += '<table class="ui very basic compact table"><tbody>';
                protein.signatures.forEach(signature => {
                    if (signature.active)
                        html += '<tr class="active">';
                    else
                        html += '<tr>';

                    if (signature.integrated) {
                        html += '<td class="nowrap">'
                            + '<a href="'+URL_PREFIX+'/entry/'+ signature.integrated +'/">'+ signature.integrated +'</a>'
                            + '</td>';
                    } else
                        html += '<td></td>';

                    html += '<td class="nowrap">'
                        + '<a href="'+URL_PREFIX+'/prediction/'+ signature.accession +'/">'+ signature.accession +'</a>'
                        + '</td>'
                        + '<td class="collapsing">'
                        + '<a href="#" data-add-id="'+ signature.accession +'">&nbsp;'
                        + '<i class="cart plus icon"></i>'
                        + '</a>'
                        + '</td>'
                        + '<td class="nowrap"><a target="_blank" href="'+ signature.link +'">'+ signature.name +'<i class="external icon"></i></a></td>';

                    // Matches
                    const svgWidth = 700;
                    const paddingLeft = 5;
                    const paddingRight = 30;
                    const width = Math.floor(protein.length * (svgWidth - (paddingLeft + paddingRight)) / maxLength);

                    html += '<td>' +
                        '<svg version="1.1" baseProfile="full" xmlns="http://www.w3.org/2000/svg" class="matches" width="'+ svgWidth +'" height="30">' +
                        '<line x1="'+ paddingLeft +'" y1="20" x2="'+ width +'" y2="20" stroke="#888" stroke-width="1px" />' +
                        '<text x="'+ (paddingLeft + width + 2) +'" y="20" class="length">'+ protein.length +'</text>';

                    signature.matches.forEach(fragments => {
                        fragments.forEach((frag, i) => {
                            const x = Math.round(frag.start * width / protein.length) + paddingLeft;
                            const w = Math.round((frag.end - frag.start) * width / protein.length);

                            html += '<g>';
                            if (i) {
                                // Discontinuous domain: draw arc
                                const px = Math.round(fragments[i-1].end * width / protein.length) + paddingLeft;
                                const x1 = (px + x) / 2;
                                html += '<path d="M'+px +' 15 Q '+ [x1, 0, x, 15].join(' ') +'" fill="none" stroke="'+ signature.color +'" />';
                            }

                            html += '<rect x="'+ x +'" y="15" width="'+ w +'" height="10" rx="1" ry="1" style="fill: '+ signature.color +';" />'
                                + '<text x="'+ x +'" y="10" class="position">'+ frag.start +'</text>'
                                + '<text x="'+ (x + w) +'" y="10" class="position">'+ frag.end +'</text>'
                                + '</g>';
                        });
                    });

                    html += '</svg></td></tr>';
                });

                html += '</tbody></table>';

                // Close segment
                html += "</div>";
            });

            document.querySelector('.segments').innerHTML = html;

            // Adding/removing signatures
            Array.from(document.querySelectorAll('tbody a[data-add-id]')).forEach(elem => {
                elem.addEventListener('click', e => {
                    e.preventDefault();
                    selector.add(elem.getAttribute('data-add-id'));
                });
            });

            paginate(
                document.querySelector('.ui.vertical.segment'),
                response.page_info.page,
                response.page_info.page_size,
                response.num_structures,
                (newURL, ) => {
                    history.replaceState(null, null, newURL);
                    getProteins();
                }
            );

            dimmer(false);
        })
}

$(function () {
    const url = new URL(location.href);
    const match = location.pathname.match(/\/signatures\/(.+)\/proteins\/$/i);
    const accessions = match[1].split("/");
    document.title = "Overlapping proteins (" + accessions.join(", ") + ") | Pronto";
    selector.init(document.getElementById('methods'));
    selector.tab("proteins");
    accessions.forEach(acc => selector.add(acc));

    // Radio events
    Array.from(document.querySelectorAll('input[type=radio]')).forEach(radio => {
        radio.addEventListener('change', e => {
            if (e.target.checked) {
                url.searchParams.delete("page");
                url.searchParams.set("db", e.target.value);
                history.replaceState(null, null, url.toString());
                getProteins();
            }
        });
    });

    finaliseHeader();
    getProteins();
});