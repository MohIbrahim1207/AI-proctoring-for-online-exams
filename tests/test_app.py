import os
import json
import tempfile
import uuid
from app import app, RESULTS_FILE, FEEDBACK_FILE, load_questions


app.config['CSRF_ENABLED'] = False


def test_home_page():
    client = app.test_client()
    res = client.get('/')
    assert res.status_code == 200


def test_login_and_submit_and_results():
    client = app.test_client()

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

    # direct exam access now requires precheck and should redirect
    exam_page = client.get(f'/exam?id={exam_id}', follow_redirects=False)
    assert exam_page.status_code in (301, 302)
    assert '/precheck?id=' in (exam_page.headers.get('Location') or '')

    precheck = client.get(f'/precheck?id={exam_id}', follow_redirects=True)
    assert precheck.status_code == 200

    complete_precheck = client.post(
        '/api/precheck/complete',
        json={'exam_id': exam_id, 'camera_ok': True, 'mic_ok': True},
    )
    assert complete_precheck.status_code == 200

    exam_page = client.get(f'/exam?id={exam_id}', follow_redirects=True)
    assert exam_page.status_code in (200, 302)

    # prepare valid answers keyed by question id
    exam_questions = load_questions(exam_id)
    form = {}
    for q in exam_questions:
        form[q['id']] = q['answer']

    res2 = client.post('/submit_exam', data=form, follow_redirects=True)
    assert res2.status_code in (200, 302)

    # ensure results file contains an entry for testuser@example.com
    with open(RESULTS_FILE, 'r') as f:
        data = json.load(f)

    assert any(r.get('user') == email for r in data)


def test_duplicate_submit_is_ignored_for_same_attempt():
    client = app.test_client()

    email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
    password = "1234"

    reg = client.post(
        '/register',
        data={
            'name': 'Duplicate Submit User',
            'email': email,
            'password': password,
            'role': 'student',
        },
        follow_redirects=True,
    )
    assert reg.status_code in (200, 302)

    login = client.post('/', data={'email': email, 'password': password, 'role': 'student'}, follow_redirects=True)
    assert login.status_code in (200, 302)

    exams = client.get('/api/exams').get_json()
    exam_id = exams[0]['id']

    assert client.post(
        '/api/precheck/complete',
        json={'exam_id': exam_id, 'camera_ok': True, 'mic_ok': True},
    ).status_code == 200

    assert client.get(f'/exam?id={exam_id}', follow_redirects=True).status_code in (200, 302)

    exam_questions = load_questions(exam_id)
    form = {q['id']: q['answer'] for q in exam_questions}

    first_submit = client.post('/submit_exam', data=form, follow_redirects=True)
    assert first_submit.status_code in (200, 302)

    with open(RESULTS_FILE, 'r') as f:
        before_second = [r for r in json.load(f) if r.get('user') == email]

    second_submit = client.post('/submit_exam', data=form, follow_redirects=True)
    assert second_submit.status_code in (200, 302)

    with open(RESULTS_FILE, 'r') as f:
        after_second = [r for r in json.load(f) if r.get('user') == email]

    assert len(after_second) == len(before_second)


def test_exit_active_attempt_from_dashboard():
    client = app.test_client()

    email = f"exit_{uuid.uuid4().hex[:8]}@example.com"
    password = "1234"

    reg = client.post(
        '/register',
        data={
            'name': 'Exit Attempt User',
            'email': email,
            'password': password,
            'role': 'student',
        },
        follow_redirects=True,
    )
    assert reg.status_code in (200, 302)

    login = client.post('/', data={'email': email, 'password': password, 'role': 'student'}, follow_redirects=True)
    assert login.status_code in (200, 302)

    exams = client.get('/api/exams').get_json()
    exam_id = exams[0]['id']

    assert client.post(
        '/api/precheck/complete',
        json={'exam_id': exam_id, 'camera_ok': True, 'mic_ok': True},
    ).status_code == 200

    assert client.get(f'/exam?id={exam_id}', follow_redirects=True).status_code in (200, 302)

    active = client.get('/api/active_attempt')
    assert active.status_code == 200
    active_payload = active.get_json()
    assert active_payload.get('active') is not None

    exited = client.post('/api/exam/exit', json={})
    assert exited.status_code == 200
    assert exited.get_json().get('status') == 'exited'

    active_after = client.get('/api/active_attempt')
    assert active_after.status_code == 200
    assert active_after.get_json().get('active') is None

    with open(RESULTS_FILE, 'r') as f:
        data = json.load(f)

    assert any(r.get('user') == email and r.get('status') == 'Exited by student' for r in data)


def test_teacher_reports_and_feedback_api():
    client = app.test_client()

    teacher_login = client.post(
        '/',
        data={'email': 'admin@example.com', 'password': '1234'},
        follow_redirects=True,
    )
    assert teacher_login.status_code in (200, 302)

    reports = client.get('/api/teacher/student_reports')
    assert reports.status_code == 200
    assert isinstance(reports.get_json(), list)

    unique_user = f"report_{uuid.uuid4().hex[:8]}@example.com"
    unique_exam = f"API Test Exam {uuid.uuid4().hex[:6]}"

    feedback_post = client.post(
        '/api/teacher/feedback',
        json={
            'user': unique_user,
            'examName': unique_exam,
            'feedback': 'Focus on time management and SQL joins.',
        },
    )
    assert feedback_post.status_code == 200
    assert feedback_post.get_json().get('status') == 'saved'

    feedbacks = client.get('/api/teacher/feedbacks')
    assert feedbacks.status_code == 200
    payload = feedbacks.get_json()
    assert any(f.get('user') == unique_user and f.get('examName') == unique_exam for f in payload)

    with open(FEEDBACK_FILE, 'r') as f:
        stored = json.load(f)
    assert any(f.get('user') == unique_user and f.get('examName') == unique_exam for f in stored)
