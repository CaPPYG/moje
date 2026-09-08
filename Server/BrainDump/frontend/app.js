/**
 * BrainDump — Main Application Logic v1.1
 * Voice → LLM → Categorised Tasks with Due Dates & Calendar Strip
 */

'use strict';

// ─── Config ──────────────────────────────────────────────────────────────────
const API_BASE = (() => {
  if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
    return 'http://127.0.0.1:5090';
  }
  return '/braindump/api';
})();

// ─── State ───────────────────────────────────────────────────────────────────
let tasks = [];           // Local cache of all tasks
let filter = 'open';      // 'all' | 'open' | 'done'
let recognition = null;   // SpeechRecognition instance
let isRecording = false;
let transcript = '';      // Accumulated transcript
let editingTaskId = null; // Currently edited task (modal)

// Calendar state
let calendarOffset = 0;   // offset in days from today (0 = today visible)
let selectedDate = null;  // null = "inbox" (tasks without date), 'YYYY-MM-DD' = specific day

// ─── DOM References ───────────────────────────────────────────────────────────
const micBtn                = document.getElementById('mic-btn');
const micIcon               = document.getElementById('mic-icon');
const voiceStatus           = document.getElementById('voice-status');
const transcriptBox         = document.getElementById('transcript-box');
const transcriptPlaceholder = document.getElementById('transcript-placeholder');
const transcriptText        = document.getElementById('transcript-text');
const transcriptCursor      = document.getElementById('transcript-cursor');
const btnSend               = document.getElementById('btn-send');
const btnClearText          = document.getElementById('btn-clear-text');
const processingBar         = document.getElementById('processing-bar');
const taskBoard             = document.getElementById('task-board');
const boardTitle            = document.getElementById('board-title');
const langSelect            = document.getElementById('lang-select');
const btnExport             = document.getElementById('btn-export');
const btnClearDone          = document.getElementById('btn-clear-done');
const btnLogout             = document.getElementById('btn-logout');
const toastContainer        = document.getElementById('toast-container');
const authOverlay           = document.getElementById('auth-overlay');
const authForm              = document.getElementById('auth-form');
const authPassword          = document.getElementById('auth-password');
const authError             = document.getElementById('auth-error');
const authSubmitBtn         = document.getElementById('auth-submit-btn');

// Quick Add
const btnQuickAdd      = document.getElementById('btn-quick-add');
const quickAddOverlay  = document.getElementById('quick-add-overlay');
const quickAddForm     = document.getElementById('quick-add-form');
const quickAddText     = document.getElementById('quick-add-text');
const quickAddClose    = document.getElementById('quick-add-close');
const quickAddCancel   = document.getElementById('quick-add-cancel');
const quickAddSubmit   = document.getElementById('quick-add-submit');
const categoryPills    = document.getElementById('category-pills');
const quickAddDueDate  = document.getElementById('quick-add-due-date');
const quickAddDueClear = document.getElementById('quick-add-due-clear');
let selectedCategory   = 'Work';

// Edit Task Modal
const editTaskOverlay  = document.getElementById('edit-task-overlay');
const editTaskForm     = document.getElementById('edit-task-form');
const editTaskText     = document.getElementById('edit-task-text');
const editTaskClose    = document.getElementById('edit-task-close');
const editTaskCancel   = document.getElementById('edit-task-cancel');
const editTaskSubmit   = document.getElementById('edit-task-submit');
const editCatPills     = document.getElementById('edit-category-pills');
const editDueDate      = document.getElementById('edit-task-due-date');
const editDueClear     = document.getElementById('edit-due-clear');
let editSelectedCat    = 'Work';

// Calendar
const calendarStrip = document.getElementById('calendar-strip');
const calPrev       = document.getElementById('cal-prev');
const calNext       = document.getElementById('cal-next');

// ─── Date Helpers ─────────────────────────────────────────────────────────────
const SK_DAYS_SHORT  = ['Ne', 'Po', 'Ut', 'St', 'Št', 'Pi', 'So'];
const SK_MONTHS_SHORT = ['jan', 'feb', 'mar', 'apr', 'máj', 'jún', 'júl', 'aug', 'sep', 'okt', 'nov', 'dec'];

