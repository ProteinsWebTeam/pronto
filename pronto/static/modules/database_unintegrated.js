import {finaliseHeader} from "../header.js";
import * as ui from "../ui.js";

function getFilter() {
    return new URL(location.href).pathname.match(/^.*\/([^/]+)\/?$/)[1];
}

function setFilter(filter) {
    const url = new URL(location.href);
    const matches = url.pathname.match(/^(.*)\/[^/]+\/?$/);
    url.pathname = matches[1] + "/" + filter + "/";
    return url;
}

function renderCell(targets) {
    let html = '<div class="ui list">';
    targets.forEach(t => {
        html += '<div class="item">'
            + '<div class="content">'
            + '<a href="'+URL_PREFIX+'/prediction/'+ t.accession +'/">'+ t.accession +'</a>'
            + (
                t.entry.accession === null ? '' : '&nbsp;<span class="ui circular mini label type-'+ t.entry.type +'">'+ t.entry.type +'</span><a href="'+URL_PREFIX+'/entry/'+ t.entry.accession +'/">'+ t.entry.accession +'</a>'
            )
            + '</div>'
            + '</div>'
    });

    return html + '</div>';
}

function getSignatures() {
    ui.dimmer(true);
    const pathname = location.pathname.match(/(\/database\/.+\/)/)[1];
    fetch(URL_PREFIX+"/api" + pathname + location.search)
        .then(response => response.ok ? response.json() : null)
        .then(response => {
            if (response === null)
                return;

            const title = response.database.name + ' (' + response.database.version + ') unintegrated signatures';
            document.querySelector('h1.ui.header').innerHTML = title;
            document.title = title + ' | Pronto';

            let html = '';
            if (response.signatures.length) {
                response.signatures.forEach(query => {
                    const columns = {
                        S: [],
                        R: [],
                        P: [],
                        C: []
                    };

                    query.signatures.forEach(target => {
                        columns[target.prediction].push(target);
                    });

                    html += '<tr>'
                        + '<td><a href="'+URL_PREFIX+'/prediction/'+ query.accession +'/">'+ query.accession +'</a></td>'
                        + '<td class="nowrap">' + renderCell(columns['S']) + '</td>'
                        + '<td class="nowrap">' + renderCell(columns['R']) + '</td>'
                        + '<td class="nowrap">' + renderCell(columns['P']) + '</td>'
                        + '<td class="nowrap">' + renderCell(columns['C']) + '</td>'
                        + '</tr>';
                });
            } else
                html = '<tr><td class="center aligned" colspan="5">No matching signatures found</td></tr>';

            const table = document.getElementById("table-signatures");
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

            ui.dimmer(false);
        });
}

$(function () {
    finaliseHeader();
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

    const filter = getFilter();
    (function () {
        const input = document.querySelector("input[type=radio][name=filter][value='"+ filter +"']");
        if (input) {
            input.checked = true;
        }
    })();

    Array.from(document.querySelectorAll("input[type=radio]")).forEach(radio => {
        radio.addEventListener('change', e => {
            const url = setFilter(e.target.value);
            history.replaceState(null, null, url.toString());
            getSignatures();
        });
    });

    document.querySelector('input[type=checkbox][name=allpredictions]').addEventListener('change', e => {
        const url = new URL(location.href);

        if (e.target.checked)
            url.searchParams.set(e.target.name, '');
        else
            url.searchParams.delete(e.target.name);

        history.replaceState(null, null, url.toString());
        getSignatures();
    });
});