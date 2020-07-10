import {setClass} from "./utils.js";

export const selector = {
    elem: null,
    signatures: [],
    init: function (elem) {
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
        return this;
    },
    add: function (accession) {
        if (accession.length && !this.signatures.includes(accession)) {
            this.signatures.push(accession);
        }
        return this;
    },
    render: function () {
        const div = this.elem.querySelector('.ui.grid .column:last-child');

        let html = '';
        this.signatures.forEach(accession => {
            html += '<a class="ui basic label" data-id="' + accession + '">' + accession + '<i class="delete icon"></i></a>';
        });
        div.innerHTML = html;

        for (const elem of div.querySelectorAll('a i.delete')) {
            elem.addEventListener('click', e => {
                if (this.signatures.length === 1)
                    return;  // Always have at least one signature selected

                const accession = e.currentTarget.parentNode.dataset.id;
                this.signatures = this.signatures.filter(item => item !== accession);
                this.render();
            });
        }

        const params = [];
        for (let [key, value] of new URL(location.href).searchParams.entries()) {
            if (key !== 'page' && key !== 'page_size')
                params.push(`${key}=${value}`);
        }

        for (const elem of this.elem.querySelectorAll('.links a')) {
            elem.setAttribute('href', `/signatures/${this.signatures.join('/')}/${elem.dataset.link}/?${params.join('&')}`);
        }
        return this;
    },
    tab: function (tabName) {
        for (const elem of this.elem.querySelectorAll('.links a')) {
            setClass(elem, 'active', elem.dataset.name === tabName);
        }
        return this;
    }
};