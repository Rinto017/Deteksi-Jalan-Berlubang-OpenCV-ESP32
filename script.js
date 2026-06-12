function updateClock() {
    const now = new Date();
    document.getElementById("clock").innerText = now.toLocaleTimeString("id-ID");
}

function updateData() {
    fetch('/data')
        .then(response => response.json())
        .then(data => {
            const status = document.getElementById("status");
            const badge = document.getElementById("status-badge");
            const warningBox = document.getElementById("warning-box");
            const warningText = document.getElementById("warning-text");

            status.innerText = data.status;
            badge.innerText = "Status: " + data.status;

            if (data.status === "BAHAYA") {
                status.className = "bahaya";
                badge.className = "bahaya";
                warningBox.classList.add("bahaya");
                warningText.innerText = "Lubang jalan terdeteksi! Kurangi kecepatan.";
            } else {
                status.className = "aman";
                badge.className = "aman";
                warningBox.classList.remove("bahaya");
                warningText.innerText = "Sistem dalam kondisi aman.";
            }

            document.getElementById("lubang").innerText = data.jumlah_lubang;
            document.getElementById("confidence").innerText = data.confidence;
            document.getElementById("buzzer").innerText = data.buzzer;
            document.getElementById("esp32").innerText = data.esp32;
            document.getElementById("source-name").innerText = data.source_name;
        });
}

function updateLogs() {
    fetch('/logs')
        .then(response => response.json())
        .then(logs => {
            const logList = document.getElementById("log-list");
            logList.innerHTML = "";

            logs.forEach(log => {
                const item = document.createElement("div");
                item.className = "log-item";

                item.innerHTML = `
                    <span>${log.waktu}</span>
                    <span>${log.status}</span>
                    <span>Lubang: ${log.jumlah_lubang}</span>
                    <span>Conf: ${log.confidence}</span>
                `;

                logList.appendChild(item);
            });
        });
}

function uploadVideo(file) {
    const uploadStatus = document.getElementById("upload-status");

    if (!file) {
        uploadStatus.innerText = "Tidak ada file dipilih.";
        return;
    }

    const formData = new FormData();
    formData.append("video", file);

    uploadStatus.innerText = "Mengupload video: " + file.name + " ...";

    fetch("/upload_video", {
        method: "POST",
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            uploadStatus.innerText = "Video aktif: " + data.filename;

            const videoFeed = document.querySelector(".video-feed");
            videoFeed.src = "/video_feed?t=" + new Date().getTime();
        } else {
            uploadStatus.innerText = "Gagal upload: " + data.message;
        }
    })
    .catch(error => {
        uploadStatus.innerText = "Terjadi error saat upload.";
        console.log(error);
    });
}

function clearVideo() {
    const uploadStatus = document.getElementById("upload-status");

    fetch("/clear_video", {
        method: "POST"
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            uploadStatus.innerText = "Video dibersihkan. Silakan upload video untuk mulai deteksi.";

            const videoFeed = document.querySelector(".video-feed");
            videoFeed.src = "/video_feed?t=" + new Date().getTime();
        } else {
            uploadStatus.innerText = "Gagal reset video.";
        }
    });
}

document.addEventListener("DOMContentLoaded", function () {
    const selectFile = document.getElementById("select-file");
    const clearBtn = document.getElementById("clear-video");
    const videoInput = document.getElementById("video-input");
    const dropZone = document.getElementById("drop-zone");

    selectFile.addEventListener("click", function () {
        videoInput.click();
    });

    videoInput.addEventListener("change", function () {
        const file = videoInput.files[0];
        uploadVideo(file);
    });

    clearBtn.addEventListener("click", function () {
        clearVideo();
    });

    dropZone.addEventListener("dragover", function (event) {
        event.preventDefault();
        dropZone.classList.add("drag-over");
    });

    dropZone.addEventListener("dragleave", function () {
        dropZone.classList.remove("drag-over");
    });

    dropZone.addEventListener("drop", function (event) {
        event.preventDefault();
        dropZone.classList.remove("drag-over");

        const file = event.dataTransfer.files[0];
        uploadVideo(file);
    });
});

setInterval(updateClock, 1000);
setInterval(updateData, 500);
setInterval(updateLogs, 2000);

updateClock();
updateData();
updateLogs();