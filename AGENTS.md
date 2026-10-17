# Aion repository instructions

Read README.md, docs/requirements/web-release-specification.md and the relevant architecture/contract before behavior changes. Engineering language is English; product content is EN/ES.

## Boundaries

- Aion is free and local-only. No backend, account/authentication, cloud sync, analytics, advertising, AI, journal, goals or streaks.
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

Use Node 24.19.0 and pnpm 11.25.0. `pnpm install --frozen-lockfile`; `pnpm dev`; `pnpm check` (fixture/type/unit/build); `pnpm test:e2e` (production browser flows). Install Playwright engines as documented in docs/development/setup.md. Application logic must pass the shared fixture consumer tests; fixture edits also run `pnpm fixtures`.

Visible ticking derives from current clock snapshots, with pause/resume and no per-second grid redraw. Nominal date-only subday totals remain approximate. Keep font dependencies self-hosted and include third-party notices.

Build output is generated `apps/web/dist`, never tracked. `pnpm deploy:dry`, `pnpm deploy:staging`, `pnpm deploy` use Wrangler static assets, not a data backend. Follow docs/operations/web-deployment.md; preserve built artifact identity across promotion. No automated deployment credentials are stored in CI. Actual-device/accessibility/user-walkthrough limits live in docs/testing/web-verification.md.
