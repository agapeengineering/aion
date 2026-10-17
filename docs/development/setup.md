# Development setup

Status: documentation baseline only, 2026-10-17.

Clone with Git:

```sh
git clone https://github.com/agapeengineering/aion.git
cd aion
```

Read AGENTS.md and docs/requirements/web-release-specification.md. There is no package manifest, lockfile, dependency install, dev server, application build, test suite or CI workflow yet. Do not run or document hypothetical commands as if they exist.

The next setup work defines shared domain fixtures, reviews a coded prototype and adds the React/TypeScript/Vite scaffold. That scaffold must pin a compatible Node/pnpm environment and dependencies, document commands and prove clean-checkout checks/builds. Subsequent native tools are selected when their modules exist.

No environment variables or credentials are required for the current baseline. Never put birth dates, private exports or signing credentials in tracked files. Use synthetic fixture data for all verification.
