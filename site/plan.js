// Планировщик визуальной новеллы — состояние, этапы, чекбоксы, таймеры.
// Работает и через API сервера, и автономно через localStorage (файл plan.html).

import { STAGES, DAILY, SURPRISE, TIPS } from './plan_tasks.js';

const $ = (sel) => document.querySelector(sel);
const STORE_KEY = 'vn-plan-v1';
const RING = 2 * Math.PI * 52;

const state = {
  done: {},
  counters: {},
  notes: {},
  picks: {},
  custom: [],
  opened: [],
  daily: {},
  streak: 0,
  bestStreak: 0,
  lastDay: '',
  surpriseTask: null,
  log: [],
  gameTitle: '',
  sessionNote: '',
};

const ui = {
  filter: 'all',
  collapsed: new Set(),
  online: false,
  ready: false,
  scrollNext: false,
};

const timers = {};
const timerButtons = new Map();

// ------------------------------------------------------------------ utils --

function pad(n) { return String(n).padStart(2, '0'); }

function dayKey(d = new Date()) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function shiftDay(key, delta) {
  const [y, m, d] = key.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  date.setDate(date.getDate() + delta);
  return dayKey(date);
}

function hhmm(ts) {
  const d = new Date(ts);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function toast(msg, kind = '') {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast ' + kind;
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, kind === 'err' ? 5000 : 2400);
}

function uid(prefix) {
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

// ------------------------------------------------------------- persistence --

let saveTimer = null;

function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, 350);
}

async function save() {
  clearTimeout(saveTimer);
  state.log = state.log.slice(-60);
  if (ui.online) {
    try {
      await fetch('/api/plan', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pickPayload()),
      });
      return;
    } catch (_) { ui.online = false; }
  }
  try { localStorage.setItem(STORE_KEY, JSON.stringify(pickPayload())); } catch (_) {}
}

function pickPayload() {
  return {
    done: state.done,
    counters: state.counters,
    notes: state.notes,
    picks: state.picks,
    custom: state.custom,
    opened: state.opened,
    daily: state.daily,
    streak: state.streak,
    bestStreak: state.bestStreak,
    lastDay: state.lastDay,
    surpriseTask: state.surpriseTask,
    log: state.log,
    gameTitle: state.gameTitle,
    sessionNote: state.sessionNote,
  };
}

function applyPayload(data) {
  if (!data || typeof data !== 'object') return;
  for (const key of ['done', 'counters', 'notes', 'picks', 'daily']) {
    if (data[key] && typeof data[key] === 'object') state[key] = { ...data[key] };
  }
  if (Array.isArray(data.opened)) state.opened = data.opened.map(String);
  if (Array.isArray(data.custom)) state.custom = data.custom.filter((c) => c && c.id);
  if (Array.isArray(data.log)) state.log = data.log.slice(-60);
  for (const key of ['streak', 'bestStreak']) {
    if (typeof data[key] === 'number') state[key] = data[key];
  }
  for (const key of ['lastDay', 'surpriseTask', 'gameTitle', 'sessionNote']) {
    if (typeof data[key] === 'string') state[key] = data[key];
  }
}

function setupLinks() {
  const link = $('#linkForge');
  if (!link) return;
  const host = location.hostname;
  if (host === '127.0.0.1' || host === 'localhost') {
    link.href = '/';
    link.textContent = 'Генератор ассетов';
  }
}

function probeStorage() {
  try {
    localStorage.setItem(STORE_KEY + '_probe', '1');
    localStorage.removeItem(STORE_KEY + '_probe');
    return true;
  } catch (_) {
    toast('Браузер не даёт сохранять данные. Прогресс не переживёт перезагрузку.', 'err');
    return false;
  }
}

async function load() {
  try {
    const res = await fetch('/api/plan', { headers: { 'Accept': 'application/json' } });
    if (!res.ok) throw new Error('bad status');
    applyPayload(await res.json());
    ui.online = true;
    return;
  } catch (_) {
    ui.online = false;
  }
  try { applyPayload(JSON.parse(localStorage.getItem(STORE_KEY) || 'null')); } catch (_) {}
}

// -------------------------------------------------------------- task model --

