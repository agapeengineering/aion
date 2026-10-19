# Local email reminder verification

Verified 2026-10-18 against local Docker/PostgreSQL and synthetic SMTP capture. This is local implementation evidence, not a public deployment, real-reminder inbox result or account-lifecycle release approval.

- `sh tools/check-backend.sh` with explicit disposable database: **128 passed**, lint/format/types, phrase validation, OpenAPI and generated ERAlchemy schema drift checks passed.
- `pnpm check`: fixture corruption checks, TypeScript, **91 unit tests** and production build passed.
- Guest browser regressions: **33 passed**, Chromium/Firefox/WebKit.
- Auth, account pages, profile sync and reminders together: **33 passed**, all three engines. Reminder cases include EN/ES, saved-profile gating, off-by-default consent, Sunday 09:00, missing-content gating, narrow layout/axe, persistence, offline behavior, captured delivery and GET-confirmation/POST unsubscribe.
- Verification + reminder email layouts: **24 passed**, both languages, 320/800px, all three engines, no remote assets and no axe A/AA findings. Inspected the synthetic narrow English reminder rendering. These engines do not establish native Gmail/Outlook rendering fidelity.
- Runtime dependency advisory audit: no known vulnerabilities found in the locked runtime dependency set.

Backend scenarios cover owner/CSRF/Origin and revision checks; no retrospective send; unique owner/local day; parallel schedulers/workers; crash lease recovery with frozen retry body/key; bounded retries/ambiguous acceptance; expiry payload erasure while disabled; stale profile/consent cancellation and in-flight stop barrier; DST gap/fold; lost unsubscribe key; hide-remaining/beyond-horizon snapshots; publication anchor/approval/missing-slot/content-version handling; signed raw-body verification, tampering/replay/duplicate/out-of-order events and other-product isolation; independent sticky suppression blocking reminders and verification mail.

The weekly attributed catalogue intentionally has zero published slots until editorial validation completes. Existing original calendar content remains available. Captured tests do not import research passages or send externally. Live reminder sending remains disabled until the deployed webhook and secret are configured and a controlled real send/unsubscribe test is authorized. Account deletion/export/session management and restore reconciliation remain separate incomplete release work.
