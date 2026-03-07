const video = document.getElementById('video');
const startBtn = document.getElementById('startBtn');
const submitBtn = document.getElementById('submitBtn');
const examForm = document.getElementById('examForm');
const alertsBox = document.getElementById('alerts');
const micStatus = document.getElementById('micStatus');
const timeDisplay = document.getElementById('timeRemaining');
const csrfInput = document.querySelector('input[name="csrf_token"]');

const studentIdInput = document.getElementById('studentId');
const totalMinutesInput = document.getElementById('totalMinutes');

const studentId = studentIdInput ? studentIdInput.value : 'student_001';
const csrfToken = csrfInput ? csrfInput.value : '';
const totalMinutes = totalMinutesInput ? Number(totalMinutesInput.value || 60) : 60;
const maxViolations = 3;

let stream;
let captureInterval;
let timerInterval;
let audioMonitorInterval;
let violationCount = 0;
let timeRemaining = totalMinutes * 60;

let audioContext;
let analyser;
let audioDataArray;
let loudSpeechSeconds = 0;
let whisperSeconds = 0;
let lastAudioViolationAt = 0;

const AUDIO_SAMPLE_MS = 250;
const AUDIO_ALERT_COOLDOWN_MS = 20000;
const LOUD_RMS_THRESHOLD = 0.07;
const WHISPER_RMS_MIN = 0.015;
const WHISPER_RMS_MAX = 0.05;
const SPEECH_ZCR_MIN = 0.08;
const LOUD_DURATION_SECONDS = 1.5;
const WHISPER_DURATION_SECONDS = 4;

function csrfHeaders(extraHeaders = {}) {
  const headers = { ...extraHeaders };
  if (csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }
  return headers;
}

function submitExam() {
  if (examForm) {
    examForm.submit();
  }
}

function checkAutoSubmit() {
  if (violationCount >= maxViolations) {
    alert('Too many violations. Exam submitted.');
    submitExam();
  }
}

async function logViolation(reason) {
  try {
    const response = await fetch('/log_violation', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        student_id: studentId,
        reason,
      }),
    });
    const data = await response.json();
    if (data.auto_submitted) {
      alert('Exam auto-submitted by server due to multiple violations');
      submitExam();
    }
  } catch (err) {
    console.error('Failed to log violation', err);
  }
}

function setMicStatus(text, className = 'text-muted') {
  if (!micStatus) {
    return;
  }
  micStatus.className = className;
  micStatus.innerText = text;
}

function calculateRmsAndZcr(dataArray) {
  let sumSq = 0;
  let zeroCrossings = 0;
  let prev = dataArray[0] - 128;

  for (let i = 0; i < dataArray.length; i += 1) {
    const centered = dataArray[i] - 128;
    const normalized = centered / 128;
    sumSq += normalized * normalized;

    if ((prev >= 0 && centered < 0) || (prev < 0 && centered >= 0)) {
      zeroCrossings += 1;
    }
    prev = centered;
  }

  const rms = Math.sqrt(sumSq / dataArray.length);
  const zcr = zeroCrossings / dataArray.length;
  return { rms, zcr };
}

async function flagAudioViolation(reason) {
  const now = Date.now();
  if (now - lastAudioViolationAt < AUDIO_ALERT_COOLDOWN_MS) {
    return;
  }

  lastAudioViolationAt = now;
  violationCount += 1;
  alert(`Audio alert: ${reason}`);
  if (alertsBox) {
    alertsBox.innerText = `Warning: ${reason}`;
  }
  setMicStatus('Suspicious sound detected', 'text-danger fw-bold');
  await logViolation(reason);
  checkAutoSubmit();
}

function stopAudioMonitoring() {
  if (audioMonitorInterval) {
    clearInterval(audioMonitorInterval);
    audioMonitorInterval = null;
  }
  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }
  analyser = null;
  audioDataArray = null;
  loudSpeechSeconds = 0;
  whisperSeconds = 0;
}