function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function dateISO(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function addDays(isoDate, n) {
  const d = new Date(isoDate + 'T00:00:00');
  d.setDate(d.getDate() + n);
  return dateISO(d);
}

function formatDueDate(iso) {
  if (!iso) return '';
  const today = todayISO();
  const tomorrow = addDays(today, 1);
  if (iso === today) return 'Dnes';
  if (iso === tomorrow) return 'Zajtra';
  if (iso < today) return `⚠️ ${iso}`;
  const d = new Date(iso + 'T00:00:00');
  return `${d.getDate()}. ${SK_MONTHS_SHORT[d.getMonth()]}`;
}

function dueDateClass(iso) {
  if (!iso) return '';
  const today = todayISO();
  if (iso < today) return 'due-overdue';
  if (iso === today) return 'due-today';
  return 'due-future';
}

// ─── Category Config ──────────────────────────────────────────────────────────
const CATS = {
  Work:       { emoji: '🖥️',  color: '#4299e1', label: 'Work'      },
  Groceries:  { emoji: '🛒',  color: '#10b981', label: 'Nákup'     },
  Personal:   { emoji: '👤',  color: '#a78bfa', label: 'Osobné'    },
  Other:      { emoji: '📌',  color: '#f59e0b', label: 'Ostatné'   },
};

// ─── Toast ────────────────────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type] || ''}</span><span>${msg}</span>`;
  toastContainer.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// ─── API Calls ────────────────────────────────────────────────────────────────
async function apiRequest(method, path, body = null) {
  const token = localStorage.getItem('braindump_token');
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const opts = { method, headers, credentials: 'same-origin' };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${API_BASE}${path}`, opts);
  if (res.status === 401 && !path.startsWith('/auth/')) {
    localStorage.removeItem('braindump_token');
    showAuthModal();
    throw new Error('Neautorizovaný prístup. Zadajte heslo.');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ─── Authentication Logic ─────────────────────────────────────────────────────
function showAuthModal() {
  if (!authOverlay) return;
  authOverlay.style.display = 'flex';
  if (authError) { authError.style.display = 'none'; authError.textContent = ''; }
  if (authPassword) { authPassword.value = ''; setTimeout(() => authPassword.focus(), 150); }
}

function hideAuthModal() {
  if (!authOverlay) return;
  authOverlay.style.display = 'none';
  if (authError) { authError.style.display = 'none'; authError.textContent = ''; }
  if (authPassword) authPassword.value = '';
}

async function performLogin(password) {
  if (!password || !password.trim()) {
    if (authError) { authError.textContent = 'Zadajte heslo'; authError.style.display = 'block'; }
    return false;
  }

  if (authSubmitBtn) {
    authSubmitBtn.disabled = true;
    authSubmitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Overujem…';
  }

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ password: password.trim() }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Nesprávne heslo');
    if (data.token) localStorage.setItem('braindump_token', data.token);
    hideAuthModal();
    showToast('Odomknuté! Vitaj v BrainDump', 'success');
    await loadTasks();
    checkUrlActions();
    return true;
  } catch (err) {
    if (authError) { authError.textContent = err.message || 'Nesprávne heslo'; authError.style.display = 'block'; }
    if (authPassword) authPassword.focus();
    return false;
  } finally {
    if (authSubmitBtn) {
      authSubmitBtn.disabled = false;
      authSubmitBtn.innerHTML = '<i class="fas fa-unlock"></i> Odomknúť';
    }
  }
}
window.performLogin = performLogin;

async function checkAuth() {
  const urlParams = new URLSearchParams(location.search);
  const urlKey = urlParams.get('key') || urlParams.get('password');
  if (urlKey) { const ok = await performLogin(urlKey); if (ok) return true; }

  const token = localStorage.getItem('braindump_token');
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  try {
    const res = await fetch(`${API_BASE}/auth/check`, { headers, credentials: 'same-origin' });
    if (res.ok) {
      const data = await res.json();
      if (data.authenticated) { hideAuthModal(); return true; }
    }
  } catch (e) { console.warn('Auth check error:', e); }

  showAuthModal();
  return false;
}

async function logout() {
  try { await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'same-origin' }); } catch (_) {}
  localStorage.removeItem('braindump_token');
  tasks = [];
  renderBoard();
  updateStats();
  showAuthModal();
  showToast('Boli ste odhlásený', 'info');
}

function setupAuthEvents() {
  const doLogin = () => { if (authPassword) performLogin(authPassword.value); };
  if (authForm) authForm.addEventListener('submit', (e) => { e.preventDefault(); doLogin(); });
  if (authSubmitBtn) authSubmitBtn.addEventListener('click', (e) => { e.preventDefault(); doLogin(); });
  if (authPassword) authPassword.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); doLogin(); } });
  if (btnLogout) btnLogout.addEventListener('click', logout);
}

// ─── Data Loading ─────────────────────────────────────────────────────────────
async function loadTasks() {
  try {
    // Load all tasks (we filter client-side by selectedDate for instant switching)
    tasks = await apiRequest('GET', '/tasks?limit=500');
    renderCalendar();
    renderBoard();
    updateStats();
  } catch (e) {
    showToast('Nepodarilo sa načítať úlohy: ' + e.message, 'error');
  }
}

async function processText(text) {
  setProcessing(true);
  try {
    const data = await apiRequest('POST', '/tasks/process', { text });
    if (data.tasks && data.tasks.length > 0) {
      tasks = [...data.tasks, ...tasks];
      renderCalendar();
      renderBoard();
      updateStats();
      showToast(`✨ Pridaných ${data.tasks.length} úloh!`, 'success');
    } else {
      showToast('Žiadne úlohy sa nenašli. Skús znova.', 'warning');
    }
  } catch (e) {
    showToast('AI spracovanie zlyhalo: ' + e.message, 'error');
  } finally {
    setProcessing(false);
    clearTranscript();
  }
}

async function toggleDone(id, done) {
  try {
    const updated = await apiRequest('PATCH', `/tasks/${id}`, { done });
    applyLocalUpdate(updated);
    renderCalendar();
    renderBoard();
    updateStats();
  } catch (e) {
    showToast('Chyba pri aktualizácii: ' + e.message, 'error');
  }
}

async function deleteTask(id) {
  try {
    await apiRequest('DELETE', `/tasks/${id}`);
    tasks = tasks.filter(t => t.id !== id);
    renderCalendar();
    renderBoard();
    updateStats();
    showToast('Úloha zmazaná', 'info');
  } catch (e) {
    showToast('Chyba pri mazaní: ' + e.message, 'error');
  }
}

function applyLocalUpdate(updated) {
  tasks = tasks.map(t => t.id === updated.id ? updated : t);
}

// ─── Calendar Strip ───────────────────────────────────────────────────────────
const VISIBLE_DAYS = 7; // days shown in strip at once

function renderCalendar() {
  const today = todayISO();
  const strip = calendarStrip;
  strip.innerHTML = '';

  // "Inbox" pill (first slot)
  const inbox = document.createElement('button');
  inbox.className = 'cal-day' + (selectedDate === null ? ' active' : '');
  inbox.setAttribute('role', 'tab');
  inbox.setAttribute('aria-selected', selectedDate === null);
  inbox.setAttribute('id', 'cal-inbox');
  const inboxCount = tasks.filter(t => !t.done && !t.due_date).length;
  inbox.innerHTML = `
    <span class="cal-day-name">📥</span>
    <span class="cal-day-num">Inbox</span>
    ${inboxCount > 0 ? `<span class="cal-badge">${inboxCount}</span>` : ''}
  `;
  inbox.addEventListener('click', () => { selectedDate = null; renderCalendar(); renderBoard(); updateBoardTitle(); });
  strip.appendChild(inbox);

  // Day pills
  for (let i = 0; i < VISIBLE_DAYS; i++) {
    const iso = addDays(today, calendarOffset + i);
    const d = new Date(iso + 'T00:00:00');
    const dayName = SK_DAYS_SHORT[d.getDay()];
    const dayNum = d.getDate();
    const isToday = iso === today;
    const isSelected = selectedDate === iso;
    const taskCount = tasks.filter(t => !t.done && t.due_date === iso).length;
    const overdueCount = i === 0 ? tasks.filter(t => !t.done && t.due_date && t.due_date < today).length : 0;

    const btn = document.createElement('button');
    btn.className = 'cal-day' + (isSelected ? ' active' : '') + (isToday ? ' today' : '');
    btn.setAttribute('role', 'tab');
    btn.setAttribute('aria-selected', isSelected);
    btn.setAttribute('data-date', iso);
    const badge = taskCount + overdueCount;
    btn.innerHTML = `
      <span class="cal-day-name">${dayName}</span>
      <span class="cal-day-num">${dayNum}</span>
      ${badge > 0 ? `<span class="cal-badge${overdueCount > 0 ? ' overdue' : ''}">${badge}</span>` : ''}
    `;
    btn.addEventListener('click', () => { selectedDate = iso; renderCalendar(); renderBoard(); updateBoardTitle(); });
    strip.appendChild(btn);
  }
}

function updateBoardTitle() {
  if (!boardTitle) return;
  const icon = '<i class="fas fa-list-check" style="color: var(--accent); font-size:.9em;"></i>';
  if (selectedDate === null) {
    boardTitle.innerHTML = `${icon} 📥 Inbox — bez termínu`;
  } else {
    const today = todayISO();
    const tomorrow = addDays(today, 1);
    let label = selectedDate;
    if (selectedDate === today) label = 'Dnes';
    else if (selectedDate === tomorrow) label = 'Zajtra';
    else {
      const d = new Date(selectedDate + 'T00:00:00');
      label = `${SK_DAYS_SHORT[d.getDay()]} ${d.getDate()}. ${SK_MONTHS_SHORT[d.getMonth()]}`;
    }
    boardTitle.innerHTML = `${icon} ${label}`;
  }
}

// ─── Render ───────────────────────────────────────────────────────────────────
function getFilteredTasks() {
  const today = todayISO();
  let filtered;

  if (selectedDate === null) {
    // Inbox: tasks with no due_date
    filtered = tasks.filter(t => !t.due_date);
  } else if (selectedDate === today) {
    // Today: today's tasks + overdue tasks
    filtered = tasks.filter(t => t.due_date === today || (t.due_date && t.due_date < today));
  } else {
    // Specific day
    filtered = tasks.filter(t => t.due_date === selectedDate);
  }

  if (filter === 'open') return filtered.filter(t => !t.done);
  if (filter === 'done') return filtered.filter(t => t.done);
  return filtered;
}

function renderBoard() {
  updateBoardTitle();
  const visible = getFilteredTasks();
  taskBoard.innerHTML = '';

  if (visible.length === 0) {
    const label = selectedDate === null ? 'Inbox je prázdny' : 'Žiadne úlohy pre tento deň';
    taskBoard.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">${selectedDate === null ? '📥' : '🗓️'}</div>
        <p class="empty-text">${label}</p>
        <p class="empty-sub">Stlač mikrofón a nadiktuj čo treba urobiť!</p>
      </div>`;
    return;
  }

  // Group by category
  const order = ['Work', 'Groceries', 'Personal', 'Other'];
  const grouped = {};
  order.forEach(cat => { grouped[cat] = []; });
  visible.forEach(t => {
    if (grouped[t.category]) grouped[t.category].push(t);
    else grouped['Other'].push(t);
  });

  order.forEach(cat => {
    const items = grouped[cat];
    if (items.length === 0) return;
    const cfg = CATS[cat];

    const section = document.createElement('div');
    section.className = 'category-section';
    section.setAttribute('data-cat', cat);

    section.innerHTML = `
      <div class="category-header" role="button" tabindex="0" aria-expanded="true" title="Zbaliť / rozbaliť">
        <span class="category-dot"></span>
        <span class="category-emoji">${cfg.emoji}</span>
        <span class="category-label">${cfg.label}</span>
        <span class="category-badge">${items.length}</span>
        <i class="fas fa-chevron-down category-chevron"></i>
      </div>
      <ul class="task-list" role="list" aria-label="${cfg.label} úlohy"></ul>
    `;

    const list = section.querySelector('.task-list');
    items.forEach(task => list.appendChild(renderTask(task)));

    const header = section.querySelector('.category-header');
    header.addEventListener('click', () => {
      section.classList.toggle('collapsed');
      header.setAttribute('aria-expanded', !section.classList.contains('collapsed'));
    });
    header.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); header.click(); }
    });

    taskBoard.appendChild(section);
  });
}

