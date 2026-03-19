from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100))
    role = db.Column(db.String(20), default='student')  # 'student' or 'teacher'
    password_hash = db.Column(db.String(200), nullable=False)
    
    attempts = db.relationship('Attempt', backref='user_rel', lazy=True)
    feedbacks = db.relationship('Feedback', backref='student_rel', lazy=True)

class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    duration_minutes = db.Column(db.Integer, default=60)
    
    questions = db.relationship('Question', backref='exam_rel', lazy=True)
    attempts = db.relationship('Attempt', backref='exam_rel', lazy=True)

class Question(db.Model):
    __tablename__ = 'questions'
    id = db.Column(db.String(50), primary_key=True)
    exam_id = db.Column(db.String(50), db.ForeignKey('exams.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON, nullable=False)  # Store options as a JSON array
    answer = db.Column(db.String(255), nullable=False)

class Attempt(db.Model):
    __tablename__ = 'attempts'
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    user_email = db.Column(db.String(120), db.ForeignKey('users.email'), nullable=False)
    exam_id = db.Column(db.String(50), db.ForeignKey('exams.id'), nullable=False)
    exam_name = db.Column(db.String(100))
    minutes = db.Column(db.Integer)
    status = db.Column(db.String(20), default='active')  # 'active', 'submitted', 'exited', 'auto_submitted'
    seed = db.Column(db.Integer)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime)
    score = db.Column(db.Integer, default=0)
    total_marks = db.Column(db.Integer, default=0)

    alerts = db.relationship('Alert', backref='attempt_rel', lazy=True)

class Result(db.Model):
    __tablename__ = 'results'
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(120), db.ForeignKey('users.email'), nullable=False)
    exam_name = db.Column(db.String(100))
    allotted_time = db.Column(db.Integer)
    total_marks = db.Column(db.Integer)
    score = db.Column(db.Integer)
    status = db.Column(db.String(50))
    attempt_id = db.Column(db.String(36))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Alert(db.Model):
    __tablename__ = 'alerts'
    id = db.Column(db.Integer, primary_key=True)
    user_email = db.Column(db.String(120), db.ForeignKey('users.email'), nullable=False)
    attempt_id = db.Column(db.String(36), db.ForeignKey('attempts.attempt_id'))
    issues = db.Column(db.JSON)  # Store issues as a JSON array
    file_path = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Feedback(db.Model):
    __tablename__ = 'feedbacks'
    id = db.Column(db.Integer, primary_key=True)
    feedback_id = db.Column(db.String(16))
    user_email = db.Column(db.String(120), db.ForeignKey('users.email'), nullable=False)
    exam_name = db.Column(db.String(100))
    feedback_text = db.Column(db.Text)
    teacher_email = db.Column(db.String(120))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
