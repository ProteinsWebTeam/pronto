const _colors = [
    "#dac5f3",
    "#8bd6f0",
    "#89e9e7",
    "#b8e9d3",
    "#a4e6b8",
    "#cae8ad",
    "#e0e1b1",
    "#f1d49b",
    "#f2c3b7"
];


function nvl(expr1, expr2, expr3) {
    if (expr1 !== null && expr1 !== undefined)
        return expr3 ? expr3 : expr1;
    else
        return expr2;
}

function setClass(element, className, active) {
    const classes = element.className.trim().split(' ');
    const hasClass = classes.indexOf(className) !== -1;

    if (active && !hasClass)
        element.className = classes.join(' ') + ' ' + className;
    else if (!active && hasClass) {
        let newClasses = [];
        for (let i = 0; i < classes.length; ++i) {
            if (classes[i] !== className)
                newClasses.push(classes[i]);
        }
        element.className = newClasses.join(' ');
    }
}

function renderCheckbox(entryId, isChecked) {
    if (!entryId)
        return '<div class="ui disabled fitted checkbox"><input disabled="disabled" type="checkbox"><label></label></div>';
    else if (isChecked)
        return '<div class="ui checked fitted checkbox"><input name="' + entryId + '" checked="" type="checkbox"><label></label></div>';
    else
        return '<div class="ui fitted checkbox"><input name="' + entryId + '" type="checkbox"><label></label></div>';
}

function showDimmer(show) {
    const dimmer = document.getElementById('dimmer');
    if (show) {
        dimmer.children[0].innerHTML = 'Loading';
        setClass(dimmer, 'active', true);
    } else {
        setClass(dimmer, 'active', false);
    }
}


function setGlobalError(msg) {
    const div = document.getElementById('messages');
    if (msg) {
        const message = div.querySelector('.ui.message');
        message.querySelector('span').innerHTML = msg;
        setClass(message, 'hidden', false);
        setClass(div, 'hidden', false);
    } else
        setClass(div, 'hidden', true);
}


function getMethodComments(methodId, div, size, callback) {

    getJSON('/api/method/' + methodId + '/comments' + encodeParams({size: size}), data => {
        // Sub header
        div.querySelector('.ui.header .sub').innerHTML = methodId;

        let html = '';
        data.results.forEach(comment => {
            if (comment.status)
                html += '<div class="comment" data-id="'+ comment.id +'">' +
                    '<div class="content">' +
                    '<a class="author">'+ comment.author +'</a>' +
                    '<div class="metadata">' +
                    '<span class="date">'+ comment.date +'</span>' +
                    '<a><i class="remove icon"></i></a>' +
                    '</div>' +
                    '<div class="text">'+ comment.text +'</div></div></div>';
            else
                html += '<div class="negative comment" data-id="'+ comment.id +'">' +
                    '<div class="content">' +
                    '<a class="author">'+ comment.author +'</a>' +
                    '<div class="metadata">' +
                    '<span class="date">'+ comment.date +'</span>' +
                    '</div>' +
                    '<div class="text">'+ comment.text +'</div></div></div>';
        });

        if (data.results.length < data.count)
            html += '<div class="actions"><a>View more comments</a></div>';

        div.querySelector('.comments-content').innerHTML = html;

        const form = div.querySelector('form');
        form.setAttribute('data-id', methodId);

        const textarea = form.querySelector('textarea');
        setClass(textarea.parentNode, 'error', false);
        textarea.value = null;

        const action = div.querySelector('.comments-content .actions a');
        if (action) {
            action.addEventListener('click', e => {
                e.preventDefault();
                getMethodComments(methodId, div, null, callback);
            });
        }

        Array.from(div.querySelectorAll('.comment .metadata a')).forEach(element => {
            element.addEventListener('click', e => {
                e.preventDefault();

                const commentId = e.target.closest('.comment').getAttribute('data-id');
                const commentType = 'method';
                const modal = document.getElementById('confirm-modal');

                modal.querySelector('.content').innerHTML = '<p>Flag this comment as invalid? This action <strong>cannot</strong> be undone.</p>';

                $(modal).modal({
                    onApprove: function () {
                        postXhr('/api/comment/' + commentType + '/' + commentId, {
                            status: 0
                        }, data => {
                            if (data.status)
                                getMethodComments(methodId, div, size, callback);
                            else {
                                const modal = document.getElementById('error-modal');
                                modal.querySelector('.content p').innerHTML = data.message;
                                $(modal).modal('show');
                            }
                        });
                    },
                    onDeny: function () {}
                }).modal('show');
            });
        });

        const sticky = div.closest('.sticky');
        if (sticky) {
            setClass(sticky, 'hidden', false);
            $(sticky).sticky({context: div.querySelector('table')});
        }

        if (callback)
            callback();
    });
}

function hex2rgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
    } : null;
}

function rgb2hex(c) {
    return '#' + ((1 << 24) + (Math.floor(c.r) << 16) + (Math.floor(c.g) << 8) + Math.floor(c.b)).toString(16).slice(1);
}

function calcPixelSlope(p1, p2, distance) {
    return {
        r: (p2.r - p1.r) / distance,
        g: (p2.g - p1.g) / distance,
        b: (p2.b - p1.b) / distance
    }
}

function calcPixelGradient(startingPixel, distance, slope) {
    return {
        r: startingPixel.r + slope.r * distance,
        g: startingPixel.g + slope.g * distance,
        b: startingPixel.b + slope.b * distance
    }

}

function getJSON(url, callback) {
    let xhr = new XMLHttpRequest();
    xhr.onload = function () {
        callback(JSON.parse(this.responseText), xhr.status)
    };
    xhr.open('GET', url, true);
    xhr.send();
}

function postXhr(url, params, callback) {
    let xhr = new XMLHttpRequest();
    xhr.onload = function () {
        callback(JSON.parse(this.responseText))
    };
    xhr.open('POST', url, true);
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
    let postVars = [];
    for (let key in params) {
        if (params.hasOwnProperty(key))
            postVars.push(key + '=' + params[key])
    }
    xhr.send(postVars.join('&'));
}

