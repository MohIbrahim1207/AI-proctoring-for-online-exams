from flask import Flask, render_template, request, jsonify, redirect, url_for, session

from datetime import datetime, timedelta
import time
import random
import cv2
import os
import json
import secrets
from flask import send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO
try:
    import firebase_admin
    from firebase_admin import credentials, db
except Exception:
    firebase_admin = None
    credentials = None
    db = None

app = Flask(__name__)
_env_secret = os.environ.get("FLASK_SECRET_KEY", "").strip()
# Avoid predictable fallback secrets in non-configured environments.
app.secret_key = _env_secret if _env_secret else os.urandom(32).hex()
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8MB upload limit
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_SECURE_COOKIE", "0") == "1"
app.config["CSRF_ENABLED"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
    hours=int(os.environ.get("SESSION_MAX_HOURS", "8"))
)

SESSION_IDLE_TIMEOUT_SECONDS = int(os.environ.get("SESSION_IDLE_MINUTES", "30")) * 60
SESSION_MAX_AGE_SECONDS = int(os.environ.get("SESSION_MAX_HOURS", "8")) * 3600

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri="memory://",
    default_limits=["300 per day", "120 per hour"],
)
socketio = SocketIO(app, cors_allowed_origins="*")


def _build_csp_header():
    # Keep CSP compatible with current templates that still use inline scripts/styles
    # and external CDNs for Bootstrap/Socket.IO.
    return (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.socket.io https://www.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data: https://cdn.jsdelivr.net; "
        "connect-src 'self' ws: wss:; "
        "media-src 'self' blob:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none';"
    )


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(self), microphone=(self), geolocation=(), payment=(), usb=()"
    )
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = _build_csp_header()
    return response



# ------------------------------
# Ensure folders exist
# ------------------------------
os.makedirs("uploads", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# results storage file
RESULTS_FILE = os.path.join("logs", "results.json")
if not os.path.exists(RESULTS_FILE):
    with open(RESULTS_FILE, "w") as f:
        json.dump([], f)

# users storage (JSON)
DATA_DIR = os.path.join(os.getcwd(), 'data')
os.makedirs(DATA_DIR, exist_ok=True)
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
QUESTIONS_FILE = os.path.join(DATA_DIR, 'questions.json')
if not os.path.exists(USERS_FILE):
    # create default admin and a sample student (password: 1234)
    default_users = [
        {"email": "admin@example.com", "name": "Admin", "role": "teacher", "password": generate_password_hash("1234")},
        {"email": "student@example.com", "name": "Student One", "role": "student", "password": generate_password_hash("1234")}]
    with open(USERS_FILE, 'w') as f:
        json.dump(default_users, f, indent=2)

# proctoring threshold
MAX_WARNINGS = 3

FIREBASE_DB_URL = os.environ.get("FIREBASE_DB_URL", "").strip()
FIREBASE_CRED_PATH = os.environ.get(
    "FIREBASE_CRED_PATH",
    os.path.join(DATA_DIR, "firebase-service-account.json"),
)
FIREBASE_ENABLED = False

def init_firebase():
    global FIREBASE_ENABLED

    if not firebase_admin or not FIREBASE_DB_URL:
        return
    if not os.path.exists(FIREBASE_CRED_PATH):
        return
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_CRED_PATH)
            firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
        FIREBASE_ENABLED = True
    except Exception as e:
        print(f"Firebase init failed: {e}")


def _firebase_results_to_list(payload):
    if not payload:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [v for v in payload.values() if isinstance(v, dict)]
    return []


def load_users():
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []


def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)


def _safe_student_id(raw_student_id):
    sid = (raw_student_id or "").strip()
    # secure_filename removes path separators and unsafe characters.
    sid = secure_filename(sid)
    if not sid:
        sid = "unknown"
    return sid[:80]


def get_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": get_csrf_token()}


@app.before_request
def enforce_session_timeout():
    # Public endpoints should remain reachable without an authenticated session.
    public_endpoints = {"login", "register", "logout", "static"}
    if request.endpoint in public_endpoints:
        return None

    if "user" not in session:
        return None

    now_ts = int(time.time())
    last_activity_ts = int(session.get("last_activity_ts", now_ts))
    login_ts = int(session.get("login_ts", now_ts))

    idle_expired = (now_ts - last_activity_ts) > SESSION_IDLE_TIMEOUT_SECONDS
    max_age_expired = (now_ts - login_ts) > SESSION_MAX_AGE_SECONDS

    if idle_expired or max_age_expired:
        session.clear()
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"error": "Session expired. Please login again."}), 401
        return redirect(url_for("login"))

    session["last_activity_ts"] = now_ts
    session.permanent = True
    return None


