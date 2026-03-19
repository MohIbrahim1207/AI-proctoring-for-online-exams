import json
import os
from flask import Flask
from werkzeug.security import generate_password_hash
from models import db, User, Exam, Question, Attempt, Result, Alert, Feedback
from datetime import datetime

def migrate():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()

        DATA_DIR = os.path.join(os.getcwd(), 'data')
        LOGS_DIR = os.path.join(os.getcwd(), 'logs')
        
        # 1. Migrate Users
        users_file = os.path.join(DATA_DIR, 'users.json')
        if os.path.exists(users_file):
            print("Migrating users...")
            with open(users_file, 'r') as f:
                users_data = json.load(f)
                for u in users_data:
                    if not User.query.filter_by(email=u['email']).first():
                        user = User(
                            email=u['email'],
                            name=u.get('name'),
                            role=u.get('role', 'student'),
                            password_hash=u.get('password') # Already hashed in JSON
                        )
                        db.session.add(user)
            db.session.commit()

        # 2. Migrate Exams & Questions
        AVAILABLE_EXAMS = [
            {"id": "c_programming", "name": "C Programming", "minutes": 45, "file": "c_programming.json"},
            {"id": "sql", "name": "SQL", "minutes": 30, "file": "sql.json"},
            {"id": "rdbms", "name": "RDBMS", "minutes": 30, "file": "rdbms.json"},
            {"id": "data_structures", "name": "Data Structures", "minutes": 45, "file": "data_structures.json"},
            {"id": "python", "name": "Python", "minutes": 45, "file": "python.json"},
            {"id": "java", "name": "Java", "minutes": 60, "file": "java.json"},
            {"id": "spring_boot", "name": "Spring Boot", "minutes": 60, "file": "spring_boot.json"}
        ]
        
        exams_dir = os.path.join(DATA_DIR, 'questions')
        for ex in AVAILABLE_EXAMS:
            if not Exam.query.get(ex['id']):
                print(f"Migrating exam: {ex['name']}")
                exam = Exam(id=ex['id'], name=ex['name'], duration_minutes=ex['minutes'])
                db.session.add(exam)
                
                # Load questions for this exam
                q_file = os.path.join(exams_dir, ex['file'])
                if os.path.exists(q_file):
                    with open(q_file, 'r') as f:
                        qs = json.load(f)
                        for q_data in qs:
                            if not Question.query.get(q_data['id']):
                                q = Question(
                                    id=q_data['id'],
                                    exam_id=ex['id'],
                                    question_text=q_data['question'],
                                    options=q_data['options'],
                                    answer=q_data['answer']
                                )
                                db.session.add(q)
        db.session.commit()

        # 3. Migrate Attempts
        attempts_file = os.path.join(LOGS_DIR, 'attempts.json')
        if os.path.exists(attempts_file):
            print("Migrating attempts...")
            with open(attempts_file, 'r') as f:
                attempts_data = json.load(f)
                for a in attempts_data:
                    if not Attempt.query.filter_by(attempt_id=a['attempt_id']).first():
                        started_at = None
                        if a.get('started_at'):
                            try:
                                started_at = datetime.fromisoformat(a['started_at'])
                            except: pass
                        
                        submitted_at = None
                        if a.get('submitted_at'):
                            try:
                                submitted_at = datetime.fromisoformat(a['submitted_at'])
                            except: pass

                        attempt = Attempt(
                            attempt_id=a['attempt_id'],
                            user_email=a['user'],
                            exam_id=a['exam_id'],
                            exam_name=a.get('exam_name'),
                            minutes=a.get('minutes'),
                            status=a.get('status'),
                            seed=a.get('seed'),
                            started_at=started_at,
                            submitted_at=submitted_at,
                            score=a.get('score', 0),
                            total_marks=a.get('totalMarks', 0)
                        )
                        db.session.add(attempt)
            db.session.commit()

        # 4. Migrate Results
        results_file = os.path.join(LOGS_DIR, 'results.json')
        if os.path.exists(results_file):
            print("Migrating results...")
            with open(results_file, 'r') as f:
                results_data = json.load(f)
                for r in results_data:
                    ts = None
                    if r.get('timestamp'):
                        try:
                            ts = datetime.fromisoformat(r['timestamp'])
                        except: pass
                    
                    res = Result(
                        user_email=r['user'],
                        exam_name=r.get('examName'),
                        allotted_time=r.get('allottedTime'),
                        total_marks=r.get('totalMarks'),
                        score=r.get('score'),
                        status=r.get('status'),
                        attempt_id=r.get('attempt_id'),
                        timestamp=ts
                    )
                    db.session.add(res)
            db.session.commit()

        # 5. Migrate Alerts
        alerts_file = os.path.join(LOGS_DIR, 'alerts.json')
        if os.path.exists(alerts_file):
            print("Migrating alerts...")
            with open(alerts_file, 'r') as f:
                alerts_data = json.load(f)
                for al in alerts_data:
                    ts = None
                    if al.get('timestamp'):
                        try:
                            ts = datetime.fromisoformat(al['timestamp'])
                        except: pass
                    
                    alert = Alert(
                        user_email=al['user'],
                        issues=al.get('issues') or [al.get('reason')],
                        file_path=al.get('file'),
                        timestamp=ts
                    )
                    db.session.add(alert)
            db.session.commit()

        # 6. Migrate Feedbacks
        feedback_file = os.path.join(LOGS_DIR, 'feedback.json')
        if os.path.exists(feedback_file):
            print("Migrating feedback...")
            with open(feedback_file, 'r') as f:
                feedbacks_data = json.load(f)
                for fb in feedbacks_data:
                    ts = None
                    if fb.get('timestamp'):
                        try:
                            ts = datetime.fromisoformat(fb['timestamp'])
                        except: pass
                    
                    f_obj = Feedback(
                        feedback_id=fb.get('id'),
                        user_email=fb['user'],
                        exam_name=fb.get('examName'),
                        feedback_text=fb.get('feedback'),
                        teacher_email=fb.get('teacher'),
                        timestamp=ts
                    )
                    db.session.add(f_obj)
            db.session.commit()

        print("Migration complete!")

if __name__ == "__main__":
    migrate()
