import {setClass, dimmer, paginate, initSearchBox} from "./ui.js";

export const selector = {
    elem: null,
    signatures: [],
    init: function (elem, accession) {
        this.elem = elem;

        const input = this.elem.querySelector('input[type=text]');
        const self = this;

        input.addEventListener('keyup', e => {
            if (e.which === 13) {
                let render = false;
                e.target.value.trim().replace(/,/g, ' ').split(' ').forEach(accession => {
                    if (accession.length && !self.signatures.includes(accession)) {
                        self.signatures.push(accession);
                        render = true;
                    }
                });

                e.target.value = null;
                if (render)
                    self.render();
            }
        });

        if (accession) {
            this.signatures.push(accession);
            this.render();
        }
    },
    add: function (accession) {
        if (accession.length && !this.signatures.includes(accession)) {
            this.signatures.push(accession);
            this.render();
        }

    },
    render: function () {
        const div = this.elem.querySelector('.ui.grid .column:last-child');

        let html = '';
        this.signatures.forEach(accession => {
            html += '<a class="ui basic label" data-id="' + accession + '">' + accession + '<i class="delete icon"></i></a>';
        });
        div.innerHTML = html;

        let nodes = div.querySelectorAll('a i.delete');
        for (let i = 0; i < nodes.length; ++i) {
            nodes[i].addEventListener('click', e => {
                const methodAc = e.target.parentNode.getAttribute('data-id');
                const signatures = [];
                this.signatures.forEach(m => {
                    if (m !== methodAc)
                        signatures.push(m);
                });
                this.signatures = signatures;
                this.render();

                setClass(this.elem.querySelector('.ui.input'), 'error', !this.signatures.length);
            });
        }

        Array.from(this.elem.querySelectorAll('.links a')).forEach(element => {
            element.setAttribute('href', '/signatures/' + this.signatures.join('/') + '/' + element.getAttribute('data-page') + '/');
        });
    },
    tab: function (tabName) {
        Array.from(this.elem.querySelectorAll('.links a')).forEach(e => {
            setClass(e, 'active', e.getAttribute('data-page') === tabName);
        });
    }
};

