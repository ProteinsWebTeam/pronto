let _processResults = true;

export function getJSON(url, callback) {
    _processResults = true;
    let xhr = new XMLHttpRequest();
    xhr.onload = function () {
        if (_processResults)
            callback(JSON.parse(this.responseText), xhr.status);
    };
    xhr.open('GET', url, true);
    xhr.send();
}

export function cancelQuery() {
    _processResults = false;
}

export function parseLocation(url) {
    let search;
    if (url) {
        const i = url.indexOf('?');
        search = i !== -1 ? url.substr(i) : '';
    } else
        search = location.search;

    let params = {};
    if (search.length) {
        const arr = search.substr(1).split('&');
        arr.forEach(function (p) {
            if (p.trim()) {
                const pArr = p.trim().split('=');
                params[pArr[0]] = pArr.length > 1 ? pArr[1] : null;
            }
        })
    }

    return params

}

// $(function () {
//     const search = document.getElementById('search');
//     search.querySelector('input').addEventListener()
// });