# Changelog

## 0.9.2 — 2026-10-02
- Credits App Enablement (appenablement.com), which offers emliq for free, in the app, README and guide

## 0.9.1 — 2026-10-02
- Bulk Unsubscribe now also lists senders that only offer an unsubscribe web page, or whose unsubscribe link is broken, in the Trash / Spam / Leave choice (with an Unsubscribe page link where there is one)
- The Unsubscribe button's count only includes senders emliq can unsubscribe from automatically

## 0.9.0 — 2026-10-02
- Update check: when a newer emliq is released, the version badge shows Update available, with what's new and the command to update (with a Copy button)
- Settings → Updates: turn the once-a-day check on or off, or Check now; emliq never updates itself and sends nothing about you

## 0.8.0 — 2026-10-01
- Bulk Unsubscribe handles senders with no unsubscribe option: choose Trash (default), Spam or Leave for each one, or set all at once
- New Spam action in the bulk bar, the same as Gmail's "Report spam"
- Errors during bulk unsubscribe stay visible and keep your selection

## 0.7.1 — 2026-09-30
- New screenshots and feature list in the README
- Neutral wording for the suggested AI question about unsubscribe suggestions

## 0.7.0 — 2026-09-30
- Help: a built-in guide to every feature, with contents, search and links to any section; press ? anywhere to open it
- “?” links next to Gmail sign-in, AI settings, AI categories and Ask AI open the matching part of the guide

## 0.6.1 — 2026-09-30
- Collapsing Insights leaves a slim rail on the right (or a small tab on smaller windows) to reopen it; rail icons jump straight to a tile
- The page uses the full window width

## 0.6.0 — 2026-09-30
- Insights panel on the right holds the dashboard tiles; collapse it with » or the Insights button, and on smaller windows it slides in as a drawer
- The sender table adapts to its own width: columns step aside instead of being cut off, and it fits on phones
- The version badge slides away while you scroll down so it never covers row buttons

## 0.5.5 — 2026-09-30
- Hide dashboard tiles (✕ on each tile) and left-menu groupings you don't use; Customize dashboard brings them back

## 0.5.4 — 2026-09-30
- The left menu scrolls on short windows, so every item and Sign out stay reachable

## 0.5.3 — 2026-09-30
- Every row has a checkbox again, alongside clicking the sender's circle; both support Shift-click ranges

## 0.5.2 — 2026-09-30
- Sync progress shows every step with real numbers (for example "Step 2 of 3 · 6,000 of ~12,434") instead of just spinning

## 0.5.1 — 2026-09-30
- Email content is never stored: emliq refuses anything but headers, and tests check it
- Settings shows exactly what's stored per email

## 0.5.0 — 2026-09-29
- Ask AI: ask questions about your mailbox in plain language; answers come with buttons that open the senders it found, preselected
- Search your cached mail by sender or subject from the bar at the top
- Sign in to and out of Gmail from emliq (Settings or the sidebar); switching accounts never mixes their mail
- The version badge moved to the bottom-right corner
- Open source under the Apache 2.0 license, with install instructions for macOS, Windows and Linux
- `emliq demo`: try emliq with a made-up mailbox, no Google account needed
- Windows support, and tests that run on Windows, macOS and Linux

## 0.4.0 — 2026-09-29
- AI categories list their senders first; click a sender to see its emails, or open them all for bulk cleanup
- Faster selection: click a sender's circle to select, then click any row to add it; Shift-click selects a range
- Every confirmation is an in-app popup instead of a browser dialog
- Version badge with this “What's new” history

## 0.3.0 — 2026-09-29
- Local AI categorizing with Ollama: pick or download a model in Settings, free and fully on this Mac
- Settings page: choose Claude or a local model, save and test an Anthropic API key
- Floating progress panel for syncing and categorizing, with Stop and Resume
- New logo; clicking it returns to the dashboard
- Unread is the default view

## 0.2.0 — 2026-09-29
- Dashboard with summary tiles and charts (top senders, mail by year, Gmail and AI categories)
- Select multiple bundles and mark read, archive, unsubscribe, block or trash them together
- Lists are paged: 15, 30 or 50 rows per page
- AI categories with Claude: category and keep/archive/unsubscribe suggestion per sender
- Activity page: everything emliq did, storage freed, mailbox over time
- “Load all unread” and sync progress bar; runs in Docker

## 0.1.0 — 2026-09-29
- First version: sync Gmail headers, group mail into bundles, archive, mark read, trash, unsubscribe and block
