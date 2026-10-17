# Aion repository instructions

Read README.md and docs/requirements/web-release-specification.md before changes. Read the relevant architecture decisions and actual manifests when they exist.

- Aion is free, local-only and bilingual (English/Spanish). No backend, accounts, authentication, cloud sync, analytics, AI, journal, goals or streaks.
- The reviewed specification owns behavior. Keep stable FR/NFR IDs and update requirements, tests and implementation together.
- The web countdown ticks; its values remain approximate and the lifespan is a chosen assumption. Never use private birth dates in examples, fixtures, requests or logs.
- One active implementation slice. Review the coded prototype before production UI implementation. Do not create native modules until their phase is scheduled.
- Repository documents own product behavior, contracts, code, tests and release evidence. Use GitHub Issues for public feedback; maintainers may track execution separately.
- Write for public contributors. Do not include internal tracker IDs/links, private planning notes, local filesystem paths, personal conversations/preferences or unrelated project priorities. Express accepted preferences as product requirements with rationale. Keep internal mappings in the private planning system.
- Keep credentials, signing keys, local settings and personal data outside Git. Use synthetic test data.
- Do not commit, push, merge, deploy, enroll or purchase without user authorization. Preserve unrelated changes.
- Run meaningful checks appropriate to the change. Never describe a planned check, prototype or build as released evidence.

## Current baseline

Specification and fixture-audit baseline; no application manifests, runnable app, dependencies or CI yet. Read docs/requirements/calendar-clock-contract.md for calculation detail and docs/testing/calendar-clock-fixtures.md for the shared golden data. Run `node tools/verify-calendar-clock-fixtures.mjs --self-test` after contract/fixture edits; this is a fixture audit, not application test evidence. Next setup work reviews a coded prototype and establishes the reproducible web toolchain/CI. Do not invent application commands until implemented.
