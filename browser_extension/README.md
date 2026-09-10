# DeepGuard Verify browser extension

Manifest V3 extension for Chromium browsers. It reads only the active tab after
the user clicks the extension, then sends either the selected sentence or a
bounded slice of visible page text to your DeepGuard `/api/verify/claim` endpoint.

## Load locally

1. Start DeepGuard on `http://localhost:8000` or deploy it.
2. Open `chrome://extensions` (or the equivalent extensions page in Edge/Brave).
3. Enable **Developer mode**.
4. Choose **Load unpacked** and select the `browser_extension` folder.
5. Pin **DeepGuard Verify**.
6. On an article, select a factual sentence and click **Verify selected text**.

For an HTTPS production server, paste the server URL in the popup and press
**Save**. Chrome will ask for permission only for that configured server origin.
The extension uses `activeTab` + `scripting`, so it does not need permanent read
access to every page just to inspect the current tab.
