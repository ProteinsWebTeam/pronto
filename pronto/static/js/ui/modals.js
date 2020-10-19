export function ask(header, content, approve, onApprove, onDeny) {
    const modal = document.getElementById('confirm-modal');

    modal.querySelector('.header').innerText = header;
    modal.querySelector('.content').innerHTML = `<p>${content}</p>`;
    modal.querySelector('.approve').innerText = approve;

    $(modal)
        .modal({
            allowMultiple: true,
            onApprove: function () {
                if (onApprove) onApprove();
            },
            onDeny: function () {
                if (onDeny) onDeny();
            }
        })
        .modal('show');
}

export function error(title, message) {
    const modal = document.getElementById('error-modal');
    modal.querySelector('.header').innerHTML = title || 'Something went wrong';
    modal.querySelector('.content').innerHTML = `<p>${message}</p>`;
    $(modal).modal('show');
}