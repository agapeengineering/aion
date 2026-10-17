# Aion by Agape

**[Open Aion →](https://aion.agape.engineering)** · [Español](https://aion.agape.engineering/es)

A quiet life-in-weeks calendar. See the weeks behind you, the present week and the time ahead under a lifespan you choose.

Free, open source and bilingual. Your birth date and preferences stay in your browser. No accounts, backend, cloud sync, advertising or product analytics.

## Web 0.1.0

- Two inputs: date of birth and chosen lifespan, with an editable 90-year default.
- Lived/current/future week grid, accessible text summary and exact interval exploration.
- Years, months, weeks, days, hours, minutes and seconds; weeks is the primary view.
- Ticking approximate countdown with pause/resume and optional hidden remaining figures.
- Local save/edit/reset, clear storage-error states and local cross-tab updates.
- Original English/Spanish phrases and local phone/desktop PNG wallpaper export.
- Self-hosted fonts, a privacy explanation, source/license and public feedback route.

A lifespan is a visualization assumption, never a prediction. Another browser/device starts fresh: enter the two details again. PNGs are static images applied manually; native widgets and automatic wallpaper updates are later work.

This is an early release. Chromium, Firefox and WebKit journeys are automated; physical iPhone/Safari, VoiceOver and the product-owner walkthrough remain explicit validation work. See [release notes](docs/releases/0.1.0.md) and [verification limits](docs/testing/web-verification.md).

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

## Documentation

- [R1 specification](docs/requirements/web-release-specification.md)
- [Calendar/clock contract](docs/requirements/calendar-clock-contract.md) · [shared fixture audit](docs/testing/calendar-clock-fixtures.md)
- [Architecture](docs/architecture/overview.md) · [static hosting decision](docs/architecture/decisions/0001-static-web-release.md)
- [Deploy/rollback/recovery](docs/operations/web-deployment.md)
- [Product overview](docs/product/README.md) · [interface study/review](docs/design/interface-review.md)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

## Feedback and license

Use [GitHub Issues](https://github.com/agapeengineering/aion/issues) for public bugs and suggestions. Leave out birth dates and other private information. Sensitive reports use [private vulnerability reporting](https://github.com/agapeengineering/aion/security/advisories/new).

Original source: [MIT](LICENSE). Fonts/dependencies retain their own [licenses and notices](THIRD_PARTY_NOTICES.md). Agape/Aion names and marks are not granted as trademarks by the source license.
