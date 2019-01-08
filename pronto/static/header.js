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

function getTasks() {
    fetch('/api/tasks/')
        .then(response => response.json())
        .then(tasks => {
            let html = '<i class="tasks icon"></i>'
                + '<div class="menu">';

            if (tasks.length) {
                tasks.forEach(task => {
                    html += '<div class="item">';

                    if (task.status === null)
                        html += '<i class="loading notched circle icon"></i>';
                    else if (task.status)
                        html += '<i class="green check circle icon"></i>';
                    else
                        html += '<i class="red exclamation circle icon"></i>';
                    html += task.name + '</div>';
                });
            } else
                html += '<div class="item">No tasks</div>';
            html += '</div>';

            document.getElementById('tasks').innerHTML = html;
        })
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
    getTasks();

    document.getElementById('tasks').addEventListener('click', e => getTasks());
}