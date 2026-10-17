# Contributing to Aion

The project is in setup. Read the reviewed R1 specification and repository AGENTS.md first. GitHub Issues is the public feedback route; maintainers coordinate planned work separately. Discuss material scope changes before implementation.

Keep changes small and tied to requirement IDs. Use synthetic dates/settings only. Update relevant requirements, tests and documentation together. PRs should explain the user-visible change, actual checks run and remaining limitations. Do not claim tests/builds/releases that have not run.

No application toolchain exists yet; application commands will be added with the web scaffold. After calendar/clock contract or fixture changes, run `node tools/verify-calendar-clock-fixtures.mjs --self-test` and review affected expected results independently. See the fixture guide for its scope and limitations. No paid services, accounts, backend or cloud sync belong in the current product scope. Contributors retain copyright to their work and submit contributions under this repository's MIT license.
