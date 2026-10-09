// SpriteForge frontend — vanilla ES modules, no build step.

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  catalog: null,
  category: 'prop',
  style: 'pixel16',
  postOverrides: null,   // null = follow style/category defaults
  lastResult: null,
  activeJob: null,
  galleryFilter: null,
};

const EXAMPLES = {
  character: ['рыцарь в стальных доспехах', 'зелёный слизень монстр', 'ниндзя в чёрном костюме',
    'девочка-маг с посохом', 'робот-пёс с антенной', 'ведьма с метлой'],
  background: ['тёмный лес с туманом', ' medievalVillage рынок', 'подземелье с факелами',
    'пустынные дюны на закате', 'космическая станция', 'замок на горе'],
  tileset: ['трава с камнями', 'деревянный пол', 'булыжник мостовой', 'снежная тропа',
    'песчаные дюны', 'мозаичный пол храма'],
  prop: ['деревянный меч', 'бутылка зелёного зелья', 'сундук с золотом', 'факел',
    'стальной щит', 'яблоко', 'ключ от двери', 'ромбик руды'],
  ui: ['сердце здоровья', 'иконка меча', 'кнопка паузы', 'монета', 'звезда рейтинга',
    'иконка инвентаря'],
  sprite_sheet: ['рыцарь идёт вправо', 'маг атакует посохом', 'гоблин бежит', 'самурай с мечом'],
  vfx: ['взрыв огня', 'вспышка молнии', 'зелёное исцеление', 'ледяной шар', 'магический портал'],
};

// ------------------------------------------------------------------ utils --

function toast(msg, kind = '') {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast ' + kind;
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, kind === 'err' ? 6000 : 2600);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function styleById(id) { return state.catalog.styles.find((s) => s.id === id); }
function catById(id) { return state.catalog.categories.find((c) => c.id === id); }

function defaultPostFor(styleId, catId) {
  const cat = catById(catId);
  const style = styleById(styleId);
  const list = [...(cat?.post || [])];
  for (const p of style?.post || []) if (!list.includes(p)) list.push(p);
  return list;
}

// ----------------------------------------------------------------- render --

function renderCategories() {
  const wrap = $('#catTabs');
  wrap.innerHTML = '';
  for (const c of state.catalog.categories) {
    const b = document.createElement('button');
    b.textContent = c.label;
    b.className = c.id === state.category ? 'active' : '';
    b.onclick = () => {
      state.category = c.id;
      state.postOverrides = null;
      renderCategories();
      renderExamples();
      renderPost();
      // Keep the style only if it supports this category, otherwise fall back.
      const st = styleById(state.style);
      if (st && !st.categories.includes(c.id)) {
        const fallback = state.catalog.styles.find((s) => s.categories.includes(c.id));
        if (fallback) { state.style = fallback.id; applyStyleDefaults(); renderStyles(); }
      }
      updatePromptPreview();
    };
    wrap.appendChild(b);
  }
}

function renderExamples() {
  const wrap = $('#promptChips');
  wrap.innerHTML = '';
  for (const ex of EXAMPLES[state.category] || []) {
    const b = document.createElement('button');
    b.textContent = ex;
    b.onclick = () => { $('#prompt').value = ex; updatePromptPreview(); };
    wrap.appendChild(b);
  }
}

function renderStyles() {
  const wrap = $('#styleGrid');
  wrap.innerHTML = '';
  for (const s of state.catalog.styles) {
    const supported = s.categories.includes(state.category);
    const b = document.createElement('button');
    b.className = 'style-card' + (s.id === state.style ? ' active' : '');
    b.style.setProperty('--swatch', s.swatch);
    b.style.opacity = supported ? '1' : '.42';
    const loraNames = s.loras.map((l) => l.label).join(', ');
    b.innerHTML = `<span class="sc-name">${s.label}</span>
      <span class="sc-meta">${s.base_label}</span>
      ${loraNames ? `<span class="sc-meta">${loraNames}</span>` : ''}
      ${s.note ? `<span class="sc-note">${s.note}</span>` : ''}`;
    b.onclick = () => {
      state.style = s.id;
      state.postOverrides = null;
      applyStyleDefaults();
      renderStyles();
      renderPost();
      updatePromptPreview();
    };
    wrap.appendChild(b);
  }
}