function taskId(stage, index) {
  return `${stage.id}:${index}`;
}

function countOf(id) {
  return Number(state.counters[id] || 0);
}

function isDone(id, task) {
  if (task.k === 'count') return countOf(id) >= (task.n || 1);
  if (task.k === 'pick') return Boolean(state.picks[id]);
  if (task.k === 'note') return Boolean((state.notes[id] || '').trim());
  return Boolean(state.done[id]);
}

function setDone(id, value) {
  if (value) state.done[id] = true;
  else delete state.done[id];
  if (state.done[id]) addLog(`Готово: ${labelFor(id)}`);
}

function labelFor(id) {
  const [stageId, idx] = id.split(':');
  const stage = STAGES.find((s) => s.id === stageId);
  const task = stage?.tasks[Number(idx)];
  if (task) return task.t;
  const custom = state.custom.find((c) => c.id === id);
  return custom ? custom.text : id;
}

function addLog(text) {
  state.log.push({ at: Date.now(), text });
  if (state.log.length > 60) state.log = state.log.slice(-60);
}

function stageTasks(stage) {
  const extra = state.custom.filter((c) => c.stage === stage.id);
  return stage.tasks.map((task, i) => ({ id: taskId(stage, i), task, custom: false }))
    .concat(extra.map((c) => ({ id: c.id, task: { t: c.text, k: 'check' }, custom: true })));
}

function stageProgress(stage) {
  const items = stageTasks(stage).filter((x) => !x.custom);
  const done = items.filter((x) => isDone(x.id, x.task)).length;
  return { done, total: items.length };
}

function isStageComplete(stage) {
  const { done, total } = stageProgress(stage);
  return total > 0 && done >= total;
}

function isUnlocked(index) {
  if (index === 0) return true;
  if (isStageComplete(STAGES[index - 1])) return true;
  return state.opened.includes(STAGES[index].id);
}

function currentStageIndex() {
  const i = STAGES.findIndex((s) => !isStageComplete(s));
  return i === -1 ? STAGES.length - 1 : i;
}

// ----------------------------------------------------------------- timers --

function timerLabel(seconds) {
  return `${pad(Math.floor(seconds / 60))}:${pad(seconds % 60)}`;
}

function startTimer(id, minutes) {
  timers[id] = { endsAt: Date.now() + minutes * 60000, left: minutes * 60, total: minutes * 60, running: true };
  render();
}

function stopTimer(id) {
  const t = timers[id];
  if (!t) return;
  t.left = leftOf(id);
  t.running = false;
  delete t.endsAt;
  render();
}

function leftOf(id) {
  const t = timers[id];
  if (!t) return 0;
  if (!t.running) return t.left;
  return Math.max(0, Math.round((t.endsAt - Date.now()) / 1000));
}

function resetTimer(id) {
  const t = timers[id];
  if (!t) return;
  t.running = false;
  delete t.endsAt;
  t.left = t.total;
  render();
}

function finishTimer(id) {
  const stage = STAGES.find((s) => s.tasks.some((_, i) => taskId(s, i) === id));
  const idx = stage ? stage.tasks.findIndex((_, i) => taskId(stage, i) === id) : -1;
  const task = stage && idx >= 0 ? stage.tasks[idx] : null;
  if (!task) return;
  delete timers[id];
  state.done[id] = true;
  const mins = task.min || 0;
  state.counters.__focus = Number(state.counters.__focus || 0) + mins;
  addLog(`Таймер ${mins} мин закрыт: ${task.t}`);
  toast(`Таймер на ${mins} мин закрыт. +${mins} минут фокуса`, 'ok');
  checkUnlocks();
  scheduleSave();
  render();
}

// ------------------------------------------------------------ daily quest --

function dailyTask() {
  const key = dayKey();
  return DAILY[hash('vn-daily-' + key) % DAILY.length];
}

function dailyDoneToday() {
  return Boolean(state.daily[dayKey()]);
}

function rollStreak() {
  const today = dayKey();
  if (state.lastDay === today) return;
  state.streak = state.lastDay === shiftDay(today, -1) ? state.streak : 0;
}

// ----------------------------------------------------------------- render --

