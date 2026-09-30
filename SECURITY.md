# Security

emliq handles access to people's email, so security reports are taken seriously.

**Please don't report vulnerabilities in public issues.** Use GitHub's
[private vulnerability reporting](https://github.com/yeshaib/emliq/security/advisories/new)
instead. Include steps to reproduce and the emliq version. You'll get a reply as soon as
possible, and credit in the changelog if you'd like it.

## Design notes

- emliq runs locally and only listens on `127.0.0.1`. It rejects requests for other host names
  (DNS rebinding) and cross-site POSTs.
- Google tokens, the Google client file and any Anthropic key are stored in `~/.emliq` with
  owner-only permissions (on macOS/Linux).
- The AI features get read-only lookups over the local cache and cannot change mail.
- One-click unsubscribe requests refuse to contact private or local network addresses.