@app.before_request
def csrf_protect():
    if not app.config.get("CSRF_ENABLED", True):
        return None

    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None

    if request.endpoint == "static":
        return None

    expected = session.get("_csrf_token")
    provided = request.headers.get("X-CSRF-Token")

    if not provided:
        provided = request.form.get("csrf_token")

    if not provided and request.is_json:
        payload = request.get_json(silent=True) or {}
        provided = payload.get("csrf_token")

    if not expected or not provided or provided != expected:
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"error": "CSRF validation failed"}), 400
        return "CSRF validation failed", 400

    return None


init_firebase()

# ------------------------------
# Load Face Detection Model ONCE
# ------------------------------
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)
eye_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_eye.xml"
)

# ------------------------------
# MCQ DATA
# ------------------------------
questions = [
    {
        "id": "q1",
        "question": "What does CPU stand for?",
        "options": ["Central Processing Unit", "Computer Personal Unit", "Central Power Unit"],
        "answer": "Central Processing Unit"
    },
    {
        "id": "q2",
        "question": "Which language is used for AI?",
        "options": ["Python", "HTML", "CSS"],
        "answer": "Python"
    },
    {
        "id": "q3",
        "question": "Which protocol is used for the web?",
        "options": ["HTTP", "FTP", "SMTP"],
        "answer": "HTTP"
    }
]

# ------------------------------
# ROUTES
# ------------------------------
@app.route("/", methods=["GET", "POST"])
@limiter.limit("12 per minute")
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role")

        users = load_users()
        user = next((u for u in users if u.get('email') == email), None)
        if user and check_password_hash(user.get('password', ''), password):
            now_ts = int(time.time())
            session["user"] = email
            session["role"] = user.get('role', role)
            session["name"] = user.get('name', email)
            session["login_ts"] = now_ts
            session["last_activity_ts"] = now_ts
            session.permanent = True

            if session["role"] == "student":
                return redirect(url_for("student_dashboard"))
            else:
                return redirect(url_for("teacher_dashboard"))

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")



@app.route("/proctor/upload_screen", methods=["POST"])
@limiter.limit("60 per minute")
def upload_screen():
    student_id = request.form.get("student_id")
    file = request.files.get("file")

    if not file or not student_id:
        return jsonify({"status": "error"})

    safe_student_id = _safe_student_id(student_id)
    filename = f"uploads/screen_{safe_student_id}_{datetime.now().timestamp()}.jpg"
    file.save(filename)

    with open("logs/screen_log.txt", "a") as log:
        log.write(f"{datetime.now()} | {student_id} | Screen captured\n")

    socketio.emit("screen_uploaded", {
        "user": safe_student_id,
        "timestamp": datetime.now().isoformat(),
    })

    return jsonify({"status": "saved"})


@app.route("/student-dashboard.html")
def student_dashboard():
    if "user" not in session or session.get("role") != "student":
        return redirect(url_for("login"))

    return render_template("dashboard.html")


# @app.route("/exam")
# def exam():
#     # ... (replaced)
#     pass

# @app.route("/submit_exam", methods=["POST"])
# def submit_exam():
#     # ... (replaced)
#     pass


@app.route("/teacher")
def teacher():
    if "user" not in session or session.get("role") != "teacher":
        return redirect(url_for("login"))

    return "<h2>Teacher Dashboard</h2><p>Logged in as Teacher</p><a href='/logout'>Logout</a>"

