import * as utils from './utils.js';

$(function () {
    const params = utils.parseLocation();
    if (!params.query) return;

    document.querySelector('form input[name=query]').value = decodeURIComponent(params.query).replace(/\+/g, ' ');

    utils.getJSON('/api/search/?query=' + params.query, (data, status) => {
        console.log(data);
    });
});