function renderTask(task) {
  const li = document.createElement('li');
  li.className = `task-item${task.done ? ' done' : ''}`;
  li.setAttribute('data-id', task.id);
  li.setAttribute('data-cat', task.category);

  const today = todayISO();
  const dueBadge = task.due_date
    ? `<span class="due-badge ${dueDateClass(task.due_date)}">${formatDueDate(task.due_date)}</span>`
    : '';

  const isOverdue = task.due_date && task.due_date < today && !task.done;
  if (isOverdue) li.classList.add('task-overdue');

  li.innerHTML = `
    <input type="checkbox" class="task-checkbox" ${task.done ? 'checked' : ''}
      aria-label="Označiť ako splnené" id="chk-${task.id}">
    <div class="task-body">
      <div class="task-text">${escHtml(task.text)}</div>
      <div class="task-meta">
        <span class="task-date">${new Date(task.created_at + 'Z').toLocaleDateString('sk-SK', { day: 'numeric', month: 'short' })}</span>
        ${dueBadge}
      </div>
    </div>
    <div class="task-actions">
      <button class="task-btn edit" data-action="edit" title="Upraviť">
        <i class="fas fa-pen"></i>
      </button>
      <button class="task-btn delete" data-action="delete" title="Zmazať">
        <i class="fas fa-trash-alt"></i>
      </button>
    </div>`;

  li.addEventListener('change', e => {
    if (e.target.type === 'checkbox') toggleDone(task.id, e.target.checked);
  });
  li.addEventListener('click', e => {
    const action = e.target.closest('[data-action]')?.dataset.action;
    if (!action) return;
    if (action === 'edit')   { openEditModal(task); }
    if (action === 'delete') { if (confirm('Zmazať úlohu?')) deleteTask(task.id); }
  });

  return li;
}

