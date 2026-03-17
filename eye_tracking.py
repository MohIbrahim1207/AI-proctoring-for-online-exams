
import cv2
import mediapipe as mp
import time
import numpy as np
import requests
from datetime import datetime

mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils


# Eye and iris landmark indices for MediaPipe Face Mesh
LEFT_EYE = [33, 133, 160, 159, 158, 157, 173, 153, 154, 155]
RIGHT_EYE = [362, 263, 387, 386, 385, 384, 398, 382, 381, 380]
LEFT_IRIS = [474, 475, 476, 477]
RIGHT_IRIS = [469, 470, 471, 472]



def get_eye_landmarks(landmarks, eye_indices):
    return np.array([[landmarks[i].x, landmarks[i].y] for i in eye_indices])

def get_iris_center(landmarks, iris_indices):
    iris_points = np.array([[landmarks[i].x, landmarks[i].y] for i in iris_indices])
    return np.mean(iris_points, axis=0)


# Improved gaze detection using iris center
def get_gaze_direction(landmarks, eye_indices, iris_indices):
    eye_pts = np.array([[landmarks[i].x, landmarks[i].y] for i in eye_indices])
    iris_center = get_iris_center(landmarks, iris_indices)
    left_corner = eye_pts[0]
    right_corner = eye_pts[1]
    top = eye_pts[2]
    bottom = eye_pts[4]
    # Horizontal gaze
    x_ratio = (iris_center[0] - left_corner[0]) / (right_corner[0] - left_corner[0])
    # Vertical gaze (not used for now)
    # y_ratio = (iris_center[1] - top[1]) / (bottom[1] - top[1])
    if x_ratio < 0.35:
        return "Left"
    elif x_ratio > 0.65:
        return "Right"
    else:
        return "Center"


def draw_eye_landmarks(frame, landmarks, eye_indices, color=(0,255,0)):
    h, w, _ = frame.shape
    for idx in eye_indices:
        x = int(landmarks[idx].x * w)
        y = int(landmarks[idx].y * h)
        cv2.circle(frame, (x, y), 2, color, -1)

def draw_iris(frame, landmarks, iris_indices, color=(255,0,255)):
    h, w, _ = frame.shape
    for idx in iris_indices:
        x = int(landmarks[idx].x * w)
        y = int(landmarks[idx].y * h)
        cv2.circle(frame, (x, y), 2, color, -1)
    # Draw iris center
    iris_center = get_iris_center(landmarks, iris_indices)
    cx, cy = int(iris_center[0] * w), int(iris_center[1] * h)
    cv2.circle(frame, (cx, cy), 3, (0,0,255), -1)


def log_violation(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open('logs/violations.txt', 'a') as f:
        f.write(f"{timestamp} | {message}\n")

def send_violation_alert(issue):
    # Adjust the URL if your backend is running elsewhere
    try:
        requests.post('http://localhost:5000/proctor/violation', json={
            'issue': issue,
            'timestamp': datetime.now().isoformat(),
        }, timeout=1)
    except Exception:
        pass


def eye_tracking():
    cap = cv2.VideoCapture(0)
    with mp_face_mesh.FaceMesh(
        max_num_faces=3,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as face_mesh:
        away_start = None
        last_face_time = time.time()
        violation_cooldown = 2  # seconds between logs for same violation
        last_away_violation = 0
        last_multi_violation = 0
        last_no_face_violation = 0
        gaze_threshold = 1  # seconds to trigger "look away" (was 2)
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(frame_rgb)
            gaze = "Unknown"
            num_faces = 0
            gaze_left = "Unknown"
            gaze_right = "Unknown"
            if results.multi_face_landmarks:
                num_faces = len(results.multi_face_landmarks)
                # Multiple faces detection
                if num_faces > 1 and (time.time() - last_multi_violation > violation_cooldown):
                    msg = f"Multiple faces detected: {num_faces}"
                    log_violation(msg)
                    send_violation_alert(msg)
                    last_multi_violation = time.time()
                # Face(s) detected
                last_face_time = time.time()
                # Gaze tracking for first face
                landmarks = results.multi_face_landmarks[0].landmark
                gaze_left = get_gaze_direction(landmarks, LEFT_EYE, LEFT_IRIS)
                gaze_right = get_gaze_direction(landmarks, RIGHT_EYE, RIGHT_IRIS)
                # If either eye is not center, consider as looking away
                if gaze_left != "Center":
                    gaze = gaze_left
                elif gaze_right != "Center":
                    gaze = gaze_right
                else:
                    gaze = "Center"
                # Debug log
                print(f"Gaze Left: {gaze_left}, Gaze Right: {gaze_right}, Final: {gaze}")
                draw_eye_landmarks(frame, landmarks, LEFT_EYE, color=(0,255,0))
                draw_eye_landmarks(frame, landmarks, RIGHT_EYE, color=(0,255,0))
                draw_iris(frame, landmarks, LEFT_IRIS, color=(255,0,255))
                draw_iris(frame, landmarks, RIGHT_IRIS, color=(255,0,255))
                cv2.putText(frame, f"Gaze: {gaze}", (30, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
                if gaze != "Center":
                    if away_start is None:
                        away_start = time.time()
                    elif time.time() - away_start > gaze_threshold and (time.time() - last_away_violation > violation_cooldown):
                        msg = f"Student looked away from screen (gaze: {gaze})"
                        log_violation(msg)
                        send_violation_alert(msg)
                        last_away_violation = time.time()
                        cv2.putText(frame, "WARNING: Please look at the screen!", (30, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                else:
                    away_start = None
            else:
                # No face detected
                if time.time() - last_face_time > 2 and (time.time() - last_no_face_violation > violation_cooldown):
                    msg = "Face disappeared from camera"
                    log_violation(msg)
                    send_violation_alert(msg)
                    last_no_face_violation = time.time()
                cv2.putText(frame, "Face not detected", (30, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                away_start = None
            # Draw number of faces
            cv2.putText(frame, f"Faces: {num_faces}", (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 128, 255), 2)
            cv2.imshow('AI Proctor Eye Tracking', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    eye_tracking()
