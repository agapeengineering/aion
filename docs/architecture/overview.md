# Architecture overview

Aion's deployed R1 web release is a client-only React/TypeScript/Vite application. See [ADR-0001](decisions/0001-static-web-release.md), the [R1 specification](../requirements/web-release-specification.md) and [calendar/clock contract](../requirements/calendar-clock-contract.md).

The [accepted R2 specification](../requirements/backend-release-specification.md) and [ADR-0002](decisions/0002-optional-account-backend.md) define the next implementation: optional accounts, sync and email through a containerized FastAPI/PostgreSQL/worker backend. The module and deployment descriptions below remain the actual R1 state until implementation evidence replaces them.

## Local R2 foundation

See the [database diagrams and data ownership map](database.md) for actual foundation tables, implemented sync and planned reminder entities and the source-controlled phrase bank.

`apps/backend/src/aion` now provides validated explicit database configuration, typed initial identity models, migration-aware liveness/readiness endpoints and a probe/heartbeat worker. Explicit Alembic migration `0001_identity` creates users, sessions, email challenges and persistent abuse-counter tables; table existence does not implement auth. The opt-in signup/login slice adds identity/session routes, browser-bound codes and sealed verification mail in migration `0002_verification`. The worker defaults to local capture and supports [controlled allowlisted Resend delivery](../development/resend-setup.md); Migration `0004_profiles` adds owned, revisioned profile reads/writes/reset and idempotency metadata; reminders and other account lifecycle routes remain planned. API/worker/migrate share one non-root image; local Compose adds private Postgres and a static web/proxy container with explicit loopback ports only in its local override.

[Backend setup](../development/backend-setup.md) supplies commands and development limits. [Generated OpenAPI](../api/openapi.json) describes only implemented routes; [authentication contract](../api/authentication-contract.md), [security choices](backend-security-components.md) and the [account study](../design/account-flow.html) document the account slice. See [local account setup](../development/account-setup.md) and [signup/login evidence](../testing/email-code-auth.md). [Foundation verification](../testing/backend-foundation.md) distinguishes actual local checks from pending hosted CI, user review, authentication and production recovery. The live R1 deployment remains unchanged.

## Modules and data flow

- `packages/calendar/src/index.ts`: pure Gregorian date calculation, injected local-clock snapshot, all totals and display pause/visibility transitions.
- `apps/web/src/storage.ts`: versioned local settings, validation and failure/newer-format protection.
- `apps/web/src/App.tsx`: bilingual onboarding/settings, lifecycle clock refresh, statistics, privacy/reset/export dialogs and local tab coordination.
- `apps/web/src/Grid.tsx`: fixed-size canvas overview/detail, non-color cues, accessible summary and exact keyboard-selectable date intervals. Date/grid painting is separate from per-second text refresh.
- `apps/web/src/export.ts`: one coherent live snapshot into a local phone/desktop PNG, honoring hidden remaining figures and omitting birth date.
- `apps/web/src/i18n.ts`: EN/ES content and original phrase bank; self-hosted font assets are bundled at build time.

In the deployed R1 build there is no backend/API/authentication/cloud sync, queue, analytics or server-side personal data. The separately enabled local account preview stores verified email and sessions; calendar data stays local until explicit account saving; account caches are separate from guest settings. See the [profile contract](../api/profile-contract.md). The only initial requests are static assets. Settings and malformed/unknown storage are untrusted; validate before use, protect unsupported versions and use session-only fallback when saving is denied. Reset removes only the app-owned setting key; downloaded images remain user-controlled.

## Build and delivery

One pnpm product workspace; native clients are added only when scheduled and retain separate artifacts. Pinned Node/pnpm/dependencies and the lockfile make setup reproducible. GitHub Actions runs fixture/type/unit/build/browser checks with read-only repository access. Publication is a separate authorized Wrangler action; CI has no deployment credentials.

Cloudflare serves the static build with HTTPS, a restrictive CSP, no-referrer and nosniff headers. English and Spanish entry documents have appropriate language/title metadata. `version.json` identifies source revision/build cleanliness. Stage and promote the same built directory; see the [operations runbook](../operations/web-deployment.md) and [verification record](../testing/web-verification.md).

## Known limits

Browser-engine tests are not physical iPhone or VoiceOver validation. Those checks and the product-owner walkthrough are recorded explicitly rather than inferred. Native ambient integration, offline-first installation and further export controls remain separate work. Approximate wall-clock totals can jump with clock/zone/DST changes as specified.