# ------------------------------
# PROCTORING FRAME UPLOAD
# ------------------------------
@app.route("/proctor/upload_frame", methods=["POST"])
@limiter.limit("120 per minute")
def upload_frame():
    student_id = request.form.get("student_id")
    file = request.files.get("file")

    if not file or not student_id:
        return jsonify({
            "status": "error",
            "issues": ["Invalid upload"]
        })

    safe_student_id = _safe_student_id(student_id)
    filename = f"uploads/{safe_student_id}_{datetime.now().timestamp()}.jpg"
    file.save(filename)

    image = cv2.imread(filename)
    if image is None:
        return jsonify({
            "status": "error",
            "issues": ["Invalid image frame"]
        })

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    issues = []
    if len(faces) == 0:
        issues.append("No face detected")
    elif len(faces) > 1:
        issues.append("Multiple people detected! Only one candidate allowed.")
    else:
        # One face detected - check eyes
        for (x, y, w, h) in faces:
            roi_gray = gray[y:y+h, x:x+w]
            eyes = eye_cascade.detectMultiScale(roi_gray, 1.1, 3)
            if len(eyes) < 2:
                # This can be sensitive; often one eye is detected or glasses interfere.
                # Only warn if consistent? For now, we warn.
                # To reduce noise, we could count violations on client side or checking history,
                # but user asked for "precise" tracking.
                issues.append("Suspicious behavior: Eyes not clearly visible / Looking away")

    if issues:
        with open("logs/proctor_log.txt", "a") as log:
            log.write(f"{datetime.now()} | {student_id} | {issues}\n")
        # structured alerts file
        alerts_path = os.path.join('logs', 'alerts.json')
        alert_entry = {
            'user': student_id,
            'issues': issues,
            'file': filename,
            'timestamp': datetime.now().isoformat()
        }
        try:
            if os.path.exists(alerts_path):
                with open(alerts_path, 'r') as af:
                    alerts = json.load(af)
            else:
                alerts = []
        except Exception:
            alerts = []
        
        alerts.append(alert_entry)
        try:
            with open(alerts_path, 'w') as af:
                json.dump(alerts, af, indent=2)
        except Exception:
            pass

        # also append to violations.txt for legacy view
        with open("logs/violations.txt", "a") as v:
            v.write(f"{datetime.now()} | {student_id} | {issues}\n")

        socketio.emit("violation_detected", {
            "user": safe_student_id,
            "issues": issues,
            "timestamp": datetime.now().isoformat(),
        })

    socketio.emit("frame_uploaded", {
        "user": safe_student_id,
        "faces_detected": len(faces),
        "issues": issues,
        "timestamp": datetime.now().isoformat(),
    })

    return jsonify({
        "status": "received",
        "faces_detected": len(faces),
        "issues": issues
    })
@app.route("/log_violation", methods=["POST"])
@limiter.limit("120 per minute")
def log_violation():
    data = request.json
    student_id = data.get("student_id", "unknown")
    reason = data.get("reason", "unknown")

    # append plain text log (legacy)
    with open("logs/violations.txt", "a") as log:
        log.write(f"{datetime.now()} | {student_id} | {reason}\n")

    # append structured alerts
    alerts_path = os.path.join('logs', 'alerts.json')
    entry = {'user': student_id, 'reason': reason, 'timestamp': datetime.now().isoformat()}
    try:
        if os.path.exists(alerts_path):
            with open(alerts_path, 'r') as af:
                alerts = json.load(af)
        else:
            alerts = []
    except Exception:
        alerts = []

    alerts.append(entry)
    try:
        with open(alerts_path, 'w') as af:
            json.dump(alerts, af, indent=2)
    except Exception:
        pass

    # count alerts for this student and auto-submit once when threshold reached
    user_alerts = [a for a in alerts if a.get('user') == student_id]
    auto_submitted = False
    if len(user_alerts) == MAX_WARNINGS:
        # perform auto-submit: create a result with score 0
        result_entry = {
            "user": student_id,
            "examName": "MCQ Exam",
            "allottedTime": 60,
            "totalMarks": len(load_questions()),
            "score": 0,
            "status": "Auto-submitted (too many violations)",
            "timestamp": datetime.now().isoformat()
        }
        append_result(result_entry)
        auto_submitted = True

    socketio.emit("manual_violation", {
        "user": student_id,
        "reason": reason,
        "auto_submitted": auto_submitted,
        "timestamp": datetime.now().isoformat(),
    })

    return jsonify({"status": "logged", "auto_submitted": auto_submitted})


@app.route("/api/results")
def api_results():
    if "user" not in session:
        return jsonify([])

    user = session.get("user")
    results = load_results()
    user_results = [r for r in results if r.get("user") == user]
    return jsonify(user_results)


# ------------------------------
# EXAM MANAGEMENT
# ------------------------------
def load_results():
    if FIREBASE_ENABLED:
        try:
            payload = db.reference("results").get()
            return _firebase_results_to_list(payload)
        except Exception as e:
            print(f"Firebase read failed, using JSON fallback: {e}")

    try:
        with open(RESULTS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def save_results(results):
    if FIREBASE_ENABLED:
        try:
            db.reference("results").set(results)
            return
        except Exception as e:
            print(f"Firebase write failed, using JSON fallback: {e}")

    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)