// ─── Stats ────────────────────────────────────────────────────────────────────
function updateStats() {
  const open = tasks.filter(t => !t.done);
  ['Work', 'Groceries', 'Personal', 'Other'].forEach(cat => {
    const el = document.getElementById(`stat-${cat.toLowerCase()}`);
    if (el) el.textContent = open.filter(t => t.category === cat).length;
  });
}

// ─── Export ───────────────────────────────────────────────────────────────────
function exportTasks() {
  const openTasks = tasks.filter(t => !t.done);
  if (openTasks.length === 0) { showToast('Žiadne otvorené úlohy na export', 'info'); return; }

  const lines = [];
  const order = ['Work', 'Groceries', 'Personal', 'Other'];
  const grouped = {};
  order.forEach(cat => { grouped[cat] = []; });
  openTasks.forEach(t => { (grouped[t.category] || grouped['Other']).push(t); });

  order.forEach(cat => {
    if (grouped[cat].length === 0) return;
    const cfg = CATS[cat];
    lines.push(`${cfg.emoji} ${cfg.label.toUpperCase()}`);
    grouped[cat].forEach(t => {
      const dd = t.due_date ? ` [${formatDueDate(t.due_date)}]` : '';
      lines.push(`  • ${t.text}${dd}`);
    });
    lines.push('');
  });

  navigator.clipboard.writeText(lines.join('\n').trim())
    .then(() => showToast('Zoznam skopírovaný do schránky!', 'success'))
    .catch(() => showToast('Kopírovanie zlyhalo', 'error'));
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
function escHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ─── Voice Recording ──────────────────────────────────────────────────────────
function initSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return null;

  const rec = new SpeechRecognition();
  rec.continuous = true;
  rec.interimResults = true;
  rec.lang = langSelect.value;
  rec.maxAlternatives = 1;

  let finalTranscript = '';

  rec.onstart = () => {
    isRecording = true;
    finalTranscript = transcript;
    micBtn.classList.add('recording');
    micIcon.className = 'fas fa-stop';
    micBtn.setAttribute('aria-label', 'Zastaviť nahrávanie');
    transcriptBox.classList.add('active');
    transcriptCursor.style.display = 'inline-block';
    setStatus('🔴 Nahrávam… (hovor teraz)', 'active');
  };

  rec.onresult = (e) => {
    let interim = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const result = e.results[i];
      if (result.isFinal) { finalTranscript += result[0].transcript + ' '; }
      else { interim += result[0].transcript; }
    }
    transcript = finalTranscript;
    showTranscript(finalTranscript + interim, interim.length > 0);
  };

  rec.onerror = (e) => {
    if (e.error === 'not-allowed') { showToast('Prístup k mikrofónu bol zamietnutý.', 'error'); }
    else if (e.error !== 'aborted' && e.error !== 'no-speech') { showToast(`Chyba rozpoznávania reči: ${e.error}`, 'error'); }
    stopRecording();
  };

  rec.onend = () => {
    if (isRecording) { try { rec.start(); } catch (_) { stopRecording(); } }
  };

  return rec;
}

