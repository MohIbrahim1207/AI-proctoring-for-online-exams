import os
import json
import pytest
import uuid
from app import app
from models import db, User, Exam, Question, Attempt, Result, Alert, Feedback

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['CSRF_ENABLED'] = False
    
    with app.app_context():
        db.create_all()
        # Ensure AVAILABLE_EXAMS are also in the Exam table for foreign key integrity
        from app import AVAILABLE_EXAMS
        for ex in AVAILABLE_EXAMS:
            exam_rec = Exam(id=ex['id'], name=ex['name'], duration_minutes=ex['minutes'])
            db.session.add(exam_rec)
        db.session.commit()
        
        yield app.test_client()
        db.session.remove()
        db.drop_all()

def test_home_page(client):
    res = client.get('/')
    assert res.status_code == 200

def test_login_and_submit_and_results(client):
    email = f"testuser_{uuid.uuid4().hex[:8]}@example.com"
    password = "1234"

    # register a unique user for this run
    reg = client.post(
        '/register',
        data={
            'name': 'Test User',
            'email': email,
            'password': password,
            'role': 'student',
        },
        follow_redirects=True,
    )
    assert reg.status_code in (200, 302)

    # login with the newly registered user
    res = client.post('/', data={'email': email, 'password': password, 'role': 'student'}, follow_redirects=True)
    assert res.status_code in (200, 302)

    exams_res = client.get('/api/exams')
    assert exams_res.status_code == 200
    exams = exams_res.get_json()
    assert exams and len(exams) > 0

    exam_id = exams[0]['id']

    # complete precheck
    complete_precheck = client.post(
        '/api/precheck/complete',
        json={'exam_id': exam_id, 'camera_ok': True, 'mic_ok': True},
    )
    assert complete_precheck.status_code == 200

    exam_page = client.get(f'/exam?id={exam_id}', follow_redirects=True)
    assert exam_page.status_code in (200, 302)

    # prepare valid answers keyed by question id
    with app.app_context():
        if not Question.query.filter_by(exam_id=exam_id).first():
            q = Question(id=f"q_{exam_id}", exam_id=exam_id, question_text="What is 1+1?", options=["1","2","3"], answer="2")
            db.session.add(q)
            db.session.commit()

    with app.app_context():
        exam_questions = Question.query.filter_by(exam_id=exam_id).all()
        form = {q.id: q.answer for q in exam_questions}

    res2 = client.post('/submit_exam', data=form, follow_redirects=True)
    assert res2.status_code in (200, 302)

    # ensure results DB contains an entry for testuser@example.com
    with app.app_context():
        result = Result.query.filter_by(user_email=email).first()
        assert result is not None

def test_duplicate_submit_is_ignored_for_same_attempt(client):
    email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
    password = "1234"

    client.post(
        '/register',
        data={'name': 'Dup User', 'email': email, 'password': password, 'role': 'student'},
        follow_redirects=True
    )
    client.post('/', data={'email': email, 'password': password, 'role': 'student'}, follow_redirects=True)

    exams = client.get('/api/exams').get_json()
    exam_id = exams[0]['id']

    with app.app_context():
        if not Question.query.filter_by(exam_id=exam_id).first():
            q = Question(id=f"q_dup_{exam_id}", exam_id=exam_id, question_text="Q?", options=["A","B"], answer="A")
            db.session.add(q)
            db.session.commit()

    client.post('/api/precheck/complete', json={'exam_id': exam_id, 'camera_ok': True, 'mic_ok': True})
    client.get(f'/exam?id={exam_id}', follow_redirects=True)

    with app.app_context():
        qs = Question.query.filter_by(exam_id=exam_id).all()
        form = {q.id: q.answer for q in qs}

    client.post('/submit_exam', data=form, follow_redirects=True)
    
    with app.app_context():
        count_before = Result.query.filter_by(user_email=email).count()

    client.post('/submit_exam', data=form, follow_redirects=True)

    with app.app_context():
        count_after = Result.query.filter_by(user_email=email).count()
    
    assert count_after == count_before

def test_exit_active_attempt_from_dashboard(client):
    email = f"exit_{uuid.uuid4().hex[:8]}@example.com"
    password = "1234"

    client.post(
        '/register',
        data={'name': 'Exit User', 'email': email, 'password': password, 'role': 'student'}
    )
    client.post('/', data={'email': email, 'password': password, 'role': 'student'}, follow_redirects=True)

    exams = client.get('/api/exams').get_json()
    exam_id = exams[0]['id']

    client.post('/api/precheck/complete', json={'exam_id': exam_id, 'camera_ok': True, 'mic_ok': True})
    client.get(f'/exam?id={exam_id}', follow_redirects=True)

    active = client.get('/api/active_attempt')
    assert active.get_json().get('active') is not None

    exited = client.post('/api/exam/exit', json={})
    assert exited.get_json().get('status') == 'exited'

    assert client.get('/api/active_attempt').get_json().get('active') is None
    
    with app.app_context():
        res = Result.query.filter_by(user_email=email, status='Exited by student').first()
        assert res is not None