function startAudioMonitoring() {
  const hasAudioTrack = stream && stream.getAudioTracks && stream.getAudioTracks().length > 0;
  if (!hasAudioTrack) {
    setMicStatus('Microphone unavailable', 'text-danger');
    return;
  }

  try {
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    audioContext = new AudioContextCtor();
    const source = audioContext.createMediaStreamSource(stream);
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    audioDataArray = new Uint8Array(analyser.fftSize);
    setMicStatus('Microphone monitoring active', 'text-success');
  } catch (err) {
    console.error('Unable to initialize audio monitor', err);
    setMicStatus('Microphone monitor failed', 'text-danger');
    return;
  }

  audioMonitorInterval = setInterval(async () => {
    if (!analyser || !audioDataArray) {
      return;
    }

    analyser.getByteTimeDomainData(audioDataArray);
    const { rms, zcr } = calculateRmsAndZcr(audioDataArray);

    const isLoudSpeech = rms >= LOUD_RMS_THRESHOLD;
    const isLikelyWhisper = rms >= WHISPER_RMS_MIN && rms <= WHISPER_RMS_MAX && zcr >= SPEECH_ZCR_MIN;

    const tickSeconds = AUDIO_SAMPLE_MS / 1000;
    loudSpeechSeconds = isLoudSpeech ? loudSpeechSeconds + tickSeconds : Math.max(0, loudSpeechSeconds - tickSeconds);
    whisperSeconds = isLikelyWhisper ? whisperSeconds + tickSeconds : Math.max(0, whisperSeconds - tickSeconds);

    if (loudSpeechSeconds >= LOUD_DURATION_SECONDS) {
      loudSpeechSeconds = 0;
      await flagAudioViolation('Suspicious audio: loud talking/noise detected');
      return;
    }

    if (whisperSeconds >= WHISPER_DURATION_SECONDS) {
      whisperSeconds = 0;
      await flagAudioViolation('Suspicious audio: whispering/talking detected');
    }
  }, AUDIO_SAMPLE_MS);
}

async function startCamera() {
  stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
  video.srcObject = stream;
}

function stopCamera() {
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
  }
  if (captureInterval) {
    clearInterval(captureInterval);
  }
  if (timerInterval) {
    clearInterval(timerInterval);
  }
  stopAudioMonitoring();
}

function startTimer() {
  timerInterval = setInterval(() => {
    const minutes = Math.floor(timeRemaining / 60);
    const seconds = timeRemaining % 60;
    if (timeDisplay) {
      timeDisplay.textContent = `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
    }

    if (timeRemaining <= 0) {
      clearInterval(timerInterval);
      alert("Time's up! Submitting exam.");
      submitExam();
      return;
    }
    timeRemaining -= 1;
  }, 1000);
}

function startProctoring() {
  captureInterval = setInterval(() => {
    if (!video || !video.videoWidth || !video.videoHeight) {
      return;
    }

    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);

    canvas.toBlob(async (blob) => {
      if (!blob) {
        return;
      }

      const formData = new FormData();
      formData.append('file', blob, 'frame.jpg');
      formData.append('student_id', studentId);

      try {
        const response = await fetch('/proctor/upload_frame', {
          method: 'POST',
          headers: csrfHeaders(),
          body: formData,
        });

        const data = await response.json();
        if (data.issues && data.issues.length > 0) {
          violationCount += 1;
          if (alertsBox) {
            alertsBox.innerText = `Warning: ${data.issues.join(', ')}`;
          }

          await logViolation(data.issues.join(', '));
          checkAutoSubmit();
        } else if (alertsBox) {
          alertsBox.innerText = '';
        }
      } catch (err) {
        console.error('Frame upload failed', err);
      }
    }, 'image/jpeg');
  }, 5000);
}

async function startExam() {
  try {
    await startCamera();
    startAudioMonitoring();
    startProctoring();
    startTimer();

    alert('Exam started. Proctoring enabled.');

    document.querySelectorAll('input[type=radio]').forEach((input) => {
      input.disabled = false;
    });

    if (submitBtn) {
      submitBtn.disabled = false;
    }
    if (startBtn) {
      startBtn.disabled = true;
    }
  } catch (err) {
    console.error(err);
    setMicStatus('Microphone permission required', 'text-danger');
    alert('Camera and microphone permissions are mandatory.');
  }
}

document.addEventListener('visibilitychange', async () => {
  if (document.hidden) {
    violationCount += 1;
    alert('Tab switching detected!');
    await logViolation('Tab switched');
    checkAutoSubmit();
  }
});

if (startBtn) {
  startBtn.addEventListener('click', startExam);
}

window.onbeforeunload = () => 'Leaving will submit your exam!';
window.addEventListener('beforeunload', stopCamera);