function startRecording() {
  recognition = initSpeechRecognition();
  if (!recognition) {
    showToast('Web Speech API nie je podporovaná v tomto prehliadači. Skús Chrome/Edge.', 'error');
    return;
  }
  recognition.lang = langSelect.value;
  try { recognition.start(); }
  catch (e) { showToast('Nepodarilo sa spustiť mikrofón: ' + e.message, 'error'); }
}

function stopRecording() {
  isRecording = false;
  if (recognition) { try { recognition.stop(); } catch (_) {} }
  micBtn.classList.remove('recording');
  micIcon.className = 'fas fa-microphone';
  micBtn.setAttribute('aria-label', 'Spustiť nahrávanie');
  transcriptBox.classList.remove('active');
  transcriptCursor.style.display = 'none';

  if (transcript.trim()) {
    setStatus('✅ Zaznamenaný text. Stlač „Spracovať cez AI".', 'success');
    btnSend.disabled = false;
    btnClearText.style.display = 'flex';
  } else {
    setStatus('Stlač mikrofón a hovor…');
  }
}

function toggleRecording() {
  if (isRecording) stopRecording(); else startRecording();
}

// ─── Transcript UI Helpers ────────────────────────────────────────────────────
function showTranscript(text, hasInterim = false) {
  if (!text.trim()) return;
  transcriptPlaceholder.style.display = 'none';
  transcriptText.style.display = 'inline';
  transcriptText.textContent = text;
  btnSend.disabled = false;
  btnClearText.style.display = 'flex';
}

