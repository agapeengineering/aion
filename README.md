# Aion by Agape

**[Open Aion →](https://aion.agape.engineering)** · [Español](https://aion.agape.engineering/es)

A quiet life-in-weeks calendar. See the weeks behind you, the present week and the time ahead under a lifespan you choose.

Use Aion for free in English or Spanish. As a guest, your calendar and PNG exports stay on your device. Sign in with an emailed code to save a calendar and sync it across devices. You choose whether to import an existing guest calendar. Aion is open source and has no advertising or product analytics.

## Web features

- Two inputs: date of birth and chosen lifespan, with an editable 90-year default.
- Lived/current/future week grid, accessible text summary and exact interval exploration.
- Years, months, weeks, days, hours, minutes and seconds; weeks is the primary view.
- Ticking approximate countdown with pause/resume and optional hidden remaining figures.
- Local save/edit/reset, clear storage-error states and local cross-tab updates.
- Original English/Spanish phrases and local phone/desktop PNG wallpaper export.
- Optional email-verified accounts, cross-device profile sync, session management, account export and permanent deletion.
- Self-hosted fonts, a privacy explanation, source/license and public feedback route.

A lifespan is a visualization assumption. Each new guest browser starts with an empty calendar. To use a saved account calendar on another device, sign in with the same email address. Apply exported PNGs manually as wallpapers.

The public account release was checked in Chromium, Firefox and WebKit. Physical-device and screen-reader verification have separate coverage. [Account release notes](docs/releases/web-accounts.md) · [Verification limits](docs/testing/web-verification.md)

## Run locally

Use Node 24.19.0 and pnpm 11.25.0:

```sh
pnpm install --frozen-lockfile
pnpm dev
```

No environment variables, user accounts or credentials are needed. For checks:

```sh
pnpm check
pnpm exec playwright install chromium firefox webkit
pnpm test:e2e
```

See [development setup](docs/development/setup.md) for CI, offline-after-load limits and deployment checks.

## Accounts and local development

FastAPI and PostgreSQL serve the same-origin account API. A worker delivers sign-in and account-confirmation codes. Local development uses Mailpit to capture messages. [Account setup](docs/development/account-setup.md) · [Authentication](docs/api/authentication-contract.md) · [Email delivery setup](docs/development/resend-setup.md)

Account profiles support explicit import, offline edits, conflict resolution and reset. Export and permanent deletion require a fresh email confirmation. Scheduled email reflections are deferred. [Profile sync](docs/api/profile-contract.md) · [Account management](docs/api/account-management-contract.md) · [Reminder scope](docs/api/reminder-contract.md)

## Documentation

- [R1 specification](docs/requirements/web-release-specification.md)
- [R2 specification for accounts, sync and reminders](docs/requirements/backend-release-specification.md) · [Backend decision](docs/architecture/decisions/0002-optional-account-backend.md)
- [Calendar/clock contract](docs/requirements/calendar-clock-contract.md) · [shared fixture audit](docs/testing/calendar-clock-fixtures.md)
- [Architecture](docs/architecture/overview.md) · [static hosting decision](docs/architecture/decisions/0001-static-web-release.md)
- [Database diagrams and phrase-bank ownership](docs/architecture/database.md) · [generated implemented schema](docs/architecture/database-schema.md) · [generation/check commands](docs/development/database-documentation.md)
- [Account deployment and rollback](docs/operations/account-deployment.md) · [Database recovery](docs/operations/backend-recovery.md)
- [Backend setup](docs/development/backend-setup.md) · [foundation verification](docs/testing/backend-foundation.md) · [implemented API](docs/api/openapi.json)
- [Product overview](docs/product/README.md) · [interface study/review](docs/design/interface-review.md)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

## Feedback and license

Use [GitHub Issues](https://github.com/agapeengineering/aion/issues) for public bugs and suggestions. Leave out birth dates and other private information. Sensitive reports use [private vulnerability reporting](https://github.com/agapeengineering/aion/security/advisories/new).

Original source: [MIT](LICENSE). Fonts/dependencies retain their own [licenses and notices](THIRD_PARTY_NOTICES.md). Agape/Aion names and marks are not granted as trademarks by the source license.
