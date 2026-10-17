# Development setup

Use Node **24.19.0** (`.node-version`) and pnpm **11.25.0** (`packageManager`). Dependencies are pinned in the workspace manifests and `pnpm-lock.yaml`; only esbuild/workerd dependency builds are explicitly allowed in the workspace configuration.

```sh
git clone https://github.com/agapeengineering/aion.git
cd aion
npm install --global pnpm@11.25.0
pnpm install --frozen-lockfile
pnpm dev
```

The application is at `http://127.0.0.1:5173`. It needs no environment variables, accounts or credentials. Never put private dates, settings or signing material in source. Use synthetic fixtures and isolated browser contexts.

## Checks and production preview

```sh
pnpm fixtures
pnpm typecheck
pnpm test
pnpm build
pnpm exec playwright install chromium firefox webkit
pnpm test:e2e
```

`pnpm check` runs fixture audit, typecheck, unit tests and build. `pnpm test:e2e` starts the production Vite preview at port 4173 unless one is already running. On Linux CI, install browsers with `pnpm exec playwright install --with-deps chromium firefox webkit`.

For a deployed staging/production check:

```sh
AION_BASE_URL=https://aion-staging.jorgesandev.workers.dev pnpm test:e2e
```

This uses synthetic inputs in isolated browser storage; it creates no remote user data. The app's production security policy upgrades insecure asset requests, so WebKit testing behind Wrangler must use HTTPS rather than an HTTP local server. Vite preview does not apply Cloudflare `_headers`; verify them on a secure deployment separately. See the [verification record](../testing/web-verification.md).

## Workspace and publication

`apps/web` is the web client; `packages/calendar` is pure logic shared by the web code. `tests/fixtures` is the stable language-neutral contract corpus; never regenerate expected data to make an implementation pass. The standalone audit and application consumer tests are distinct.

Build output is `apps/web/dist`; `tools/finalize-web-build.mjs` creates Spanish entry HTML, license and source-version metadata. Wrangler configuration owns static deployment. Only deploy within explicit user authorization after the applicable checks. See [deploy/rollback](../operations/web-deployment.md).
