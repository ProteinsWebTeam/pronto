import {setClass} from "./utils.js";

export function listenMenu(menu) {
    const items = Array.from(menu.querySelectorAll('a.item'));
    for (const item of items) {
        item.addEventListener('click', e => {
            for (const item of items)
                setClass(item, 'active', item === e.currentTarget);
        });
    }
}