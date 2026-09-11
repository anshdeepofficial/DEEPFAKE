/* DeepGuard – frontend */
'use strict';

let maxUploadBytes = 50 * 1024 * 1024;
fetch('/api/capabilities', { cache: 'no-store' })
  .then(r => r.ok ? r.json() : null)
  .then(data => {
    const mb = Number(data?.limits?.max_upload_mb);
    if (Number.isFinite(mb) && mb > 0) maxUploadBytes = mb * 1024 * 1024;
  })
  .catch(() => {});

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`panel-${tab.dataset.tab}`).classList.add('active');
    hideResults();
  });
});

function validateClientFile(file) {
  if (file.size > maxUploadBytes) {
    throw new Error(`File is too large. Server limit is about ${(maxUploadBytes / 1024 / 1024).toFixed(0)} MB.`);
  }
}

function setupUploadZone(type, previewFn) {
  const zone = document.getElementById(`drop-${type}`);
  const input = document.getElementById(`file-${type}`);

  zone.addEventListener('click', () => input.click());
  zone.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') input.click();
  });
  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('drag-over');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (!file) return;
    try {
      validateClientFile(file);
      input.files = e.dataTransfer.files;
      previewFn(file);
    } catch (error) {
      showError(error.message);
    }
  });
  input.addEventListener('change', () => {
    const file = input.files[0];
    if (!file) return;
    try {
      validateClientFile(file);
      previewFn(file);
    } catch (error) {
      input.value = '';
      showError(error.message);
    }
  });
}

function showPreview(type, file) {
  const zone = document.getElementById(`drop-${type}`);
  const wrap = document.getElementById(`preview-${type}-wrap`);
  const el = document.getElementById(`preview-${type}`);

  if (el.dataset.objectUrl) URL.revokeObjectURL(el.dataset.objectUrl);
  const objectUrl = URL.createObjectURL(file);
  el.dataset.objectUrl = objectUrl;
  el.src = objectUrl;
  zone.style.display = 'none';
  wrap.classList.remove('hidden');
}

setupUploadZone('image', f => showPreview('image', f));
setupUploadZone('video', f => showPreview('video', f));
setupUploadZone('audio', f => showPreview('audio', f));

document.querySelectorAll('.btn-clear').forEach(btn => {
  btn.addEventListener('click', () => {
    const type = btn.dataset.target;
    const zone = document.getElementById(`drop-${type}`);
    const wrap = document.getElementById(`preview-${type}-wrap`);
    const input = document.getElementById(`file-${type}`);
    const el = document.getElementById(`preview-${type}`);
    if (el.dataset.objectUrl) {
      URL.revokeObjectURL(el.dataset.objectUrl);
      delete el.dataset.objectUrl;
    }
    el.removeAttribute('src');
    if (typeof el.load === 'function') el.load();
    input.value = '';
    wrap.classList.add('hidden');
    zone.style.display = '';
    hideResults();
  });
});

const textInput = document.getElementById('text-input');
const charCount = document.getElementById('char-count');
const btnClearTx = document.getElementById('btn-clear-text');

textInput.addEventListener('input', () => {
  const n = textInput.value.length;
  charCount.textContent = `${n.toLocaleString()} character${n !== 1 ? 's' : ''}`;
});
btnClearTx.addEventListener('click', () => {
  textInput.value = '';
  charCount.textContent = '0 characters';
  hideResults();
});

document.getElementById('btn-image').addEventListener('click', () => analyseFile('image'));
document.getElementById('btn-video').addEventListener('click', () => analyseFile('video'));
document.getElementById('btn-audio').addEventListener('click', () => analyseFile('audio'));
document.getElementById('btn-text').addEventListener('click', () => {
  const text = textInput.value.trim();
  if (!text) return showError('Please enter some text first.');
  sendText('/api/detect/text', text);
});

