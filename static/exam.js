const video = document.getElementById('video');
const startBtn = document.getElementById('startBtn');
const submitBtn = document.getElementById('submitBtn');
const retryMediaBtn = document.getElementById('retryMediaBtn');
const exitTestBtn = document.getElementById('exitTestBtn');
const examForm = document.getElementById('examForm');
const alertsBox = document.getElementById('alerts');
const micStatus = document.getElementById('micStatus');
const timeDisplay = document.getElementById('timeRemaining');
const cameraSelect = document.getElementById('cameraSelect');
const micSelect = document.getElementById('micSelect');
const csrfInput = document.querySelector('input[name="csrf_token"]');

const studentIdInput = document.getElementById('studentId');
const totalMinutesInput = document.getElementById('totalMinutes');

const studentId = studentIdInput ? studentIdInput.value : 'student_001';
const csrfToken = csrfInput ? csrfInput.value : '';
const totalMinutes = totalMinutesInput ? Number(totalMinutesInput.value || 60) : 60;
const maxViolations = 3;
const DEVICE_PREF_KEY = 'proctor_device_preferences';

let stream;
let captureInterval;
let timerInterval;
let audioMonitorInterval;
let violationCount = 0;
let timeRemaining = totalMinutes * 60;
let proctoringStarted = false;
let tabSwitchMonitoringEnabled = false;

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

function mediaErrorMessage(err) {
  const name = err && err.name ? err.name : 'UnknownError';
  if (name === 'NotAllowedError') {
    return 'Permission denied. Allow camera/microphone for this site.';
  }
  if (name === 'NotFoundError') {
    return 'No camera or microphone device found.';
  }
  if (name === 'NotReadableError') {
    return 'Device is busy in another application. Close video call apps and retry.';
  }
  if (name === 'OverconstrainedError') {
    return 'Selected device is unavailable. Choose another device and retry.';
  }
  return `${name}: ${err && err.message ? err.message : 'media setup failed'}`;
}

function loadDevicePrefs() {
  try {
    const parsed = JSON.parse(localStorage.getItem(DEVICE_PREF_KEY) || '{}');
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch (err) {
    console.warn('Unable to parse device preferences', err);
    return {};
  }
}

function saveDevicePrefs(videoDeviceId, audioDeviceId) {
  const prefs = {
    videoDeviceId: videoDeviceId || '',
    audioDeviceId: audioDeviceId || '',
  };
  localStorage.setItem(DEVICE_PREF_KEY, JSON.stringify(prefs));
}

function getSelectedPrefs() {
  return {
    videoDeviceId: cameraSelect ? cameraSelect.value : '',
    audioDeviceId: micSelect ? micSelect.value : '',
  };
}

function stopMediaTracksOnly() {
  if (stream && stream.getTracks) {
    stream.getTracks().forEach((track) => track.stop());
  }
}

function buildConstraints(preferred) {
  const prefs = preferred || {};
  const videoConstraint = prefs.videoDeviceId
    ? { deviceId: { exact: prefs.videoDeviceId } }
    : true;
  const audioConstraint = prefs.audioDeviceId
    ? { deviceId: { exact: prefs.audioDeviceId } }
    : true;

  return {
    av: { video: videoConstraint, audio: audioConstraint },
    vOnly: { video: videoConstraint, audio: false },
  };
}

async function populateDeviceSelectors() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
    return;
  }

  const prefs = loadDevicePrefs();
  const devices = await navigator.mediaDevices.enumerateDevices();
  const videoInputs = devices.filter((d) => d.kind === 'videoinput');
  const audioInputs = devices.filter((d) => d.kind === 'audioinput');

  if (cameraSelect) {
    cameraSelect.innerHTML = '';
    videoInputs.forEach((device, idx) => {
      const option = document.createElement('option');
      option.value = device.deviceId;
      option.textContent = device.label || `Camera ${idx + 1}`;
      cameraSelect.appendChild(option);
    });
    if (prefs.videoDeviceId) {
      cameraSelect.value = prefs.videoDeviceId;
    }
  }

  if (micSelect) {
    micSelect.innerHTML = '';
    audioInputs.forEach((device, idx) => {
      const option = document.createElement('option');
      option.value = device.deviceId;
      option.textContent = device.label || `Microphone ${idx + 1}`;
      micSelect.appendChild(option);
    });
    if (prefs.audioDeviceId) {
      micSelect.value = prefs.audioDeviceId;
    }
  }
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

