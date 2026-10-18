# Aion repository instructions

Read README.md, docs/requirements/web-release-specification.md and the relevant architecture/contract before behavior changes. Engineering language is English; product content is EN/ES.

`docs/requirements/backend-release-specification.md` v1.0.0 and ADR-0002 are the accepted R2 baseline (2026-10-17). Read them for backend/account/sync/reminder work. R1 remains deployed until verified migration; acceptance is not implementation or release evidence.

## Boundaries

- Aion is free. R1 is local-only; accepted R2 adds optional email-verified accounts, profile sync and explicitly opted-in reminders through a FastAPI/PostgreSQL/worker backend. Preserve complete local guest use. No analytics, advertising, AI, journal, goals or streaks. Follow R2 privacy, authorization, retention, recovery and same-origin `/api/v1` requirements; do not expose features before their release gates pass.
- Product behavior and stable FR/NFR IDs live in repository specifications. Keep implementation, contracts, tests and release evidence aligned.
- Public artifacts must stand alone: no internal tracker IDs/links, private planning notes, local machine paths, personal conversations/preferences or unrelated priorities. Express decisions as product behavior and rationale; keep private execution mappings separately.
- Use synthetic data. No private birth dates/settings/credentials in examples, requests, telemetry or logs. Unsupported storage formats are not silently overwritten.
- Preserve unrelated changes; one active implementation slice/writer. External commit/push/merge/deploy/purchase actions require user authorization.
- Review the actual diff and execute meaningful checks. Never equate engine automation with physical-device/human validation.

## Layout and commands

- `apps/web/src`: React UI, versioned settings, i18n, canvas grid and local PNG export.
- `packages/calendar/src`: pure clock-injected domain and display controller, no browser/storage dependency.
- `tests/fixtures/calendar-clock/v1.json`: golden shared expectations. Do not regenerate to hide regressions.
- `docs/requirements/calendar-clock-contract.md`: exact arithmetic, validation and lifecycle conventions.
- `apps/backend`: Python 3.14.7 / uv 0.11.19 backend, typed identity models, explicit Alembic migrations, health API, opt-in email-code signup/login and a capture-mail worker and opt-in allowlisted Resend adapter. Provider setup/secret injection: `docs/development/resend-setup.md`; real sending is disabled by default. Profile sync is implemented locally under `docs/api/profile-contract.md`; reminders and remaining account lifecycle are not implemented.
- `deploy/compose.yaml` + `deploy/compose.local.yaml`: development-only stack; no cloud deployment. Setup/check commands and secret handling: `docs/development/backend-setup.md`.
- `docs/architecture/database-schema.md` and `.dot`: generated from a fresh migrated disposable PostgreSQL schema with pinned ERAlchemy. Regenerate with `AION_TEST_DATABASE_URL_FILE="$PWD/.local/backend/database-url-host" uv run --project apps/backend --locked python tools/export-database-diagram.py`; `--check` fails on drift. Update these with schema changes; never hand-edit generated files. Keep plans/ownership in `docs/architecture/database.md`. Setup/rendering: `docs/development/database-documentation.md`.
- `docs/api/openapi.json`: generated implemented API. Regenerate with `uv run --locked python ../../tools/export-backend-openapi.py` from `apps/backend`; `--check` detects drift. Authentication contract marks implemented login routes and planned lifecycle operations. See docs/development/account-setup.md; auth stays disabled by default.

Use Node 24.19.0 and pnpm 11.25.0. `pnpm install --frozen-lockfile`; `pnpm dev`; `pnpm check` (fixture/type/unit/build); `pnpm test:e2e` (production browser flows). Install Playwright engines as documented in docs/development/setup.md. Application logic must pass the shared fixture consumer tests; fixture edits also run `pnpm fixtures`.

Visible ticking derives from current clock snapshots, with pause/resume and no per-second grid redraw. Nominal date-only subday totals remain approximate. Keep font dependencies self-hosted and include third-party notices.

Backend checks from the root: create local configuration with `python3 tools/backend-local-config.py`; start disposable PostgreSQL as documented; then `AION_TEST_DATABASE_URL_FILE="$PWD/.local/backend/database-url-host" sh tools/check-backend.sh`. Tests fail without an explicit disposable DB; never point them at production. Tests create/drop only random `aion_test_*` schemas. `python3 tools/smoke-backend.py` exercises outages/restarts in the local foundation stack, preserving its volume. Do not log secrets, enable real sending or claim production security/restore readiness from these local checks. Public auth requires the separate runtime DB grants, cookie/CSRF/abuse controls and R2 release evidence.

Build output is generated `apps/web/dist`, never tracked. `pnpm deploy:dry`, `pnpm deploy:staging`, `pnpm deploy` describe the deployed R1 Wrangler static-assets release. R2 targets Docker Compose on EC2 under ADR-0002; its commands and runbooks must be added and verified before use. Follow docs/operations/web-deployment.md; preserve built artifact identity across promotion. No automated deployment credentials are stored in CI. Actual-device/accessibility/user-walkthrough limits live in docs/testing/web-verification.md.
