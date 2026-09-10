'use strict';

const DEFAULT_API = 'http://localhost:8000';
const apiInput = document.getElementById('api-url');
const serverState = document.getElementById('server-state');
const statusBox = document.getElementById('status');
const resultBox = document.getElementById('result');

function normalizeApiUrl(value) {
  return (value || DEFAULT_API).trim().replace(/\/+$/, '');
}

async function loadSettings() {
  const data = await chrome.storage.sync.get({ apiUrl: DEFAULT_API });
  apiInput.value = data.apiUrl;
}

async function requestBackendPermission(apiUrl) {
  const url = new URL(apiUrl);
  if (url.protocol !== 'https:') return true;
  return chrome.permissions.request({ origins: [`${url.origin}/*`] });
}

document.getElementById('save-url').addEventListener('click', async () => {
  try {
    const apiUrl = normalizeApiUrl(apiInput.value);
    const url = new URL(apiUrl);
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Use an http:// or https:// server URL.');
    const granted = await requestBackendPermission(apiUrl);
    if (!granted) throw new Error('Permission for this server was not granted.');
    await chrome.storage.sync.set({ apiUrl });
    apiInput.value = apiUrl;
    serverState.textContent = 'Server saved.';
  } catch (error) {
    serverState.textContent = error.message;
  }
});

async function capturePage() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error('No active webpage found.');
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => ({
      selectedText: String(window.getSelection()?.toString() || '').trim().slice(0, 2000),
      pageTitle: document.title.slice(0, 500),
      pageUrl: location.href,
      pageText: (document.body?.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 25000),
    }),
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

async function verify(useSelection) {
  resultBox.classList.add('hidden');
  setStatus('Collecting the current page and searching for independent evidence…');
  try {
    const page = await capturePage();
    if (useSelection && !page.selectedText) {
      throw new Error('Select the sentence or claim on the page first.');
    }
    const apiUrl = await getApiUrl();
    const response = await fetch(`${apiUrl}/api/verify/claim`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        claim: useSelection ? page.selectedText : null,
        context_url: page.pageUrl,
        page_title: page.pageTitle,
        page_text: page.pageText,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Server returned HTTP ${response.status}`);
    render(data);
    setStatus('');
  } catch (error) {
    setStatus(error.message || 'Verification failed.');
  }
}

document.getElementById('verify-selection').addEventListener('click', () => verify(true));
document.getElementById('verify-page').addEventListener('click', () => verify(false));

function render(data) {
  document.getElementById('verdict').textContent = data.verdict || 'INCONCLUSIVE';
  document.getElementById('confidence').textContent = data.confidence ? `Evidence confidence ${data.confidence}%` : '';
  document.getElementById('claim').textContent = data.claim || data.message || 'No claim extracted.';
  document.getElementById('counts').textContent = `${data.supporting_sources || 0} supporting • ${data.contradicting_sources || 0} contradicting • ${data.independent_domains || 0} domains`;

  const evidence = document.getElementById('evidence');
  evidence.replaceChildren();
  for (const item of data.evidence || []) {
    const link = document.createElement('a');
    link.href = item.url;
    link.target = '_blank';
    link.rel = 'noreferrer';
    const title = document.createElement('strong');
    title.textContent = item.title || item.domain;
    const meta = document.createElement('span');
    meta.textContent = `${item.stance} • ${item.domain}`;
    link.append(title, meta);
    evidence.appendChild(link);
  }
  if (!(data.evidence || []).length) {
    evidence.textContent = data.message || 'No sufficiently relevant evidence found.';
  }
  resultBox.classList.remove('hidden');
}

loadSettings();
