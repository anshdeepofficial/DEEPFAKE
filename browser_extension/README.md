# DeepGuard Verify browser extension

A Manifest V3 extension for Chrome/Edge that sends a user-selected factual claim
(or a bounded section of visible article text) to a DeepGuard server and renders
source-backed evidence.

## Local install

1. Run or deploy DeepGuard.
2. Open `chrome://extensions`.
3. Enable **Developer mode**.
4. Choose **Load unpacked** and select this `browser_extension` folder.
5. Pin **DeepGuard Verify**.
6. Open the popup, enter your DeepGuard server URL, and click **Save**.
7. The extension performs a health check before saving the server.

You can verify content in two ways:

- select text, open the popup, and choose **Verify selected text**;
- right-click selected text and choose **Verify with DeepGuard**.

For full-page mode, DeepGuard reads at most 12,000 characters from the visible
`article` / `main` element (falling back to the body) so it can extract a likely
checkable claim.

## Privacy

Selected-text mode sends only the selected claim, page URL and page title.
Full-page mode additionally sends a bounded section of visible page text.
See `PRIVACY.md` and the server `/privacy` page.

## Production

After deployment, set the extension's server URL to your HTTPS DeepGuard origin.
The backend permits browser-extension origins through its configurable CORS
origin regex. Before publishing in a browser store, replace/update screenshots,
review the store disclosure in `STORE_LISTING.md`, and use your final public
privacy-policy URL.
