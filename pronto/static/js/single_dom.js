function getSingleDomain(accession) {
    return new Promise((resolve, reject) => {
        fetch('/api/single_dom/' + accession)
            .then(response => {
                if (response.ok)
                    resolve(response.json());
                else
                    reject(response.status);
            })
    });
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelector('.ui.single.dom form button').addEventListener('click', e => {
        e.preventDefault();
        const form = e.target.closest('form');
        const textarea = form.querySelector('input');

        getSingleDomain(textarea.value.trim()).then(
            (result,) => {
                const sequence = result.sequence;
                const len_seq = result.sequence_len;
                const feature = result.domains;

                if (feature.length !== 0) {
                    customElements.whenDefined("nightingale-navigation").then(() => {
                        document.getElementById("navigation").setAttribute('length', len_seq);
                        document.getElementById("navigation").setAttribute('display-end', len_seq);
                    });

                    customElements.whenDefined("nightingale-sequence").then(() => {
                        document.getElementById("sequence").sequence = sequence;
                        document.getElementById("sequence").setAttribute('length', len_seq);
                    });

                    customElements.whenDefined("nightingale-interpro-track").then(() => {
                        document.getElementById("track").setAttribute('length', len_seq);
                        document.getElementById("track").data = feature;
                        document.getElementById("track").setAttribute('label', ".feature.short_name");
                    });

                    document.getElementById("seq-viewer").style.display = 'none';
                    document.getElementById("seq-viewer").style.display = 'block';
                }
                else {
                    document.getElementById("seq-viewer").style.display = 'none';
                    document.getElementById("not-found").style.display = 'block';
                }
            },
            (status,) => {
                console.log(status);
                document.getElementById("seq-viewer").style.display = 'none';
                document.getElementById("not-found").style.display = 'block';
            }
        );
    });
});