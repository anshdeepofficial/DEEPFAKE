 'use strict';

const DEFAULT_API = 'http://localhost:8000';
const apiInput = document.getElementById('api-url');
const serverState = document.getElementById('server-state');
const statusBox = document.getElementById('status');
const resultBox = document.getElementById('result');

function normalizeApiUrl(value) {
  const raw = (value || DEFAULT_API).trim();
  const url = new URL(raw);
  if (!['http:', 'https:'].includes(url.protocol)) {
    throw new Error('Use an http:// or https:// server URL.');
  }
  if (url.username || url.password) {
    throw new Error('Do not put credentials in the server URL.');
  }
  return url.origin;
}

async function loadSettings() {
  const data = await chrome.storage.sync.get({ apiUrl: DEFAULT_API });
  apiInput.value = data.apiUrl;
}

async function requestBackendPermission(apiUrl) {
  const url = new URL(apiUrl);
  return chrome.permissions.request({ origins: [`${url.origin}/*`] });
}

async function healthCheck(apiUrl) {
  const response = await fetch(`${apiUrl}/api/health`, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Server health check failed (HTTP ${response.status}).`);
  const data = await response.json();
  if (data.status !== 'ok') throw new Error('This does not look like a healthy DeepGuard server.');
  return data;
}

document.getElementById('save-url').addEventListener('click', async () => {
  serverState.textContent = 'Checking server…';
  try {
    const apiUrl = normalizeApiUrl(apiInput.value);
    const granted = await requestBackendPermission(apiUrl);
    if (!granted) throw new Error('Permission for this server was not granted.');
    const health = await healthCheck(apiUrl);
    await chrome.storage.sync.set({ apiUrl });
    apiInput.value = apiUrl;
    serverState.textContent = `Connected · DeepGuard ${health.version || ''}`.trim();
  } catch (error) {
    serverState.textContent = error.message || 'Could not connect to the server.';
  }
});

async function capturePage() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error('No active webpage found.');
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => {
      const article = document.querySelector('article, main, [role="main"]');
      const pageText = (article?.innerText || document.body?.innerText || '')
        .replace(/\s+/g, ' ').trim().slice(0, 12000);
      return {
        selectedText: String(window.getSelection()?.toString() || '').trim().slice(0, 2000),
        pageTitle: document.title.slice(0, 500),
        pageUrl: location.href,
        pageText
      };
    }
  });
  return result;
}

async function getApiUrl() {
  const data = await chrome.storage.sync.get({ apiUrl: DEFAULT_API });
  return normalizeApiUrl(data.apiUrl);
}

function setStatus(text) {
  statusBox.textContent = text;
  statusBox.classList.toggle('hidden', !text);
}

async function verifyPayload(payload) {
  resultBox.classList.add('hidden');
  setStatus('Searching independent evidence…');
  try {
    const apiUrl = await getApiUrl();
    const response = await fetch(`${apiUrl}/api/verify/claim`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Server returned HTTP ${response.status}`);
    render(data);
    setStatus('');
  } catch (error) {
    setStatus(error.message || 'Verification failed.');
  }
}

async function verify(useSelection) {
  try {
    const page = await capturePage();
    if (useSelection && !page.selectedText) {
      throw new Error('Select the sentence or claim on the page first.');
    }
    await verifyPayload({
      claim: useSelection ? page.selectedText : null,
      context_url: page.pageUrl,
      page_title: page.pageTitle,
      page_text: useSelection ? null : page.pageText
    });
  } catch (error) {
    setStatus(error.message || 'Could not read this page.');
  }
}

document.getElementById('verify-selection').addEventListener('click', () => verify(true));
document.getElementById('verify-page').addEventListener('click', () => verify(false));

document.getElementById('open-privacy').addEventListener('click', async () => {
  const apiUrl = await getApiUrl();
  chrome.tabs.create({ url: `${apiUrl}/privacy` });
});
document.getElementById('open-site').addEventListener('click', async () => {
  const apiUrl = await getApiUrl();
  chrome.tabs.create({ url: apiUrl });
});

function render(data) {
  document.getElementById('verdict').textContent = data.verdict || 'INCONCLUSIVE';
  document.getElementById('confidence').textContent =
    Number.isFinite(Number(data.confidence)) ? `Evidence strength ${Number(data.confidence).toFixed(1)}%` : '';
  document.getElementById('claim').textContent = data.claim || data.message || 'No claim extracted.';
  document.getElementById('counts').textContent =
    `${data.supporting_sources || 0} supporting • ${data.contradicting_sources || 0} contradicting • ${data.independent_domains || 0} domains`;

  const meta = document.getElementById('meta');
  meta.replaceChildren();
  const metaValues = [
    data.claim_kind ? `type: ${String(data.claim_kind).replaceAll('_', ' ')}` : '',
    ...(data.providers_used || []).map(x => `provider: ${String(x).replaceAll('_', ' ')}`)
  ];
  for (const value of metaValues.filter(Boolean)) {
    const chip = document.createElement('span');
    chip.textContent = value;
    meta.appendChild(chip);
  }

  const questions = document.getElementById('questions');
  questions.replaceChildren();
  for (const item of data.verification_questions || []) {
    const line = document.createElement('div');
    line.textContent = `• ${item}`;
    questions.appendChild(line);
  }

  const evidence = document.getElementById('evidence');
  evidence.replaceChildren();
  for (const item of data.evidence || []) {
    const link = document.createElement('a');
    link.href = item.url;
    link.target = '_blank';
    link.rel = 'noreferrer';
    const title = document.createElement('strong');
    title.textContent = item.title || item.domain;
    const details = document.createElement('span');
    details.textContent = `${item.stance} • ${item.source_type || 'web'} • ${item.domain}`;
    link.append(title, details);
    evidence.appendChild(link);
  }
  if (!(data.evidence || []).length) {
    evidence.textContent = data.message || 'No sufficiently relevant evidence found.';
  }

  document.getElementById('warnings').textContent =
    [...(data.warnings || []), data.disclaimer || ''].filter(Boolean).join(' ');
  resultBox.classList.remove('hidden');
}

async function consumePendingClaim() {
  const pending = await chrome.storage.session.get({
    pendingClaim: '',
    pendingUrl: '',
    pendingTitle: ''
  });
  if (!pending.pendingClaim) return;
  await chrome.storage.session.remove(['pendingClaim', 'pendingUrl', 'pendingTitle']);
  await verifyPayload({
    claim: pending.pendingClaim,
    context_url: pending.pendingUrl || null,
    page_title: pending.pendingTitle || null,
    page_text: null
  });
}

loadSettings().then(consumePendingClaim);
