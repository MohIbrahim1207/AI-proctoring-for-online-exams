const studentId = window.STUDENT_ID || 'student1';
const csrfToken = window.CSRF_TOKEN || '';
const examId = window.EXAM_ID || '';

const video = document.getElementById('video');
const statusEl = document.getElementById('status');
const micPrecheckEl = document.getElementById('micPrecheck');
const alertsEl = document.getElementById('alerts');
const continueBtn = document.getElementById('continueBtn');

let cameraStream;
let sendInterval;

function mediaMessage(err) {
    if (!err || !err.name) {
        return 'Unknown media error';
    }
    if (err.name === 'NotAllowedError') {
        return 'Permission denied. Allow camera and microphone in browser site settings.';
    }
    if (err.name === 'NotFoundError') {
        return 'Camera or microphone not found on this device.';
    }
    if (err.name === 'NotReadableError') {
        return 'Camera or microphone is currently in use by another app.';
    }
    return `${err.name}: ${err.message || 'media access failed'}`;
}

async function checkCameraAndPreview() {
    cameraStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    video.srcObject = cameraStream;
    statusEl.innerText = 'Webcam active';
}

async function checkMicrophone() {
    const micStream = await navigator.mediaDevices.getUserMedia({ video: false, audio: true });
    micStream.getTracks().forEach((track) => track.stop());
    micPrecheckEl.className = 'status-line mb-2 text-success';
    micPrecheckEl.innerText = 'Microphone active';
}

function startSendingFrames() {
    if (sendInterval) {
        clearInterval(sendInterval);
    }

    sendInterval = setInterval(() => {
        if (!video.videoWidth || !video.videoHeight) {
            return;
        }

        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;

        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0);

        canvas.toBlob((blob) => {
            if (!blob) {
                return;
            }

            const formData = new FormData();
            formData.append('student_id', studentId);
            formData.append('file', blob, 'frame.jpg');

            fetch('/proctor/upload_frame', {
                method: 'POST',
                headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : {},
                body: formData,
            })
                .then((res) => res.json())
                .then((data) => {
                    if (data.issues && data.issues.length > 0) {
                        alertsEl.innerText = `Warning: ${data.issues.join(', ')}`;
                    } else {
                        alertsEl.innerText = '';
                    }
                })
                .catch((err) => {
                    console.warn('Precheck frame upload failed', err);
                });
        }, 'image/jpeg');
    }, 5000);
}

async function completePrecheck() {
    const response = await fetch('/api/precheck/complete', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
        },
        body: JSON.stringify({
            exam_id: examId,
            camera_ok: true,
            mic_ok: true,
        }),
    });

    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || 'Precheck confirmation failed');
    }
}

async function runPrecheck() {
    if (!examId) {
        statusEl.innerText = 'Missing exam context. Return to dashboard and try again.';
        return;
    }

    try {
        await checkCameraAndPreview();
        await checkMicrophone();
        startSendingFrames();
        alertsEl.innerText = '';
        continueBtn.disabled = false;
    } catch (err) {
        continueBtn.disabled = true;
        const msg = mediaMessage(err);
        statusEl.innerText = msg;
        micPrecheckEl.className = 'status-line mb-2 text-danger';
        micPrecheckEl.innerText = 'Microphone check failed';
        alertsEl.innerText = msg;
    }
}

continueBtn.addEventListener('click', async () => {
    continueBtn.disabled = true;
    try {
        await completePrecheck();
        window.location.href = `/exam?id=${encodeURIComponent(examId)}`;
    } catch (err) {
        alertsEl.innerText = err.message || 'Unable to continue';
        continueBtn.disabled = false;
    }
});

window.addEventListener('beforeunload', () => {
    if (sendInterval) {
        clearInterval(sendInterval);
    }
    if (cameraStream) {
        cameraStream.getTracks().forEach((track) => track.stop());
    }
});

window.addEventListener('load', runPrecheck);
