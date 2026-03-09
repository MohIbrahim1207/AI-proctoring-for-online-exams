// dashboard.js - fetches results from server API and renders table

function appendCell(tr, value) {
  const td = document.createElement('td');
  td.textContent = value == null ? '' : String(value);
  tr.appendChild(td);
}

function csrfHeaders(extraHeaders = {}) {
  const headers = { ...extraHeaders };
  const csrfToken = window.CSRF_TOKEN || '';
  if (csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }
  return headers;
}

async function exitActiveTest() {
  const confirmed = window.confirm('Exit your active test now? This attempt will be closed.');
  if (!confirmed) {
    return;
  }

  try {
    const response = await fetch('/api/exam/exit', {
      method: 'POST',
      headers: csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({}),
    });

    if (!response.ok) {
      throw new Error('Failed to exit active test');
    }

    await loadActiveAttempt();
    await loadDashboard();
    alert('Active test exited.');
  } catch (err) {
    console.error(err);
    alert('Unable to exit active test right now.');
  }
}

async function loadActiveAttempt() {
  const section = document.getElementById('activeAttemptSection');
  const body = document.getElementById('activeAttemptBody');
  if (!section || !body) {
    return;
  }

  try {
    const res = await fetch('/api/active_attempt');
    if (res.status === 401) {
      window.location.href = '/';
      return;
    }
    if (!res.ok) {
      throw new Error('Failed to fetch active attempt');
    }

    const payload = await res.json();
    if (!payload || !payload.active) {
      section.style.display = 'none';
      body.textContent = '';
      return;
    }

    const started = payload.active.started_at
      ? new Date(payload.active.started_at).toLocaleString()
      : 'Unknown';

    section.style.display = '';
    body.innerHTML = '';

    const examInfo = document.createElement('p');
    examInfo.className = 'mb-2';
    examInfo.textContent = `Exam: ${payload.active.exam_name} | Started: ${started}`;
    body.appendChild(examInfo);

    const exitBtn = document.createElement('button');
    exitBtn.className = 'btn btn-outline-danger btn-sm';
    exitBtn.textContent = 'Exit Test';
    exitBtn.addEventListener('click', exitActiveTest);
    body.appendChild(exitBtn);
  } catch (err) {
    console.error(err);
    section.style.display = 'none';
    body.textContent = '';
  }
}

async function loadDashboard() {
  try {
    const res = await fetch('/api/results');
    if (res.status === 401) {
      window.location.href = '/';
      return;
    }
    if (!res.ok) throw new Error('Failed to fetch results');
    const results = await res.json();

    const table = document.getElementById('examTable');
    table.textContent = '';

    if (!results || results.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 6;
      td.className = 'text-center';
      td.textContent = 'No results found.';
      tr.appendChild(td);
      table.appendChild(tr);
      return;
    }

    for (const r of results) {
      const when = new Date(r.timestamp).toLocaleString();
      const tr = document.createElement('tr');
      appendCell(tr, r.examName);
      appendCell(tr, r.allottedTime);
      appendCell(tr, r.totalMarks);
      appendCell(tr, r.score);
      appendCell(tr, r.status);
      appendCell(tr, when);
      table.appendChild(tr);
    }
  } catch (err) {
    console.error(err);
    document.getElementById('examTable').innerHTML = '<tr><td colspan="6">Error loading dashboard</td></tr>';
  }
}

async function loadAvailableExams() {
  try {
    const res = await fetch('/api/exams');
    if (res.status === 401) {
      window.location.href = '/';
      return;
    }
    if (!res.ok) throw new Error('Failed to fetch exams');
    const exams = await res.json();

    const table = document.getElementById('availableExamsTable');
    table.textContent = '';

    if (!exams || exams.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 4;
      td.className = 'text-center';
      td.textContent = 'No exams available.';
      tr.appendChild(td);
      table.appendChild(tr);
      return;
    }

    for (const exam of exams) {
      const tr = document.createElement('tr');
      appendCell(tr, exam.name);
      appendCell(tr, exam.duration);
      appendCell(tr, exam.totalMarks);

      const actionTd = document.createElement('td');
      const link = document.createElement('a');
      link.className = 'btn btn-primary btn-sm';
      link.textContent = 'Take Exam';
      link.href = `/precheck?id=${encodeURIComponent(exam.id)}`;
      actionTd.appendChild(link);
      tr.appendChild(actionTd);

      table.appendChild(tr);
    }
  } catch (err) {
    console.error(err);
    document.getElementById('availableExamsTable').innerHTML = '<tr><td colspan="4" class="text-center text-danger">Error loading exams</td></tr>';
  }
}

loadDashboard();
loadAvailableExams();
loadActiveAttempt();