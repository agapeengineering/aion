# Local email-code signup/login verification

Date: 2026-10-17. Evidence applies to the local, uncommitted signup/login working tree following foundation commit `f2de7f9daa624e03951a95bb81bbd065a3f1c7d7`. It is not hosted CI, production security certification, physical-device validation or human UI approval. The public R1 deployment remains unchanged.

## Implemented scope

- Optional EN/ES email-code signup/login; first verification creates the user, subsequent verification reuses normalized identity.
- Eight-digit browser-bound single-use codes, ten-minute expiry, resend cooldown and PostgreSQL attempt/send budgets. Fixed UTC hourly windows are documented in the authentication contract.
- Secure/HttpOnly host-only opaque session cookies, digest-only storage, idle/absolute expiry and Origin plus session-bound CSRF protection for logout.
- Encrypted temporary verification-mail outbox, bounded retry/expiry/purge, injectable test sender and synthetic-only local SMTP capture. No provider adapter or external sending.
- Default guest build has no account controls or API requests. Explicit account preview leaves calendar data local and explains that sync/reminders remain unavailable.
- Schema and phrase ownership documented in the [database map](../architecture/database.md); implemented routes generated into [OpenAPI](../api/openapi.json).

## Checks completed locally

| Check | Result |
| --- | --- |
| Backend locked installation, Ruff lint/format, mypy, generated API drift | Passed |
| Real PostgreSQL backend suite | 37 passed, including 16 authentication tests |
| Authentication security cases | Concurrent consumption; failed attempts commit; replay/expiry/browser binding; resend/IP budgets; normalization/session rotation; CSRF/Origin; two-user nonce isolation; idle and absolute expiry under continued activity; expired mail purge and transient retry |
| Web fixtures/type/unit/build | Passed; 82 unit tests |
| Default guest browser regression | 33 passed in Chromium/Firefox/WebKit; six opt-in auth cases intentionally skipped in this run |
| HTTPS account → request → SMTP capture → verify → reload → logout | Six passed: EN/ES in Chromium/Firefox/WebKit |
| Local container build/start/migration/readiness | Passed for API, worker, database, web/proxy and capture inbox |
| Selected axe checks on EN desktop/ES narrow account dialogs | No violations for selected rules; not a full accessibility certification |
| Visual inspection | Account form desktop/narrow layout and rendered database map inspected |
| Runtime Python advisory audit | No known vulnerabilities reported for pinned runtime set by pip-audit 2.10.1 |
| Prettier and diff whitespace | Passed |

Credential-bearing browser tests retain no traces/screenshots/videos. Only synthetic addresses and codes are used. The account browser tests are added to backend CI, but that hosted run has not happened for these uncommitted changes.

## Remaining gates

Reverification, session-management UI/revoke-other/all operations, account export/deletion, sync/import/conflicts, reminder consent/scheduling, shared phrase extraction, external delivery/webhooks/suppressions and recovery remain separate implementation work. Before public accounts: complete applicable R2 lifecycle/retention/recovery checks, restricted runtime DB roles, trusted proxy client IP handling, provider idempotency/uncertain-send evidence, production secret rotation and infrastructure configuration. Local Mailpit duplicate-message handling is not an exactly-once email guarantee. Human review and physical-device/accessibility checks remain pending.

Reproduce using [local account setup](../development/account-setup.md). Proposed commit: `feat(auth): add local email-code signup and login with data diagrams`.

## Local origin regression fix

The development HTTPS `localhost:18443` alias now redirects to `https://127.0.0.1:18443`, preserving path/query. Previously it served the UI on an origin rejected by the API, which produced the generic service-unavailable message on Send a code. Authentication Origin checks remain exact and cookies remain host-only/Secure. Browser auth tests now start on the alias and verify the complete flow after the redirect; a separate request test checks the redirect contract. Reload an already open localhost tab to enter the canonical origin.
