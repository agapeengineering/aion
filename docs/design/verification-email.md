# Verification email

Implemented locally, 2026-10-18. EN/ES passwordless signup/login uses a compact, single-column HTML email and equivalent plain text. This changes presentation only: eight-digit codes, ten-minute expiry, browser binding, delivery consent and rate limits remain unchanged.

The email follows the app's warm paper, ink, terracotta wordmark dot and serif heading. A text wordmark remains visible when images are blocked. The uninterrupted code is selectable, preserves leading zeroes and appears once in each body, never in the subject, preheader, URLs or image requests. The body explains where to enter the code, expiry, safe handling and unsolicited requests. A footer uses the configured Reply-To as the support contact; local SMTP capture uses a synthetic contact. No reminder content, promotional button, auto-login link, remote font, image, script or tracking is included.

HTML uses inline styles, presentation tables, system fonts, explicit EN/ES language/direction and a single heading. It has a bounded fluid width with an Outlook table fallback. No client script or copy button is required. Inbox sender avatars/BIMI are separate from this body and have not been configured.

## Rendering and delivery

`apps/backend/src/aion/mail_content.py` supplies both formats from the same localized copy. The Resend request seals HTML, text, subject, sender, recipient and Reply-To at enqueue; a retry uses that exact request. Previously queued text-only payloads remain unchanged. The local SMTP adapter sends multipart/alternative with text first and HTML second. No schema, API-key, DNS or paid-service change is required.

Generate only synthetic previews from the repository root:

```sh
uv run --project apps/backend --locked python tools/preview-verification-email.py
AION_EMAIL_TESTS=1 pnpm exec playwright test tests/e2e/email-template.spec.ts
```

Outputs: `.local/email-preview/en.html`, `es.html` and matching `.txt` files. The preview code is synthetic and cannot authenticate. The helper never connects to a database or sends email. Keep generated files under ignored `.local/`; actual verification email bodies/codes must not be retained in screenshots or public artifacts.

## Local evidence and limits

- Full backend checks pass: **91 tests**, including localized HTML/plain-text parity, subject/code separation, leading zeroes, escaping, invalid inputs, actual MIME alternatives, existing frozen Resend retries and PostgreSQL-backed authentication/sync tests.
- **12 browser checks** cover EN/ES at 320px and 800px in Chromium, Firefox and WebKit: no horizontal overflow, no automated WCAG A/AA violations and no external requests. Desktop English and narrow Spanish previews were visually inspected.
- **Nine capture-mode authentication browser checks** verify real local SMTP HTML/text delivery and successful EN/ES code login/logout across the three engines. Tests retain no credential-bearing screenshots/traces.
- CI generates synthetic previews and includes their Chromium browser checks alongside account tests.

These browser previews do not establish actual Gmail, Outlook or Apple Mail rendering, forced dark-mode behavior or inbox deliverability. No live Resend test was sent for this change. A fresh allowlisted login request in the rebuilt local Resend preview can be used for a separately requested real-inbox review. Human inbox review, hosted CI and public deployment remain pending.
