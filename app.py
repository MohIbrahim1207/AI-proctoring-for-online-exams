from flask import Flask, render_template, request, jsonify
from datetime import datetime
import cv2
import numpy as np
import os

app = Flask(__name__)

# ------------------------------
# Ensure folders exist
# ------------------------------
os.makedirs("uploads", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# ------------------------------
# MCQ DATA
# ------------------------------
questions = [
    {
        "question": "What does CPU stand for?",
        "options": ["Central Processing Unit", "Computer Personal Unit", "Central Power Unit"],
        "answer": "Central Processing Unit"
    },
    {
        "question": "Which language is used for AI?",
        "options": ["Python", "HTML", "CSS"],
        "answer": "Python"
    },
    {
        "question": "Which protocol is used for the web?",
        "options": ["HTTP", "FTP", "SMTP"],
        "answer": "HTTP"
    }
]

# ------------------------------
# ROUTES
# ------------------------------

@app.route("/")
def index():
    return render_template("index.html")

# --- MCQ Exam Page ---
@app.route("/exam")
def exam():
    return render_template("exam.html", questions=questions)

# --- MCQ Submit ---
@app.route("/submit_exam", methods=["POST"])
def submit_exam():
    score = 0

    for i, q in enumerate(questions):
        selected = request.form.get(f"q{i+1}")
        if selected == q["answer"]:
            score += 1

    return f"<h2>Your Score: {score}/{len(questions)}</h2>"

# --- Upload Proctoring Frames ---
@app.route("/proctor/upload_frame", methods=["POST"])
def upload_frame():
    student_id = request.form.get("student_id")
    file = request.files.get("file")

    if not file:
        return jsonify({"status": "error", "message": "No file uploaded"})

    filename = f"uploads/{student_id}_{datetime.now().timestamp()}.jpg"
    file.save(filename)

    # Load image for face detection
    image = cv2.imread(filename)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    issues = []
    if len(faces) == 0:
        issues.append("No face detected")
    if len(faces) > 1:
        issues.append("Multiple faces detected")

    # Log issues
    if issues:
        with open("logs/proctor_log.txt", "a") as log:
            log.write(f"{datetime.now()} | {student_id} | {issues}\n")

    return jsonify({
        "status": "received",
        "faces_detected": len(faces),
        "issues": issues
    })

# ------------------------------
# Run the server
# ------------------------------
if __name__ == "__main__":
    app.run(debug=True)
