# Aion by Agape

A quiet life-in-weeks calendar: see lived weeks, the present week and the time ahead under a lifespan you choose.

Free and open source. English and Spanish. Your birth date and preferences stay on your device; no account, backend or cloud sync.

## Status

Planning and repository baseline. **No runnable application or published release yet.** The intended web address is `aion.agape.engineering`; it is not a deployment link. Native downloads/store listings will be linked only when they exist.

The first web release includes a life grid, all seven lived/remaining time units, a ticking approximate countdown, local settings/reset, optional hiding of remaining figures, original bilingual phrases and simple PNG wallpaper export. A chosen lifespan is an assumption, never a prediction.

Later native releases aim to offer widgets and supported automatically updating wallpaper. Feasibility and release order require separate device validation; web export is manual.

## Documentation

- [Reviewed R1 specification](docs/requirements/web-release-specification.md)
- [Calendar/clock contract](docs/requirements/calendar-clock-contract.md) · [Shared fixtures and audit](docs/testing/calendar-clock-fixtures.md)
- [Product context](docs/product/README.md)
- [Architecture and decisions](docs/architecture/overview.md)
- [Development setup/status](docs/development/setup.md)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

## Development

There is no application install/build/dev command yet. Shared calendar/clock expectations and a standalone fixture audit are available; the next setup work reviews a coded UI prototype and establishes the React/TypeScript/Vite toolchain. Run `node tools/verify-calendar-clock-fixtures.mjs --self-test` to audit the fixture data without installing dependencies. See the setup document before adding dependencies. Native components are added when scheduled; releases remain independent within this product repository.

## Contact and license

Use [GitHub Issues](https://github.com/agapeengineering/aion/issues) for public bugs and suggestions; do not include birth dates, credentials or private settings. See SECURITY.md for sensitive reports.

Original source is available under the [MIT License](LICENSE). Agape/Aion names and marks are not granted as trademarks by the source license. Third-party assets/dependencies retain their own licenses and require attribution review before addition.
