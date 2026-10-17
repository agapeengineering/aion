# Contributing to Aion

Read the R1 specification, repository AGENTS.md and development setup first. GitHub Issues is the public feedback route; maintainers coordinate execution separately. Discuss material product changes before implementation.

Keep changes small and tied to requirement IDs. Use synthetic dates/settings only. Update requirements, meaningful tests and documentation together. PRs should explain the user-visible change, actual checks and remaining limits; public text must not include private planning context.

Use Node 24.19.0 and pnpm 11.25.0. Run `pnpm check` for changed code/contracts and relevant browser checks with `pnpm test:e2e`. After fixture/contract changes, independently verify golden expectations; never rewrite them to match a bug. Application and fixture tests serve different purposes. The setup guide explains engine installation and deployment-header testing.

No paid services, accounts/backend/cloud sync belong in the current product scope. Preserve self-hosted fonts/licenses and privacy boundaries. Contributors retain copyright to their work and submit original contributions under this repository's MIT license; third-party components keep their own licenses.