function applyStyleDefaults() {
  const s = styleById(state.style);
  if (!s) return;
  $('#base').value = s.base;
  $('#size').value = String(s.size);
  if (s.steps) { $('#steps').value = String(s.steps); $('#stepsOut').textContent = s.steps; }
  if (s.cfg !== null && s.cfg !== undefined) {
    $('#cfg').value = String(s.cfg);
    $('#cfgOut').textContent = Number(s.cfg).toFixed(1);
  }
}

function renderBases() {
  const sel = $('#base');
  sel.innerHTML = '';
  for (const b of state.catalog.bases) {
    const o = document.createElement('option');
    o.value = b.id;
    o.textContent = `${b.label} · ${b.size_gb} ГБ`;
    sel.appendChild(o);
  }
  sel.onchange = () => {
    // LoRAs are arch-specific: drop ones that will not load.
    const base = sel.value;
    const extra = $('#extraLora');
    for (const opt of Array.from(extra.options)) {
      if (opt.dataset.base && opt.dataset.base !== base) opt.hidden = true;
      else opt.hidden = false;
    }
    const b = state.catalog.bases.find((x) => x.id === base);
    if (b) {
      $('#steps').value = String(b.steps);
      $('#stepsOut').textContent = b.steps;
      $('#cfg').value = String(b.cfg);
      $('#cfgOut').textContent = Number(b.cfg).toFixed(1);
    }
  };
}

function renderSizes() {
  const sel = $('#size');
  sel.innerHTML = '';
  for (const v of state.catalog.sizes) {
    const o = document.createElement('option');
    o.value = String(v);
    o.textContent = `${v} × ${v} px`;
    sel.appendChild(o);
  }
}

function renderLoRAs() {
  const sel = $('#extraLora');
  sel.innerHTML = '';
  const none = document.createElement('option');
  none.value = '';
  none.textContent = 'Без доп. LoRA';
  sel.appendChild(none);
  for (const l of state.catalog.loras) {
    const o = document.createElement('option');
    o.value = l.id;
    o.dataset.base = l.base;
    o.textContent = `${l.label} · ${l.size_gb.toFixed(1)} ГБ`;
    sel.appendChild(o);
  }
}

function renderPost() {
  const wrap = $('#postGrid');
  wrap.innerHTML = '';
  const active = state.postOverrides || defaultPostFor(state.style, state.category);
  for (const [key, label] of Object.entries(state.catalog.post_labels)) {
    const lab = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = active.includes(key);
    cb.onchange = () => {
      const cur = new Set(state.postOverrides || defaultPostFor(state.style, state.category));
      cb.checked ? cur.add(key) : cur.delete(key);
      state.postOverrides = Array.from(cur);
    };
    lab.append(cb, document.createTextNode(label));
    wrap.appendChild(lab);
  }
  const sheet = state.postOverrides?.includes('split') || defaultPostFor(state.style, state.category).includes('split');
  $('#sheetNumbers').style.display = sheet ? '' : 'none';
  const px = (state.postOverrides || defaultPostFor(state.style, state.category));
  $('#advancedNumbers').style.display = (px.includes('pixelate') || px.includes('palette')) ? '' : 'none';
}

