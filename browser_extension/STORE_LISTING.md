# Chrome Web Store listing draft

## Name
DeepGuard Verify

## Short description
Verify selected claims with source-backed evidence from your DeepGuard server.

## Suggested category
Productivity / News & weather (choose the closest currently available store category)

## Core purpose
DeepGuard Verify lets a user deliberately select a factual statement on a web
page and send it to a configured DeepGuard server. The server searches public
evidence and returns supporting, contradicting and inconclusive sources.

## Permissions justification
- `activeTab`: temporary access to the current tab after the user invokes the extension.
- `scripting`: read selected text or bounded visible article text after user action.
- `storage`: remember the configured DeepGuard server and temporary context-menu claim.
- `contextMenus`: add “Verify with DeepGuard” for selected text.
- optional host permissions: connect only to the DeepGuard server origin the user chooses.

## Data disclosure
The extension sends user-selected claim text, page URL and title to the configured
DeepGuard server. Full-page verification additionally sends bounded visible page
text. No analytics or advertising SDK is included in the repository version.

## Before publishing
- Deploy DeepGuard at a stable HTTPS URL.
- Host the privacy policy publicly at `/privacy`.
- Add final store screenshots and promotional images.
- Test unpacked extension against the production server.
- Complete the store privacy/data-use questionnaire consistently with this file.
