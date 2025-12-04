export async function sleep(ms) {
    return new Promise(((resolve, reject) => {
        setTimeout(resolve, ms);
    }));
}

export async function fetchTasks() {
    const response = await fetch(`/api/tasks/?s=3600`);
    return response.json();
}

export async function waitForTask(taskId, ms = 5000) {
    let response;
    let task;

    while (true) {
        response = await fetch(`/api/task/${taskId}/`)
        task = await response.json();

        if (task.end_time !== null)
            return task;

        await sleep(ms);
    }
}