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

                    html += '<td class="nowrap">'
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


function getDatabases(dbcode) {
    fetch('/api/databases/')
        .then(response => response.json())
        .then(databases => {
            /*
                `.equal.width.fields` class only works with `field` (not `fields`)
                so we wrap our `.grouped.fields` in a `.field`
             */
            let html = '<div class="field">'
                + '<div class="grouped fields">'
                + '<label for="database">Select your database:</label>'
                + '<div class="field">'
                + '<div class="ui radio checkbox">'
                + '<input type="radio" name="database" value="" class="hidden" '+ (dbcode === null ? 'checked="checked"': '') +'>'
                + '<label>All</label>'
                + '</div>'
                + '</div>';

            let i = 1;
            databases.filter(db => db.short_name !== 'mobidblt').sort((a, b) => a.name.localeCompare(b.name)).forEach(db => {
                html += '<div class="field">'
                    + '<div class="ui radio checkbox">'
                    + '<input type="radio" name="database" value="'+ db.code +'" class="hidden"'+ (dbcode === db.code ? 'checked="checked"': '') +'>'
                    + '<label><span style="border-bottom: 3px solid '+db.color+';">'+ db.name +'</span></label>'
                    + '</div>'
                    + '</div>';
                i++;
                if (i === 5) {
                    /*
                        Close `.field .grouped.fields` and open a new one
                        (note the empty label to have all groups aligned)
                     */
                    html += '</div>'
                        + '</div>'
                        + '<div class="field">'
                        + '<div class="grouped fields">'
                        + '<label for="database">&nbsp;</label>';
                    i = 0;
                }
            });

            html += '</div></div>';

            document.querySelector('#form-signatures .fields').innerHTML = html;
            $('.ui.radio.checkbox').checkbox({
                onChecked: function () {
                    const val = this.value.trim();
                    const url = new URL(location.href);
                    if (val)
                        url.searchParams.set(this.name, val);
                    else
                        url.searchParams.delete(this.name);
                    history.replaceState(null, null, url.toString());
                    getSignatures();
                }
            });
        });
}


$(function () {
    finaliseHeader(null);
    getSignatures();
    const url = new URL(location.href);
    getDatabases(url.searchParams.get('database'));
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