function renderOverview() {
  let total = 0;
  let done = 0;
  STAGES.forEach((stage, i) => {
    const p = stageProgress(stage);
    total += p.total;
    if (isUnlocked(i)) done += p.done;
  });
  for (const c of state.custom) {
    total += 1;
    if (state.done[c.id]) done += 1;
  }
  const pct = total ? Math.round((done / total) * 100) : 0;

  $('#overallPct').textContent = pct + '%';
  $('#ringFg').style.strokeDashoffset = String(RING * (1 - pct / 100));
  $('#overallBar').style.width = pct + '%';
  $('#ovCount').textContent = `${done} из ${total} задач закрыто`;

  const focus = Number(state.counters.__focus || 0);
  $('#focusNum').textContent = focus;

  const opened = STAGES.filter((_, i) => isUnlocked(i)).length;
  const completed = STAGES.filter((s) => isStageComplete(s)).length;
  $('#stageNum').textContent = `${completed}/${STAGES.length}`;
  $('#stageName').textContent = `${STAGES[currentStageIndex()].name} · 🔒 ещё ${STAGES.length - opened}`;

  $('#streakNum').textContent = state.streak;
  $('#bestStreak').textContent = `рекорд ${state.bestStreak}`;

  if ($('#gameTitle').value !== state.gameTitle) $('#gameTitle').value = state.gameTitle;
  if ($('#ideas').value !== state.sessionNote) $('#ideas').value = state.sessionNote;
  $('#storeMode').hidden = ui.online;
}

function renderDaily() {
  const text = dailyTask();
  const done = dailyDoneToday();
  $('#dailyDate').textContent = dayKey().slice(5).replace('-', '.');
  $('#dailyText').textContent = text;
  $('#dailyText').className = 'daily-text' + (done ? ' done' : '');
  const btn = $('#dailyDone');
  btn.textContent = done ? 'Выполнено ✓' : 'Сделано ✓';
  btn.disabled = done;
}

function renderSurprise() {
  const box = $('#surpriseText');
  const btn = $('#surpriseDone');
  if (state.surpriseTask) {
    box.textContent = state.surpriseTask.text;
    box.className = 'daily-text done';
    btn.disabled = false;
  } else {
    const tip = TIPS[hash(dayKey()) % TIPS.length];
    box.textContent = tip;
    box.className = 'daily-text';
    btn.disabled = true;
  }
}

function renderCustom() {
  const list = $('#customList');
  list.innerHTML = '';
  if (!state.custom.length) {
    list.innerHTML = '<li class="empty">Пока пусто — напиши свою задачу сверху</li>';
    return;
  }
  for (const c of [...state.custom].reverse()) {
    const li = document.createElement('li');
    if (state.done[c.id]) li.className = 'done';
    const tick = document.createElement('button');
    tick.textContent = state.done[c.id] ? '✓' : '○';
    tick.title = 'Отметить';
    tick.onclick = () => {
      setDone(c.id, !state.done[c.id]);
      scheduleSave();
      render();
    };
    const span = document.createElement('span');
    span.textContent = c.text;
    if (c.stage && c.stage !== 'inbox') {
      const tag = document.createElement('span');
      tag.className = 'custom-tag';
      tag.textContent = STAGES.find((s) => s.id === c.stage)?.name || '';
      li.append(span, tag);
    } else {
      li.append(span);
    }
    const del = document.createElement('button');
    del.textContent = '×';
    del.title = 'Удалить';
    del.onclick = () => {
      state.custom = state.custom.filter((x) => x.id !== c.id);
      delete state.done[c.id];
      scheduleSave();
      render();
    };
    li.prepend(tick);
    li.append(del);
    list.append(li);
  }
}

function renderLog() {
  const list = $('#logList');
  list.innerHTML = '';
  const items = [...state.log].reverse().slice(0, 14);
  if (!items.length) {
    list.innerHTML = '<li class="empty">Здесь появятся закрытые этапы и челленджи</li>';
    return;
  }
  for (const e of items) {
    const li = document.createElement('li');
    const t = document.createElement('time');
    t.textContent = hhmm(e.at);
    const s = document.createElement('span');
    s.textContent = e.text;
    li.append(t, s);
    list.append(li);
  }
}

