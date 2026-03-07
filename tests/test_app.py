import os
import json
import tempfile
import uuid
from app import app, RESULTS_FILE, load_questions


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

    # initialize exam context in session
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
