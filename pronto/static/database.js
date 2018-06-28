import * as utils from './utils.js';

function getMethods() {
    const url = location.pathname + location.search;

    utils.dimmer(true);
    utils.getJSON('/api' + url, (data, status) => {
        utils.dimmer(false);

        if (!data.database) {
            // TODO: show error
            return;
        }

        const title = data.database.name + ' (' + data.database.version + ') signatures';
        document.querySelector('h1.ui.header').innerHTML = title;
        document.title = title + ' | Pronto';

        let html = '';
        if (data.results.length) {
            data.results.forEach(m => {
                html += '<tr data-id="'+ m.id +'">' +
                    '<td><a href="/method/'+ m.id +'">'+ m.id +'</a></td>' +
                    '<td>'+ utils.nvl(m.entryId, '', '<a href="/entry/'+ m.entryId +'">'+m.entryId+'</a>') +'</td>' +
                    '<td>'+ utils.renderCheckbox(m.entryId, m.isChecked) +'</td>' +
                    '<td>'+ utils.nvl(m.countNow, '') +'</td>' +
                    '<td>'+ utils.nvl(m.countThen, '') +'</td>' +
                    '<td>'+ (m.countNow && m.countThen ? Math.floor(m.countNow / m.countThen * 1000) / 10 : '') +'</td>';

                // Comment row
                html += '<td class="ui comments"><div class="comment"><div class="content">';
                if (m.latestComment) {
                    html += '<a class="author">' + m.latestComment.author + '&nbsp;</a>' +
                        '<div class="metadata"><span class="date">' + m.latestComment.date + '</span></div>' +
                        '<div class="text">' + (m.latestComment.text.length < 40 ? m.latestComment.text : m.latestComment.text.substr(0, 40) + '&hellip;')  + '</div>';
                }
                html += '<div class="actions"><a class="reply">Leave a comment</a></div></div></div></td></tr>';
            });
        } else
            html = '<tr><td class="center aligned" colspan="7">No matching entries found</td></tr>';

        document.querySelector('tbody').innerHTML = html;

        utils.paginate(
            document.querySelector('table'),
            data.pageInfo.page,
            data.pageInfo.pageSize,
            data.count,
            (url, ) => {
                history.replaceState(null, null, url);
                getMethods();
            }
        );

        Array.from(document.querySelectorAll('tbody input[type=checkbox]')).forEach(input => {
            input.addEventListener('change', e => {
                utils.openConfirmModal(
                    (input.checked ? 'Check' : 'Uncheck') + ' entry?',
                    '<strong>' + input.name + '</strong> will be marked as ' + (input.checked ? 'checked' : 'unchecked'),
                    (input.checked ? 'Check' : 'Uncheck'),
                    function () {
                        utils.post('/api/entry/' + input.name + '/check/', {
                            checked: input.checked ? 1 : 0
                        }, data => {
                            if (data.status) {
                                const cboxes = document.querySelectorAll('input[type=checkbox][name="'+ input.name +'"]');
                                for (let i = 0; i < cboxes.length; ++i)
                                    cboxes[i].checked = input.checked;
                            } else {
                                const modal = document.getElementById('error-modal');
                                modal.querySelector('.content p').innerHTML = data.message;
                                $(modal).modal('show');
                            }
                        });
                    },
                    function () {
                        input.checked = !input.checked;
                    }
                );
            });
        });

        const div = document.querySelector('.ui.sticky .ui.comments');
        Array.from(document.querySelectorAll('.comment .reply')).forEach(elem => {
            elem.addEventListener('click', e => {
                utils.getComments(div, 'method', e.target.closest('tr').getAttribute('data-id'), 2, null);
            });
        });
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

    document.querySelector('.ui.comments form button').addEventListener('click', e => {
        e.preventDefault();
        const form = e.target.closest('form');
        const methodID = form.getAttribute('data-id');
        const textarea = form.querySelector('textarea');

        utils.post('/api/method/'+ methodID +'/comment/', {
            comment: textarea.value.trim()
        }, data => {
            utils.setClass(textarea.closest('.field'), 'error', !data.status);

            if (!data.status) {
                const modal = document.getElementById('error-modal');
                modal.querySelector('.content p').innerHTML = data.message;
                $(modal).modal('show');
            } else {
                getMethods();  // need this to get the latest comment in the table
                utils.getComments(e.target.closest('.ui.comments'), 'method', methodID, 2, null);
            }
        });
    });
});