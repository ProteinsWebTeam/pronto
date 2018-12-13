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
            let item;
            if (response.user) {
                item = document.createElement("div");
                item.className = "ui simple dropdown item";
                item.innerHTML = '<i class="user circle icon"></i> '
                    + response.user.name
                    + '<i class="dropdown icon"></i>'
                    + '<div class="menu">'
                    + '<div class="item">'
                    + '<a class="icon" href="/logout/">'
                    + '<i class="sign out icon"></i>&nbsp;Log out'
                    + '</a>'
                    + '</div>'
                    + '</div>';
            } else {
                item = document.createElement("a");
                item.className = "icon item";
                item.href = "/login/";
                item.innerHTML = '<i class="sign in icon"></i>&nbsp;Log in</a>';
            }

            document.querySelector("header .right.menu").appendChild(item);
        });
}

function getInstance() {
    fetch("/api/instance/")
        .then(response => response.json())
        .then(response => {
            document.getElementById("instance").innerHTML = response.instance;
        });
}

export function finaliseHeader() {
    getUniProtVersion();
    getCurrentUser();
    getInstance();
}