export function createDisabled(checked) {
    if (checked)
        return '<div class="ui fitted checked checkbox"><input type="checkbox" checked="" disabled="disabled"><label></label></div>';
    else
        return '<div class="ui fitted checkbox"><input type="checkbox" disabled="disabled"><label></label></div>';
}
