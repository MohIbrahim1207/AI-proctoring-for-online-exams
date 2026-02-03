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
# Load face detector ONCE
# ------------------------------
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

# ------------------------------
# ROUTES
# ------------------------------
@app.route("/")
def index():
    return render_template("backend/index.html")

@app.route("/exam")
def exam():
    return render_template("backend/exam.html")

# ------------------------------
# Optional Login (Demo only)
# ------------------------------
@app.route("/auth/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")

    if username == "student" and password == "password123":
        return jsonify({"status": "success", "message": "Logged in"})
    return jsonify({"status": "error", "message": "Invalid credentials"})

# ------------------------------
# Proctoring Frame Upload
# ------------------------------
@app.route("/proctor/upload_frame", methods=["POST"])
def upload_frame():
    student_id = request.form.get("student_id", "unknown")
    file = request.files.get("file")

    if not file:
        return jsonify({
            "status": "error",
            "issues": ["No file received"]
        })

    # Decode image directly from memory
    npimg = np.frombuffer(file.read(), np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    if frame is None:
        return jsonify({
            "status": "error",
            "issues": ["Invalid image frame"]
        })

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=4,
        minSize=(60, 60)
    )

    issues = []
    if len(faces) == 0:
        issues.append("No face detected")
    if len(faces) > 1:
        issues.append("Multiple faces detected")

    # Draw face boxes (debug)
    for (x, y, w, h) in faces:
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

    # Save debug image
    debug_filename = f"uploads/debug_{student_id}_{datetime.now().timestamp()}.jpg"
    cv2.imwrite(debug_filename, frame)

    # Log violations
    if issues:
        with open("logs/log.txt", "a") as log:
            log.write(f"{datetime.now()} | {student_id} | {issues}\n")

    return jsonify({
        "status": "received",
        "faces_detected": len(faces),
        "issues": issues
    })

# ------------------------------
# Run Flask App
# ------------------------------
if __name__ == "__main__":
    app.run(debug=True)
