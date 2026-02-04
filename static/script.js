const student_id = "student1";

window.onload = () => {
    startWebcam();
    startSendingFrames(student_id);
};

// ---------------------------
// START WEBCAM
// ---------------------------
function startWebcam() {
    const video = document.getElementById("video");

    navigator.mediaDevices.getUserMedia({ video: true })
        .then(stream => {
            video.srcObject = stream;
            document.getElementById("status").innerText = "Webcam active";
        })
        .catch(err => {
            document.getElementById("status").innerText =
                "Webcam error: " + err.name;
        });
}

// ---------------------------
// SEND FRAMES EVERY 5 SECONDS
// ---------------------------
function startSendingFrames(student_id) {
    const video = document.getElementById("video");

    setInterval(() => {

        // ✅ wait for video to be ready
        if (!video.videoWidth || !video.videoHeight) {
            console.log("⏳ Video not ready");
            return;
        }

        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;

        const ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0);

        canvas.toBlob(blob => {
            if (!blob) return;

            const formData = new FormData();
            formData.append("student_id", student_id);
            formData.append("file", blob, "frame.jpg");

            fetch("/proctor/upload_frame", {
                method: "POST",
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                console.log("Server:", data);

                if (data.issues && data.issues.length > 0) {
                    document.getElementById("alerts").innerText =
                        "⚠️ " + data.issues.join(", ");
                } else {
                    document.getElementById("alerts").innerText = "";
                }
            });

        }, "image/jpeg");

    }, 5000);
}
