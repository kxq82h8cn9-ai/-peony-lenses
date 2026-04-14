/* ═══════════════════════════════════════════════════════════════
   AI Educational Platform — Main Application JS
   ═══════════════════════════════════════════════════════════════ */

const API = 'http://localhost:8000';

// ── State ─────────────────────────────────────────────────────────────────────
const State = {
  token: localStorage.getItem('edu_token'),
  user:  JSON.parse(localStorage.getItem('edu_user') || 'null'),
  currentPanel: 'chat',
  currentSession: null,
  currentPersona: 'general',
  currentSubject: 'عام',
  uploadedFiles: [],
  quizData: null,
  quizAnswers: [],
  quizTimer: null,
  quizSeconds: 0,
  screenCapture: null,
  mindMapData: null,
};

// ── API Helper ─────────────────────────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (State.token) headers['Authorization'] = `Bearer ${State.token}`;
  const res = await fetch(API + path, { ...options, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Server error');
  }
  return res.json();
}

// ── Toast ──────────────────────────────────────────────────────────────────────
function showToast(msg, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type]}</span><span>${msg}</span>`;
  container.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateY(-20px)'; setTimeout(() => el.remove(), 400); }, duration);
}

// ── Auth ───────────────────────────────────────────────────────────────────────
function saveAuth(token, user) {
  State.token = token; State.user = user;
  localStorage.setItem('edu_token', token);
  localStorage.setItem('edu_user', JSON.stringify(user));
}

function logout() {
  State.token = null; State.user = null;
  localStorage.removeItem('edu_token'); localStorage.removeItem('edu_user');
  showAuthScreen();
}

async function handleLogin(e) {
  e.preventDefault();
  const btn = e.target.querySelector('button[type=submit]');
  btn.disabled = true; btn.innerHTML = '<div class="spinner"></div>';
  try {
    const data = await apiFetch('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        email: document.getElementById('login-email').value,
        password: document.getElementById('login-password').value,
      }),
    });
    saveAuth(data.token, data.user);
    showApp();
  } catch (err) { showToast(err.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = 'دخول'; }
}

async function handleRegister(e) {
  e.preventDefault();
  const btn = e.target.querySelector('button[type=submit]');
  btn.disabled = true; btn.innerHTML = '<div class="spinner"></div>';
  try {
    const data = await apiFetch('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        name: document.getElementById('reg-name').value,
        email: document.getElementById('reg-email').value,
        password: document.getElementById('reg-password').value,
        role: document.getElementById('reg-role').value,
      }),
    });
    saveAuth(data.token, data.user);
    showApp();
  } catch (err) { showToast(err.message, 'error'); }
  finally { btn.disabled = false; btn.textContent = 'إنشاء حساب'; }
}

// ── Navigation ─────────────────────────────────────────────────────────────────
function showAuthScreen() {
  document.getElementById('auth-screen').classList.remove('hidden');
  document.getElementById('app-root').classList.add('hidden');
}

function showApp() {
  document.getElementById('auth-screen').classList.add('hidden');
  document.getElementById('app-root').classList.remove('hidden');
  document.getElementById('user-name').textContent = State.user?.name || 'الطالب';
  document.getElementById('user-role').textContent = roleLabel(State.user?.role);
  loadPanel('chat');
  initChatSession();
}

function roleLabel(r) {
  return { student: 'طالب', teacher: 'معلم', parent: 'ولي أمر', admin: 'مدير' }[r] || r;
}

function loadPanel(panelName) {
  State.currentPanel = panelName;
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const panel = document.getElementById(`panel-${panelName}`);
  if (panel) panel.classList.add('active');
  const navItem = document.querySelector(`[data-panel="${panelName}"]`);
  if (navItem) navItem.classList.add('active');
  const titles = {
    chat: '💬 المحادثة التعليمية', files: '📂 ملفاتي',
    mindmap: '🗺️ الخرائط الذهنية', quiz: '❓ الاختبارات',
    progress: '📊 تقدمي', rewards: '🏆 مكافآتي',
    assessment: '📋 التقييم', report: '📄 التقارير',
  };
  document.getElementById('topbar-title').textContent = titles[panelName] || panelName;

  // Lazy load data
  if (panelName === 'progress') loadProgress();
  if (panelName === 'rewards') loadRewards();
  if (panelName === 'files') renderFileList();
  if (panelName === 'mindmap') loadMindMaps();
}

// ── Chat ───────────────────────────────────────────────────────────────────────
async function initChatSession() {
  if (!State.currentSession) {
    try {
      const res = await apiFetch('/api/sessions', {
        method: 'POST',
        body: JSON.stringify({ subject: State.currentSubject, persona: State.currentPersona }),
      });
      State.currentSession = res.session_id;
    } catch (e) { console.error(e); }
  }
  renderPersonaBar();
}

function renderPersonaBar() {
  const personas = [
    { key: 'general', icon: '🎓', name: 'معلم ذكي' },
    { key: 'history', icon: '📜', name: 'التاريخ' },
    { key: 'science', icon: '🔬', name: 'العلوم' },
    { key: 'math',    icon: '📐', name: 'الرياضيات' },
    { key: 'language',icon: '🌍', name: 'اللغات' },
  ];
  const bar = document.getElementById('persona-bar');
  if (!bar) return;
  bar.innerHTML = personas.map(p => `
    <div class="persona-option ${p.key === State.currentPersona ? 'selected' : ''}"
         onclick="selectPersona('${p.key}')">
      <span class="p-icon">${p.icon}</span>
      <span class="p-name">${p.name}</span>
    </div>`).join('');
}

async function selectPersona(key) {
  State.currentPersona = key;
  State.currentSession = null;
  document.getElementById('chat-messages').innerHTML = '';
  await initChatSession();
  const map = { general:'معلم ذكي', history:'المؤرخ', science:'العالِم', math:'الرياضياتي', language:'اللغوي' };
  const icons= { general:'🎓', history:'📜', science:'🔬', math:'📐', language:'🌍' };
  document.getElementById('persona-name').textContent = map[key] || key;
  document.getElementById('persona-icon').textContent = icons[key] || '🎓';
  showToast(`تم التبديل إلى شخصية ${map[key]}`, 'success');
}

function appendMessage(role, text, typing = false) {
  const wrap = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = `message ${role}`;
  const icons = { user: '👤', ai: '🤖' };
  div.innerHTML = `
    <div class="message-avatar">${icons[role] || '💬'}</div>
    <div class="message-bubble">${typing ? '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>' : formatMessage(text)}</div>`;
  div.id = typing ? 'typing-msg' : '';
  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
  return div;
}

function formatMessage(text) {
  // Basic markdown-like formatting
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/```([\s\S]*?)```/g, '<pre>$1</pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = ''; input.style.height = 'auto';

  appendMessage('user', text);
  const typingEl = appendMessage('ai', '', true);

  try {
    const headers = { 'Content-Type': 'application/json' };
    if (State.token) headers['Authorization'] = `Bearer ${State.token}`;

    const body = {
      session_id: State.currentSession || 1,
      message: text,
      persona: State.currentPersona,
      screen_image: State.screenCapture || null,
    };
    State.screenCapture = null;

    const res = await fetch(`${API}/api/chat`, {
      method: 'POST', headers, body: JSON.stringify(body),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let bubble = null;
    let fullText = '';

    typingEl.remove();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const lines = decoder.decode(value).split('\n');
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const evt = JSON.parse(line.slice(6));
          if (evt.type === 'text') {
            if (!bubble) {
              const msgEl = appendMessage('ai', '');
              bubble = msgEl.querySelector('.message-bubble');
              fullText = '';
            }
            fullText += evt.content;
            bubble.innerHTML = formatMessage(fullText);
            document.getElementById('chat-messages').scrollTop = 99999;
          }
        } catch (_) {}
      }
    }
  } catch (err) {
    typingEl?.remove();
    appendMessage('ai', `عذراً، حدث خطأ: ${err.message}`);
  }
}

// ── Screen Share ───────────────────────────────────────────────────────────────
async function startScreenShare() {
  try {
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
    const track = stream.getVideoTracks()[0];
    const imageCapture = new ImageCapture(track);
    const bitmap = await imageCapture.grabFrame();
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width; canvas.height = bitmap.height;
    canvas.getContext('2d').drawImage(bitmap, 0, 0);
    State.screenCapture = canvas.toDataURL('image/png');
    track.stop();
    showToast('تم التقاط الشاشة! أرسل رسالتك لتحليلها 📸', 'success');
    document.getElementById('screen-indicator').classList.remove('hidden');
  } catch (e) {
    showToast('تعذّر مشاركة الشاشة: ' + e.message, 'warning');
  }
}

// ── File Upload ─────────────────────────────────────────────────────────────────
function initFileUpload() {
  const zone = document.getElementById('upload-zone');
  const inp  = document.getElementById('file-input');
  zone.onclick = () => inp.click();
  zone.ondragover = e => { e.preventDefault(); zone.classList.add('drag-over'); };
  zone.ondragleave = () => zone.classList.remove('drag-over');
  zone.ondrop = e => { e.preventDefault(); zone.classList.remove('drag-over'); handleFiles(e.dataTransfer.files); };
  inp.onchange = e => handleFiles(e.target.files);
}

async function handleFiles(files) {
  for (const file of files) {
    await uploadFile(file);
  }
}

async function uploadFile(file) {
  const form = new FormData();
  form.append('file', file);
  if (State.currentSession) form.append('session_id', State.currentSession);
  showToast(`جاري رفع ${file.name}...`, 'info');
  try {
    const res = await fetch(`${API}/api/files/upload`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${State.token}` },
      body: form,
    });
    const data = await res.json();
    State.uploadedFiles.unshift(data);
    renderFileList();
    showToast(`✅ تم رفع ${file.name}`, 'success');
  } catch (e) { showToast('فشل رفع الملف: ' + e.message, 'error'); }
}