function analyseFile(type) {
  const file = document.getElementById(`file-${type}`).files[0];
  if (!file) return showError(`Please select ${type === 'image' ? 'an image' : `a ${type} file`} first.`);
  try {
    validateClientFile(file);
    uploadFile(`/api/detect/${type}`, file);
  } catch (error) {
    showError(error.message);
  }
}

async function fetchWithTimeout(url, options, timeoutMs = 150000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function uploadFile(endpoint, file) {
  showSpinner(true);
  hideResults();
  try {
    const form = new FormData();
    form.append('file', file);
    const resp = await fetchWithTimeout(endpoint, { method: 'POST', body: form });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    renderResult(await resp.json());
  } catch (error) {
    showError(error.name === 'AbortError' ? 'Analysis took too long and the browser request was cancelled.' : error.message);
  } finally {
    showSpinner(false);
  }
}

async function sendText(endpoint, text) {
  showSpinner(true);
  hideResults();
  try {
    const resp = await fetchWithTimeout(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    }, 60000);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    renderResult(await resp.json());
  } catch (error) {
    showError(error.name === 'AbortError' ? 'Request timed out.' : error.message);
  } finally {
    showSpinner(false);
  }
}

function renderResult(data) {
  const area = document.getElementById('results-area');
  const verdict = document.getElementById('result-verdict');
  const confBar = document.getElementById('conf-bar');
  const confPct = document.getElementById('conf-pct');
  const flagsList = document.getElementById('result-flags');
  const detailGrid = document.getElementById('result-details');

  const label = data.label || 'UNKNOWN';
  const conf = parseFloat(data.confidence) || 0;
  verdict.className = `verdict ${label}`;
  const icons = {
    FAKE: '⛔', SUSPICIOUS: '⚠️', REAL: '✅', ERROR: '❌',
    INSUFFICIENT_DATA: 'ℹ️', LIMIT_EXCEEDED: 'ℹ️'
  };
  verdict.textContent = `${icons[label] || '?'} ${label}`;

  confBar.className = `conf-bar ${label}`;
  confPct.textContent = data.calibrated === false
    ? `${conf.toFixed(1)} % heuristic confidence`
    : `${conf.toFixed(1)} %`;
  setTimeout(() => { confBar.style.width = `${Math.min(conf, 100)}%`; }, 50);

  flagsList.replaceChildren();
  const messages = [
    ...(data.flags || []),
    ...(data.limitations || []).map(x => `Limitation: ${x}`)
  ];
  messages.forEach(flag => {
    const el = document.createElement('span');
    el.className = 'flag-item';
    el.textContent = `⚠ ${flag}`;
    flagsList.appendChild(el);
  });

  detailGrid.replaceChildren();
  const details = { ...(data.details || {}) };
  if (data.method) details.method = data.method;
  if (data.meta?.format) details.format = data.meta.format;
  if (data.meta?.analyzed_seconds) details.analyzed_seconds = data.meta.analyzed_seconds;
  if (data.meta?.estimated_duration_seconds) details.duration_seconds = data.meta.estimated_duration_seconds;
  Object.entries(details).forEach(([key, value]) => {
    const card = document.createElement('div');
    card.className = 'detail-card';
    const lbl = document.createElement('div');
    lbl.className = 'detail-label';
    lbl.textContent = key.replace(/_/g, ' ');
    const val = document.createElement('div');
    val.className = 'detail-value';
    val.textContent = typeof value === 'number' ? value.toFixed(4) : String(value);
    card.append(lbl, val);
    detailGrid.appendChild(card);
  });

  area.classList.remove('hidden');
  area.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function showSpinner(show) {
  document.getElementById('spinner').classList.toggle('hidden', !show);
}
function hideResults() {
  document.getElementById('results-area').classList.add('hidden');
}
function showError(msg) {
  renderResult({ label: 'ERROR', confidence: 0, score: 0, flags: [msg], details: {} });
}