export const proteinViewer = {
    modal: document.getElementById('proteins-modal'),
    accession: null,
    url: null,
    search: null,
    accessions: null,
    init: function () {
        const self = this;
        const input = this.modal.querySelector('thead input');
        initSearchBox(input, null, (value,) => {
            if (self.url) {
                self.url.searchParams.delete("page");
                self.url.searchParams.delete("page_size");
                self.search = value;
                self.fetch();
            }
        });

        const button = self.modal.querySelector('.actions button');
        button.addEventListener('click', e => {
            if (self.accessions === null) {
                const url = new URL(
                    self.url.origin
                    + "/api/signature/" + self.accession + "/proteins/"
                    + self.url.search
                );

                button.innerHTML = '<i class="refresh loading icon"></i>&nbsp;Loading';
                fetch(url.toString())
                    .then(response => response.json())
                    .then(proteins => {
                        self.accessions = proteins.map(x => x.accession).join(' ');
                        button.innerHTML = '<i class="copy icon"></i>&nbsp;Copy to clipboard';
                    });
            } else {
                const input = document.createElement('input');
                input.value = self.accessions;
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
            }
        });
    },
    observe: function (selector) {
        const self = this;
        Array.from(selector).forEach(elem => {
            elem.addEventListener('click', e => {
                e.preventDefault();
                const accession = e.target.getAttribute('data-accession');
                const row = e.target.closest('tr');
                const type = row.getAttribute('data-type');
                const filter = row.getAttribute('data-filter');
                const params = row.getAttribute('data-params');
                self.open(accession, params, true)
                    .then(() => {
                        self.modal.querySelector('.ui.header').innerHTML = accession + ' proteins<div class="sub header">'+ type +': <em>'+ filter +'</em></div>';
                    })
            });
        });
    },
    open: function (accession, params, matches) {
        const self = this;
        return new Promise(((resolve, reject) => {
            self.accession = accession;

            // Update URL
            const url = new URL(
                location.origin +
                "/api/signature/" + accession + "/" +
                (matches ? "matches/" : "proteins/")
            );
            params.split('&').map(item => {
                const kv = item.split('=');
                url.searchParams.set(kv[0], kv[1]);
            });

            if (self.url === null || self.url.toString() !==url.toString()) {
                self.url = url;

                // Reset search
                const input = self.modal.querySelector('thead input');
                input.value = null;
                self.search = null;

                // Rest protein accession
                self.accessions = null;

                self.fetch().then(() => {
                    $(self.modal).modal('show');
                    resolve();
                });
            } else {
                $(self.modal).modal('show');
                resolve();
            }
        }));
    },
    fetch: function () {
        const self = this;
        return new Promise(((resolve, reject) => {
            dimmer(true);

            if (this.search)
                this.url.searchParams.set("search", this.search);
            else
                this.url.searchParams.delete("search");

            fetch(this.url.toString())
                .then(response => response.json())
                .then(results => {
                    // SVG globals
                    const svgWidth = 400;
                    const paddingLeft = 5;
                    const paddingRight = 20;

                    // Longest protein
                    const maxLength = Math.max(...results.proteins.map(x => x.length));

                    let html = '';
                    results.proteins.forEach(protein => {
                        html += '<tr><td class="nowrap"><a target="_blank" href="'+ protein.link +'">';

                        if (protein.reviewed)
                            html += '<i class="star icon"></i>&nbsp;';

                        html += protein.accession + '&nbsp;<i class="external icon"></i></a></td>'
                            + '<td>'+ protein.identifier +'</td>'
                            + '<td>'+ protein.name +'</td>'
                            + '<td class="italic">'+ protein.taxon.name +'</td>';

                        const width = Math.floor(protein.length * (svgWidth - (paddingLeft + paddingRight)) / maxLength);
                        if (protein.matches) {
                            html += '<td>'
                                + '<svg width="'+ svgWidth +'" height="30" version="1.1" baseProfile="full" xmlns="http://www.w3.org/2000/svg">'
                                + '<line x1="'+ paddingLeft +'" y1="20" x2="'+ width +'" y2="20" stroke="#888" stroke-width="1px" />'
                                + '<text class="length" x="'+(paddingLeft + width + 2)+'" y="20">'+ protein.length +'</text>';

                            protein.matches.forEach(fragments => {
                                fragments.forEach((fragment, i) => {
                                    const x = Math.round(fragment.start * width / protein.length) + paddingLeft;
                                    const w = Math.round((fragment.end - fragment.start) * width / protein.length);

                                    if (i) {
                                        // Discontinuous domain: draw arc
                                        const px = Math.round(fragments[i-1].end * width / protein.length) + paddingLeft;
                                        const x1 = (px + x) / 2;
                                        html += '<path d="M'+ px +' '+ 15 +' Q '+ [x1, 0, x, 15].join(' ') +'" fill="none" stroke="#607D8B"/>';
                                    }

                                    html += '<g><rect x="'+ x +'" y="15" width="'+ w +'" height="10" rx="1" ry="1" style="fill: #607D8B;"/>'
                                        + '<text class="position" x="'+ x +'" y="10">'+ fragment.start +'</text>'
                                        + '<text class="position" x="'+ (x + w) +'" y="10">'+ fragment.end +'</text></g>';
                                });
                            });

                            html += '</svg></td></tr>';
                        } else
                            html += '<td></td></tr>';
                    });

                    self.modal.querySelector('tbody').innerHTML = html;

                    // Update pagination
                    paginate(
                        self.modal.querySelector('table'),
                        results.page_info.page,
                        results.page_info.page_size,
                        results.count,
                        (url,) => {
                            self.url = new URL(url);
                            self.fetch();
                        },
                        self.url.toString()
                    );

                    // Reset copy button
                    const button = self.modal.querySelector('.actions button');
                    button.innerHTML = '<i class="download icon"></i>&nbsp;UniProt accessions';
                    setClass(button, 'green', false);
                    setClass(button, 'red', false);

                    // Update button to load overlapping proteins
                    const url = new URL(self.url);
                    url.pathname = "/signatures/" + self.accession + "/proteins/";
                    url.searchParams.delete("search");
                    url.searchParams.delete("page");
                    url.searchParams.delete("page_size");
                    self.modal.querySelector('.actions a').href = url.toString();

                    dimmer(false);

                    resolve();
                });
        }));

    }
};
proteinViewer.init();


export const gradientPuBu = [
    {r: 255, g: 255, b:255},    // #ffffff
    {r: 236, g: 231, b:242},    // #ece7f2
    {r: 208, g: 209, b:230},    // #d0d1e6
    {r: 166, g: 189, b:219},    // #a6bddb
    {r: 116, g: 169, b:207},    // #74a9cf
    {r: 54, g: 144, b:192},     // #3690c0
    {r: 5, g: 112, b:176},      // #0570b0
    {r: 4, g: 90, b:141},       // #045a8d
    {r: 2, g: 56, b:88}         // #023858
];

