export function init(input, initValue, callback) {
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