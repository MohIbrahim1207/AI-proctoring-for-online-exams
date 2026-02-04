from flask import Flask, render_template, request, jsonify, redirect, url_for, session

from datetime import datetime
import cv2
import os

app = Flask(__name__)

app.secret_key = "exam_secret_key"



# ------------------------------
# Ensure folders exist
# ------------------------------
os.makedirs("uploads", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# ------------------------------
# Load Face Detection Model ONCE
# ------------------------------
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
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
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role")

        if password == "1234":
            session["user"] = email
            session["role"] = role

            if role == "student":
                return redirect(url_for("exam"))
            else:
                return redirect(url_for("teacher"))

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")



@app.route("/proctor/upload_screen", methods=["POST"])
def upload_screen():
    student_id = request.form.get("student_id")
    file = request.files.get("file")

    if not file or not student_id:
        return jsonify({"status": "error"})

    filename = f"uploads/screen_{student_id}_{datetime.now().timestamp()}.jpg"
    file.save(filename)

    with open("logs/screen_log.txt", "a") as log:
        log.write(f"{datetime.now()} | {student_id} | Screen captured\n")

    return jsonify({"status": "saved"})


@app.route("/exam")
def exam():
    if "user" not in session or session.get("role") != "student":
        return redirect(url_for("login"))

    return render_template("exam.html", questions=questions)


@app.route("/submit_exam", methods=["POST"])
def submit_exam():
    score = 0
    for q in questions:
        if request.form.get(q["id"]) == q["answer"]:
            score += 1

    return f"<h2>Your Score: {score}/{len(questions)}</h2>"


@app.route("/teacher")
def teacher():
    if "user" not in session or session.get("role") != "teacher":
        return redirect(url_for("login"))

    return "<h2>Teacher Dashboard</h2><p>Logged in as Teacher</p><a href='/logout'>Logout</a>"

# ------------------------------
# PROCTORING FRAME UPLOAD
# ------------------------------
@app.route("/proctor/upload_frame", methods=["POST"])
def upload_frame():
    student_id = request.form.get("student_id")
    file = request.files.get("file")

    if not file or not student_id:
        return jsonify({
            "status": "error",
            "issues": ["Invalid upload"]
        })

    filename = f"uploads/{student_id}_{datetime.now().timestamp()}.jpg"
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
    if len(faces) > 1:
        issues.append("Multiple faces detected")

    if issues:
        with open("logs/proctor_log.txt", "a") as log:
            log.write(f"{datetime.now()} | {student_id} | {issues}\n")

    return jsonify({
        "status": "received",
        "faces_detected": len(faces),
        "issues": issues
    })
@app.route("/log_violation", methods=["POST"])
def log_violation():
    data = request.json
    student_id = data.get("student_id", "unknown")
    reason = data.get("reason", "unknown")

    with open("logs/violations.txt", "a") as log:
        log.write(f"{datetime.now()} | {student_id} | {reason}\n")

    return jsonify({"status": "logged"})

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))



# ------------------------------
# Run Server
# ------------------------------
if __name__ == "__main__":
    app.run(debug=True)