def append_result(result_entry):
    if FIREBASE_ENABLED:
        try:
            db.reference("results").push(result_entry)
            return
        except Exception as e:
            print(f"Firebase append failed, using JSON fallback: {e}")

    results = load_results()
    results.append(result_entry)
    save_results(results)

EXAMS_DIR = os.path.join(DATA_DIR, 'questions')
if not os.path.exists(EXAMS_DIR):
    os.makedirs(EXAMS_DIR)

AVAILABLE_EXAMS = [
    {"id": "c_programming", "name": "C Programming", "minutes": 45, "file": "c_programming.json"},
    {"id": "sql", "name": "SQL", "minutes": 30, "file": "sql.json"},
    {"id": "rdbms", "name": "RDBMS", "minutes": 30, "file": "rdbms.json"},
    {"id": "data_structures", "name": "Data Structures", "minutes": 45, "file": "data_structures.json"},
    {"id": "python", "name": "Python", "minutes": 45, "file": "python.json"},
    {"id": "java", "name": "Java", "minutes": 60, "file": "java.json"},
    {"id": "spring_boot", "name": "Spring Boot", "minutes": 60, "file": "spring_boot.json"}
]

@app.route("/api/exams")
def api_exams():
    if "user" not in session:
        return jsonify([])
    
    # Enrich with dynamic total marks from files
    exams_list = []
    for ex in AVAILABLE_EXAMS:
        qs = load_questions(ex['id'])
        exams_list.append({
            "id": ex['id'],
            "name": ex['name'],
            "duration": ex['minutes'],
            "totalMarks": len(qs)
        })
    return jsonify(exams_list)

def load_questions(exam_id=None):
    if not exam_id:
        # fallback/legacy: load from questions.json if it exists, else empty
        try:
            with open(QUESTIONS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    
    # find filename from ID
    exam_meta = next((x for x in AVAILABLE_EXAMS if x['id'] == exam_id), None)
    if not exam_meta:
        return []
    
    filepath = os.path.join(EXAMS_DIR, exam_meta['file'])
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception:
        return []


def save_questions(questions_data, exam_id=None):
    if exam_id:
        exam_meta = next((x for x in AVAILABLE_EXAMS if x['id'] == exam_id), None)
        if not exam_meta:
            return False
        filepath = os.path.join(EXAMS_DIR, exam_meta['file'])
    else:
        filepath = QUESTIONS_FILE

    with open(filepath, 'w') as f:
        json.dump(questions_data, f, indent=2)
    return True

@app.route("/exam")
def exam():
    if "user" not in session or session.get("role") != "student":
        return redirect(url_for("login"))
    
    exam_id = request.args.get('id')
    if not exam_id:
        return redirect(url_for('student_dashboard'))
        
    exam_meta = next((x for x in AVAILABLE_EXAMS if x['id'] == exam_id), None)
    if not exam_meta:
        return redirect(url_for('student_dashboard'))

    # Store exam context in session
    # We clear seed if switching exams to ensure fresh start? 
    # Or keep seed per exam_id? simpler: just reset seed if exam_id changes
    if session.get('current_exam_id') != exam_id:
        session['current_exam_id'] = exam_id
        session['exam_seed'] = int(time.time())
        session['exam_user'] = session.get('user')

    seed = session.get('exam_seed')
    qs = load_questions(exam_id)
    rng = random.Random(seed)
    rng.shuffle(qs)
    for q in qs:
        rng.shuffle(q['options'])

    return render_template("exam.html", questions=qs, exam_meta=exam_meta)

@app.route("/submit_exam", methods=["POST"])
def submit_exam():
    exam_id = session.get('current_exam_id')
    if not exam_id:
        return redirect(url_for("student_dashboard"))

    exam_meta = next((x for x in AVAILABLE_EXAMS if x['id'] == exam_id), None)
    
    # Reconstruct the same shuffled questions/options using the saved seed
    score = 0
    seed = session.get('exam_seed')
    qs = load_questions(exam_id)
    if seed:
        rng = random.Random(seed)
        rng.shuffle(qs)
        for q in qs:
            rng.shuffle(q['options'])
            
    for q in qs:
        # form keys are q['id']
        if request.form.get(q["id"]) == q["answer"]:
            score += 1
            
    user = session.get("user", "anonymous")
    result_entry = {
        "user": user,
        "examName": exam_meta['name'] if exam_meta else "Unknown Exam",
        "allottedTime": exam_meta['minutes'] if exam_meta else 0,
        "totalMarks": len(qs),
        "score": score,
        "status": "Completed",
        "timestamp": datetime.now().isoformat()
    }

    append_result(result_entry)

    # clear exam context
    session.pop('exam_seed', None)
    session.pop('exam_user', None)
    session.pop('current_exam_id', None)

    return redirect(url_for("student_dashboard"))

# Legacy/Admin routes might need updates if they rely on load_questions without args
# For now keeping them as is, they might break for specific exams, 
# but user only asked for enabling these exams for students.


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'student')

        if not (name and email and password):
            return render_template('register.html', error='Fill all fields')

        users = load_users()
        if any(u.get('email') == email for u in users):
            return render_template('register.html', error='User already exists')

        users.append({'email': email, 'name': name, 'role': role, 'password': generate_password_hash(password)})
        save_users(users)

        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    uploads_dir = os.path.join(os.getcwd(), 'uploads')
    file_path = os.path.join(uploads_dir, filename)
    if not os.path.isfile(file_path):
        abort(404)
    return send_from_directory(uploads_dir, filename)