function renderFileList() {
  const list = document.getElementById('file-list');
  if (!list) return;
  if (!State.uploadedFiles.length) {
    list.innerHTML = '<p class="text-muted text-center mt-4">لا توجد ملفات مرفوعة بعد</p>';
    return;
  }
  const icons = { pdf: '📕', txt: '📄', png: '🖼️', jpg: '🖼️', jpeg: '🖼️', webp: '🖼️', md: '📝' };
  list.innerHTML = State.uploadedFiles.map((f, i) => `
    <div class="file-item">
      <span class="file-icon">${icons[f.type] || '📎'}</span>
      <div class="file-info">
        <div class="name">${f.filename}</div>
        <div class="size">${formatSize(f.size)}</div>
      </div>
      <div class="file-actions">
        <button class="btn btn-sm btn-secondary" onclick="analyzeFile(${i})">تحليل مع AI</button>
        <button class="btn btn-sm btn-outline" onclick="generateMindMapFromFile(${i})">خريطة ذهنية</button>
      </div>
    </div>`).join('');
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/1048576).toFixed(1) + ' MB';
}

async function analyzeFile(idx) {
  const file = State.uploadedFiles[idx];
  loadPanel('chat');
  const msg = `حلّل هذا الملف وقدّم ملخصاً شاملاً:\n\nاسم الملف: ${file.filename}\nمحتوى النص:\n${file.extracted_text || 'ملف مرئي'}`;
  document.getElementById('chat-input').value = msg;
  await sendMessage();
}

