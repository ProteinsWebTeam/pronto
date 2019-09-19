import {finaliseHeader} from "../../header.js";
import * as ui from "../../ui.js";

function getSignatures() {
    ui.dimmer(true);
    fetch('/api/signatures/' + location.search)
        .then(response => response.json())
        .then(response => {
            ui.dimmer(false);

            let html = '';

            response.results.forEach(s => {
                const rowspan = s.predictions.length;
                html += '<tr>'
                    + '<td rowspan="'+rowspan+'">'
                    + '<a href="/prediction/'+s.accession+'/" class="ui label" style="background-color: '+s.color+'!important;color: #fff;">'+ s.accession +'</a>'
                    + '</td>'
                    + '<td rowspan="'+rowspan+'" class="collapsing"><a target="_blank" href="'+s.link+'"><i class="fitted external icon"></i></a></td>'
                    + '<td rowspan="'+rowspan+'" class="collapsing">'+ s.proteins.toLocaleString() +'</td>';

                s.predictions.forEach((p, i) => {
                    if (i) html += '<tr>';

                    html += '<td>'
                        + '<a href="/prediction/'+ p.accession +'/">'+p.accession+'</a>'
                        + (p.residues ? '&nbsp;<i class="yellow fitted star icon"></i>' : '')
                        + '</td>'
                        + '<td class="collapsing">'+ p.proteins.toLocaleString() +'</td>'
                        + '<td><span class="ui circular mini label type-'+p.entry.type+'">'+p.entry.type+'</span><a href="/entry/'+ p.entry.accession +'/">'+ p.entry.accession + '&nbsp;('+ p.entry.name +')</a></td>'
                        + '<td class="collapsing">'+ p.collocations.toLocaleString() +'</td>'
                        + '<td class="collapsing">'+ p.overlaps.toLocaleString() +'</td>'
                        + '</tr>';
                });
            });

            const table = document.getElementById('table-signatures');
            table.querySelector('tbody').innerHTML = html;

            ui.paginate(
                table,
                response.page_info.page,
                response.page_info.page_size,
                response.count,
                (url,) => {
                    history.replaceState(null, null, url);
                    getSignatures();
                });
        })
        .catch(error => {
            if (error.message === '404') {
                document.querySelector('.ui.container.segment').innerHTML = '<div class="ui error message">'
                    + '<div class="header">Signature not found</div>'
                    + '<p><strong>'+ accession +'</strong> is not a valid member database signature accession.</p>'
                    + '</div>';
            } else {
                document.querySelector('.ui.container.segment').innerHTML = '<div class="ui error message">'
                    + '<div class="header">'+ error.name +'</div>'
                    + '<p>'+ error.message +'</p>'
                    + '</div>';
            }
        });
}


$(function () {
    finaliseHeader(null);
    getSignatures();
    const url = new URL(location.href);
    ui.initSearchBox(
        document.querySelector("thead input"),
        url.searchParams.get("search"),
        (value, ) => {
            url.searchParams.delete("page");
            if (value !== null)
                url.searchParams.set("search", value);
            else
                url.searchParams.delete("search");

            history.replaceState(null, null, url.toString());
            getSignatures();
        }
    );
    document.querySelector('input[type=checkbox][name=resevi]').addEventListener('change', e => {
        if (e.target.checked)
            url.searchParams.set(e.target.name, '');
        else
            url.searchParams.delete(e.target.name);

        history.replaceState(null, null, url.toString());
        getSignatures();
    });
});