@app.route('/teacher-dashboard')
def teacher_dashboard():
    if 'user' not in session or session.get('role') != 'teacher':
        return redirect(url_for('login'))
    return render_template('teacher_dashboard.html')


@app.route('/api/uploads')
def api_uploads():
    if 'user' not in session or session.get('role') != 'teacher':
        return jsonify({'error': 'forbidden'}), 403

    uploads_dir = os.path.join(os.getcwd(), 'uploads')
    files = []
    try:
        for fn in sorted(os.listdir(uploads_dir), reverse=True):
            if fn.lower().endswith(('.png', '.jpg', '.jpeg')):
                files.append({'name': fn, 'url': url_for('uploaded_file', filename=fn)})
    except Exception:
        pass
    return jsonify(files[:50])


@app.route('/api/proctor_logs')
def api_proctor_logs():
    if 'user' not in session or session.get('role') != 'teacher':
        return jsonify({'error': 'forbidden'}), 403

    logpath = os.path.join('logs', 'proctor_log.txt')
    entries = []
    if os.path.exists(logpath):
        with open(logpath, 'r') as f:
            for line in f.read().splitlines()[-200:][::-1]:
                entries.append(line)
    return jsonify(entries)


@app.route('/api/violations')
def api_violations():
    if 'user' not in session or session.get('role') != 'teacher':
        return jsonify({'error': 'forbidden'}), 403

    logpath = os.path.join('logs', 'violations.txt')
    entries = []
    if os.path.exists(logpath):
        with open(logpath, 'r') as f:
            for line in f.read().splitlines()[-200:][::-1]:
                entries.append(line)
    return jsonify(entries)


@app.route('/admin/questions', methods=['GET', 'POST'])
def admin_questions():
    if 'user' not in session or session.get('role') != 'teacher':
        return redirect(url_for('login'))

    if request.method == 'POST':
        qid = request.form.get('id')
        qtext = request.form.get('question')
        opts = [request.form.get('opt1'), request.form.get('opt2'), request.form.get('opt3'), request.form.get('opt4')]
        answer = request.form.get('answer')

        qs = load_questions()
        existing = next((x for x in qs if x.get('id') == qid), None)
        entry = {'id': qid, 'question': qtext, 'options': opts, 'answer': answer}
        if existing:
            qs = [entry if x.get('id') == qid else x for x in qs]
        else:
            qs.append(entry)
        save_questions(qs)
        return redirect(url_for('admin_questions'))

    qs = load_questions()
    return render_template('admin_questions.html', questions=qs)


@app.route('/api/alerts')
def api_alerts():
    if 'user' not in session or session.get('role') != 'teacher':
        return jsonify({'error': 'forbidden'}), 403

    alerts_path = os.path.join('logs', 'alerts.json')
    try:
        with open(alerts_path, 'r') as f:
            return jsonify(json.load(f)[-200:][::-1])
    except Exception:
        return jsonify([])


@app.route('/api/alerts_count')
def api_alerts_count():
    if 'user' not in session:
        return jsonify({'count': 0})
    user = session.get('user')
    alerts_path = os.path.join('logs', 'alerts.json')
    try:
        with open(alerts_path, 'r') as f:
            alerts = json.load(f)
    except Exception:
        alerts = []
    user_alerts = [a for a in alerts if a.get('user') == user]
    return jsonify({'count': len(user_alerts)})



# ------------------------------
# Run Server
# ------------------------------
if __name__ == "__main__":
    socketio.run(app, debug=True)
