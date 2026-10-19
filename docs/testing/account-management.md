# Local account management verification

Verified 2026-10-18 against disposable PostgreSQL and local Docker/SMTP capture. This records local implementation, not a public release, live-provider confirmation-email result or completed independent recovery rehearsal.

- Backend: **145 tests passed**, including real PostgreSQL migration, lint/format/types, generated OpenAPI/schema freshness and phrase validation.
- Web: **102 unit tests**, unchanged shared calendar fixtures, TypeScript and production builds passed.
- Guest browser regressions: **33 passed**, Chromium/Firefox/WebKit.
- Auth, account pages, sync, retained reminder functionality and account management: **45 passed**, 15 per engine against separately reset disposable capture data. One deferred-UI test per engine is deliberately skipped in reminder-enabled builds; it is exercised separately below.
- Default account build with reminder enrollment hidden: **3 passed**, one per engine. The local preview also has scheduled sending disabled.
- Sign-in, account-confirmation and retained reminder templates: **36 passed**, EN/ES, 320/800px, all three engines, no remote assets, no axe A/AA findings.
- Inspected synthetic mobile account-section renderings. Browser engine checks do not establish physical-device/VoiceOver behavior or native Gmail/Outlook rendering.

Backend coverage includes fresh/session/browser/owner-bound single-use verification, credential rotation, strict ten-minute sensitive-action expiry, CSRF/Origin/owner checks, two-user session revocation isolation, revoke-all/current-cookie invalidation, export whitelist, deletion cleanup of unowned pending login challenges, dispatch/deletion serialization, independent suppression retention, new signup after deletion with a new identity/empty profile, canceled mail for revoked confirmation sessions, and transaction rollback on an injected deletion fault. Existing login rate/expiry/replay/concurrency and delivery tests also pass.

The EN/ES browser journey covers signed-in sessions, mobile overflow/axe, fresh confirmation mail through SMTP capture, JSON download, verification surviving reload, explicit irreversible deletion acknowledgment, return to login, auth rejection/cache clearing, preservation of a separate guest calendar, and confirmed sign-out everywhere. Sensitive browser traces/screenshots/videos remain disabled; optional visual review captures only synthetic account sections before code entry.

Migration `0006_account_lifecycle` preserves existing accounts and adds session binding/deletion markers. The new multiple-FK schema exposed unordered ERAlchemy edge output; the generator now sorts relationship lines while still reflecting actual migrated SQL, and repeatability/schema tests pass.

Remaining: owner UI walkthrough; actual-device/screen-reader checks; controlled real confirmation delivery if desired; independent off-instance deletion/suppression copying and restore reconciliation; runtime database grants, trusted proxy/IP, EC2/TLS/webhook/backup/monitoring/load/cutover evidence. Scheduled reflections are explicitly deferred and not a blocker for the account/sync launch. No external email or deletion of a real account was performed. No public deployment was performed by these checks.

## Audit follow-up

Targeted regression coverage now verifies queued-upload suppression and refresh pause during terminal actions, draining already-issued writes, stale 401 callbacks, retaining pending edits on failure, completion reasons independent of panel lifetime, old responses after identity switch, session-ended cache boundaries, and one bounded cross-tab CSRF retry with an unchanged operation key/body. Relative verification-lifetime tests cover fast/slow/changing device clocks; EN/ES browser export/deletion runs use clocks skewed one hour in opposite directions. Backend cases assert transactional cancellation/cookie cleanup for logout and single/all-session revocation, serialization with in-flight confirmation dispatch, unchanged original revocation timestamps/cleanup deadline, and relative server expiry. Purpose-specific EN/ES confirmation content also has direct unit coverage.