function clearTranscript() {
  transcript = '';
  transcriptText.style.display = 'none';
  transcriptPlaceholder.style.display = 'inline';
  transcriptCursor.style.display = 'none';
  transcriptBox.className = 'transcript-box';
  btnSend.disabled = true;
  btnClearText.style.display = 'none';
  setStatus('Stlač mikrofón a hovor…');
}

function setStatus(msg, type = '') {
  voiceStatus.textContent = msg;
  voiceStatus.className = 'voice-status' + (type ? ` ${type}` : '');
}

function setProcessing(active) {
  processingBar.classList.toggle('active', active);
  micBtn.disabled = active;
  btnSend.disabled = active;
  if (active) {
    transcriptBox.classList.add('processing');
    setStatus('🤖 AI spracováva úlohy…', 'processing');
  } else {
    transcriptBox.classList.remove('processing');
  }
}

// ─── Quick Add Modal ──────────────────────────────────────────────────────────
function openQuickAddModal() {
  if (!quickAddOverlay) return;
  // Pre-fill due date if a date is selected in calendar
  if (quickAddDueDate && selectedDate) quickAddDueDate.value = selectedDate;
  else if (quickAddDueDate) quickAddDueDate.value = '';
  quickAddOverlay.style.display = 'flex';
  if (quickAddText) { quickAddText.value = ''; setTimeout(() => quickAddText.focus(), 150); }
}

function closeQuickAddModal() {
  if (!quickAddOverlay) return;
  quickAddOverlay.style.display = 'none';
  if (quickAddText) quickAddText.value = '';
  if (quickAddDueDate) quickAddDueDate.value = '';
}

