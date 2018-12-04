function getUniProtVersion() {
    fetch("/api/uniprot/version/")
        .then(response => response.json())
        .then(response => {
            document.getElementById("uniprot-version").innerHTML = response.version;
        });

}

function getCurrentUser() {
    fetch("/api/user/")
        .then(response => response.json())
        .then(response => {
            const div = document.getElementById("user-info");
            let html;
            if (response.user) {
                html = '<i class="user circle icon"></i> '
                    + response.user.name
                    + '<i class="dropdown icon"></i>'
                    + '<div class="menu">'
                    + '<div class="item">'
                    + '<a class="icon" href="/logout/">'
                    + '<i class="sign out icon"></i>&nbsp;Log out'
                    + '</a>'
                    + '</div>'
                    + '</div>';
                div.innerHTML = html;
                div.className = "ui simple dropdown item";
            } else {
                div.innerHTML = '<a href="/login/" class="icon"><i class="sign in icon"></i>&nbsp;Log in</a>';
                div.className = "item";
            }
        });
}

export function finaliseHeader() {
    getUniProtVersion();
    getCurrentUser();
}