function getParams(url) {
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

function getPathName(url) {
    return url ? url.split('?')[0].replace(/\/+$/g, '') : location.pathname.replace(/\/+$/g, '');
}

function encodeParams(params, requiresValue) {
    const arrParams = [];
    for (let p in params) {
        if (params.hasOwnProperty(p)) {
            if (params[p] !== null)
                arrParams.push(p + '=' + params[p]);
            else if (!requiresValue)
                arrParams.push(p);
        }
    }

    return arrParams.length ? '?' + arrParams.join('&') : '';
}

function extendObj(original, options) {
    const obj = Object.assign({}, original);
    for (let prop in options) {
        if (options.hasOwnProperty(prop))
            obj[prop] = options[prop];
    }

    return obj;
}

function observeLink(element) {
    element.addEventListener('click', e => {
        e.preventDefault();
        const url = e.target.getAttribute('href');
        history.pushState({}, '', url);
        initApp();
    });
}

function observeLinks(div, callback) {
    const links = div.querySelectorAll('table a[data-method]');
    for (let i = 0; i < links.length; ++i) {
        links[i].addEventListener('click', e => {
            e.preventDefault();
            const link = e.target;
            const row = link.closest('tr');
            const methodId = link.getAttribute('data-method');
            const filter = row.getAttribute('data-filter');
            const search = row.getAttribute('data-search');
            callback(methodId, filter, search);
        });
    }
}

function setSelected(dropdown, value) {
    Array.from(dropdown.querySelectorAll('option')).forEach(option => {
        option.selected = option.value === value;
    });
}


function ProteinView() {
    this.section = document.getElementById('protein');
    const self = this;

    // Init
    (function () {
        const items = self.section.querySelectorAll('.ui.menu a.item');
        Array.from(items).forEach(item => {
            item.addEventListener('click', e => {
                Array.from(items).forEach(i => {
                    setClass(i, 'active', i === e.target);
                });
            });
        });
    })();

    this.tooltip = {
        element: document.getElementById('tooltip'),
        isInit: false,
        active: false,

        show: function(rect) {
            this.active = true;
            this.element.style.display = 'block';
            this.element.style.top = Math.round(rect.top - this.element.offsetHeight + window.scrollY - 5).toString() + 'px';
            this.element.style.left = Math.round(rect.left + rect .width / 2 - this.element.offsetWidth / 2).toString() + 'px';

        },
        _hide: function () {
            if (!this.active)
                this.element.style.display = 'none';
        },
        hide: function () {
            this.active = false;
            setTimeout(() => {
                this._hide();
            }, 500);
        },
        update: function (id, name, start, end, dbName, link) {
            let content = '<div class="header">' + start.toLocaleString() + ' - ' + end.toLocaleString() +'</div><div class="meta">' + nvl(name, '') + '</div>';

            if (id[0].indexOf('IPR') === 0)  // todo show hierarchy
                content += '<div class="description"><a href="/entry/'+ id[0] +'">'+ id[0] +'</a></div>';
            else
                content += '<div class="description"><strong>'+ dbName +'</strong>&nbsp;<a target="_blank" href="'+ link +'">'+ id +'&nbsp;<i class="external icon"></i></div>';

            this.element.querySelector('.content').innerHTML = content;
        },
        init: function () {
            if (this.isInit)
                return;

            this.isInit = true;

            this.element.addEventListener('mouseenter', e => {
                this.active = true;
            });

            this.element.addEventListener('mouseleave', e => {
                this.hide();
            });

            this.element.querySelector('.close').addEventListener('click', e => {
                this.element.style.display = 'none';
            });
        }
    };

    this.get = function(proteinId) {
        const url = location.pathname + location.search;
        showDimmer(true);

        getJSON('/api/protein/' + proteinId, (data, status) => {
            history.replaceState({data: data, page: 'protein', url: url}, '', url);
            this.render(data);
            showDimmer(false);
        });
    };

    this.render = function (data) {
        if (!data.status) {
            setGlobalError(data.error);
            setClass(this.section, 'hidden', true);
            return;
        }

        setClass(this.section, 'hidden', false);
        setGlobalError(null);

        const protein = data.result;

        document.title = protein.name + ' (' + protein.id + ') | Pronto';
        this.section.querySelector('h1.header').innerHTML = protein.name + '<div class="sub header"><a target="_blank" href="'+ protein.link +'">' + (protein.isReviewed ? '<i class="star icon"></i>' : '') + protein.id  + '&nbsp;<i class="external icon"></i></a></div>';

        const arr = protein.taxon.scientificName.split(' ');
        let nEntries = 0;
        let nMatches = 0;

        protein.entries.forEach(e => {
            if (e.id !== null)
                nEntries++;

            e.methods.forEach(m => {
                nMatches += m.matches.length;
            });
        });

        const entries = (function (entries) {
            const arr = [];
            const obj = {};
            const children = {};

            entries.forEach(entry => {
                arr.push(entry.id);
                obj[entry.id] = entry;

                if (entry.parent !== null) {
                    if (!children.hasOwnProperty(entry.parent))
                        children[entry.parent] = [];

                    children[entry.parent].push(entry.id);
                }
            });

            const final = [];
            arr.forEach(id => {
                const entry = obj[id];
                entry.children = children.hasOwnProperty(id) ? children[id].map(id => {return obj[id]}) : [];

                if (!entry.parent || !children.hasOwnProperty(entry.parent))
                    final.push(entry);
            });

            return final;
        })(protein.entries);

        this.section.querySelector('[data-stats=organism]').innerHTML = '<abbr title="'+ protein.taxon.scientificName +'">'+ arr[0].charAt(0) + '. ' + arr[1] +'</abbr>';
        this.section.querySelector('[data-stats=length]').innerHTML = protein.length.toLocaleString();
        this.section.querySelector('[data-stats=entries]').innerHTML = nEntries.toLocaleString();
        this.section.querySelector('[data-stats=matches]').innerHTML = nMatches.toLocaleString();

        // Global variables for SVG
        const paddingTop = 10;
        const paddingBottom = 10;
        const matchHeight = 10;
        const matchMarginBottom = 2;

        // Global matche info for tooltip
        const allMatches = {};
        let index = 0;

        const sortById = function (a, b) {
            if (a.id < b.id)
                return -1;
            else if (a.id > b.id)
                return 1;
            else
                return 0;
        };

        const sortByPos = function (a, b) {
            return a.start !== b.start ? a.start - b.start : a.end - b.end;
        };

        const flattenMatches = function (entry) {
            let matches = [];

            entry.methods.forEach(method => {
                method.matches.forEach(match => {
                    matches.push({
                        start: match.start,
                        end: match.end,
                        id: [entry.id],
                        name: entry.name,
                        db: method.db,
                    });
                });
            });

            entry.children.forEach(child => {
                matches = matches.concat(flattenMatches(child));
            });

            return matches;
        };

        const getLeftmostMatch = function (entry) {
            return flattenMatches(entry).sort(sortByPos)[0];
        };

        const sortByLeftmostMatch = function (a, b) {
            const m1 = getLeftmostMatch(a);
            const m2 = getLeftmostMatch(b);
            return m1.start !== m2.start ? m1.start - m2.start : m1.end - m2.end;
        };

        const mergeMatches = function (entry) {
            const matches = flattenMatches(entry);

            const oMatches = [];
            matches
                .sort(sortByPos)
                .forEach(match => {
                    const i = oMatches.length - 1;

                    if (i < 0) {
                        oMatches.push(match);
                        return;
                    }

                    if (match.start <= oMatches[i].end) {
                        oMatches[i].end = match.end;

                        // Add the entry ID to the match
                        if (oMatches[i].id.indexOf(match.id[0]) === -1)
                            oMatches[i].id.push(match.id[0]);
                    }
                    else
                        oMatches.push(match);
                });

            const getLevel = function(id, e, l) {
                if (e.id === id)
                    return l;

                for (let i = 0; i < e.children.length; ++i) {
                    const cl = getLevel(id, e.children[i], l+1);
                    if (cl)
                        return cl;
                }

                return 0;
            };

            const findEntry = function (id, e) {
                if (e.id === id)
                    return e;

                for (let i = 0; i < e.children.length; ++i) {
                    const _e = findEntry(id, e.children[i]);
                    if (_e)
                        return _e;
                }

                return e;
            };

            oMatches.forEach(match => {
                match.id = match.id.sort((id1, id2) => {
                    return getLevel(id1, entry, 0) - getLevel(id2, entry, 0);
                });
                match.name = findEntry(match.id[0], entry).name;
            });

            return oMatches;
        };

        const determineLines = function (entries) {
            // Determine the position of matches on the SVG

            let matches = [];
            entries.forEach(entry => {
                matches = matches.concat(mergeMatches(entry));
            });


            const lines = [];
            matches
                .sort(sortByPos)
                .forEach(match => {
                    let overlap = true;

                    for (let i = 0; i < lines.length; ++i) {
                        const j = lines[i].length - 1;

                        if (j < 0 || lines[i][j].end < match.start) {
                            overlap = false;
                            lines[i].push(match);
                            break;
                        }
                    }

                    if (overlap)
                        lines.push([match]);
                });
            return lines;
        };

        const initSVG = function (nLines) {
            const rectHeight = paddingTop + paddingBottom + nLines * matchHeight + (nLines - 1) * matchMarginBottom;
            let content = '<svg width="' + svgWidth + '" height="'+ (rectHeight + 10) +'" version="1.1" baseProfile="full" xmlns="http://www.w3.org/2000/svg">';
            content += '<rect x="0" y="0" height="'+ rectHeight +'" width="'+ width +'" style="fill: #eee;"/>';
            content += '<g class="ticks">';

            for (let pos = step; pos < protein.length; pos += step) {
                const x = Math.round(pos * width / protein.length);
                content += '<line x1="'+ x +'" y1="0" x2="'+ x +'" y2="' + rectHeight + '" />';
                content += '<text x="' + x + '" y="'+ rectHeight +'">' + pos.toLocaleString() + '</text>';
            }
            content += '<line x1="'+ width +'" y1="0" x2="'+ width +'" y2="' + rectHeight + '" />';
            content += '<text x="' + width + '" y="'+ rectHeight +'">' + protein.length.toLocaleString() + '</text>';
            return content + '</g>';
        };

        const renderEntryMatches = function (entry) {
            let html = '';

            if (entry.id)
                html += '<h3 class="ui header"><span class="ui tiny type-'+ entry.typeCode +' circular label">'+ entry.typeCode +'</span>&nbsp;<a href="/entry/'+ entry.id +'">'+ entry.id +'</a><div class="sub header">'+ entry.name +'</div></h3>';
            else
                html += '<h3 class="ui header">Unintegrated</h3>';

            html += initSVG(entry.methods.length);

            entry.methods.sort(sortById).forEach((method, i) => {
                const y = paddingTop + i * matchHeight + (i - 1) * matchMarginBottom;

                method.matches.forEach(match => {
                    const x = Math.round(match.start * width / protein.length);
                    const w = Math.round((match.end - match.start) * width / protein.length);
                    html += '<rect data-id="'+ index +'" class="match" x="'+ x +'" y="' + y + '" width="' + w + '" height="'+ matchHeight +'" rx="1" ry="1" style="fill: '+ method.db.color +'"/>';
                    allMatches[index++] = {
                        start: match.start,
                        end: match.end,
                        id: [entry.id],
                        name: entry.name,
                        db: method.db,
                    };
                });

                html += '<text x="' + (width + 10) + '" y="'+ (y + matchHeight / 2) +'"><a href="/method/'+ method.id +'">'+ method.id +'</a></text>';
            });

            html += '</svg>';

            entry.children.forEach(child => {
                html += renderEntryMatches(child);
            });

            return html;
        };

        let html = '';

        // Protein family membership
        const families = entries.filter(e => e.typeCode === 'F');
        if (families.length) {
            const renderEntry = function (entry) {
                let item = '<div class="item"><div class="content"><span class="ui tiny type-F circular label">F</span>&nbsp;<a href="/entry/'+ entry.id +'">'+ entry.id +'</a>&nbsp;'+ entry.name +'</div>';

                if (entry.children.length) {
                    item += '<div class="list">';
                    entry.children.sort(sortById).forEach(child => {
                        item += renderEntry(child);
                    });
                    item += '</div>';
                }

                item += '</div>';
                return item;
            };

            families.sort(sortById).forEach(entry => {
                html += renderEntry(entry);
            });

            document.querySelector('#families + div').innerHTML = '<div class="ui list">' + html + '</div>';
        } else
            document.querySelector('#families + div').innerHTML = 'None.';

        // Homologous superfamily matches
        const superfamilies = entries.filter(e => e.typeCode === 'H');

        let div = this.section.querySelector('#superfamilies + div');
        const svgWidth = div.offsetWidth;
        const width = svgWidth - 200;
        const step = Math.pow(10, Math.floor(Math.log(protein.length) / Math.log(10))) / 2;

        html = '';
        if (superfamilies.length) {
            const lines = determineLines(superfamilies);
            html += initSVG(lines.length);

            lines.forEach((line, i) => {
                const y = paddingTop + i * matchHeight + (i - 1) * matchMarginBottom;

                line.forEach(match => {
                    const x = Math.round(match.start * width / protein.length);
                    const w = Math.round((match.end - match.start) * width / protein.length);
                    html += '<rect data-id="'+ index +'" class="match" x="'+ x +'" y="' + y + '" width="' + w + '" height="'+ matchHeight +'" rx="1" ry="1" style="fill: '+ match.db.color +'"/>';
                    allMatches[index++] = match;
                });

                if (!i)
                    html += '<text x="' + (width + 10) + '" y="'+ (y + matchHeight / 2) +'">Homologous superfamily</text>';
            });

            html += '</svg>';
        } else
            html = 'None.';

        div.innerHTML = html;


        // Domains/repeats
        const domains = entries.filter(e => e.typeCode === 'D');
        const repeats = entries.filter(e => e.typeCode === 'R');

        html = '';
        if (domains.length || repeats.length) {
            const domainLines = determineLines(domains);
            const repeatsLines = determineLines(repeats);
            html += initSVG(domainLines.length + repeatsLines.length);

            domainLines.forEach((line, i) => {
                const y = paddingTop + i * matchHeight + (i - 1) * matchMarginBottom;

                line.forEach(match => {
                    const x = Math.round(match.start * width / protein.length);
                    const w = Math.round((match.end - match.start) * width / protein.length);
                    html += '<rect data-id="'+ index +'" class="match" x="'+ x +'" y="' + y + '" width="' + w + '" height="'+ matchHeight +'" rx="1" ry="1" style="fill: '+ match.db.color +'"/>';
                    allMatches[index++] = match;
                });

                if (!i)
                    html += '<text x="' + (width + 10) + '" y="'+ (y + matchHeight / 2) +'">Domain</text>';
            });

            const offset = paddingTop + domainLines.length * (matchHeight + matchMarginBottom);

            repeatsLines.forEach((line, i) => {
                const y = offset + i * matchHeight + (i - 1) * matchMarginBottom;

                line.forEach(match => {
                    const x = Math.round(match.start * width / protein.length);
                    const w = Math.round((match.end - match.start) * width / protein.length);
                    html += '<rect data-id="'+ index +'" class="match" x="'+ x +'" y="' + y + '" width="' + w + '" height="'+ matchHeight +'" rx="1" ry="1" style="fill: '+ match.db.color +'"/>';
                    allMatches[index++] = match;
                });

                if (!i)
                    html += '<text x="' + (width + 10) + '" y="'+ (y + matchHeight / 2) +'">Repeat</text>';
            });
        } else
            html = 'None.';

        document.querySelector('#domains-repeats + div').innerHTML = html;

        // Detailed signatures matches
        const others = entries.filter(e => ['F', 'H', 'D', 'R'].indexOf(e.typeCode) === -1);
        html = '';
        superfamilies.sort(sortByLeftmostMatch).forEach(entry => {
            html += renderEntryMatches(entry);
        });

        families.sort(sortByLeftmostMatch).forEach(entry => {
            html += renderEntryMatches(entry);
        });

        domains.sort(sortByLeftmostMatch).forEach(entry => {
            html += renderEntryMatches(entry);
        });

        others
            .sort((a, b) => {
                if (a.typeCode === b.typeCode)
                    return sortByLeftmostMatch(a, b);
                else if (a.typeCode === null)
                    return -1;
                else
                    return 1;
            })
            .forEach(entry => {
                html += renderEntryMatches(entry);
            });

        document.querySelector('#detailed + div').innerHTML = html;

        // Structural features and predictions
        if (protein.structures.length) {
            // todo
            const structures = {};
            let nLines = 0;

            protein.structures.forEach(struct => {
                const dbName = struct.db.name;

                if (! structures.hasOwnProperty(dbName)) {
                    structures[dbName] = [];
                    nLines++;
                }

                structures[dbName].push(struct);
            });

            html = initSVG(nLines);

            let i = 0;
            let dbName;
            for (dbName in structures) {
                if (structures.hasOwnProperty(dbName)) {
                    const y = paddingTop + i * matchHeight + (i - 1) * matchMarginBottom;

                    structures[dbName].forEach(struct => {
                        struct.matches.forEach(match => {
                            const x = Math.round(match.start * width / protein.length);
                            const w = Math.round((match.end - match.start) * width / protein.length);
                            html += '<rect data-id="'+ index +'" class="match" x="'+ x +'" y="' + y + '" width="' + w + '" height="'+ matchHeight +'" rx="1" ry="1" style="fill: '+ struct.db.color +'"/>';
                            allMatches[index++] = {
                                start: match.start,
                                end: match.end,
                                id: [struct.id],
                                name: null,
                                db: struct.db,
                            };
                        });
                    });

                    html += '<text x="' + (width + 10) + '" y="'+ (y + matchHeight / 2) +'"><a target="_blank" href="' + structures[dbName][0].db.home +'">'+ dbName +'&nbsp;<tspan>&#xf08e;</tspan></a></text>';
                    ++i;
                }
            }

            html += '</svg>';
        } else
            html = 'None.';

        document.querySelector('#structures + div').innerHTML = html;

        $(this.section.querySelector('.ui.sticky')).sticky({
            context: this.section.querySelector('.twelve.column')
        });

        this.tooltip.init();

        Array.from(this.section.querySelectorAll('rect[data-id]')).forEach(element => {
            element.addEventListener('mouseenter', e => {
                const target = e.target;
                const id = target.getAttribute('data-id');
                const m = allMatches[id];

                self.tooltip.update(m.id, m.name, m.start, m.end, m.db.name, m.db.link);
                self.tooltip.show(target.getBoundingClientRect());
            });

            element.addEventListener('mouseleave', e => {
                self.tooltip.hide();
            });
        });
    }
}


function EntryView() {
    this.section = document.getElementById('entry');
    const self = this;

    // Init
    (function () {
        const items = self.section.querySelectorAll('.ui.menu a.item');
        Array.from(items).forEach(item => {
            item.addEventListener('click', e => {
                Array.from(items).forEach(i => {
                    setClass(i, 'active', i === e.target);
                });
            });
        });

        self.section.querySelector('.ui.comments form button').addEventListener('click', e => {
            e.preventDefault();
            const form = e.target.closest('form');
            const entryId = form.getAttribute('data-id');
            const textarea = form.querySelector('textarea');

            postXhr('/api/entry/'+ entryId +'/comment/', {
                comment: textarea.value.trim()
            }, data => {
                setClass(textarea.closest('.field'), 'error', !data.status);

                if (!data.status) {
                    const modal = document.getElementById('error-modal');
                    modal.querySelector('.content p').innerHTML = data.message;
                    $(modal).modal('show');
                } else
                    self.getComments(entryId, 2);
            });
        });
    })();

    this.get = function(entryId) {
        const url = location.pathname + location.search;
        showDimmer(true);

        getJSON('/api/entry/' + entryId, (data, status) => {
            history.replaceState({data: data, page: 'entry', url: url}, '', url);
            this.render(data);
            showDimmer(false);
        });
    };

    this.render = function (data) {
        if (!data.status) {
            setGlobalError(data.error);
            setClass(this.section, 'hidden', true);
            return;
        }

        setClass(this.section, 'hidden', false);
        setGlobalError(null);

        const entry = data.result;
        document.title = entry.name + ' (' + entry.id + ') | Pronto';
        this.section.querySelector('h1.header').innerHTML = entry.id + (entry.isChecked ? '<i class="checkmark icon"></i>' : '') + '<div class="sub header">'+ entry.name +'</div>';
        this.section.querySelector('h1.header').innerHTML = entry.name + '<div class="sub header">'+ (entry.isChecked ? '<i class="checkmark icon"></i>' : '') + entry.shortName + ' (' + entry.id + ')</div>';
        this.section.querySelector('.ui.segment').className = 'ui segment type-' + entry.typeCode;

        const stats = [{
            selector: 'proteins',
            value: entry.proteinCount.toLocaleString()
        }, {
            selector: 'type',
            value: entry.type.replace('_', '<br>')
        }, {
            selector: 'methods',
            value: entry.methods.length
        }, {
            selector: 'terms',
            value: entry.go.length
        }, {
            selector: 'references',
            value: entry.references.count
        }, {
            selector: 'relationships',
            value: entry.relationships.count
        }];

        stats.forEach(s => {
            Array.from(this.section.querySelectorAll('[data-stats="'+s.selector+'"]')).forEach(e => {
                e.innerHTML = s.value;
            });
        });

        // Curation
        Array.from(this.section.querySelectorAll('dl a[data-external]')).forEach(element => {
            element.setAttribute('href', element.getAttribute('data-external') + entry.id);
        });

        const methodIds = [];
        entry.methods.forEach(method => methodIds.push(method.id));

        Array.from(this.section.querySelectorAll('dl a[data-internal]')).forEach(element => {
            element.setAttribute('href', '/methods/' + methodIds.join('/') + '/' + element.getAttribute('data-internal'));
        });

        // Description
        let description = entry.description;
        const references = entry.references.values;
        const orderedRefs = [];
        const re = /<cite id="([A-Z0-9,]+)"\/>/g;
        let arr;
        while ((arr = re.exec(description)) !== null) {
            const content = [];

            arr[1].split(',').forEach(function (refID) {
                refID = refID.trim();
                if (references.hasOwnProperty(refID)) {
                    let i = orderedRefs.indexOf(refID);
                    if (i === -1) {
                        i = orderedRefs.length;
                        orderedRefs.push(refID);
                    }

                    content.push('<a href="#' + refID + '">' + (i + 1) + '</a>')
                }
            });

            description = description.replace(arr[0], '<sup>[' + content.join(', ') + ']</sup>');
        }

        document.querySelector('#description + div').innerHTML = description;

        // References
        let content = '';
        orderedRefs.forEach(function (refID) {
            const ref = references[refID];

            content += '<li id="' + ref.id + '">' + ref.authors + ' ' + ref.title + ' <i>' + ref.journal + '</i> ' +
                ref.year + ';' + ref.volume + ':' + ref.pages;

            if (ref.doi || ref.pmid) {
                content += '<div class="ui horizontal link list">';

                if (ref.doi)
                    content += '<a target="_blank" class="item" href="'+ ref.doi +'">View article&nbsp;<i class="external icon"></i></a>';

                if (ref.pmid)
                    content += '<span class="item">Europe PMC:&nbsp;<a target="_blank" href="http://europepmc.org/abstract/MED/' + ref.pmid + '">'+ ref.pmid +'&nbsp;<i class="external icon"></i></a></span>';

                content += '</div>';
            }

            content += '</li>';
        });

        if (content.length)
            document.querySelector('#references + div').innerHTML = '<ol class="ui list">' + content + '</ol>';
        else
            document.querySelector('#references + div').innerHTML = '<p>This entry has no references.</p>';

        // Suppl. references
        content = '';
        for (refID in references) {
            if (references.hasOwnProperty(refID) && orderedRefs.indexOf(refID) === -1) {
                content += '<li id="' + references[refID].id + '">' + references[refID].authors + ' ' +
                    references[refID].title + ' <i>' + references[refID].journal + '</i> ' +
                    references[refID].year + ';' + references[refID].volume + ':' + references[refID].pages +
                    '<div class="ui horizontal link list">';

                if (references[refID].doi)
                    content += '<a target="_blank" class="item" href="'+ references[refID].doi +'">View article&nbsp;<i class="external icon"></i></a>';

                if (references[refID].pmid)
                    content += '<span class="item">Europe PMC:&nbsp;<a target="_blank" href="http://europepmc.org/abstract/MED/' + references[refID].pmid + '">'+ references[refID].pmid +'&nbsp;<i class="external icon"></i></a></span>';

                content += '</div></li>';
            }
        }

        if (content.length)
            document.querySelector('#supp-references + div').innerHTML = '<p>The following publications were not referred to in the description, but provide useful additional information.</p><ul class="ui list">' + content + '</ul>';
        else
            document.querySelector('#supp-references + div').innerHTML = '<p>This entry has no additional references.</p>';

        // Signatures
        content = '';
        entry.methods.forEach(method => {
            content += '<tr><td><a href="/method/'+ method.id +'">'+ method.id +'</a></td>';

            if (method.link)
                content += '<td><a target="_blank" href="'+ method.link +'">'+ method.dbname +'&nbsp;<i class="external icon"></i></a></td>';
            else if (method.home)
                content += '<td><a target="_blank" href="'+ method.home +'">'+ method.dbname +'&nbsp;<i class="external icon"></i></a></td>';
            else
                content += '<td>'+ method.dbname +'</td>';

            content += '<td>' + method.name + '</td><td>' + method.count.toLocaleString() + '</td></tr>';

        });

        document.querySelector('#signatures + table tbody').innerHTML = content;

        // Relationships
        content = '';
        if (entry.relationships.types.parents.length) {
            content += '<dt>Parents</dt>';
            entry.relationships.types.parents.forEach(e => {
                content += '<dd><span class="ui tiny label circular type-'+ e.typeCode +'">'+ e.typeCode +'</span>&nbsp;<a href="/entry/'+ e.id +'">' + e.id + '</a>&nbsp;' + e.name + '</dd>';
            });
        }
        if (entry.relationships.types.children.length) {
            content += '<dt>Children</dt>';
            entry.relationships.types.children.forEach(e => {
                content += '<dd><span class="ui tiny label circular type-'+ e.typeCode +'">'+ e.typeCode +'</span>&nbsp;<a href="/entry/'+ e.id +'">' + e.id + '</a>&nbsp;' + e.name + '</dd>';
            });
        }
        if (entry.relationships.types.containers.length) {
            content += '<dt>Found in</dt>';
            entry.relationships.types.containers.forEach(e => {
                content += '<dd><span class="ui tiny label circular type-'+ e.typeCode +'">'+ e.typeCode +'</span>&nbsp;<a href="/entry/'+ e.id +'">' + e.id + '</a>&nbsp;' + e.name + '</dd>';
            });
        }
        if (entry.relationships.types.components.length) {
            content += '<dt>Contains</dt>';
            entry.relationships.types.components.forEach(e => {
                content += '<dd><span class="ui tiny label circular type-'+ e.typeCode +'">'+ e.typeCode +'</span>&nbsp;<a href="/entry/'+ e.id +'">' + e.id + '</a>&nbsp;' + e.name + '</dd>';
            });
        }

        if (content.length)
            document.querySelector('#relationships + div').innerHTML = '<dl class="ui list">'+ content + '</dl>';
        else
            document.querySelector('#relationships + div').innerHTML = '<p>This entry has no relationships.</p>';

        // GO terms block
        const goTerms = {
            'P': '',
            'F': '',
            'C': ''
        };

        entry.go.forEach(function (term) {
            if (goTerms.hasOwnProperty(term.category))
                goTerms[term.category] += '<dd>' + '<a href="http://www.ebi.ac.uk/QuickGO/GTerm?id=' + term.id + '" target="_blank">' + term.id + '&nbsp;<i class="external icon"></i></a>&nbsp;' + term.name + '</dd>';
        });

        content = '<dt>Biological Process</dt>' + (goTerms['P'].length ? goTerms['P'] : '<dd>No terms assigned in this category.</dd>');
        content += '<dt>Molecular Function</dt>' + (goTerms['F'].length ? goTerms['F'] : '<dd>No terms assigned in this category.</dd>');
        content += '<dt>Cellular Component</dt>' + (goTerms['C'].length ? goTerms['C'] : '<dd>No terms assigned in this category.</dd>');
        document.querySelector('#go-terms + dl').innerHTML = content;

        this.getComments(entry.id, 2);
    };

    this.getComments = function (entryId, size) {
        getJSON('/api/entry/' + entryId + '/comments' + encodeParams({size: size}), (data, status) => {
            const div = this.section.querySelector('.comments');

            let html = '';
            data.results.forEach(comment => {
                if (comment.status)
                    html += '<div class="comment" data-id="'+ comment.id +'">' +
                        '<div class="content">' +
                        '<a class="author">'+ comment.author +'</a>' +
                        '<div class="metadata">' +
                        '<span class="date">'+ comment.date +'</span>' +
                        '<a><i class="remove icon"></i></a>' +
                        '</div>' +
                        '<div class="text">'+ comment.text +'</div></div></div>';
                else
                    html += '<div class="negative comment" data-id="'+ comment.id +'">' +
                        '<div class="content">' +
                        '<a class="author">'+ comment.author +'</a>' +
                        '<div class="metadata">' +
                        '<span class="date">'+ comment.date +'</span>' +
                        '</div>' +
                        '<div class="text">'+ comment.text +'</div></div></div>';
            });

            if (data.results.length < data.count)
                html += '<div class="actions"><a>View more comments</a></div>';

            div.querySelector('.comments-content').innerHTML = html;

            const form = div.querySelector('form');
            form.setAttribute('data-id', entryId);

            const textarea = form.querySelector('textarea');
            setClass(textarea.parentNode, 'error', false);
            textarea.value = null;

            const action = div.querySelector('.comments-content .actions a');
            if (action) {
                action.addEventListener('click', e => {
                    e.preventDefault();
                    this.getComments(entryId, null);
                });
            }

            Array.from(div.querySelectorAll('.comment .metadata a')).forEach(element => {
                element.addEventListener('click', e => {
                    e.preventDefault();

                    const commentId = e.target.closest('.comment').getAttribute('data-id');
                    const commentType = 'entry';
                    const modal = document.getElementById('confirm-modal');

                    modal.querySelector('.content').innerHTML = '<p>Flag this comment as invalid? This action <strong>cannot</strong> be undone.</p>';

                    $(modal).modal({
                        onApprove: function () {
                            postXhr('/api/comment/' + commentType + '/' + commentId, {
                                status: 0
                            }, data => {
                                if (data.status)
                                    self.getComments(entryId, size);
                                else {
                                    const modal = document.getElementById('error-modal');
                                    modal.querySelector('.content p').innerHTML = data.message;
                                    $(modal).modal('show');
                                }
                            });
                        },
                        onDeny: function () {}
                    }).modal('show');
                });
            });

            // Update sticky here, as it needs to be updated again if the user display more comments
            $(this.section.querySelector('.ui.sticky')).sticky({
                context: this.section.querySelector('.twelve.column')
            });
        });
    };
}


function MethodsSelectionView(root) {
    this.root = root;
    this.methods = [];
    const self = this;

    // Init
    (function () {
        self.root.querySelector('input[type=text]').addEventListener('keyup', e => {
            if (e.which === 13) {
                let render = false;
                e.target.value.trim().replace(/,/g, ' ').split(' ').forEach(id => {
                    if (id.length && self.methods.indexOf(id) === -1) {
                        self.methods.push(id);
                        render = true;
                    }
                });

                e.target.value = null;
                if (render)
                    self.render();
            }
        });

        Array.from(self.root.querySelectorAll('.links a:not([target="_blank"]')).forEach(element => {
            observeLink(element);
        });
    })();

    this.clear = function () {
        this.methods = [];
        return this;
    };


    this.add = function(methodId) {
        if (this.methods.indexOf(methodId) === -1)
            this.methods.push(methodId);
        return this;
    };

    this.render = function () {
        const div = this.root.querySelector('.ui.grid .column:last-child');
        let html = '';
        this.methods.forEach(m => {
            html += '<a class="ui basic label" data-id="' + m + '">' + m + '<i class="delete icon"></i></a>';
        });
        div.innerHTML = html;

        let nodes = div.querySelectorAll('a i.delete');
        for (let i = 0; i < nodes.length; ++i) {
            nodes[i].addEventListener('click', e => {
                const methodAc = e.target.parentNode.getAttribute('data-id');
                const newMethods = [];
                this.methods.forEach(m => {
                    if (m !== methodAc)
                        newMethods.push(m);
                });
                this.methods = newMethods;
                this.render();
            });
        }

        Array.from(this.root.querySelectorAll('.links a')).forEach(element => {
            element.setAttribute('href', '/methods/' + this.methods.join('/') + '/' + element.getAttribute('data-page'));
        });
    };

    this.toggle = function (page) {
        Array.from(this.root.querySelectorAll('.links a')).forEach(e => {
            setClass(e, 'active', e.getAttribute('data-page') === page);
        });
    };
}


function ComparisonViews(methodsIds) {
    const self = this;
    this.root = document.getElementById('comparison');
    this.sv = new MethodsSelectionView(this.root.querySelector('.methods'));
    this.methods = methodsIds;
    this.proteinList = {
        id: null,
        url: null,
        search: null,
        list: null,

        modal: document.getElementById('proteins-modal'),

        init: function () {
            const input = this.modal.querySelector('thead input');
            let counter = 0;

            input.addEventListener('keydown', e => {
                ++counter
            });

            input.addEventListener('keyup', e => {
                setTimeout(() => {
                    const value = e.target.value.trim();
                    if (!--counter && this.search !== value) {
                        const baseUrl = getPathName(this.url);
                        const params = getParams(this.url);
                        this.search = value.length ? value : null;
                        this.url = baseUrl + encodeParams(extendObj(params, {search: this.search, page: 1, pageSize: null}));
                        this.update();
                    }
                }, 350);
            });

            this.modal.querySelector('.actions a').addEventListener('click', e => {
                e.preventDefault();
                const url = e.target.getAttribute('href');
                $(this.modal).modal('hide');
                history.pushState({}, '', url);  // todo: do not store an empty object as going backwards will do nothing
                self.getMatches();
            });

            const button = this.modal.querySelector('.actions button');
            button.addEventListener('click', e => {
                const input = document.createElement('input');
                input.value = this.list.join(' ');
                input.style = 'position: absolute; left: -1000px; top: -1000px';
                document.body.appendChild(input);

                try {
                    input.select();
                    document.execCommand('copy');
                    setClass(button, 'green', true);
                    button.innerHTML = '<i class="smile icon"></i>&nbsp;Copied!';
                } catch (err) {
                    setClass(button, 'red', true);
                    button.innerHTML = '<i class="frown icon"></i>&nbsp;Could not copy.';
                } finally {
                    document.body.removeChild(input);
                }
            });
        },

        open: function (methodId, locSearch, header) {
            this.url = '/api/method/' + methodId + '/proteins' + locSearch;
            this.id = methodId;
            this.modal.querySelector('thead input').value = null;
            this.modal.querySelector('.header').innerHTML = header ? header : '';

            this.update((data) => {
                this.modal.querySelector('thead input').disabled = data.count <= data.pageInfo.pageSize;
            });
        },

        update: function (callback) {
            showDimmer(true);
            getJSON(this.url, data => {
                const svgWidth = 400;
                let html = '';

                this.list = data.list;

                data.results.forEach(protein => {
                    if (protein.isReviewed)
                        html += '<tr><td class="nowrap"><a target="_blank" href="'+ protein.link +'"><i class="star icon"></i>'+ protein.id +'</a></td>';
                    else
                        html += '<tr><td><a target="_blank" href="'+ protein.link +'">'+ protein.id +'</a></td>';

                    html += '<td>'+ protein.name +'</td><td>'+ protein.taxon.fullName +'</td>';

                    const paddingLeft = 5;
                    const paddingRight = 20;
                    const width = Math.floor(protein.length * (svgWidth - (paddingLeft + paddingRight)) / data.maxLength);

                    html += '<td><svg class="matches" width="' + svgWidth + '" height="30" version="1.1" baseProfile="full" xmlns="http://www.w3.org/2000/svg">' +
                        '<line x1="' + paddingLeft + '" y1="20" x2="'+width+'" y2="20" />' +
                        '<text x="'+ (paddingLeft + width + 2) +'" y="20">'+ protein.length +'</text>';

                    protein.matches.forEach(match => {
                        const x = Math.round(match.start * width / protein.length) + paddingLeft;
                        const w = Math.round((match.end - match.start) * width / protein.length);
                        html += '<g><rect x="'+ x +'" y="15" width="'+ w +'" height="10" rx="1" ry="1" style="fill: #607D8B;"/>' +
                            '<text x="'+ x +'" y="10">'+ match.start +'</text>' +
                            '<text x="'+ (x + w) +'" y="10">'+ match.end +'</text></g>'
                    });

                    html += '</svg></tr>';
                });

                this.modal.querySelector('tbody').innerHTML = html;

                const page = data.pageInfo.page;
                const pageSize = data.pageInfo.pageSize;
                const lastPage = Math.ceil(data.count / pageSize);

                this.modal.querySelector('thead span').innerHTML = (data.count ? (page - 1) * pageSize + 1 : 0) + ' - ' + Math.min(page * pageSize, data.count) + ' of ' + data.count.toLocaleString() + ' entries';

                // Pagination
                html = '';

                const baseUrl = getPathName(this.url);
                const params = getParams(this.url);

                if (page === 1)
                    html += '<a class="icon disabled item"><i class="left chevron icon"></i></a><a class="active item">1</a>';
                else
                    html += '<a class="icon item" href="'+ (baseUrl + encodeParams(extendObj(params, {page: page - 1, pageSize: pageSize}))) +'"><i class="left chevron icon"></i></a><a class="item" href="'+ (baseUrl + encodeParams(extendObj(params, {page: 1, pageSize: pageSize}))) +'">1</a>';

                let ellipsisBefore = false;
                let ellipsisAfter = false;
                for (let i = 2; i < lastPage; ++i) {
                    if (i === page)
                        html += '<a class="active item">'+ i +'</a>';
                    else if (Math.abs(i - page) === 1)
                        html += '<a class="item" href="'+ (baseUrl + encodeParams(extendObj(params, {page: i, pageSize: pageSize}))) +'">'+ i +'</a>';
                    else if (i < page && !ellipsisBefore) {
                        html += '<div class="disabled item">&hellip;</div>';
                        ellipsisBefore = true;
                    } else if (i > page && !ellipsisAfter) {
                        html += '<div class="disabled item">&hellip;</div>';
                        ellipsisAfter = true;
                    }
                }

                if (lastPage > 1) {
                    if (page === lastPage)
                        html += '<a class="active item">'+ lastPage +'</a>';
                    else
                        html += '<a class="item" href="'+ (baseUrl + encodeParams(extendObj(params, {page: lastPage, pageSize: pageSize}))) +'">'+ lastPage +'</a>'
                }


                if (page === lastPage || !lastPage)
                    html += '<a class="icon disabled item"><i class="right chevron icon"></i></a>';
                else
                    html += '<a class="icon item" href="'+ (baseUrl + encodeParams(extendObj(params, {page: page + 1, pageSize: pageSize}))) +'"><i class="right chevron icon"></i></a>';

                const pagination = this.modal.querySelector('.pagination');
                pagination.innerHTML = html;
                Array.from(pagination.querySelectorAll('a[href]'), element => {
                    element.addEventListener('click', e => {
                        e.preventDefault();
                        setClass(pagination.querySelector('a.active'), 'active', false);
                        setClass(element, 'active', true);
                        this.url = element.href;
                        this.update();
                    });
                });

                const actionLink = this.modal.querySelector('.actions a');
                actionLink.setAttribute(
                    'href',
                    '/methods/' + this.id + '/matches' + encodeParams(
                        extendObj(getParams(this.url), {search: null, page: 1, pageSize: null}),
                        true
                    )
                );
                observeLink(actionLink);

                // Reset copy button
                const copyBtn = this.modal.querySelector('.actions button');
                copyBtn.innerHTML = '<i class="copy icon"></i>&nbsp;Copy proteins';
                setClass(copyBtn, 'green', false);
                setClass(copyBtn, 'red', false);

                showDimmer(false);
                $(this.modal).modal('show');

                if (callback)
                    callback(data);
            });
        }
    };

    // Init
    (function () {
        Array.from(document.querySelectorAll('#descriptions input[type=radio]')).forEach(radio => {
            radio.addEventListener('change', e => {
                if (e.target.checked) {
                    const baseUrl = getPathName(history.state.url);
                    const params = extendObj(getParams(history.state.url), {db: e.target.value});
                    history.pushState({}, '', baseUrl + encodeParams(params));
                    self.getDescriptions();
                }
            });
        });

        Array.from(document.querySelectorAll('#go input[type=checkbox][name=aspect]')).forEach((cbox, i, cboxes) => {
            cbox.addEventListener('change', e => {
                const aspects = [];
                cboxes.forEach(cbox => {
                    if (cbox.checked)
                        aspects.push(cbox.value);
                });
                const baseUrl = getPathName(history.state.url);
                const params = extendObj(getParams(history.state.url), {aspect: aspects.length ? aspects.join(',') : null});
                history.pushState({}, '', baseUrl + encodeParams(params));
                self.getGoTerms();
            });
        });

        Array.from(document.querySelectorAll('#taxonomy .tabular.menu .item')).forEach(item => {
            item.addEventListener('click', e => {
                const baseUrl = getPathName(history.state.url);
                const params = extendObj(getParams(history.state.url), {rank: item.getAttribute('data-rank')});
                history.pushState({}, '', baseUrl + encodeParams(params));
                self.getTaxonomy();
            });
        });

        self.proteinList.init();

        self.methods.forEach(id => {
            self.sv.add(id)
        });
        self.sv.render();
    })();

    this.setMethods = function (methods) {
        this.methods = methods;
        this.sv.clear();
        this.methods.forEach(id => {
            this.sv.add(id)
        });
        this.sv.render();
    };

    this.toggle = function (id) {
        this.sv.toggle(id);
        Array.from(this.root.querySelectorAll('.ui.compare.segment')).forEach(element => {
            setClass(element, 'hidden', element.id !== id);
        });
    };

    this.getMatrices = function () {
        const url = location.pathname + location.search;

        showDimmer(true);
        getJSON('/api' + url, (data, status) => {
            try {
                history.replaceState({page: 'matrix', data: data, methods: this.methods, url: url}, '', url);
            } catch (err) {
                history.replaceState({page: 'matrix', data: null, methods: this.methods, url: url}, '', url);
            }
            this.renderMatrices(data);
            showDimmer(false);
        });
    };

    this.renderMatrices = function (data) {
        this.toggle('matrices');
        document.title = 'Match matrices (' + this.methods.join(', ') + ') | Pronto';

        let html1 = '<thead><tr><th></th>';
        let html2 = '<thead><tr><th></th>';
        this.methods.forEach(methodAc => {
            html1 += '<th>' + methodAc + '</th>';
            html2 += '<th>' + methodAc + '</th>';
        });

        html1 += '</thead><tbody>';
        html2 += '</thead><tbody>';

        this.methods.forEach(methodAcY => {
            html1 += '<tr><td>'+ methodAcY +'</td>';
            html2 += '<tr><td>'+ methodAcY +'</td>';

            this.methods.forEach(methodAcX => {
                if (data.matrix.hasOwnProperty(methodAcX) && data.matrix[methodAcX].methods.hasOwnProperty(methodAcY)) {
                    let count, i, color;

                    count = data.matrix[methodAcX].methods[methodAcY].over;
                    i = Math.floor(count / data.max * _colors.length);
                    color = _colors[Math.min(i, _colors.length - 1)];

                    if (count && methodAcX !== methodAcY)
                        html1 += '<td style="background-color: '+ color +'"><a data-x="'+ methodAcX +'" data-y="'+ methodAcY +'" href="#">' + count + '</a></td>';
                    else
                        html1 += '<td style="background-color: '+ color +'">' + count + '</td>';

                    count = data.matrix[methodAcX].methods[methodAcY].coloc;
                    i = Math.floor(count / data.max * _colors.length);
                    color = _colors[Math.min(i, _colors.length - 1)];

                    if (count && methodAcX !== methodAcY)
                        html2 += '<td style="background-color: '+ color +'"><a data-x="'+ methodAcX +'" data-y="'+ methodAcY +'" href="#">' + count + '</a></td>';
                    else
                        html2 += '<td style="background-color: '+ color +'">' + count + '</td>';
                } else {
                    html1 += '<td style="background-color: '+ _colors[0] +'"><a data-x="'+ methodAcX +'" data-y="'+ methodAcY +'" href="#">0</a></td>';
                    html2 += '<td style="background-color: '+ _colors[0] +'"><a data-x="'+ methodAcX +'" data-y="'+ methodAcY +'" href="#">0</a></td>';
                }
            });

            html1 += '</tr>';
            html2 += '</tr>';
        });

        const div = document.getElementById('matrices');
        const tables = div.querySelectorAll('table');

        tables[0].innerHTML = html1 + '</tbody>';
        tables[1].innerHTML = html2 + '</tbody>';

        Array.from(div.querySelectorAll('tbody a[data-x][data-y]')).forEach(element => {
            element.addEventListener('click', e => {
                e.preventDefault();
                const methodAcX = e.target.getAttribute('data-x');
                const methodAcY = e.target.getAttribute('data-y');
                const statsX = data.matrix.hasOwnProperty(methodAcX) && data.matrix[methodAcX].methods.hasOwnProperty(methodAcX) ? data.matrix[methodAcX].methods[methodAcX] : null;
                const statsY = data.matrix.hasOwnProperty(methodAcY) && data.matrix[methodAcY].methods.hasOwnProperty(methodAcY) ? data.matrix[methodAcY].methods[methodAcY] : null;
                const statsXY = data.matrix.hasOwnProperty(methodAcX) && data.matrix[methodAcX].methods.hasOwnProperty(methodAcY) ? data.matrix[methodAcX].methods[methodAcY] : null;

                let html = '<h5 class="ui header">Proteins</h5><table class="ui very basic small compact table"><tbody>';

                html += '<tr><td>Overlapping</td><td class="right aligned">'+ (statsXY !== null ? statsXY.over : 0) +'</td></tr>';
                html += '<tr><td>Average overlap</td><td class="right aligned">'+ (statsXY !== null ? statsXY.avgOver : '') +'</td></tr>';

                if (statsXY !== null)
                    html += '<tr><td>In both signatures</td><td class="right aligned"><a href="/methods/'+ methodAcX + '/' + methodAcY +'/matches?force='+ methodAcX + ',' + methodAcY +'">'+ statsXY.coloc +'</a></td></tr>';
                else
                    html += '<tr><td>In both signatures</td><td class="right aligned">0</td></tr>';

                html += '<tr><td>In either signatures</td><td class="right aligned"><a href="/methods/'+ methodAcX + '/' + methodAcY +'/matches">'+ (statsX.coloc + statsY.coloc - (statsXY !== null ? statsXY.coloc : 0)) +'</a></td></tr>';
                html += '<tr><td>In '+ methodAcX +' only</td><td class="right aligned"><a href="/methods/'+ methodAcX + '/matches?exclude='+ methodAcY +'">'+ (statsX.coloc - (statsXY !== null ? statsXY.coloc : 0)) +'</a></td></tr>';
                html += '<tr><td>In '+ methodAcY +' only</td><td class="right aligned"><a href="/methods/'+ methodAcY + '/matches?exclude='+ methodAcX +'">'+ (statsY.coloc - (statsXY !== null ? statsXY.coloc : 0)) +'</a></td></tr>';
                html += '<tr><td>In '+ methodAcX +'</td><td class="right aligned"><a href="/methods/'+ methodAcX + '/matches">'+ statsX.coloc +'</a></td></tr>';
                html += '<tr><td>In '+ methodAcY +'</td><td class="right aligned"><a href="/methods/'+ methodAcY + '/matches">'+ statsY.coloc +'</a></td></tr>';

                div.querySelector('.column:last-child').innerHTML = html + '</tbody></table>';
            });
        });

        setClass(div, 'hidden', false);
    };

    this.getGoTerms = function () {
        const url = location.pathname + location.search;

        showDimmer(true);
        getJSON('/api' + url, (data, status) => {
            try {
                history.replaceState({page: 'go', data: data, methods: this.methods, url: url}, '', url);
            } catch (err) {
                history.replaceState({page: 'go', data: null, methods: this.methods, url: url}, '', url);
            }
            this.renderGoTerms(data);
            showDimmer(false);
        });
    };

    this.renderGoTerms = function (data) {
        this.toggle('go');
        document.title = 'GO terms (' + this.methods.join(', ') + ') | Pronto';

        let html = '<thead><tr>' +
            '<th>'+ data.results.length +' terms</th>' +
            '<th class="center aligned"><button class="ui fluid very compact blue icon button"><i class="sitemap icon"></i></button></th>';
        this.methods.forEach(methodId => { html += '<th colspan="2" class="center aligned">' + methodId + '</th>'; });
        html += '</thead><tbody>';

        data.results.forEach(term => {
            html += '<tr data-filter="'+ term.id +'" data-search="?term=' + term.id + '">' +
                '<td class="nowrap">' +
                '<span class="ui circular small label aspect-'+ term.aspect +'">'+ term.aspect +'</span>' +
                '<a target="_blank" href="https://www.ebi.ac.uk/QuickGO/term/'+ term.id +'">'+ term.id + ':&nbsp;' + term.value +'&nbsp;<i class="external icon"></i></a></td>' +
                '<td class="collapsing center aligned">'+ renderCheckbox(term.id, false) +'</td>';

            this.methods.forEach(methodId => {
                if (term.methods.hasOwnProperty(methodId) && data.methods.hasOwnProperty(methodId)) {
                    const method = term.methods[methodId];
                    const i = Math.floor(method.proteins / data.methods[methodId] * _colors.length);
                    const color = _colors[Math.min(i, _colors.length - 1)];
                    html += '<td style="background-color: '+ color +';"><a href="#" data-method="'+ methodId +'">' + method.proteins + '</a></td>' +
                        '<td class="collapsing"><a data-term="'+ term.id +'" data-method2="'+ methodId +'" class="ui basic label"><i class="book icon"></i>&nbsp;'+ method.references +'</a></td>';
                } else
                    html += '<td colspan="2"></td>';

            });

            html += '</tr>';
        });
        html += '</tbody>';

        const div = document.getElementById('go');
        Array.from(div.querySelectorAll('input[type=checkbox]')).forEach(cbox => {
            cbox.checked = data.aspects.indexOf(cbox.value) !== -1;
        });

        const table = div.querySelector('table');
        table.innerHTML = html;

        observeLinks(div, (methodId, filter, search) => {
            const header = '<em>' + methodId + '</em> proteins<div class="sub header">GO term: <em>'+ filter +'</em></div>';
            this.proteinList.open(methodId, search, header);
        });

        Array.from(div.querySelectorAll('a[data-term][data-method2]')).forEach(element => {
            element.addEventListener('click', e => {
                e.preventDefault();
                const goId = e.target.getAttribute('data-term');
                const methodId = e.target.getAttribute('data-method2');
                showDimmer(true);
                getJSON('/api/method/' + methodId + '/references/' + goId, (data, status) => {
                    const modal = document.getElementById('go-references-modal');
                    let html = '';

                    if (data.count) {
                        data.results.forEach(ref => {
                            html += '<li class="item">' +
                                '<div class="header"><a target="_blank" href="http://europepmc.org/abstract/MED/'+ ref.id +'">'+ ref.id +'&nbsp;<i class="external icon"></i></a></div><div class="description">'+ nvl(ref.title, '') + ' ' + nvl(ref.date, '') +'</div></li>';
                        });
                    } else {
                        html = '<div class="ui negative message"><div class="header">No references found</div><p>This entry does not have any references in the literature.</p></div>';
                    }

                    modal.querySelector('.ui.header').innerHTML = '<i class="book icon"></i>' + goId + ' / ' + methodId;
                    modal.querySelector('.content ol').innerHTML = html;
                    modal.querySelector('.actions a').setAttribute('href', 'https://www.ebi.ac.uk/QuickGO/term/' + goId);
                    showDimmer(false);
                    $(modal).modal('show');
                });
            });
        });

        table.querySelector('thead button').addEventListener('click', e => {
            const terms = [];
            Array.from(table.querySelectorAll('input[type=checkbox]:checked')).forEach(cbox => {
                terms.push(cbox.name);
            });

            if (terms.length) {
                const modal = document.getElementById('go-chart-modal');
                modal.querySelector('.content').innerHTML = '<img class="image" alt="'+ terms.join(',') +'" src="https://www.ebi.ac.uk/QuickGO/services/ontology/go/terms/' + terms.join(',') + '/chart">';
                setTimeout(function () {
                    $(modal).modal('show');
                }, 500);
            }
        });

        setClass(div, 'hidden', false);
    };

    this.getSwissProtComments = function () {
        const url = location.pathname + location.search;

        showDimmer(true);
        getJSON('/api' + url, (data, status) => {
            try {
                history.replaceState({page: 'comments', data: data, methods: this.methods, url: url}, '', url);
            } catch (err) {
                history.replaceState({page: 'comments', data: null, methods: this.methods, url: url}, '', url);
            }
            this.renderSwissProtComments(data);
            showDimmer(false);
        });
    };

    this.renderSwissProtComments = function (data) {
        this.toggle('comments');
        document.title = 'Swiss-Prot comments (' + this.methods.join(', ') + ') | Pronto';

        const div = document.getElementById('comments');
        const dropdown = div.querySelector('.ui.dropdown');
        setSelected(dropdown, data.topic.id.toString());

        $(dropdown).dropdown({
            onChange: function(value, text, $selectedItem) {
                const baseUrl = getPathName(history.state.url);
                const params = extendObj(getParams(history.state.url), {topic: value});
                history.pushState({}, '', baseUrl + encodeParams(params));
                self.getSwissProtComments();
            }
        });

        let html = '<thead><tr><th colspan="2">'+ data.results.length +' comments</th>';
        this.methods.forEach(methodId => { html += '<th>' + methodId + '</th>'; });

        html += '</thead><tbody>';

        data.results.forEach(comment => {
            html += '<tr data-filter="'+ comment.value +'" data-search="?comment=' + comment.id + '&topic='+ data.topic.id +'">' +
                '<td>'+ comment.value +'</td>' +
                '<td>'+ comment.max +'</td>';

            this.methods.forEach(methodId => {
                if (comment.methods.hasOwnProperty(methodId)) {
                    const i = Math.floor(comment.methods[methodId] / comment.max * _colors.length);
                    const color = _colors[Math.min(i, _colors.length - 1)];
                    html += '<td style="background-color: '+ color +'"><a href="#" data-method="'+ methodId +'">' + comment.methods[methodId] + '</a></td>';
                } else
                    html += '<td></td>';

            });

            html += '</tr>';
        });

        div.querySelector('table').innerHTML = html + '</tbody>';

        observeLinks(div, (methodId, filter, search) => {
            const header = '<em>' + methodId + '</em> proteins<div class="sub header">Comment: <em>'+ filter +'</em></div>';
            this.proteinList.open(methodId, search, header);
        });

        setClass(div, 'hidden', false);
    };

    this.getDescriptions = function () {
        const url = location.pathname + location.search;

        showDimmer(true);
        getJSON('/api' + url, (data, status) => {
            try {
                history.replaceState({page: 'descriptions', data: data, methods: this.methods, url: url}, '', url);
            } catch (err) {
                history.replaceState({page: 'descriptions', data: null, methods: this.methods, url: url}, '', url);
            }
            this.renderDescriptions(data);
            showDimmer(false);
        });
    };

    this.renderDescriptions = function (data) {
        this.toggle('descriptions');
        document.title = 'UniProt descriptions (' + this.methods.join(', ') + ') | Pronto';

        let html = '<thead><tr><th colspan="2">'+ data.results.length +' descriptions</th>';
        this.methods.forEach(methodAc => { html += '<th>' + methodAc + '</th>'; });

        html += '</thead><tbody>';

        data.results.forEach(desc => {
            html += '<tr data-filter="'+ desc.value +'" data-search="?description=' + desc.id + '&db='+ data.database +'">' +
                '<td>'+ desc.value +'</td>' +
                '<td>' + desc.max + '</td>';

            this.methods.forEach(methodId => {
                if (desc.methods.hasOwnProperty(methodId)) {
                    const i = Math.floor(desc.methods[methodId] / desc.max * _colors.length);
                    const color = _colors[Math.min(i, _colors.length - 1)];
                    html += '<td style="background-color: '+ color +'"><a href="#" data-method="'+ methodId +'">' + desc.methods[methodId] + '</a></td>';
                } else
                    html += '<td></td>';

            });

            html += '</tr>';
        });

        const div = document.getElementById('descriptions');
        div.querySelector('table').innerHTML = html + '</tbody>';

        observeLinks(div, (methodId, filter, search) => {
            const header = '<em>' + methodId + '</em> proteins<div class="sub header">Description: <em>'+ filter +'</em></div>';
            this.proteinList.open(methodId, search, header);
        });

        Array.from(div.querySelectorAll('td:first-child a[data-id]')).forEach(element => {
            element.addEventListener('click', e => {
                e.preventDefault();
                const descId = e.target.getAttribute('data-id');
                const desc = e.target.closest('tr').getAttribute('data-filter');

                showDimmer(true);
                getJSON('/api/description/' + descId, (data, status) => {
                    let html = '';

                    data.results.forEach(protein => {
                        html += '<tr><td><a href="/protein/'+ protein.id +'">'+ (protein.isReviewed ? '<i class="star icon"></i>&nbsp;' : '') + protein.id +'</a></td><td>'+ protein.shortName +'</td><td>'+ protein.organism +'</td></tr>';
                    });

                    const modal = document.getElementById('descriptions-modal');
                    modal.querySelector('.header').innerHTML = data.count + ' proteins<div class="sub header">'+ desc +'</div>';
                    modal.querySelector('tbody').innerHTML = html;
                    $(modal).modal('show');

                    showDimmer(false);

                });

            });
        });

        div.querySelector('input[type=radio][value="'+ nvl(data.database, '') +'"]').checked = true;
        setClass(div, 'hidden', false);
    };

    this.getTaxonomy = function () {
        const url = location.pathname + location.search;

        showDimmer(true);
        getJSON('/api' + url, (data, status) => {
            try {
                history.replaceState({page: 'taxonomy', data: data, methods: this.methods, url: url}, '', url);
            } catch (err) {
                history.replaceState({page: 'taxonomy', data: null, methods: this.methods, url: url}, '', url);
            }
            this.renderTaxonomy(data);
            showDimmer(false);
        });
    };

    this.renderTaxonomy = function (data) {
        const div = document.getElementById('taxonomy');
        this.toggle('taxonomy');
        document.title = 'Taxonomic origin (' + this.methods.join(', ') + ') | Pronto';

        const items = Array.from(document.querySelectorAll('#taxonomy .tabular.menu .item'));
        items.forEach(item => {
            setClass(item, 'active', item.getAttribute('data-rank') === data.rank);
        });

        // const dropdown = div.querySelector('.ui.dropdown');
        // setSelected(dropdown, data.rank);
        //
        // $(dropdown).dropdown({
        //     onChange: function(value, text, $selectedItem) {
        //         const baseUrl = getPathName(history.state.url);
        //         const params = extendObj(getParams(history.state.url), {rank: value});
        //         history.pushState({}, '', baseUrl + encodeParams(params));
        //         self.getTaxonomy();
        //     }
        // });

        let html = '';
        if (data.taxon.id === 1)
            html += '<thead><tr><th>'+ data.taxon.fullName +'</th>';
        else
            html += '<thead><tr><th><a class="ui basic label">'+ data.taxon.fullName +'<i class="delete icon"></i></a></th>';
        this.methods.forEach(methodAc => { html += '<th>' + methodAc + '</th>'; });

        html += '</thead><tbody>';

        data.results.forEach(taxon => {
            html += '<tr data-filter="'+ taxon.fullName +'" data-search="?taxon='+ taxon.id +'"><td><a href="/methods/'+ this.methods.join('/') +'/taxonomy?taxon='+ taxon.id + '&rank=' + data.rank +'">'+ taxon.fullName +'</a></td>';

            this.methods.forEach(methodId => {
                if (taxon.methods.hasOwnProperty(methodId)) {
                    const i = Math.floor(taxon.methods[methodId] / data.max * _colors.length);
                    const color = _colors[Math.min(i, _colors.length - 1)];
                    html += '<td style="background-color: '+ color +'"><a href="#" data-method="'+ methodId +'">' + taxon.methods[methodId] + '</a></td>';
                } else
                    html += '<td></td>';

            });

            html += '</tr>';
        });

        div.querySelector('table').innerHTML = html + '</tbody>';

        observeLinks(div, (methodId, filter, search) => {
            const header = '<em>' + methodId + '</em> proteins<div class="sub header">Organism: <em>'+ filter +'</em></div>';
            this.proteinList.open(methodId, search, header);
        });

        if (data.taxon.id !== 1) {
            div.querySelector('table a.label i.delete').addEventListener('click', e => {
                const baseUrl = getPathName(history.state.url);
                const params = extendObj(getParams(history.state.url), {taxon: null, rank: null});
                history.pushState({}, '', baseUrl + encodeParams(params));
                self.getTaxonomy();
            });
        }

        setClass(div, 'hidden', false);
    };

    this.getMatches = function () {
        const url = location.pathname + location.search;

        showDimmer(true);
        getJSON('/api' + url, (data, status) => {
            try {
                history.replaceState({page: 'matches', data: data, methods: this.methods, url: url}, '', url);
            } catch (err) {
                history.replaceState({page: 'matches', data: null, methods: this.methods, url: url}, '', url);
            }
            this.renderMatches(data);
        });
    };

    this.renderMatches = function (data) {
        const div = document.getElementById('matches');
        this.toggle('matches');
        document.title = 'Overlapping proteins (' + this.methods.join(', ') + ') | Pronto';

        div.querySelector('.statistic .value').innerHTML = data.count.toLocaleString();
        const svgWidth = 700;

        const baseUrl = getPathName(history.state.url);
        const params = getParams(history.state.url);

        let html = '';
        data.proteins.forEach((protein, i) => {
            html += '<div class="ui segment">' +
                '<span class="ui red ribbon label">' + (protein.isReviewed ? '<i class="star icon"></i>&nbsp;' : '') + protein.id + '</a></span>' +
                '<a target="_blank" href="'+ protein.link +'">'+ protein.description +'&nbsp;<i class="external icon"></i></a>';

            const uncondensedURL = baseUrl + encodeParams(extendObj(params, {code: protein.code, page: null, pageSize: null}), true);

            html += '<div><div class="ui horizontal list">' +
                '<div class="item">' +
                '<div class="content">' +
                '<div class="ui sub header">Proteins</div><a href="'+ uncondensedURL +'" ">'+ protein.count.toLocaleString() +'</a>' +
                '</div>' +
                '</div>' +
                '<div class="item">' +
                '<div class="content">' +
                '<div class="ui sub header">Organism</div><em>'+ protein.organism +'</em>' +
                '</div>' +
                '</div>' +
                '</div></div>';

            html += '<table class="ui very basic compact table"><tbody>';

            protein.methods.forEach((method, j) => {
                html += method.isSelected ? '<tr class="selected">' : '<tr>';

                if (method.entryId)
                    html += '<td class="nowrap"><a href="/entry/'+ method.entryId +'">'+ method.entryId +'</a></td>';
                else
                    html += '<td></td>';

                html += '<td class="nowrap"><a target="_blank" href="'+ method.db.link +'">'+ method.id + '&nbsp;<i class="external icon"></i></a></td>' +
                    '<td>'+ method.name + '</td>' +
                    '<td>'+ (method.isCandidate ? '&nbsp;<i class="checkmark box icon"></i>' : '') +'</td>';

                const paddingLeft = 5;
                const paddingRight = 30;
                const width = Math.floor(protein.length * (svgWidth - (paddingLeft + paddingRight)) / data.maxLength);

                html += '<td><svg class="matches" width="' + svgWidth + '" height="30" version="1.1" baseProfile="full" xmlns="http://www.w3.org/2000/svg">' +
                    '<line x1="'+ paddingLeft +'" y1="20" x2="'+width+'" y2="20" />' +
                    '<text x="'+ (paddingLeft + width + 2) +'" y="20">'+ protein.length +'</text>';

                method.matches.forEach(match => {
                    const x = Math.round(match.start * width / protein.length) + paddingLeft;
                    const w = Math.round((match.end - match.start) * width / protein.length);
                    html += '<g><rect x="'+ x +'" y="15" width="'+ w +'" height="10" rx="1" ry="1" style="fill: '+ method.db.color +';"/>' +
                        '<text x="'+ x +'" y="10">'+ match.start +'</text>' +
                        '<text x="'+ (x + w) +'" y="10">'+ match.end +'</text></g>'
                });

                html += '</svg></td></tr>';
            });

            html += '</tbody></table></div>';
        });

        div.querySelector('.segments').innerHTML = html;

        // Pagination
        html = '';
        const page = data.pageInfo.page;
        const pageSize = data.pageInfo.pageSize;
        const lastPage = Math.ceil(data.count / pageSize);

        const genLink = function(page) {
            return baseUrl + encodeParams(extendObj(params, {page: page, pageSize: pageSize}))
        };

        if (page === 1)
            html += '<a class="icon disabled item"><i class="left chevron icon"></i></a><a class="active item">1</a>';
        else
            html += '<a class="icon item" href="'+ genLink(page-1)  +'"><i class="left chevron icon"></i></a><a class="item" href="'+ genLink(1)  +'">1</a>';

        let ellipsisBefore = false;
        let ellipsisAfter = false;
        for (let i = 2; i < lastPage; ++i) {
            if (i === page)
                html += '<a class="active item">'+ i +'</a>';
            else if (Math.abs(i - page) === 1)
                html += '<a class="item" href="'+ genLink(i) +'">'+ i +'</a>';
            else if (i < page && !ellipsisBefore) {
                html += '<div class="disabled item">&hellip;</div>';
                ellipsisBefore = true;
            } else if (i > page && !ellipsisAfter) {
                html += '<div class="disabled item">&hellip;</div>';
                ellipsisAfter = true;
            }
        }

        if (lastPage > 1) {
            if (page === lastPage)
                html += '<a class="active item">'+ lastPage +'</a>';
            else
                html += '<a class="item" href="'+ genLink(lastPage) +'">'+ lastPage +'</a>'
        }


        if (page === lastPage || !lastPage)
            html += '<a class="icon disabled item"><i class="right chevron icon"></i></a>';
        else
            html += '<a class="icon item" href="'+ genLink(page + 1) +'"><i class="right chevron icon"></i></a>';

        const pagination = div.querySelector('.pagination');
        pagination.innerHTML = html;

        const elements = pagination.querySelectorAll('a[href]');
        for (let i  = 0; i < elements.length; ++i) {
            elements[i].addEventListener('click', e => {
                e.preventDefault();
                setClass(pagination.querySelector('a.active'), 'active', false);
                setClass(elements[i], 'active', true);
                history.pushState({}, '', elements[i].href);
                self.getMatches();
            });
        }

        setClass(div, 'hidden', false);
        showDimmer(false);
    };
}


function DatabaseView() {
    this.section = document.getElementById('methods');
    const self = this;
    this.pageSize = 20;

    // Init
    (function () {
        function initInput(input, initValue, callback) {
            let value = initValue;
            let counter = 0;

            if (value) input.value = value;

            input.addEventListener('keydown', e => {
                ++counter;
            });

            input.addEventListener('keyup', e => {
                setTimeout(() => {
                    if (!--counter && value !== e.target.value) {
                        value = e.target.value;
                        callback(value.length ? value : null);
                    }
                }, 350);
            });
        }

        const params = getParams();

        initInput(document.querySelector('#methods-all thead input'), params.search, value => {
            const pathname = getPathName(history.state.url);
            const params = extendObj(getParams(history.state.url), {search: value, page: 1, pageSize: self.pageSize});
            history.pushState({}, '', pathname + encodeParams(params));
            self.get();
        });

        initInput(document.querySelector('#methods-unintegrated thead input'), params.search, value => {
            const pathname = getPathName(history.state.url);
            const params = extendObj(getParams(history.state.url), {search: value, page: 1, pageSize: self.pageSize});
            history.pushState({}, '', pathname + encodeParams(params));
            self.get();
        });

        self.section.querySelector('.ui.comments form button').addEventListener('click', e => {
            e.preventDefault();
            const form = e.target.closest('form');
            const methodId = form.getAttribute('data-id');
            const textarea = form.querySelector('textarea');

            postXhr('/api/method/'+ methodId +'/comment/', {
                comment: textarea.value.trim()
            }, data => {
                setClass(textarea.closest('.field'), 'error', !data.status);

                if (!data.status) {
                    const modal = document.getElementById('error-modal');
                    modal.querySelector('.content p').innerHTML = data.message;
                    $(modal).modal('show');
                } else {
                    self.get();  // need this to get the latest comment in the table
                    getMethodComments(methodId, form.closest('.ui.comments'), 2);
                }
            });
        });

        Array.from(document.querySelectorAll('#methods-all input[type=radio]')).forEach(radio => {
            radio.addEventListener('change', e => {
                const obj = {};
                obj[radio.name] = radio.value;
                const baseUrl = getPathName(history.state.url);
                const params = extendObj(getParams(history.state.url), obj);
                history.pushState({}, '', baseUrl + encodeParams(params));
                self.get();
            });
        });

        Array.from(document.querySelectorAll('#methods-unintegrated input[type=radio]')).forEach(radio => {
            radio.addEventListener('change', e => {
                const obj = {};
                obj[radio.name] = radio.value;
                const baseUrl = getPathName(history.state.url);
                const params = extendObj(getParams(history.state.url), obj);
                history.pushState({}, '', baseUrl + encodeParams(params));
                self.get();
            });
        });
    })();

    this.get = function () {
        const url = location.pathname + location.search;

        showDimmer(true);
        getJSON('/api' + url, (data, status) => {
            const params = getParams(url);
            history.replaceState({data: data, page: 'methods', url: url, unintegrated: params.unintegrated}, '', url);

            const message = this.section.querySelector('.ui.message');

            if (!data.database) {
                message.innerHTML = '<div class="header">Sorry, no results for your search term.</div>';
                setClass(message, 'hidden', false);
                ['all-methods', 'unintegrated-methods'].forEach(element => setClass(element, 'hidden', true));
                return;
            }

            setClass(message, 'hidden', true);

            if (params.unintegrated !== undefined) {
                this.renderUnintegratedMethods(data);
            } else {
                this.renderMethods(data);
            }
            showDimmer(false);
        });
    };

    this.generatePagination = function (div, page, pageSize, count) {
        this.pageSize = pageSize;
        const lastPage = Math.ceil(count / pageSize);
        const baseUrl = getPathName(history.state.url);
        const params = getParams(history.state.url);
        let html = '';

        const genLink = function(page) {
            return baseUrl + encodeParams(extendObj(params, {page: page, pageSize: pageSize}))
        };

        if (page === 1)
            html += '<a class="icon disabled item"><i class="left chevron icon"></i></a><a class="active item">1</a>';
        else
            html += '<a class="icon item" href="'+ genLink(page-1)  +'"><i class="left chevron icon"></i></a><a class="item" href="'+ genLink(1)  +'">1</a>';

        let ellipsisBefore = false;
        let ellipsisAfter = false;
        for (let i = 2; i < lastPage; ++i) {
            if (i === page)
                html += '<a class="active item">'+ i +'</a>';
            else if (Math.abs(i - page) === 1)
                html += '<a class="item" href="'+ genLink(i) +'">'+ i +'</a>';
            else if (i < page && !ellipsisBefore) {
                html += '<div class="disabled item">&hellip;</div>';
                ellipsisBefore = true;
            } else if (i > page && !ellipsisAfter) {
                html += '<div class="disabled item">&hellip;</div>';
                ellipsisAfter = true;
            }
        }

        if (lastPage > 1) {
            if (page === lastPage)
                html += '<a class="active item">'+ lastPage +'</a>';
            else
                html += '<a class="item" href="'+ genLink(lastPage)  +'">'+ lastPage +'</a>'
        }


        if (page === lastPage || !lastPage)
            html += '<a class="icon disabled item"><i class="right chevron icon"></i></a>';
        else
            html += '<a class="icon item" href="'+ genLink(page + 1)  +'"><i class="right chevron icon"></i></a>';

        const pagination = div.querySelector('.pagination');
        pagination.innerHTML = html;
        div.querySelector('thead span').innerHTML = (count ? (page - 1) * pageSize + 1 : 0) + ' - ' + Math.min(page * pageSize, count) + ' of ' + count.toLocaleString() + ' entries';

        const elements = pagination.querySelectorAll('a[href]');
        for (let i  = 0; i < elements.length; ++i) {
            elements[i].addEventListener('click', e => {
                e.preventDefault();
                setClass(pagination.querySelector('a.active'), 'active', false);
                setClass(elements[i], 'active', true);
                history.pushState({}, '', elements[i].href);
                self.get();
            });
        }
    };

    this.renderMethods = function (data) {
        const section = document.getElementById('methods-all');
        const title = data.database.name + ' (' + data.database.version + ') signatures';
        document.title = title + ' | Pronto';
        section.querySelector('h1.header').innerHTML = title;

        let html = '';
        if (data.results.length) {
            data.results.forEach(m => {
                html += '<tr data-id="'+ m.id +'">' +
                    '<td><a href="/method/'+ m.id +'">'+ m.id +'</a></td>' +
                    '<td>'+ nvl(m.entryId, '', '<a href="/entry/'+ m.entryId +'">'+m.entryId+'</a>') +'</td>' +
                    '<td>'+ renderCheckbox(m.entryId, m.isChecked) +'</td>' +
                    '<td>'+ nvl(m.countNow, '') +'</td>' +
                    '<td>'+ nvl(m.countThen, '') +'</td>' +
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

        section.querySelector('tbody').innerHTML = html;

        this.generatePagination(section, data.pageInfo.page, data.pageInfo.pageSize, data.count);

        (function () {
            const elements = section.querySelectorAll('tbody input[type=checkbox]');
            for (let i = 0; i < elements.length; ++i) {
                elements[i].addEventListener('change', e => {
                    const cbox = e.target;
                    const modal = document.getElementById('confirm-modal');

                    modal.querySelector('.content').innerHTML = '<p>' + (cbox.checked ? 'Check' : 'Uncheck') + ' entry <strong>'+ cbox.name +'</strong>?';

                    $(modal).modal({
                        onApprove: function () {
                            postXhr('/api/entry/' + cbox.name + '/check', {
                                checked: cbox.checked ? 1 : 0
                            }, data => {
                                if (data.status) {
                                    const cboxes = section.querySelectorAll('tbody input[type=checkbox][name="'+ cbox.name +'"]');
                                    for (let i = 0; i < cboxes.length; ++i)
                                        cboxes[i].checked = cbox.checked;
                                } else {
                                    const modal = document.getElementById('error-modal');
                                    modal.querySelector('.content p').innerHTML = data.message;
                                    $(modal).modal('show');
                                }
                            });
                        },
                        onDeny: function () {
                            cbox.checked = !cbox.checked;
                        }
                    }).modal('show');
                });
            }
        })();

        observeLinks(section);

        (function () {
            const elements = section.querySelectorAll('.comment .reply');
            for (let i  = 0; i < elements.length; ++i) {
                elements[i].addEventListener('click', e => {
                    const methodId = e.target.closest('tr').getAttribute('data-id');
                    getMethodComments(methodId, section.querySelector('.ui.segment.comments'), 2);
                });
            }
        })();

        setClass(section, 'hidden', false);
    };

    this.renderUnintegratedMethods = function (data) {
        const section = document.getElementById('methods-unintegrated');

        const title = data.database.name + ' (' + data.database.version + ') unintegrated signatures';
        document.title = title + ' | Pronto';
        section.querySelector('h1.header').innerHTML = title;

        let html = '';
        if (data.results.length) {
            data.results.forEach(m => {
                html += '<tr>' +
                    '<td><a href="/method/'+ m.id +'">'+ m.id +'</a></td>' +
                    '<td class="nowrap"><div class="ui list">';

                m.addTo.forEach(pred => {
                    html += '<div class="item">';

                    if (pred.type !== null)
                        html += '<span class="ui circular mini label type-'+ pred.type +'">'+ pred.type +'</span>' +
                            '<div class="content"><a href="/entry/'+ pred.id +'">'+ pred.id +'</a></div></div>';
                    else
                        html += '<span class="ui circular mini label">&nbsp;</span>' +
                            '<div class="content"><a href="/method/'+ pred.id +'">'+ pred.id +'</a></div></div>';
                });

                html += '</div></td>' +
                    '<td>'+ m.parents.join(', ') +'</td>' +
                    '<td>'+ m.children.join(', ') +'</td></tr>';
            });
        } else
            html = '<tr><td class="center aligned" colspan="4">No matching entries found</td></tr>';

        section.querySelector('tbody').innerHTML = html;

        this.generatePagination(section, data.pageInfo.page, data.pageInfo.pageSize, data.count);
        observeLinks(section);

        setClass(section, 'hidden', false);
    }
}


function PredictionView() {
    this.section = document.getElementById('method');
    this.sv = new MethodsSelectionView(this.section.querySelector('.methods'));
    this.pixels = null;
    this.nRect = null;
    const self = this;

    // Init
    (function () {
        const heatmap = self.section.querySelector('.heatmap');
        const colors = heatmap.getAttribute('data-colors').split(',');
        const nRect = parseInt(heatmap.getAttribute('data-size'), 10);

        const pixels = [];
        const topLeft = hex2rgb(colors[0]);
        const topRight = hex2rgb(colors[1]);
        const bottomLeft = hex2rgb(colors[2]);
        const bottomRight = hex2rgb(colors[3]);

        // Color slopes
        const leftToRightTop = calcPixelSlope(topLeft, topRight, nRect);
        const leftToRightBottom = calcPixelSlope(bottomLeft, bottomRight, nRect);

        // Interpolate from left to right, then top to bottom
        for (let x = 0; x < nRect; ++x) {
            let p1 = calcPixelGradient(topLeft, x, leftToRightTop);
            let p2 = calcPixelGradient(bottomLeft, x, leftToRightBottom);

            for (let y = 0; y < nRect; ++y) {
                let topToBottom = calcPixelSlope(p1, p2, nRect);
                let p = calcPixelGradient(p1, y, topToBottom);
                pixels.push({
                    x: x,  // origin is top left corner, but we want the bottom right corner
                    y: y,
                    c: rgb2hex(p)
                });
            }
        }

        self.pixels = pixels;
        self.nRect = nRect;

        // Event listener
        self.section.querySelector('.ui.comments form button').addEventListener('click', e => {
            e.preventDefault();
            const form = e.target.closest('form');
            const methodId = form.getAttribute('data-id');
            const textarea = form.querySelector('textarea');

            postXhr('/api/method/'+ methodId +'/comment/', {
                comment: textarea.value.trim()
            }, data => {
                setClass(textarea.closest('.field'), 'error', !data.status);

                if (!data.status) {
                    const modal = document.getElementById('error-modal');
                    modal.querySelector('.content p').innerHTML = data.message;
                    $(modal).modal('show');
                } else {
                    getMethodComments(methodId, form.closest('.ui.comments'), 2);
                }
            });
        });


    })();

    this.draw = function () {
        const heatmap = self.section.querySelector('.heatmap');

        // Draw heatmap
        const svg = heatmap.querySelector('svg');
        const size = heatmap.offsetWidth;

        svg.setAttribute('width', size.toString());
        svg.setAttribute('height', size.toString());
        const rectSize = Math.floor(size / (this.nRect + 1));

        let html = '';
        this.pixels.forEach(p => {
            html += '<rect x="'+ ((p.x + 1) * rectSize) +'" y="'+ ((p.y + 1) * rectSize) +'" width="'+ (rectSize) +'" height="'+ (rectSize) +'" fill="'+ p.c +'"></rect>';
        });

        html += '<text dominant-baseline="hanging" text-anchor="middle" x="'+ ((size + rectSize) / 2) +'" y="0" fill="#333">Candidate</text>';
        for (let x = 0; x <= this.nRect; ++x) {
            let label = Math.floor(100 - (100 / this.nRect) * x);
            html += '<text font-size=".8rem" dominant-baseline="hanging" text-anchor="end" x="'+ (rectSize * (x + 1)) +'" y="'+ (rectSize / 2) +'" fill="#333">'+ label +'%</text>';
        }

        html += '<text transform="rotate(-90 0,'+ ((size + rectSize) / 2) +')" dominant-baseline="hanging" text-anchor="middle" x="0" y="'+ ((size + rectSize) / 2) +'" fill="#333">Query</text>';
        for (let y = 1; y <= this.nRect; ++y) {
            let label = Math.floor(100 - (100 / this.nRect) * y);
            html += '<text font-size=".8rem" dominant-baseline="auto" text-anchor="end" x="'+ rectSize +'" y="'+ (rectSize * (y + 1)) +'" fill="#333">'+ label +'%</text>';
        }
        svg.innerHTML = html;
    };

    this.get = function (methodId) {
        self.sv.clear().add(methodId).render();
        const url = location.pathname + location.search;

        showDimmer(true);
        getJSON('/api' + getPathName(location.pathname) + '/prediction?' + location.search, (data, status) => {
            try {
                history.replaceState({page: 'method', data: data, methodId: methodId, url: url}, '', url);
            } catch (err) {
                history.replaceState({page: 'method', data: null, methodId: methodId, url: url}, '', url);
            }
            this.render(methodId, data);
            showDimmer(false);
        });
    };

    this.findPixel = function (x, y) {
        for (let i = 0; i < this.pixels.length; ++i) {
            if (this.pixels[i].x === x && this.pixels[i].y === y)
                return this.pixels[i].c;
        }

        return null;
    };

    this.render = function(methodId, data) {
        this.section.querySelector('h1.header .sub.header').innerHTML = methodId;
        document.title = methodId + ' prediction | Pronto';

        let html = '';
        data.results.forEach(m => {
            const qRatio = Math.min(m.nProtsCand / m.nProtsQuery, 1);
            const cRatio = Math.min(m.nProtsCand / m.nProts, 1);
            let x = this.nRect - Math.floor(cRatio * this.nRect);
            let y = this.nRect - Math.floor(qRatio * this.nRect);

            const c1 = this.findPixel(
                x < this.nRect ? x : x - 1,
                y < this.nRect ? y : y - 1,
            );

            const qBlob = Math.min(m.nBlobsCand / m.nBlobsQuery, 1);
            const cBlob = Math.min(m.nBlobsCand / m.nBlobs, 1);
            x = this.nRect - Math.floor(cBlob * this.nRect);
            y = this.nRect - Math.floor(qBlob * this.nRect);

            const c2 = this.findPixel(
                x < this.nRect ? x : x - 1,
                y < this.nRect ? y : y - 1,
            );

            html += '<tr '+ (m.id === methodId ? 'class="selected"' : '') +'>' +
                '<td>'+ nvl(m.relation, '') +'</td>' +
                '<td><a href="#">' + m.id + '</a></td>' +
                '<td class="collapsing">'+ (m.dbLink ? '&nbsp;<a target="_blank" href="'+ m.dbLink +'"><i class="external icon"></i></a>' : '') +'</td>' +
                // '<td>'+ m.dbShort +'</td>' +
                '<td>'+ m.nProts +'</td>' +
                '<td>'+ m.nBlobs +'</td>' +
                '<td style="background-color: '+ c1 +'; color: #fff;">'+ m.nProtsCand +'</td>' +
                '<td style="background-color: '+ c2 +'; color: #fff;">'+ m.nBlobsCand +'</td>';

            if (m.entryId) {
                html += '<td class="nowrap"><div class="ui list">';

                m.entryHierarchy.forEach(e => {
                    html += '<div class="item"><i class="angle down icon"></i><div class="content"><a href="/entry/'+ e +'">' + e + '</a></div></div>';
                });

                html += '<div class="item"><span class="ui circular mini label type-'+ m.entryType +'">'+ m.entryType +'</span><div class="content"><a href="/entry/'+ m.entryId +'">' + m.entryId + '</a></div></div></td>';
            } else
                html += '<td></td>';

            html += '<td>'+ nvl(m.entryName, '') +'</td>' +
                '<td>'+ renderCheckbox(m.entryId, m.isChecked) +'</td>';
        });

        this.section.querySelector('tbody').innerHTML = html;
        observeLinks(this.section);

        (function () {
            const elements = self.section.querySelectorAll('tbody input[type=checkbox]');
            for (let i = 0; i < elements.length; ++i) {
                elements[i].addEventListener('change', e => {
                    const cbox = e.target;
                    const modal = document.getElementById('confirm-modal');

                    modal.querySelector('.content').innerHTML = '<p>' + (cbox.checked ? 'Check' : 'Uncheck') + ' entry <strong>'+ cbox.name +'</strong>?';

                    $(modal).modal({
                        onApprove: function () {
                            postXhr('/api/entry/' + cbox.name + '/check', {
                                checked: cbox.checked ? 1 : 0
                            }, data => {
                                if (data.status) {
                                    const cboxes = self.section.querySelectorAll('tbody input[type=checkbox][name="'+ cbox.name +'"]');
                                    for (let i = 0; i < cboxes.length; ++i)
                                        cboxes[i].checked = cbox.checked;
                                } else {
                                    const modal = document.getElementById('error-modal');
                                    modal.querySelector('.content p').innerHTML = data.message;
                                    $(modal).modal('show');
                                }
                            });
                        },
                        onDeny: function () {
                            cbox.checked = !cbox.checked;
                        }
                    }).modal('show');
                });
            }
        })();

        (function () {
            const elements = self.section.querySelectorAll('tbody a[href="#"]');
            for (let i = 0; i < elements.length; ++i) {
                elements[i].addEventListener('click', e => {
                    e.preventDefault();
                    self.sv.add(e.target.innerText).render();
                });
            }
        })();

        getMethodComments(methodId, this.section.querySelector('.ui.segment.comments'), 2, () => {this.draw()});
    };
}


function IndexView() {
    this.section = document.getElementById('index');

    this.get = function () {
        getJSON('/api/db', (data, status) => {
            this.renderDatabases(data);
        });

        // getJSON('/api/feed?n=10', (data, status) => {
        //     this.renderFeed(data);
        // });
    };

    this.renderDatabases = function (data) {
        const html = [];
        data.results.forEach(db => {
            html.push(
                [
                    '<tr>',
                    '<td><a href="'+ db.home +'" target="_blank">'+ db.name +'&nbsp;'+ db.version +'&nbsp;<i class="external icon"></i></a></td>',
                    '<td><a href="/db/'+ db.shortName +'">'+ db.count.toLocaleString() +'</a></td>',
                    '<td>'+ db.countIntegrated +'</td>',
                    '<td><a href="/db/'+ db.shortName +'?unintegrated=exist">'+ db.countUnintegrated.toLocaleString() +'</a></td>',
                    '</tr>'
                ].join('')
            );
        });

        this.section.querySelector('tbody').innerHTML = html.join('');
    };

    this.renderFeed = function (data) {
        const html = [];
        data.results.forEach(e => {
            const date = new Date(e.timestamp * 1000);
            const timeDelta = Math.floor(Date.now() / 1000) - e.timestamp;

            let event = '<div class="event">' +
                '<div class="label"><span class="ui large type-'+ e.type +' circular label">'+ e.type +'</span></div>' +
                '<div class="content"><div class="date"><abbr title="'+ date.toLocaleString() +'">';

            if (timeDelta < 60)
                event += timeDelta.toString() + 's';
            else if (timeDelta < 3600)
                event += Math.floor(timeDelta / 60).toString() + 'm';
            else if (timeDelta < (3600 * 24))
                event += Math.floor(timeDelta / 3600).toString() + 'h';
            else
                event += date.toLocaleDateString();

            event += '</abbr></div>';
            event += '<div class="summary"><a class="user">'+ e.user +'</a> created <a href="/entry/'+ e.id +'">'+ e.id +'</a></div>';

            if (e.count)
                event += '<div class="extra text">'+ e.count +' proteins</div>';

            html.push(event + '</div></div>')
        });

        this.section.querySelector('.ui.feed').innerHTML = html.join('');
    };
}


function SearchView() {
    this.section = document.getElementById('search');

    this.get = function () {
        const url = location.pathname + location.search;
        showDimmer(true);

        getJSON('/api' + url, (data, status) => {
            history.replaceState({data: data, page: 'search', url: url}, '', url);
            this.render(data);
            showDimmer(false);
        });
    };

    this.render = function (data) {
        const message = this.section.querySelector('.message');
        const urls = [];
        let html = '';

        [{
            key: 'entries',
            label: 'Entries',
            page: '/entry/'
        }, {
            key: 'methods',
            label: 'Signatures',
            page: '/method/'
        }, {
            key: 'proteins',
            label: 'Proteins',
            page: '/protein/'
        }].forEach(e => {
            if (data[e.key].length) {
                if (data[e.key].length === 1)
                    urls.push(e.page + data[e.key][0]);

                html += '<li>'+ e.label +': ' + data[e.key].map(x => '<a href="'+ e.page + x +'">'+ x +'</a>').join(',') + '</li>';
            }
        });

        setGlobalError(null);

        if (urls.length === 1) {
            // Auto-redirect
            history.pushState({}, '', urls);
            initApp();
            return;
        }

        const noDirectHit = !html.length;
        message.querySelector('.list').innerHTML = html;
        setClass(message, 'hidden', noDirectHit);

        const table = this.section.querySelector('table');
        const ebiSearch = data.ebiSearch;

        if (ebiSearch.hitCount) {
            const page = ebiSearch.page;
            const pageSize = ebiSearch.pageSize;
            const lastPage = Math.ceil(ebiSearch.hitCount / pageSize);
            html = '';

            ebiSearch.hits.forEach(entry => {
                html += '<tr><td><span class="ui tiny type-'+ entry.type +' circular label">'+ entry.type +'</span>&nbsp;<a href="/entry/'+ entry.id +'">'+ entry.id +'</a></td><td>'+ entry.name +'</td></tr>';
            });

            table.querySelector('tbody').innerHTML = html;
            table.querySelector('th').innerHTML = ((page - 1) * pageSize + 1) + ' - ' + Math.min(page * pageSize, ebiSearch.hitCount) + ' of ' + ebiSearch.hitCount.toLocaleString() + ' results';

            // Pagination
            html = '';

            const baseUrl = getPathName(this.url);
            const params = getParams(this.url);

            if (page === 1)
                html += '<a class="icon disabled item"><i class="left chevron icon"></i></a><a class="active item">1</a>';
            else
                html += '<a class="icon item" href="'+ (baseUrl + encodeParams(extendObj(params, {page: page - 1}))) +'"><i class="left chevron icon"></i></a><a class="item" href="'+ (baseUrl + encodeParams(extendObj(params, {page: 1}))) +'">1</a>';

            let ellipsisBefore = false;
            let ellipsisAfter = false;
            for (let i = 2; i < lastPage; ++i) {
                if (i === page)
                    html += '<a class="active item">'+ i +'</a>';
                else if (Math.abs(i - page) === 1)
                    html += '<a class="item" href="'+ (baseUrl + encodeParams(extendObj(params, {page: i}))) +'">'+ i +'</a>';
                else if (i < page && !ellipsisBefore) {
                    html += '<div class="disabled item">&hellip;</div>';
                    ellipsisBefore = true;
                } else if (i > page && !ellipsisAfter) {
                    html += '<div class="disabled item">&hellip;</div>';
                    ellipsisAfter = true;
                }
            }

            if (lastPage > 1) {
                if (page === lastPage)
                    html += '<a class="active item">'+ lastPage +'</a>';
                else
                    html += '<a class="item" href="'+ (baseUrl + encodeParams(extendObj(params, {page: lastPage}))) +'">'+ lastPage +'</a>'
            }


            if (page === lastPage || !lastPage)
                html += '<a class="icon disabled item"><i class="right chevron icon"></i></a>';
            else
                html += '<a class="icon item" href="'+ (baseUrl + encodeParams(extendObj(params, {page: page + 1}))) +'"><i class="right chevron icon"></i></a>';

            const pagination = table.querySelector('.pagination');
            pagination.innerHTML = html;
            Array.from(pagination.querySelectorAll('a[href]'), element => {
                observeLink(element);
            });

            setClass(table, 'hidden', false);
        } else
            setClass(table, 'hidden', true);

        if (noDirectHit && !ebiSearch.hitCount)
            setGlobalError('Your search returned no matches.');
    }
}


const views = {
    index: null,
    db: null,
    method: null,
    methods: null,
    entry: null,
    protein: null,
    search: null
};

function initApp() {
    const pathName = getPathName();
    let match;
    let section = null;

    if (!pathName.length) {
        section = 'index';
        if (!views.index)
            views.index = new IndexView();
        views.index.get();
    }

    match = pathName.match(/^\/db\/(.+)/i);
    if (match) {
        section = 'methods';
        if (!views.db)
            views.db = new DatabaseView();
        views.db.get();
    }

    match = pathName.match(/^\/method\/([^\/\s]+)/);
    if (match) {
        section = 'method';
        if (!views.method)
            views.method = new PredictionView();
        views.method.get(match[1]);
    }

    match = pathName.match(/^\/methods\/(.+)\/((?:matches)|(?:taxonomy)|(?:descriptions)|(?:comments)|(?:go)|(?:matrices))\/?$/);
    if (match) {
        section = 'comparison';
        const methods = match[1].trim().split('/');
        const page = match[2];

        if (!views.methods)
            views.methods = new ComparisonViews(methods);
        else
            views.methods.setMethods(methods);

        switch (page) {
            case 'matches':
                views.methods.getMatches();
                break;
            case 'taxonomy':
                views.methods.getTaxonomy();
                break;
            case 'descriptions':
                views.methods.getDescriptions();
                break;
            case 'comments':
                views.methods.getSwissProtComments();
                break;
            case 'go':
                views.methods.getGoTerms();
                break;
            case 'matrices':
                views.methods.getMatrices();
                break;
            default:
                break;
        }
    }

    match = pathName.match(/^\/entry\/([a-z0-9]+)/i);
    if (match) {
        section = 'entry';
        if (!views.entry)
            views.entry = new EntryView();
        views.entry.get(match[1]);
    }

    match = pathName.match(/^\/protein\/([a-z0-9]+)/i);
    if (match) {
        section = 'protein';
        if (!views.protein)
            views.protein = new ProteinView();
        views.protein.get(match[1]);
    }

    match = pathName.match(/^\/search/);
    if (match) {
        section = 'search';
        if (!views.search)
            views.search = new SearchView();
        views.search.get();
    }

    if (section) {
        Array.from(document.querySelectorAll('section')).forEach(element => {
            setClass(element, 'hidden', element.id !== section);
        });
    }
}

$(function () {
    $('.message .close').on('click', function() {
        $(this).closest('.message').transition('fade');
    });

    // Observe search input
    (function () {
        const messages = document.getElementById('messages');
        const inputWrapper = document.querySelector('header .ui.input');
        const input = inputWrapper.querySelector('input[type=text]');

        function searchTerm(search) {
            history.pushState({}, '', '/search/?query=' + encodeURIComponent(search));
            initApp();
        }

        input.addEventListener('keyup', e => {
            if (e.which === 13 && e.target.value.trim().length) {
                searchTerm(e.target.value.trim());
            }
        });

        inputWrapper.querySelector('.button').addEventListener('click', e => {
            if (input.value.trim().length)
                searchTerm(input.value.trim());
        });

        messages.querySelector('i.close').addEventListener('click', e => {
            setClass(messages, 'hidden', true);
        });
    })();

    // Init Semantic-UI elements
    $('[data-content]').popup();
    $('.ui.dropdown').dropdown();

    initApp();
});

window.onpopstate = function(event) {
    let section = null;
    if (event.state) {
        const state = event.state;

        if (state.page === 'method') {
            section = state.page;

            if (!views.method)
                views.method = new PredictionView();

            views.method.render(state.methodId, state.data);
        } else if (state.page === 'matches' || state.page === 'taxonomy' || state.page === 'descriptions' || state.page === 'comments' || state.page === 'go' || state.page === 'matrices') {
            section = 'comparison';

            if (!views.methods)
                views.methods = new ComparisonViews(state.methods);
            else
                views.methods.setMethods(state.methods);

            if (state.page === 'matches')
                views.methods.renderMatches(state.data);
            else if (state.page === 'taxonomy')
                views.methods.renderTaxonomy(state.data);
            else if (state.page === 'descriptions')
                views.methods.renderDescriptions(state.data);
            else if (state.page === 'comments')
                views.methods.renderSwissProtComments(state.data);
            else if (state.page === 'go')
                views.methods.renderGoTerms(state.data);
            else
                views.methods.renderMatrices(state.data);
        } else if (state.page === 'methods') {
            if (!views.db)
                views.db = new DatabaseView();

            if (state.unintegrated !== undefined) {
                views.db.renderUnintegratedMethods(state.data);
            } else {
                views.db.renderMethods(state.data);
            }
        } else if (state.page === 'search') {
            if (!views.search)
                views.search = new SearchView();

            views.search.render(state.data);
        }

        if (section) {
            Array.from(document.querySelectorAll('section')).forEach(element => {
                setClass(element, 'hidden', element.id !== section);
            });
        }
    }
};
