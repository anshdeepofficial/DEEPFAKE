const MENU_ID = 'deepguard-verify-selection';

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_ID,
      title: 'Verify with DeepGuard',
      contexts: ['selection']
    });
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== MENU_ID || !info.selectionText) return;
  await chrome.storage.session.set({
    pendingClaim: String(info.selectionText).trim().slice(0, 2000),
    pendingUrl: tab?.url || '',
    pendingTitle: tab?.title || ''
  });

  try {
    if (chrome.action?.openPopup) {
      await chrome.action.openPopup();
      return;
    }
  } catch (_) {}

  chrome.windows.create({
    url: chrome.runtime.getURL('popup.html'),
    type: 'popup',
    width: 420,
    height: 680
  });
});
