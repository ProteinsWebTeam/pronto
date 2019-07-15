import {finaliseHeader} from "../../header.js"
import * as ui from "../../ui.js";


$(function () {
    finaliseHeader();

    $('.ui.tabular.menu .item').tab({
        auto: true,
        path: '/api'
    });

});