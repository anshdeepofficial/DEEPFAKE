# DeepGuard Verify extension privacy disclosure

DeepGuard Verify does not continuously monitor browsing.

It accesses the active page only after a user action:

- **Verify selected text:** sends the selected claim, current page URL and title
  to the configured DeepGuard server.
- **Find a claim on this page:** also sends up to 12,000 characters of visible
  article/main text so the server can extract a likely claim.
- **Verify with DeepGuard** context menu: stores the selected text temporarily in
  extension session storage and opens the verifier popup.

The configured DeepGuard server URL is stored in browser sync storage. Temporary
context-menu claim data uses session storage and is deleted after use.

The extension does not sell data, display ads, or include analytics in this
repository version. The server operator's privacy policy also applies because
verification requests are sent to that server.