async function startCamera(preferredDevices = {}) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error('This browser does not support camera access.');
  }

  const constraints = buildConstraints(preferredDevices);
  let primaryError = null;

  try {
    stream = await navigator.mediaDevices.getUserMedia(constraints.av);
    video.srcObject = stream;
    return {
      audioEnabled: stream.getAudioTracks().length > 0,
      fallbackUsed: false,
      errorMessage: '',
    };
  } catch (err) {
    primaryError = err;
  }

  stream = await navigator.mediaDevices.getUserMedia(constraints.vOnly);
  video.srcObject = stream;
  return {
    audioEnabled: false,
    fallbackUsed: true,
    errorMessage: mediaErrorMessage(primaryError),
  };
}

function stopCamera() {
  stopMediaTracksOnly();
  if (captureInterval) {
    clearInterval(captureInterval);
    captureInterval = null;
  }
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
  stopAudioMonitoring();
  proctoringStarted = false;
  tabSwitchMonitoringEnabled = false;
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
  if (proctoringStarted) {
    return;
  }

  try {
    const selected = getSelectedPrefs();
    saveDevicePrefs(selected.videoDeviceId, selected.audioDeviceId);
    const mediaState = await startCamera(selected);

    if (mediaState.audioEnabled) {
      startAudioMonitoring();
    } else {
      setMicStatus(
        `Microphone unavailable. Camera-only mode active. ${mediaState.errorMessage}`,
        'text-warning',
      );
    }

    startProctoring();
    startTimer();
    proctoringStarted = true;
    tabSwitchMonitoringEnabled = true;

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
    if (retryMediaBtn) {
      retryMediaBtn.disabled = true;
    }
  } catch (err) {
    console.error(err);
    const msg = mediaErrorMessage(err);
    setMicStatus(msg, 'text-danger');
    alert(`Media setup failed: ${msg}`);
  }
}

async function exitTest() {
  const confirmed = window.confirm('Exit the current test now? Your active attempt will be closed.');
  if (!confirmed) {
    return;
  }

  try {
    tabSwitchMonitoringEnabled = false;
    stopCamera();
    const response = await fetch('/api/exam/exit', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({}),
    });

    if (!response.ok) {
      throw new Error('Unable to exit test');
    }

    window.location.href = '/student-dashboard.html';
  } catch (err) {
    console.error(err);
    alert('Could not exit test right now. Please try again.');
  }
}

async function retryMediaSetup() {
  try {
    stopAudioMonitoring();
    stopMediaTracksOnly();
    const selected = getSelectedPrefs();
    saveDevicePrefs(selected.videoDeviceId, selected.audioDeviceId);
    const mediaState = await startCamera(selected);

    if (mediaState.audioEnabled) {
      setMicStatus('Microphone monitoring ready', 'text-success');
      if (proctoringStarted) {
        startAudioMonitoring();
      }
    } else {
      setMicStatus(
        `Microphone unavailable. Camera-only mode active. ${mediaState.errorMessage}`,
        'text-warning',
      );
    }
  } catch (err) {
    const msg = mediaErrorMessage(err);
    setMicStatus(msg, 'text-danger');
    alert(`Retry failed: ${msg}`);
  }
}

async function onVisibilityChange() {
  if (!tabSwitchMonitoringEnabled || !proctoringStarted) {
    return;
  }

  if (document.hidden) {
    violationCount += 1;
    alert('Tab switching detected!');
    await logViolation('Tab switched');
    checkAutoSubmit();
  }
}

document.addEventListener('visibilitychange', onVisibilityChange);

if (startBtn) {
  startBtn.addEventListener('click', startExam);
}

if (retryMediaBtn) {
  retryMediaBtn.addEventListener('click', retryMediaSetup);
}

if (exitTestBtn) {
  exitTestBtn.addEventListener('click', exitTest);
}

if (cameraSelect) {
  cameraSelect.addEventListener('change', () => {
    const selected = getSelectedPrefs();
    saveDevicePrefs(selected.videoDeviceId, selected.audioDeviceId);
  });
}

if (micSelect) {
  micSelect.addEventListener('change', () => {
    const selected = getSelectedPrefs();
    saveDevicePrefs(selected.videoDeviceId, selected.audioDeviceId);
  });
}

populateDeviceSelectors().catch((err) => {
  console.warn('Unable to enumerate media devices', err);
});

window.onbeforeunload = () => 'Leaving will submit your exam!';
window.addEventListener('beforeunload', () => {
  tabSwitchMonitoringEnabled = false;
  stopCamera();
});
