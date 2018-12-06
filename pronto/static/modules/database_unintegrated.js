import {finaliseHeader} from "../header.js";
import * as ui from "../ui.js";
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


function getFilter() {
    return new URL(location.href).pathname.match(/^.*\/([^/]+)\/?$/)[1];
}

function setFilter(filter) {
    const url = new URL(location.href);
    const matches = url.pathname.match(/^(.*)\/[^/]+\/?$/);
    url.pathname = matches[1] + "/" + filter + "/";
    return url;
}

function getSignatures() {
    ui.dimmer(true);
    fetch("/api" + location.pathname + location.search)
        .then(response => response.json())
        .then(results => {
            if (!results.database) {
                // TODO: show error
                return;
            }
            const title = results.database.name + ' (' + results.database.version + ') unintegrated signatures';
            document.querySelector('h1.ui.header').innerHTML = title;
            document.title = title + ' | Pronto';

            let html = '';
            if (results.signatures.length) {
                results.signatures.forEach(signature => {
                    html += '<tr>' 
                        + '<td><a href="/method/'+ signature["accession"] +'/">'+ signature["accession"] +'</a></td>' 
                        + '<td class="nowrap">'
                        + '<div class="ui list">';
                    
                    signature.add_to.forEach(prediction => {
                        html += '<div class="item">';
                        
                        if (prediction.type !== null) {
                            html += '<div class="content">'
                                + '<span class="ui circular mini label type-'+ prediction.type +'">'+ prediction.type +'</span>'
                                + '<a href="/entry/'+ prediction.accession +'/">'+ prediction.accession +'</a>'
                                + '</div>';
                        } else {
                            html += '<div class="content">'
                                + '<span class="ui circular mini label">&nbsp;</span>'
                                + '<a href="/entry/'+ prediction.accession +'/">'+ prediction.accession +'</a>'
                                + '</div>';
                        }

                        html += '</div>';
                    });

                    html += '</div></td>'
                        + '<td>'+ signature.parents.join(", ") +'</td>'
                        + '<td>'+ signature.children.join(", ") +'</td>';


                });
            } else
                html = '<tr><td class="center aligned" colspan="4">No matching signatures found</td></tr>';

            document.querySelector('tbody').innerHTML = html;

            ui.paginate(
                document.querySelector("table"),
                results.page_info.page,
                results.page_info.page_size,
                results.count,
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
});