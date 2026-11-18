# Architecture overview

Aion serves a bilingual React/TypeScript/Vite calendar and an optional same-origin account API. Guests use the calendar entirely on their device. The original guest-only release is documented in [ADR-0001](decisions/0001-static-web-release.md) and the [R1 specification](../requirements/web-release-specification.md).

The public account release runs FastAPI, PostgreSQL, the mail worker and the static web server on EC2. Cloudflare Tunnel forwards traffic to an Aion-specific origin proxy. [R2 specification](../requirements/backend-release-specification.md) · [Deployment decision](decisions/0002-optional-account-backend.md) · [Release evidence](../releases/web-accounts.md)

## Account services

PostgreSQL holds verified identities, sessions, account profiles, mail jobs and deletion records. The schema and the source-controlled phrase bank have separate owners. [Database diagrams and data ownership](database.md)

`apps/backend/src/aion` implements browser-bound verification codes, secure sessions, revisioned profile writes and account management. The API, migration task and worker use the same non-root image. Local development captures test mail in Mailpit. The production worker uses Resend for transactional email. Scheduled reflections are disabled. [Authentication](../api/authentication-contract.md) · [Account management](../api/account-management-contract.md) · [Mail setup](../development/resend-setup.md)

The OpenAPI document is generated from implemented routes. Local checks and public release evidence are recorded separately. [OpenAPI](../api/openapi.json) · [Local backend setup](../development/backend-setup.md) · [Security choices](backend-security-components.md) · [Local verification](../testing/backend-foundation.md)

## Modules and data flow

- `packages/calendar/src/index.ts`: pure Gregorian date calculation, injected local-clock snapshot, all totals and display pause/visibility transitions.
- `apps/web/src/storage.ts`: versioned local settings, validation and failure/newer-format protection.
- `apps/web/src/App.tsx`: bilingual onboarding/settings, lifecycle clock refresh, statistics, privacy/reset/export dialogs and local tab coordination.
- `apps/web/src/Grid.tsx`: fixed-size canvas overview/detail, non-color cues, accessible summary and exact keyboard-selectable date intervals. Date/grid painting is separate from per-second text refresh.
- `apps/web/src/export.ts`: one coherent live snapshot into a local phone/desktop PNG, honoring hidden remaining figures and omitting birth date.
- `apps/web/src/i18n.ts`: EN/ES content and original phrase bank; self-hosted font assets are bundled at build time.

Guest settings and PNG generation stay in the browser. Account navigation initiates authentication requests. A profile is uploaded only after the user chooses to save or import it. Account caches are scoped to the verified owner and kept separate from guest settings. Storage validation protects unsupported formats and permits session-only use when saving is denied. [Profile contract](../api/profile-contract.md) · [Calendar and clock](../requirements/calendar-clock-contract.md)

## Build and delivery

The pnpm workspace pins the web toolchain and dependencies. GitHub Actions runs web and backend checks with read-only repository access. Production promotion uses the exact reviewed container archive.

The origin proxy routes `/api` and its descendants to FastAPI and all other paths to the web container. API responses are uncached. The web serves a restrictive CSP, EN/ES entry documents and `version.json` with the built source revision. [Deployment runbook](../operations/account-deployment.md) · [Release verification](../releases/web-accounts.md)

## Known limits

Browser-engine tests are not physical iPhone or VoiceOver validation. Those checks and the product-owner walkthrough are recorded explicitly rather than inferred. Native ambient integration, offline-first installation and further export controls remain separate work. Approximate wall-clock totals can jump with clock/zone/DST changes as specified.