function taskRow(id, task, custom) {
  const done = isDone(id, task);
  const row = document.createElement('div');
  row.className = 'task' + (done ? ' done' : '');
  row.dataset.id = id;

  const tick = document.createElement('button');
  tick.className = 'tick' + (done ? ' on' : '');
  tick.textContent = '✓';
  tick.dataset.act = 'toggle';
  tick.dataset.id = id;
  tick.dataset.kind = task.k;

  const body = document.createElement('div');
  body.className = 'task-body';

  const label = document.createElement('div');
  label.className = 'task-text';
  label.dataset.act = 'toggle';
  label.dataset.id = id;
  label.dataset.kind = task.k;
  label.innerHTML = escapeHtml(task.t);
  if (task.hint) {
    const hint = document.createElement('span');
    hint.className = 'hint';
    hint.textContent = task.hint;
    label.append(hint);
  }
  body.append(label);

  if (custom) {
    const tag = document.createElement('span');
    tag.className = 'custom-tag';
    tag.textContent = 'своя';
    tag.style.alignSelf = 'flex-start';
    body.append(tag);
  }

  if (task.k === 'count') {
    const wrap = document.createElement('div');
    wrap.className = 'counter';
    const minus = document.createElement('button');
    minus.textContent = '−';
    minus.dataset.act = 'cdec';
    minus.dataset.id = id;
    const num = document.createElement('span');
    num.className = 'counter-num';
    num.innerHTML = `<b>${countOf(id)}</b> / ${task.n}`;
    const plus = document.createElement('button');
    plus.textContent = '+';
    plus.dataset.act = 'cinc';
    plus.dataset.id = id;
    const pips = document.createElement('div');
    pips.className = 'pips';
    for (let i = 1; i <= task.n; i++) {
      const p = document.createElement('button');
      p.className = 'pip' + (i <= countOf(id) ? ' on' : '');
      p.dataset.act = 'pip';
      p.dataset.id = id;
      p.dataset.n = String(i);
      p.title = `${i} / ${task.n}`;
      pips.append(p);
    }
    minus.disabled = countOf(id) === 0;
    wrap.append(minus, num, plus, pips);
    body.append(wrap);
  }

  if (task.k === 'pick') {
    const wrap = document.createElement('div');
    wrap.className = 'picks';
    for (const opt of task.o) {
      const b = document.createElement('button');
      b.textContent = opt;
      b.dataset.act = 'pick';
      b.dataset.id = id;
      b.dataset.value = opt;
      if (state.picks[id] === opt) b.className = 'on';
      wrap.append(b);
    }
    body.append(wrap);
  }

  if (task.k === 'note') {
    const area = document.createElement('textarea');
    area.className = 'note-area';
    area.rows = 2;
    area.placeholder = task.placeholder || 'запиши ответ…';
    area.value = state.notes[id] || '';
    area.dataset.id = id;
    body.append(area);
  }

  if (task.k === 'time') {
    const t = timers[id];
    const left = t ? leftOf(id) : task.min * 60;
    const btn = document.createElement('button');
    btn.className = 'tool' + (t && t.running ? ' running' : '') + (done ? ' done' : '');
    btn.dataset.act = 'timer';
    btn.dataset.id = id;
    btn.id = `timer-${id}`;
    btn.textContent = t && t.running ? `⏸ ${timerLabel(left)}` : done ? '✓ закрыто' : `▶ ${task.min}:00`;
    timerButtons.set(id, btn);
    const reset = document.createElement('button');
    reset.className = 'tool';
    reset.dataset.act = 'timerReset';
    reset.dataset.id = id;
    reset.textContent = '↺';
    reset.title = 'Сбросить таймер';
    const tools = document.createElement('div');
    tools.className = 'task-tools';
    tools.append(btn, reset);
    body.append(tools);
  }

  row.append(tick, body);
  return row;
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function renderStages() {
  const wrap = $('#stages');
  wrap.innerHTML = '';
  const current = currentStageIndex();

  STAGES.forEach((stage, index) => {
    const unlocked = isUnlocked(index);
    const complete = isStageComplete(stage);
    const { done, total } = stageProgress(stage);
    const pct = total ? Math.round((done / total) * 100) : 0;

    if (!ui.ready) {
      if (!unlocked || (complete && index !== current)) ui.collapsed.add(stage.id);
    }

    if (ui.filter === 'open' && (!unlocked || complete)) return;
    if (ui.filter === 'done' && !complete) return;
    if (ui.filter === 'active' && index !== current) return;

    const card = document.createElement('article');
    card.className = 'stage-card';
    if (unlocked) card.classList.add('open');
    if (complete) card.classList.add('complete');
    if (index === current) card.classList.add('current');
    if (ui.collapsed.has(stage.id)) card.classList.add('collapsed');
    card.style.setProperty('--sc', stage.color);

    const head = document.createElement('header');
    head.className = 'stage-head';
    head.innerHTML = `
      <div class="stage-num">${complete ? '✓' : index + 1}</div>
      <div class="stage-info">
        <b class="stage-title">${escapeHtml(stage.name)}</b>
        <small class="stage-sub">${escapeHtml(stage.sub)}</small>
      </div>
      <div class="stage-prog">
        <div class="bar"><i style="width:${pct}%"></i></div>
        <span>${done}/${total}</span>
      </div>
      <span class="stage-caret">▾</span>`;
    head.onclick = (e) => {
      if (e.target.closest('[data-act]')) return;
      if (ui.collapsed.has(stage.id)) ui.collapsed.delete(stage.id);
      else ui.collapsed.add(stage.id);
      card.classList.toggle('collapsed');
    };
    card.append(head);

    if (!unlocked) {
      const lock = document.createElement('div');
      lock.className = 'stage-lock';
      lock.innerHTML = `<span class="lk">🔒</span><span>Откроется после «${escapeHtml(STAGES[index - 1].name)}»</span>`;
      const force = document.createElement('button');
      force.className = 'tool';
      force.dataset.act = 'force';
      force.dataset.id = stage.id;
      force.textContent = 'Открыть всё равно';
      lock.append(force);
      card.append(lock);
    } else {
      const tasks = document.createElement('div');
      tasks.className = 'tasks';
      for (const item of stageTasks(stage)) {
        tasks.append(taskRow(item.id, item.task, item.custom));
      }
      card.append(tasks);
    }

    wrap.append(card);
  });

  ui.ready = true;

  if (ui.scrollNext) {
    ui.scrollNext = false;
    const target = wrap.querySelector('.stage-card.current');
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

function render() {
  renderOverview();
  renderDaily();
  renderSurprise();
  renderCustom();
  renderLog();
  renderStages();
}

// ---------------------------------------------------------------- actions --

function findTask(id) {
  const [stageId, idx] = id.split(':');
  const stage = STAGES.find((s) => s.id === stageId);
  const task = stage && !Number.isNaN(Number(idx)) ? stage.tasks[Number(idx)] : null;
  if (stage && task) return { stage, task };
  return { stage: null, task: { t: labelFor(id), k: 'check' } };
}

function afterComplete(id) {
  const { stage, task } = findTask(id);
  if (!stage) { scheduleSave(); render(); return; }
  if (!isDone(id, task)) return;
  if (isStageComplete(stage)) {
    const idx = STAGES.indexOf(stage);
    const next = STAGES[idx + 1];
    if (next && !isUnlocked(idx + 1)) {
      addLog(`Этап закрыт: ${stage.name}${next ? ` → открыт «${next.name}»` : ''}`);
      toast(next ? `Этап «${stage.name}» закрыт. Открыт «${next.name}»` : 'Все этапы закрыты!', 'ok');
    } else {
      addLog(`Этап закрыт: ${stage.name}`);
    }
    ui.scrollNext = true;
    ui.collapsed.delete(stage.id);
  }
}

function checkUnlocks() {
  for (let i = 1; i < STAGES.length; i++) {
    if (!isUnlocked(i) && isStageComplete(STAGES[i - 1])) ui.scrollNext = true;
  }
}

function toggleTask(id) {
  const { task } = findTask(id);
  if (task.k === 'note') {
    const area = document.querySelector(`.note-area[data-id="${CSS.escape(id)}"]`);
    if (area) { area.focus(); return; }
  }
  if (task.k === 'count') {
    state.counters[id] = countOf(id) >= task.n ? 0 : task.n;
    afterComplete(id);
    scheduleSave();
    render();
    return;
  }
  if (task.k === 'pick') {
    if (state.picks[id]) delete state.picks[id];
    else {
      state.picks[id] = task.o[0];
      addLog(`Выбрано: ${state.picks[id]} — ${task.t}`);
    }
    afterComplete(id);
    scheduleSave();
    render();
    return;
  }
  const now = !state.done[id];
  setDone(id, now);
  if (now) {
    if (task.k === 'time' && timers[id]) delete timers[id];
    afterComplete(id);
  }
  checkUnlocks();
  scheduleSave();
  render();
}

function bumpCount(id, delta) {
  const { task } = findTask(id);
  const max = task.n || 1;
  const next = Math.min(max, Math.max(0, countOf(id) + delta));
  if (next === countOf(id)) return;
  state.counters[id] = next;
  if (next >= max) afterComplete(id);
  scheduleSave();
  render();
}

function pickOption(id, value) {
  state.picks[id] = state.picks[id] === value ? undefined : value;
  if (!state.picks[id]) delete state.picks[id];
  afterComplete(id);
  scheduleSave();
  render();
}

function forceOpen(stageId) {
  if (!state.opened.includes(stageId)) state.opened.push(stageId);
  ui.collapsed.delete(stageId);
  addLog(`Этап открыт вручную: ${STAGES.find((s) => s.id === stageId)?.name || stageId}`);
  toast('Этап открыт', 'ok');
  scheduleSave();
  render();
}

function completeDaily() {
  if (dailyDoneToday()) return;
  const today = dayKey();
  state.daily[today] = true;
  state.streak = state.lastDay === shiftDay(today, -1) ? state.streak + 1 : 1;
  state.lastDay = today;
  state.bestStreak = Math.max(state.bestStreak, state.streak);
  addLog(`Задание дня выполнено: ${dailyTask()}`);
  toast(`Задание дня закрыто. Серия: ${state.streak} дн.`, 'ok');
  scheduleSave();
  render();
}

function rollSurprise() {
  const pool = SURPRISE.filter((t) => !state.log.some((e) => e.text.includes(t)));
  const text = (pool.length ? pool : SURPRISE)[Math.floor(Math.random() * (pool.length || SURPRISE.length))];
  state.surpriseTask = { id: uid('sur'), text };
  toast('Челлендж выдан. Сделай до конца дня', 'ok');
  scheduleSave();
  render();
}

function completeSurprise() {
  if (!state.surpriseTask) return;
  addLog(`Случайный челлендж: ${state.surpriseTask.text}`);
  toast('Челлендж закрыт. Возьми новый!', 'ok');
  state.surpriseTask = null;
  scheduleSave();
  render();
}

function addCustom() {
  const input = $('#customText');
  const text = input.value.trim();
  if (!text) return;
  const stage = $('#customStage').value || 'inbox';
  state.custom.push({ id: uid('c'), text, stage });
  input.value = '';
  addLog(`Новая задача: ${text}`);
  scheduleSave();
  render();
}

function removeCustom(id) {
  state.custom = state.custom.filter((c) => c.id !== id);
  delete state.done[id];
  scheduleSave();
  render();
}

// ------------------------------------------------------------------ timer --

setInterval(() => {
  for (const [id, t] of Object.entries(timers)) {
    if (!t.running) continue;
    const left = leftOf(id);
    const btn = timerButtons.get(id);
    if (btn) btn.textContent = `⏸ ${timerLabel(left)}`;
    if (left <= 0) finishTimer(id);
  }
}, 500);

// ------------------------------------------------------------------- init --

function bind() {
  $('#stages').addEventListener('click', (e) => {
    const el = e.target.closest('[data-act]');
    if (!el) return;
    const { act, id } = el.dataset;
    if (act === 'toggle') toggleTask(id);
    else if (act === 'cinc') bumpCount(id, 1);
    else if (act === 'cdec') bumpCount(id, -1);
    else if (act === 'pip') {
      const n = Number(el.dataset.n);
      bumpCount(id, (countOf(id) === n ? n - 1 : n) - countOf(id));
    }
    else if (act === 'pick') pickOption(id, el.dataset.value);
    else if (act === 'force') forceOpen(id);
    else if (act === 'timer') {
      const t = timers[id];
      const { task } = findTask(id);
      if (t && t.running) stopTimer(id);
      else startTimer(id, t ? t.total : task.min);
    } else if (act === 'timerReset') resetTimer(id);
  });

  $('#stages').addEventListener('input', (e) => {
    const area = e.target.closest('.note-area');
    if (!area) return;
    state.notes[area.dataset.id] = area.value;
    const row = area.closest('.task');
    const id = area.dataset.id;
    const filled = Boolean(area.value.trim());
    if (filled) afterComplete(id);
    row.classList.toggle('done', filled);
    row.querySelector('.tick').classList.toggle('on', filled);
    scheduleSave();
  });

  $('#filters').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    ui.filter = b.dataset.filter;
    for (const btn of $('#filters').children) btn.classList.toggle('active', btn === b);
    ui.ready = false;
    ui.collapsed.clear();
    renderStages();
  });

  $('#dailyDone').onclick = completeDaily;
  $('#btnSurprise').onclick = rollSurprise;
  $('#surpriseDone').onclick = completeSurprise;
  $('#customAdd').onclick = addCustom;
  $('#customText').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') addCustom();
  });
  $('#clearLog').onclick = () => {
    state.log = [];
    scheduleSave();
    renderLog();
  };

  const title = $('#gameTitle');
  title.addEventListener('input', () => {
    state.gameTitle = title.value;
    scheduleSave();
  });

  const ideas = $('#ideas');
  ideas.addEventListener('input', () => {
    state.sessionNote = ideas.value;
    scheduleSave();
  });

  $('#btnExport').onclick = async () => {
    await save();
    const blob = new Blob([JSON.stringify(pickPayload(), null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `plan-${dayKey()}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
    addLog('План выгружен в файл');
    renderLog();
  };

  $('#fileImport').onchange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    let payload;
    try {
      const data = JSON.parse(await file.text());
      payload = data.state && typeof data.state === 'object' ? data.state : data;
    } catch (_) {
      toast('Файл не читается — это не JSON', 'err');
      return;
    }
    if (ui.online) {
      try {
        const res = await fetch('/api/plan/import', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ state: payload }),
        });
        if (res.ok) applyPayload(await res.json());
        else throw new Error('bad');
      } catch (_) {
        applyPayload(payload);
        toast('Сервер не ответил — план применён локально');
      }
    } else {
      applyPayload(payload);
      toast('План применён локально', 'ok');
    }
    ui.ready = false;
    ui.collapsed.clear();
    render();
  };

  $('#btnImport').onclick = () => $('#fileImport').click();
  $('#btnReset').onclick = async () => {
    if (!confirm('Стереть весь прогресс плана? Действие необратимо.')) return;
    for (const key of Object.keys(state)) {
      if (typeof state[key] === 'object' && state[key] !== null && !Array.isArray(state[key])) state[key] = {};
      else if (Array.isArray(state[key])) state[key] = [];
      else if (typeof state[key] === 'string') state[key] = '';
      else state[key] = 0;
    }
    state.surpriseTask = null;
    ui.ready = false;
    ui.collapsed.clear();
    try {
      if (ui.online) await fetch('/api/plan/reset', { method: 'POST' });
    } catch (_) {}
    toast('Прогресс сброшен');
    scheduleSave();
    render();
  };
}

async function init() {
  await load();
  rollStreak();
  bind();
  setupLinks();
  probeStorage();

  const sel = $('#customStage');
  sel.innerHTML = '<option value="inbox">— без этапа —</option>';
  STAGES.forEach((s) => {
    const o = document.createElement('option');
    o.value = s.id;
    o.textContent = `${STAGES.indexOf(s) + 1}. ${s.name}`;
    sel.append(o);
  });

  render();
  setInterval(() => { if (state.lastDay !== dayKey()) { rollStreak(); render(); } }, 60000);
  window.addEventListener('beforeunload', save);
}

init();
