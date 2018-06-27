import * as utils from './utils.js';


function getGOTerms(entryID) {
    utils.getJSON('/api/entry/' + entryID + '/go/', data => {
        let content = '<dt>Molecular Function</dt>';
        if (data.hasOwnProperty('F')) {
            data['F'].forEach(term => {
                content += '<dd><a target="_blank" href="http://www.ebi.ac.uk/QuickGO/GTerm?id=' + term.id + '">' + term.id + '&nbsp;<i class="external icon"></i></a>&nbsp;' + term.name;

                if (term.isObsolete)
                    content += '&nbsp;<span class="ui tiny red label">Obsolete</span>';

                if (term.replacedBy)
                    content += '&nbsp;<span class="ui tiny yellow label">Secondary</span>';

                content += '&nbsp;<a data-go-id="'+ term.id +'"><i class="trash icon"></i></a>';
                content += '<i class="right-floated caret left icon"></i><p class="hidden">'+ term.definition +'</p></dd>';
            });
        } else
            content += '<dd>No terms assigned in this category.</dd>';

        content += '<dt>Biological Process</dt>';
        if (data.hasOwnProperty('P')) {
            data['P'].forEach(term => {
                content += '<dd><a target="_blank" href="http://www.ebi.ac.uk/QuickGO/GTerm?id=' + term.id + '">' + term.id + '&nbsp;<i class="external icon"></i></a>&nbsp;' + term.name;

                if (term.isObsolete)
                    content += '&nbsp;<span class="ui tiny red label">Obsolete</span>';

                if (term.replacedBy)
                    content += '&nbsp;<span class="ui tiny yellow label">Secondary</span>';

                content += '&nbsp;<a data-go-id="'+ term.id +'"><i class="trash icon"></i></a>';
                content += '<i class="right-floated caret left icon"></i><p class="hidden">'+ term.definition +'</p></dd>';
            });
        } else
            content += '<dd>No terms assigned in this category.</dd>';

        content += '<dt>Cellular Component</dt>';
        if (data.hasOwnProperty('C')) {
            data['C'].forEach(term => {
                content += '<dd><a target="_blank" href="http://www.ebi.ac.uk/QuickGO/GTerm?id=' + term.id + '">' + term.id + '&nbsp;<i class="external icon"></i></a>&nbsp;' + term.name;

                if (term.isObsolete)
                    content += '&nbsp;<span class="ui tiny red label">Obsolete</span>';

                if (term.replacedBy)
                    content += '&nbsp;<span class="ui tiny yellow label">Secondary</span>';

                content += '&nbsp;<a data-go-id="'+ term.id +'"><i class="trash icon"></i></a>';
                content += '<i class="right-floated caret left icon"></i><p class="hidden">'+ term.definition +'</p></dd>';
            });
        } else
            content += '<dd>No terms assigned in this category.</dd>';


        document.getElementById('interpro2go').innerHTML = content;

        addGOEvents(entryID);
    });
}


function addGOEvents(entryID) {
    // Showing/hiding GO defintions
    Array.from(document.querySelectorAll('dl i.right-floated')).forEach(elem => {
        elem.addEventListener('click', e => {
            const icon = e.target;
            const block = icon.parentNode.querySelector('p');

            if (block.className === 'hidden') {
                block.className = '';
                icon.className = 'right-floated caret down icon';
            } else {
                block.className = 'hidden';
                icon.className = 'right-floated caret left icon';
            }
        });
    });

    Array.from(document.querySelectorAll('a[data-go-id]')).forEach(elem => {
        elem.addEventListener('click', e => {
            const goID = elem.getAttribute('data-go-id');

            utils.openConfirmModal(
                'Delete GO term?',
                '<strong>' + goID + '</strong> will not be associated to <strong>'+ entryID +'</strong> any more.',
                'Delete',
                function () {
                    utils.deletexhr('/api/entry/' + entryID + '/go/', {ids: goID}, data => {
                        if (data.status)
                            getGOTerms(entryID);
                        else {
                            const modal = document.getElementById('error-modal');
                            modal.querySelector('.content p').innerHTML = data.message;
                            $(modal).modal('show');
                        }
                    });
                }
            )
            // const modal = document.getElementById('confirm-modal');
            //
            // modal.querySelector('.content').innerHTML = '<p>Are you you want to delete this GO term?</p>';
            // modal.querySelector('.approve').innerText = 'Delete';
            //
            // $(modal)
            //     .modal({
            //         onApprove: function () {
            //             utils.deletexhr('/api/entry/' + entryID + '/go/', {ids: elem.getAttribute('data-go-id')}, data => {
            //                 if (data.status)
            //                     getGOTerms(entryID);
            //                 else {
            //                     const modal = document.getElementById('error-modal');
            //                     modal.querySelector('.content p').innerHTML = data.message;
            //                     $(modal).modal('show');
            //                 }
            //             });
            //         },
            //         onDeny: function () {}
            //     })
            //     .modal('show');
        });
    });
}

function addGoTerms(entryID, ids, callback) {
    utils.post('/api/entry/' + entryID + '/go/', {ids: ids}, data => {
        if (!data.status) {
            const modal = document.getElementById('error-modal');
            modal.querySelector('.content p').innerHTML = data.message;
            $(modal).modal('show');
        } else if (callback)
            callback();
    });
}

$(function () {
    const pathName = location.pathname;

    const match = pathName.match(/^\/entry\/(IPR\d+)/i);
    if (!match) {
        return;
    }

    const entryID = match[1];

    utils.getComments(
        document.querySelector('.ui.sticky .ui.comments'),
        'entry', entryID, 2, null
    );

    // Adding comments
    document.querySelector('.ui.comments form button').addEventListener('click', e => {
        e.preventDefault();
        const form = e.target.closest('form');
        const textarea = form.querySelector('textarea');

        utils.post('/api/entry/'+ entryID +'/comment/', {
            comment: textarea.value.trim()
        }, data => {
            utils.setClass(textarea.closest('.field'), 'error', !data.status);

            if (!data.status) {
                const modal = document.getElementById('error-modal');
                modal.querySelector('.content p').innerHTML = data.message;
                $(modal).modal('show');
            } else
                utils.getComments(
                    e.target.closest('.ui.comments'),
                    'entry', entryID, 2, null
                );
        });
    });

    addGOEvents(entryID);

    const div = document.getElementById('add-terms');
    const input = div.querySelector('.ui.input input');
    input.addEventListener('keyup', e => {
        if (e.which === 13 && e.target.value.trim().length)
            addGoTerms(entryID, e.target.value.trim(), function () {
                getGOTerms(entryID);
                input.value = null;
            });
    });

    div.querySelector('.ui.input button').addEventListener('click', e => {
        if (input.value.trim().length)
            addGoTerms(entryID, input.value.trim(), function () {
                getGOTerms(entryID);
                input.value = null;
            });
    });
});