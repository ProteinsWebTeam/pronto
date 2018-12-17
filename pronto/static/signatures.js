import {setClass} from "./ui.js";

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