function updatePromptPreview() {
  const p = $('#prompt').value.trim();
  if (!p) { $('#promptPreview').textContent = ''; return; }
  api('/api/prompt/preview', {
    method: 'POST',
    body: JSON.stringify(collectForm({ prompt: p })),
  }).then((r) => {
    const loraTxt = r.loras.length
      ? ' + LoRA: ' + r.loras.map((l) => l.label).join(', ')
      : '';
    $('#promptPreview').innerHTML =
      `<b>Промпт:</b> <code>${escapeHtml(r.prompt)}</code>${loraTxt}`;
  }).catch(() => {});
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function collectForm(overrides = {}) {
  const post = state.postOverrides || defaultPostFor(state.style, state.category);
  const extraLora = $('#extraLora').value;
  const speed = document.querySelector('input[name="speed"]:checked')?.value || 'normal';
  let steps = parseInt($('#steps').value, 10);
  let cfg = parseFloat($('#cfg').value);
  if (speed === 'fast') { steps = Math.min(steps, 4); cfg = Math.min(cfg, 1.0); }
  if (speed === 'quality') { steps = Math.max(steps, 50); }
  const body = {
    prompt: $('#prompt').value.trim(),
    negative: $('#negative').value.trim(),
    extra_prompt: $('#extraPrompt').value.trim(),
    category: state.category,
    style: state.style,
    base: $('#base').value,
    loras: extraLora ? [extraLora] : [],
    steps,
    cfg,
    size: parseInt($('#size').value, 10),
    batch: parseInt($('#batch').value, 10) || 1,
    scheduler: $('#scheduler').value,
    post,
    pixel_size: parseInt($('#pixelSize').value, 10) || 64,
    palette_colors: parseInt($('#paletteColors').value, 10) || 16,
    sheet_cols: parseInt($('#sheetCols').value, 10) || 4,
    sheet_rows: parseInt($('#sheetRows').value, 10) || 4,
  };
  const seedRaw = $('#seed').value.trim();
  if (seedRaw && !Number.isNaN(parseInt(seedRaw, 10))) body.seed = parseInt(seedRaw, 10);
  return { ...body, ...overrides };
}

// --------------------------------------------------------------- progress --

function setBusy(busy) {
  const btn = $('#generate');
  btn.disabled = busy;
  btn.innerHTML = busy ? '<span class="spin"></span> Генерация…' : 'Сгенерировать';
  $('#statusDot').className = 'dot ' + (busy ? 'busy' : 'ok');
  $('#statusText').textContent = busy ? 'генерация…' : $('#statusText').dataset.base || 'готово';
}

function showProgress(on, text = '') {
  $('#progress').hidden = !on;
  if (on) $('#progressText').textContent = text;
}

function setProgress(pct, text) {
  $('#barFill').style.width = Math.round(pct * 100) + '%';
  if (text) $('#progressText').textContent = text;
}

function watchJob(jobId) {
  state.activeJob = jobId;
  setBusy(true);
  showProgress(true, 'В очереди…');
  const es = new EventSource(`/api/stream/${jobId}`);
  es.onmessage = (ev) => {
    const d = JSON.parse(ev.data);
    if (d.type === 'start') {
      $('#placeholder').hidden = true;
      setProgress(0.02, 'Ожидание…');
    } else if (d.type === 'progress') {
      setProgress(d.progress, `${stageLabel(d.stage)} · ${d.message}`);
    } else if (d.type === 'done') {
      es.close();
      showProgress(false);
      setBusy(false);
      showResult(d.result);
      loadGallery();
      toast('Готово!', 'ok');
    } else if (d.type === 'error') {
      es.close();
      showProgress(false);
      setBusy(false);
      $('#placeholder').hidden = false;
      toast('Ошибка: ' + (d.error || 'неизвестно'), 'err');
    }
  };
  es.onerror = () => {
    es.close();
    showProgress(false);
    setBusy(false);
  };
}

function stageLabel(stage) {
  return ({
    queue: '⏳', load: '⬇', render: '🎨', post: '✨', done: '✅', error: '❌',
  })[stage] || '•';
}

function showResult(result) {
  state.lastResult = result;
  const main = result.images.find((i) => i.kind === 'main') || result.images[0];
  const img = $('#resultImg');
  img.src = main.url + '?t=' + Date.now();
  img.hidden = false;
  $('#placeholder').hidden = true;
  $('#resultActions').hidden = false;

  const tags = [
    `<span class="tag"><b>${escapeHtml(result.style_label || '—')}</b></span>`,
    `<span class="tag">${escapeHtml(result.base_label || '')}</span>`,
    `<span class="tag">${result.size}px · ${result.steps} шагов · CFG ${result.cfg}</span>`,
    result.seed !== null && result.seed !== undefined ? `<span class="tag">сид <b>${result.seed}</b></span>` : '',
    result.elapsed ? `<span class="tag">${result.elapsed} с</span>` : '',
    ...(result.loras || []).map((l) => `<span class="tag">LoRA: ${escapeHtml(l.label)}</span>`),
    ...(result.post || []).map((p) => `<span class="tag">${escapeHtml(state.catalog.post_labels[p] || p)}</span>`),
  ];
  $('#meta').innerHTML = tags.filter(Boolean).join('');

  const fr = $('#frames');
  if (result.frames && result.frames.frames.length) {
    fr.hidden = false;
    const row = $('#framesRow');
    row.innerHTML = '';
    for (const f of result.frames.frames) {
      const im = document.createElement('img');
      im.src = f.url;
      im.title = f.name;
      im.loading = 'lazy';
      row.appendChild(im);
    }
  } else {
    fr.hidden = true;
  }
  wireDownloads();
}

// ------------------------------------------------------------- downloads --

function currentStem() {
  const main = state.lastResult?.images?.find((i) => i.kind === 'main');
  return main ? main.name.replace(/\.png$/, '') : null;
}

function wireDownloads() {
  const stem = currentStem();
  const main = state.lastResult?.images?.find((i) => i.kind === 'main');
  if (!stem || !main) return;
  $('#dlPng').onclick = () => { window.location.href = main.url; };
  const webp = state.lastResult.images.find((i) => i.kind === 'preview');
  $('#dlWebp').onclick = () => webp && (window.location.href = webp.url);
  $('#dlZip').onclick = () => { window.location.href = `/api/zip/${stem}`; };
  $('#dlJson').onclick = () => {
    const blob = new Blob([JSON.stringify(state.lastResult, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = stem + '.json';
    a.click();
    URL.revokeObjectURL(a.href);
  };
}

// --------------------------------------------------------------- gallery --

async function loadGallery() {
  const q = state.galleryFilter ? `?category=${state.galleryFilter}&limit=60` : '?limit=60';
  let data;
  try { data = await api('/api/gallery' + q); } catch (_) { return; }
  const wrap = $('#gallery');
  wrap.innerHTML = '';
  if (!data.items.length) {
    wrap.innerHTML = '<p style="color:var(--muted)">Пока пусто. Сгенерируйте первый ассет!</p>';
    return;
  }
  for (const item of data.items) {
    const prev = item.images.find((i) => i.kind === 'preview') || item.images[0];
    const card = document.createElement('div');
    card.className = 'gcard';
    const swatch = (item.images[0].colors || []).map((c) => `<i style="background:${c}"></i>`).join('');
    card.innerHTML = `
      <div class="gcard-img">
        <img src="${prev.url}?t=${Date.now()}" alt="${escapeHtml(item.user_prompt || '')}" loading="lazy" />
        <div class="gcard-badges">
          <span class="gcard-badge">${escapeHtml(item.style_label || '')}</span>
          ${item.frames ? `<span class="gcard-badge">${item.frames.count} кадров</span>` : ''}
        </div>
        <div class="gcard-swatch">${swatch}</div>
      </div>
      <div class="gcard-body">
        <p title="${escapeHtml(item.user_prompt || '')}">${escapeHtml(item.user_prompt || '(без промпта)')}</p>
        <small>${escapeHtml(item.base_label || '')} · ${item.size}px</small>
      </div>
      <div class="gcard-actions">
        <button class="ghost" data-a="png">PNG</button>
        <button class="ghost" data-a="zip">ZIP</button>
      </div>`;
    const main = item.images.find((i) => i.kind === 'main') || item.images[0];
    const stem = main.name.replace(/\.png$/, '');
    card.onclick = (e) => {
      const act = e.target.dataset?.a;
      if (act === 'png') { e.stopPropagation(); window.location.href = main.url; return; }
      if (act === 'zip') { e.stopPropagation(); window.location.href = `/api/zip/${stem}`; return; }
      state.lastResult = item;
      $('#resultImg').src = main.url;
      $('#resultImg').hidden = false;
      $('#placeholder').hidden = true;
      $('#resultActions').hidden = false;
      $('#meta').innerHTML =
        `<span class="tag"><b>${escapeHtml(item.style_label || '')}</b></span>` +
        `<span class="tag">${escapeHtml(item.base_label || '')}</span>` +
        `<span class="tag">${item.size}px · ${item.steps} шагов</span>`;
      wireDownloads();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };
    wrap.appendChild(card);
  }
}

function renderGalleryFilters() {
  const wrap = $('#galleryFilters');
  wrap.innerHTML = '';
  const all = document.createElement('button');
  all.textContent = 'Всё';
  all.className = state.galleryFilter ? '' : 'active';
  all.onclick = () => { state.galleryFilter = null; renderGalleryFilters(); loadGallery(); };
  wrap.appendChild(all);
  for (const c of state.catalog.categories) {
    const b = document.createElement('button');
    b.textContent = c.label;
    b.className = state.galleryFilter === c.id ? 'active' : '';
    b.onclick = () => { state.galleryFilter = c.id; renderGalleryFilters(); loadGallery(); };
    wrap.appendChild(b);
  }
}

// ------------------------------------------------------------------ boot --

async function boot() {
  state.catalog = await api('/api/catalog');
  renderCategories();
  renderBases();
  renderSizes();
  renderLoRAs();
  renderStyles();
  renderExamples();
  renderPost();
  renderGalleryFilters();
  applyStyleDefaults();
  updatePromptPreview();
  loadGallery();

  // Status line
  try {
    const h = await api('/api/health');
    const e = h.engine;
    $('#statusText').dataset.base =
      e.device === 'cuda' ? `${e.device_name} · ${e.vram_gb.toFixed(1)} ГБ VRAM` : 'CPU';
    $('#statusText').textContent = $('#statusText').dataset.base;
    $('#statusDot').className = 'dot ok';
  } catch (_) {
    $('#statusDot').className = 'dot err';
    $('#statusText').textContent = 'сервер недоступен';
  }

  // Live queue events
  const es = new EventSource('/api/events');
  es.onmessage = (ev) => {
    const d = JSON.parse(ev.data);
    if (d.type === 'queued' && !state.activeJob) {
      setProgress(0.01, `В очереди (позиция ${d.job.status})`);
    }
  };
  es.onerror = () => { es.close(); };

  // Form events
  $('#generate').onclick = async () => {
    const form = collectForm();
    if (!form.prompt && !form.extra_prompt) { toast('Опишите, что нарисовать', 'err'); return; }
    try {
      setBusy(true);
      const job = await api('/api/generate', { method: 'POST', body: JSON.stringify(form) });
      watchJob(job.id);
    } catch (e) {
      setBusy(false);
      toast('Ошибка: ' + e.message, 'err');
    }
  };
  $('#prompt').addEventListener('input', debounce(updatePromptPreview, 450));
  $('#prompt').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) $('#generate').click();
  });
  $('#steps').oninput = (e) => { $('#stepsOut').textContent = e.target.value; };
  $('#cfg').oninput = (e) => { $('#cfgOut').textContent = Number(e.target.value).toFixed(1); };
  $('#reloadGallery').onclick = loadGallery;
}

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

boot().catch((e) => {
  document.body.innerHTML = `<div style="padding:40px;color:#f85149">
    <h2>Не удалось загрузить каталог</h2><p>${escapeHtml(e.message)}</p>
    <p>Проверьте, что бэкенд запущен: <code>python -m uvicorn app.main:app</code></p></div>`;
});