// ── Mind Map ───────────────────────────────────────────────────────────────────
async function generateMindMap(topic, content) {
  if (!topic) { showToast('أدخل موضوع الخريطة الذهنية', 'warning'); return; }
  showToast('جاري توليد الخريطة الذهنية... 🗺️', 'info');
  try {
    const data = await apiFetch('/api/mindmap/generate', {
      method: 'POST',
      body: JSON.stringify({
        session_id: State.currentSession || 0,
        topic, content: content || topic,
        subject: State.currentSubject, persona: State.currentPersona,
      }),
    });
    State.mindMapData = data.map_data;
    renderMindMap(data.map_data);
    showToast('✅ تم توليد الخريطة الذهنية!', 'success');
    loadPanel('mindmap');
  } catch (e) { showToast('خطأ: ' + e.message, 'error'); }
}

async function generateMindMapFromFile(idx) {
  const file = State.uploadedFiles[idx];
  await generateMindMap(file.filename, file.extracted_text || '');
}

function renderMindMap(data) {
  const canvas = document.getElementById('mindmap-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  canvas.width = canvas.parentElement.offsetWidth || 800;
  canvas.height = 600;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const cx = canvas.width / 2, cy = canvas.height / 2;

  // Draw root
  drawNode(ctx, cx, cy, data.title, data.color || '#2563eb', 60, true);

  if (!data.children || !data.children.length) return;

  const angleStep = (2 * Math.PI) / data.children.length;
  const r1 = 180;

  data.children.forEach((child, i) => {
    const angle = i * angleStep - Math.PI / 2;
    const x = cx + r1 * Math.cos(angle);
    const y = cy + r1 * Math.sin(angle);

    drawLine(ctx, cx, cy, x, y, child.color || '#7c3aed');
    drawNode(ctx, x, y, child.label, child.color || '#7c3aed', 48);

    if (child.children && child.children.length) {
      const subStep = (Math.PI * 0.7) / Math.max(child.children.length, 1);
      child.children.forEach((sub, j) => {
        const subAngle = angle - (child.children.length - 1) * subStep / 2 + j * subStep;
        const r2 = 120;
        const sx = x + r2 * Math.cos(subAngle);
        const sy = y + r2 * Math.sin(subAngle);
        drawLine(ctx, x, y, sx, sy, sub.color || '#f59e0b');
        drawNode(ctx, sx, sy, sub.label, sub.color || '#f59e0b', 36);
      });
    }
  });
}

function drawNode(ctx, x, y, text, color, size, isRoot = false) {
  const r = isRoot ? 50 : size / 1.5;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = color + '22';
  ctx.fill();
  ctx.strokeStyle = color;
  ctx.lineWidth = isRoot ? 3 : 2;
  ctx.stroke();
  ctx.fillStyle = color;
  ctx.font = `${isRoot ? 'bold ' : ''}${isRoot ? 13 : 11}px Tajawal, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  // Word wrap
  const words = text.split(' ');
  let line = '', lines = [];
  for (const w of words) {
    const test = line ? line + ' ' + w : w;
    if (ctx.measureText(test).width > r * 1.6 && line) { lines.push(line); line = w; }
    else line = test;
  }
  if (line) lines.push(line);
  const lineH = isRoot ? 16 : 13;
  lines.forEach((l, i) => ctx.fillText(l, x, y + (i - (lines.length-1)/2) * lineH));
}

function drawLine(ctx, x1, y1, x2, y2, color) {
  ctx.beginPath();
  ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
  ctx.strokeStyle = color; ctx.lineWidth = 2;
  ctx.setLineDash([4, 3]);
  ctx.stroke();
  ctx.setLineDash([]);
}

async function loadMindMaps() {
  try {
    const maps = await apiFetch('/api/mindmaps');
    const list = document.getElementById('mindmap-list');
    if (!list) return;
    if (!maps.length) { list.innerHTML = '<p class="text-muted text-center">لا توجد خرائط بعد</p>'; return; }
    list.innerHTML = maps.map(m => `
      <div class="card" style="cursor:pointer" onclick='loadSavedMap(${JSON.stringify(m.map_data)})'>
        <div class="card-title">🗺️ ${m.title}</div>
        <div class="text-sm text-muted">${m.subject} · ${new Date(m.created_at).toLocaleDateString('ar')}</div>
      </div>`).join('');
  } catch (e) {}
}

function loadSavedMap(mapData) {
  try {
    const data = typeof mapData === 'string' ? JSON.parse(mapData) : mapData;
    State.mindMapData = data;
    renderMindMap(data);
  } catch (e) {}
}

// ── Quiz ───────────────────────────────────────────────────────────────────────
async function generateQuiz() {
  const subject = document.getElementById('quiz-subject').value;
  const topic   = document.getElementById('quiz-topic').value;
  const diff    = document.getElementById('quiz-difficulty').value;
  const type    = document.getElementById('quiz-type').value;
  const count   = parseInt(document.getElementById('quiz-count').value) || 5;
  if (!subject || !topic) { showToast('أدخل المادة والموضوع', 'warning'); return; }
  showToast('جاري توليد الأسئلة... ❓', 'info');
  try {
    const data = await apiFetch('/api/quiz/generate', {
      method: 'POST',
      body: JSON.stringify({ session_id: State.currentSession || 0, subject, topic, content: topic, difficulty: diff, quiz_type: type, count, persona: State.currentPersona }),
    });
    State.quizData = data;
    State.quizAnswers = new Array(data.questions.length).fill(-1);
    startQuiz(data);
  } catch (e) { showToast('خطأ: ' + e.message, 'error'); }
}

function startQuiz(data) {
  document.getElementById('quiz-setup').classList.add('hidden');
  document.getElementById('quiz-area').classList.remove('hidden');
  document.getElementById('quiz-result').classList.add('hidden');
  State.quizSeconds = data.questions.length * 60;
  renderQuizQuestion(0, data.questions);
  startQuizTimer();
}

function renderQuizQuestion(idx, questions) {
  const q = questions[idx];
  const total = questions.length;
  document.getElementById('quiz-q-num').textContent = `${idx+1} / ${total}`;
  document.getElementById('quiz-progress-bar').style.width = `${((idx+1)/total)*100}%`;
  const area = document.getElementById('quiz-questions');
  area.innerHTML = `
    <div class="question-card">
      <div class="question-number">السؤال ${idx+1} من ${total}</div>
      <div class="question-text">${q.question}</div>
      <div class="option-list">
        ${(q.options || []).map((opt, oi) => `
          <div class="option-item ${State.quizAnswers[idx] === oi ? 'selected' : ''}"
               onclick="selectAnswer(${idx},${oi},${total})">
            <div class="option-letter">${['أ','ب','ج','د'][oi]}</div>
            <span>${opt}</span>
          </div>`).join('')}
      </div>
      <div class="flex gap-2 mt-4">
        ${idx > 0 ? `<button class="btn btn-ghost" onclick="renderQuizQuestion(${idx-1},${JSON.stringify(questions).replace(/"/g,'&quot;')})">← السابق</button>` : ''}
        ${idx < total-1 ? `<button class="btn btn-primary" onclick="renderQuizQuestion(${idx+1},${JSON.stringify(questions).replace(/"/g,'&quot;')})">التالي →</button>` : `<button class="btn btn-success" onclick="submitQuiz()">إنهاء الاختبار ✓</button>`}
      </div>
    </div>`;
}

function selectAnswer(qIdx, optIdx) {
  State.quizAnswers[qIdx] = optIdx;
  const questions = State.quizData.questions;
  renderQuizQuestion(qIdx, questions);
}

function startQuizTimer() {
  clearInterval(State.quizTimer);
  State.quizTimer = setInterval(() => {
    State.quizSeconds--;
    const m = Math.floor(State.quizSeconds / 60).toString().padStart(2,'0');
    const s = (State.quizSeconds % 60).toString().padStart(2,'0');
    const el = document.getElementById('quiz-timer');
    if (el) el.textContent = `${m}:${s}`;
    if (State.quizSeconds <= 0) { clearInterval(State.quizTimer); submitQuiz(); }
  }, 1000);
}

async function submitQuiz() {
  clearInterval(State.quizTimer);
  if (!State.quizData) return;
  const timeTaken = State.quizData.questions.length * 60 - State.quizSeconds;
  showToast('جاري تقييم إجاباتك...', 'info');
  try {
    const result = await apiFetch('/api/quiz/submit', {
      method: 'POST',
      body: JSON.stringify({ quiz_id: State.quizData.quiz_id, answers: State.quizAnswers, time_taken: timeTaken }),
    });
    document.getElementById('quiz-area').classList.add('hidden');
    document.getElementById('quiz-result').classList.remove('hidden');
    const pct = Math.round(result.score);
    document.getElementById('score-circle').style.setProperty('--pct', `${pct * 3.6}deg`);
    document.getElementById('score-value').textContent = `${pct}%`;
    document.getElementById('result-correct').textContent = `${result.correct} / ${result.total} إجابة صحيحة`;
    document.getElementById('result-feedback').textContent = result.feedback;
    if (pct >= 80) showToast('أداء رائع! 🌟 حصلت على مكافأة!', 'success');
  } catch (e) { showToast('خطأ في الإرسال: ' + e.message, 'error'); }
}

function resetQuiz() {
  clearInterval(State.quizTimer);
  State.quizData = null; State.quizAnswers = [];
  document.getElementById('quiz-setup').classList.remove('hidden');
  document.getElementById('quiz-area').classList.add('hidden');
  document.getElementById('quiz-result').classList.add('hidden');
}

// ── Progress ────────────────────────────────────────────────────────────────────
async function loadProgress() {
  try {
    const data = await apiFetch('/api/progress');
    renderProgressDashboard(data);
  } catch (e) { console.error(e); }
}

function renderProgressDashboard(data) {
  const profile = data.profile || {};
  const pts = profile.total_points || 0;
  const lvl = data.level || 1;

  document.getElementById('prog-points').textContent = pts;
  document.getElementById('prog-level').textContent = lvl;
  document.getElementById('prog-sessions').textContent = data.sessions_count || 0;
  document.getElementById('prog-streak').textContent = profile.streak_days || 0;

  // Level progress bar
  const nextPts = data.next_level_points || 100;
  const pct = Math.max(0, Math.min(100, 100 - (nextPts / 100 * 100)));
  document.getElementById('level-progress').style.width = pct + '%';
  document.getElementById('level-label').textContent = `المستوى ${lvl} — يحتاج ${nextPts} نقطة للمستوى التالي`;

  // Subject progress list
  const list = document.getElementById('subject-progress-list');
  if (!list) return;
  if (!data.progress.length) { list.innerHTML = '<p class="text-muted text-center">ابدأ جلساتك لرؤية تقدمك!</p>'; return; }
  list.innerHTML = data.progress.map(p => {
    const pct = Math.min(100, Math.round(p.mastery_percentage || 0));
    return `
    <div class="subject-progress-item">
      <div class="sp-header">
        <span class="sp-name">📚 ${p.subject}</span>
        <span class="sp-pct">${pct}%</span>
      </div>
      <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
      <div class="text-sm text-muted">${p.sessions_count} جلسة · آخر درجة: ${Math.round(p.last_score || 0)}%</div>
    </div>`;
  }).join('');
}

// ── Rewards ──────────────────────────────────────────────────────────────────────
async function loadRewards() {
  try {
    const data = await apiFetch('/api/progress');
    const rewards = data.rewards || [];
    const grid = document.getElementById('rewards-grid');
    if (!grid) return;
    if (!rewards.length) { grid.innerHTML = '<p class="text-muted text-center">أكمل مهاماً لكسب مكافآت! 🏆</p>'; return; }
    grid.innerHTML = rewards.map(r => `
      <div class="badge-card">
        <span class="badge-icon">${r.badge_icon || '⭐'}</span>
        <div class="badge-name">${r.name}</div>
        <div class="badge-pts">+${r.points} نقطة</div>
        <div class="text-sm text-muted">${new Date(r.awarded_at).toLocaleDateString('ar')}</div>
      </div>`).join('');
  } catch (e) {}
}

// ── Assessment ─────────────────────────────────────────────────────────────────
async function startAssessment(type) {
  const subject = document.getElementById('assess-subject').value;
  if (!subject) { showToast('اختر المادة', 'warning'); return; }
  showToast('جاري تحضير التقييم...', 'info');
  try {
    const data = await apiFetch('/api/assessment/generate', {
      method: 'POST',
      body: JSON.stringify({ subject, assessment_type: type }),
    });
    // Reuse quiz UI
    State.quizData = { quiz_id: data.assessment_id, questions: data.assessment.questions || [] };
    State.quizAnswers = new Array(State.quizData.questions.length).fill(-1);
    loadPanel('quiz');
    startQuiz(State.quizData);
  } catch (e) { showToast('خطأ: ' + e.message, 'error'); }
}

// ── Report ─────────────────────────────────────────────────────────────────────
async function generateReport(days = 7) {
  showToast('جاري إعداد التقرير... 📄', 'info');
  const btn = document.getElementById('btn-gen-report');
  if (btn) { btn.disabled = true; btn.innerHTML = '<div class="spinner"></div> جاري التوليد...'; }
  try {
    const data = await apiFetch(`/api/report/generate?period_days=${days}`, { method: 'POST' });
    document.getElementById('report-content').textContent = data.report;
    document.getElementById('report-date').textContent = new Date(data.generated_at).toLocaleString('ar');
    showToast('✅ تم توليد التقرير', 'success');
  } catch (e) { showToast('خطأ: ' + e.message, 'error'); }
  finally { if (btn) { btn.disabled = false; btn.textContent = 'توليد التقرير'; } }
}

// ── Auth Tab Switch ─────────────────────────────────────────────────────────────
function switchAuthTab(tab) {
  document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
  document.getElementById(`tab-${tab}`).classList.add('active');
  document.getElementById('form-login').classList.toggle('hidden', tab !== 'login');
  document.getElementById('form-register').classList.toggle('hidden', tab !== 'register');
}

// ── Init ───────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initFileUpload();

  // Enter key to send chat
  const chatInput = document.getElementById('chat-input');
  if (chatInput) {
    chatInput.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
    chatInput.addEventListener('input', () => {
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    });
  }

  // Check auth
  if (State.token && State.user) showApp();
  else showAuthScreen();
});