async function submitQuickTask() {
  if (!quickAddText) return;
  const text = quickAddText.value.trim();
  if (!text) return;
  const due_date = quickAddDueDate && quickAddDueDate.value ? quickAddDueDate.value : null;

  if (quickAddSubmit) {
    quickAddSubmit.disabled = true;
    quickAddSubmit.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Pridávam…';
  }

  try {
    const created = await apiRequest('POST', '/tasks', { text, category: selectedCategory, due_date });
    tasks.unshift(created);
    renderCalendar();
    renderBoard();
    updateStats();
    closeQuickAddModal();
    showToast(`Úloha pridaná do "${selectedCategory}"`, 'success');
  } catch (err) {
    showToast('Chyba: ' + err.message, 'error');
  } finally {
    if (quickAddSubmit) {
      quickAddSubmit.disabled = false;
      quickAddSubmit.innerHTML = '<i class="fas fa-check"></i> Pridať úlohu';
    }
  }
}

function setupQuickAddEvents() {
  if (btnQuickAdd) btnQuickAdd.addEventListener('click', openQuickAddModal);
  if (quickAddClose) quickAddClose.addEventListener('click', closeQuickAddModal);
  if (quickAddCancel) quickAddCancel.addEventListener('click', closeQuickAddModal);
  if (quickAddOverlay) quickAddOverlay.addEventListener('click', (e) => { if (e.target === quickAddOverlay) closeQuickAddModal(); });
  if (quickAddDueClear) quickAddDueClear.addEventListener('click', () => { if (quickAddDueDate) quickAddDueDate.value = ''; });

  // Category pills
  if (categoryPills) {
    categoryPills.querySelectorAll('.cat-pill').forEach(btn => {
      btn.addEventListener('click', () => {
        categoryPills.querySelectorAll('.cat-pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selectedCategory = btn.dataset.cat || 'Work';
      });
    });
  }

  if (quickAddForm) {
    quickAddForm.addEventListener('submit', async (e) => { e.preventDefault(); await submitQuickTask(); });
  }
  if (quickAddText) {
    quickAddText.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitQuickTask(); }
      else if (e.key === 'Escape') { closeQuickAddModal(); }
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'n' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
      if (authOverlay && authOverlay.style.display !== 'flex') { e.preventDefault(); openQuickAddModal(); }
    }
  });
}

// ─── Edit Task Modal ──────────────────────────────────────────────────────────
function openEditModal(task) {
  if (!editTaskOverlay) return;
  editingTaskId = task.id;
  editSelectedCat = task.category;

  if (editTaskText) editTaskText.value = task.text;
  if (editDueDate) editDueDate.value = task.due_date || '';

  // Set category pills
  if (editCatPills) {
    editCatPills.querySelectorAll('.cat-pill').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.cat === task.category);
    });
  }

  editTaskOverlay.style.display = 'flex';
  if (editTaskText) setTimeout(() => editTaskText.focus(), 150);
}

function closeEditModal() {
  if (!editTaskOverlay) return;
  editTaskOverlay.style.display = 'none';
  editingTaskId = null;
}

async function submitEditTask() {
  if (!editTaskText || !editingTaskId) return;
  const text = editTaskText.value.trim();
  if (!text) return;
  const due_date = editDueDate && editDueDate.value ? editDueDate.value : '';

  if (editTaskSubmit) {
    editTaskSubmit.disabled = true;
    editTaskSubmit.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Ukladám…';
  }

  try {
    const updated = await apiRequest('PATCH', `/tasks/${editingTaskId}`, {
      text,
      category: editSelectedCat,
      due_date,  // empty string = clear
    });
    applyLocalUpdate(updated);
    renderCalendar();
    renderBoard();
    closeEditModal();
    showToast('Úloha aktualizovaná', 'success');
  } catch (err) {
    showToast('Chyba: ' + err.message, 'error');
  } finally {
    if (editTaskSubmit) {
      editTaskSubmit.disabled = false;
      editTaskSubmit.innerHTML = '<i class="fas fa-check"></i> Uložiť zmeny';
    }
  }
}

