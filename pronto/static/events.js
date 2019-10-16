import * as ui from "./ui.js";

export function checkEntry(input) {
    // Expects input.name to be the entry accession
    ui.openConfirmModal(
        (input.checked ? "Check" : "Uncheck") + " entry?",
        "<strong>" + input.name + "</strong> will be marked as " + (input.checked ? "checked" : "unchecked"),
        (input.checked ? "Check" : "Uncheck"),
        () => {
            fetch(URL_PREFIX+"/api/entry/" + input.name + "/check/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json; charset=utf-8",
                },
                body: JSON.stringify({
                    checked: input.checked ? 1 : 0
                })
            }).then(response => response.json())
                .then(result => {
                    if (result.status) {
                        Array.from(document.querySelectorAll("input[type=checkbox][name="+input.name+"]")).forEach(cbox => {
                            cbox.checked = input.checked;
                        });
                    } else {
                        ui.openErrorModal(result.message);
                        input.checked = !input.checked;
                    }
                });
        },
        () => {
            input.checked = !input.checked;
        }
    );

}
