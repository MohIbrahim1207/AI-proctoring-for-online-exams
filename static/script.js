// ===============================
// LOGIN REMOVED FOR NOW
// ===============================

// The app now starts immediately without login.
// Student ID is hardcoded for testing.
const student_id = "student1";

// =====================================
// START WEBCAM IMMEDIATELY ON PAGE LOAD
// =====================================
window.onload = function () {
    startWebcam();
    startSendingFrames(student_id);
};

// ---------------------------
// START WEBCAM
// ---------------------------
function startWebcam() {
    const video = document.getElementById("video");

    console.log("Requesting camera…");

    navigator.mediaDevices.getUserMedia({ video: true })
        .then(stream => {
            console.log("Camera stream obtained:", stream);
            video.srcObject = stream;
            document.getElementById("status").innerText = "Webcam active.";
        })
        .catch(err => {
            console.error("Camera error: ", err);
            document.getElementById("status").innerText = "Webcam error: " + err.name;

            if (err.name === "NotAllowedError") {
                document.getElementById("status").innerText +=
                    " (Camera blocked — enable permissions)";
            }

            if (err.name === "NotFoundError") {
                document.getElementById("status").innerText +=
                    " (No camera detected)";
            }
        });
}


// ---------------------------
// SEND FRAMES EVERY 5 SEC
// ---------------------------
function startSendingFrames(student_id) {
    const video = document.getElementById("video");

    setInterval(() => {
        let canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;

        let ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0);

        canvas.toBlob(blob => {
            const formData = new FormData();
            formData.append("student_id", student_id);
            formData.append("file", blob, "frame.jpg");

            fetch("/proctor/upload_frame", {
                method: "POST",
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                if (data.issues.length > 0) {
                    document.getElementById("alerts").innerText =
                        "⚠️ " + data.issues.join(", ");
                } else {
                    document.getElementById("alerts").innerText = "";
                }
            });
        }, "image/jpeg");
    }, 5000);
}
