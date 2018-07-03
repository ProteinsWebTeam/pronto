import * as utils from '../utils.js';

$(function () {
    const feed = document.getElementById('feed');

    if (feed) {
        utils.getJSON('/api/feed/?n=15', (data, status) => {
            let html = '';
            data.results.forEach(e => {
                const date = new Date(e.timestamp * 1000);
                const timeDelta = Math.floor(Date.now() / 1000) - e.timestamp;

                html += '<div class="event">' +
                    '<div class="content"><div class="date"><abbr title="'+ date.toLocaleString() +'">';

                if (timeDelta < 60)
                    html += timeDelta.toString() + 's';
                else if (timeDelta < 3600)
                    html += Math.floor(timeDelta / 60).toString() + 'm';
                else if (timeDelta < (3600 * 24))
                    html += Math.floor(timeDelta / 3600).toString() + 'h';
                else
                    html += date.toLocaleDateString();

                html += '</abbr></div>';
                html += '<div class="summary"><a class="user">'+ e.user +'</a> '+ e.event +'</div></div></div>';
            });

            feed.innerHTML = html;
        });
    }

});