function setupEditModalEvents() {
  if (editTaskClose) editTaskClose.addEventListener('click', closeEditModal);
  if (editTaskCancel) editTaskCancel.addEventListener('click', closeEditModal);
  if (editTaskOverlay) editTaskOverlay.addEventListener('click', (e) => { if (e.target === editTaskOverlay) closeEditModal(); });
  if (editDueClear) editDueClear.addEventListener('click', () => { if (editDueDate) editDueDate.value = ''; });

  if (editCatPills) {
    editCatPills.querySelectorAll('.cat-pill').forEach(btn => {
      btn.addEventListener('click', () => {
        editCatPills.querySelectorAll('.cat-pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        editSelectedCat = btn.dataset.cat || 'Work';
      });
    });
  }

  if (editTaskForm) {
    editTaskForm.addEventListener('submit', async (e) => { e.preventDefault(); await submitEditTask(); });
  }
  if (editTaskText) {
    editTaskText.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeEditModal();
    });
  }
}

// ─── Calendar Navigation ──────────────────────────────────────────────────────
function setupCalendarNav() {
  if (calPrev) {
    calPrev.addEventListener('click', () => {
      calendarOffset -= VISIBLE_DAYS;
      renderCalendar();
    });
  }
  if (calNext) {
    calNext.addEventListener('click', () => {
      calendarOffset += VISIBLE_DAYS;
      renderCalendar();
    });
  }
}

// ─── Filter Buttons ───────────────────────────────────────────────────────────
function setupFilterButtons() {
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      filter = btn.dataset.filter;
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderBoard();
    });
  });
}

// ─── Global Events ────────────────────────────────────────────────────────────
function setupGlobalEvents() {
  micBtn.addEventListener('click', toggleRecording);

  btnSend.addEventListener('click', () => {
    const text = transcript.trim();
    if (!text) return;
    if (isRecording) stopRecording();
    processText(text);
  });

  btnClearText.addEventListener('click', () => {
    if (isRecording) stopRecording();
    clearTranscript();
  });

  btnExport.addEventListener('click', exportTasks);

  btnClearDone.addEventListener('click', async () => {
    const doneTasks = tasks.filter(t => t.done);
    if (doneTasks.length === 0) { showToast('Žiadne splnené úlohy', 'info'); return; }
    if (!confirm(`Zmazať ${doneTasks.length} splnených úloh?`)) return;
    await Promise.allSettled(doneTasks.map(t => apiRequest('DELETE', `/tasks/${t.id}`)));
    tasks = tasks.filter(t => !t.done);
    renderCalendar();
    renderBoard();
    updateStats();
    showToast(`Zmazaných ${doneTasks.length} úloh`, 'success');
  });

  langSelect.addEventListener('change', () => {
    if (isRecording) {
      stopRecording();
      showToast(`Jazyk zmenený na ${langSelect.value}. Spusti nahrávanie znova.`, 'info');
    }
  });
}

// ─── Auto-actions on ?action=record or ?action=add ────────────────────────────
function checkUrlActions() {
  const params = new URLSearchParams(location.search);
  if (params.get('action') === 'record') {
    setTimeout(() => { showToast('🎤 Automatické spustenie nahrávania…', 'info'); startRecording(); }, 800);
  } else if (params.get('action') === 'add') {
    setTimeout(() => { openQuickAddModal(); }, 400);
  }
}

// ─── Service Worker ───────────────────────────────────────────────────────────
function registerSW() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js', { scope: './' })
      .then(reg => console.log('[SW] Registered, scope:', reg.scope))
      .catch(err => console.warn('[SW] Registration failed:', err));
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────
(async function init() {
  // Default: show today in calendar
  selectedDate = todayISO();

  registerSW();
  setupAuthEvents();
  setupQuickAddEvents();
  setupEditModalEvents();
  setupCalendarNav();
  setupFilterButtons();
  setupGlobalEvents();

  // Set default filter to 'open'
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  const openBtn = document.getElementById('filter-open');
  if (openBtn) { openBtn.classList.add('active'); filter = 'open'; }

  const isAuthed = await checkAuth();
  if (isAuthed) {
    await loadTasks();
    checkUrlActions();
  }
})();
