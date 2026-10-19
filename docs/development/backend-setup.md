# Backend foundation — development and checks

Status: local foundation, not a public account release. Runtime source: `apps/backend`; accepted baseline: [R2](../requirements/backend-release-specification.md), [ADR-0002](../architecture/decisions/0002-optional-account-backend.md). Foundation implementation does not imply accounts, synchronization, scheduling, Resend or EC2 configuration are working.

The optional local signup/login layer is documented separately in [account setup](account-setup.md); the default stack keeps it disabled.

## Prerequisites

- Docker Engine and Compose (tested with Engine 29.4.0 / Compose 5.1.2); start the local engine first. Commands affect only the `aion-foundation` project.
- For host-run Python checks, install Python **3.14.7** on PATH and uv **0.11.19**. The pinned Docker image includes Python; no host interpreter is required to run the containers. The uv version is also pinned in CI; preinstall Python rather than relying on an older uv download catalog to know a newer Python patch.
- Existing web build: Node/pnpm versions in the root manifests, frozen lockfile installation. No cloud account or email provider is needed.

From the repository root:

```sh
python3 tools/backend-local-config.py
docker compose -f deploy/compose.yaml -f deploy/compose.local.yaml up -d --wait postgres
AION_TEST_DATABASE_URL_FILE="$PWD/.local/backend/database-url-host" sh tools/check-backend.sh
pnpm install --frozen-lockfile
pnpm build
docker compose -f deploy/compose.yaml -f deploy/compose.local.yaml up -d --build --wait
python3 tools/smoke-backend.py
```

The configuration helper generates random development-only credentials in ignored `.local/backend` and never displays or rotates an existing complete configuration. The parent directory is owner-private; individual mount sources are readable by non-root container UIDs. They are not an encrypted secrets manager. Do not print `docker inspect` environment values, paste DSNs, commit that directory, or reuse these local credentials for a server. An incomplete configuration must be reconciled manually; recreating credentials does not change an existing database volume's password.

Local endpoints:

- App/reverse proxy: `http://127.0.0.1:18080` (`/es` for the Spanish entry).
- Direct API: `http://127.0.0.1:18000/api/v1/health/live` and `/api/v1/health/ready`.
- PostgreSQL: `127.0.0.1:15432`, reachable only through the explicit local override. The base Compose file has no published ports and an internal DB network. Docker isolated bridges disable published ingress, so the local override also makes that network non-internal; loopback publication still scopes host access.

The default stack exposes health and keeps authentication disabled; private routes return unavailable until explicit account configuration. Implemented auth/profile/account-management routes are documented in [account setup](account-setup.md) and the generated API. Reflections are deferred for launch. Interactive docs and a runtime OpenAPI endpoint are disabled. The generated [OpenAPI artifact](../api/openapi.json) is for contributor/contract review, not a hosted feature. Guest UI does not call the API.

## What the checks prove

`tools/check-backend.sh` performs locked installation, Ruff lint/format, strict mypy, generated-contract drift detection and pytest. Integration tests require **exactly one** `AION_TEST_DATABASE_URL` or `AION_TEST_DATABASE_URL_FILE`; they fail rather than silently skipping if neither/both are supplied. Use only a disposable database. Tests create/drop randomly named `aion_test_*` schemas; downgrade testing is restricted to those schemas and never downgrades the primary application schema.

`tools/smoke-backend.py` inserts a uniquely named synthetic row, stops the local Postgres container, confirms API liveness/failed readiness and available static UI, starts Postgres, verifies retained data, restarts API/worker and removes only its own row. It does not remove volumes. The worker's `--once` probe validates schema readiness; it sends no mail. This is a persistence/restart exercise, **not** an off-instance backup or disaster-restore test.

For the existing web browser suite through the new local proxy:

```sh
AION_BASE_URL=http://127.0.0.1:18080 pnpm test:e2e
```

Local HTTP omits the production-only upgrade policy so browser tests can load the app. Secure-cookie/TLS/CSRF/proxy identity and real-device behavior require the subsequent account/release checks. No production compatibility or account security is inferred from loopback health.

## Migrations and contracts

One-shot `migrate` completes successfully before API/worker start. API startup never auto-creates tables or migrates; liveness remains healthy during a DB outage while readiness returns only a generic 503. Readiness requires exact schema revision `0003_mail_result`, rejects unknown/multiple revisions and avoids printing database errors. Connections, pool waits and SQL statements have bounded timeouts.

For development migration inspection, from `apps/backend` with an explicit `AION_DATABASE_URL_FILE` pointing to the local host secret:

```sh
uv run --locked alembic current
uv run --locked alembic check
```

Review explicit migration code; never import live ORM metadata to redefine historical migration operations. Future migration changes must update the expected runtime schema revision, pass upgrade/check/isolated-downgrade tests and document compatibility. No automatic production downgrade or backup guarantee is supplied by Alembic.

Regenerate implemented OpenAPI after changing actual routes:

```sh
cd apps/backend
uv run --locked python ../../tools/export-backend-openapi.py
```

This does not load credentials/connect to PostgreSQL. `--check` detects drift. The [auth contract examples](../api/authentication-contract.md) and [account study](../design/account-flow.html) describe the next slice and remain distinct from the generated implemented API.

## Worker, containers and CI

API/worker/migration services share one multi-stage built Python image; only runtime dependencies are installed. App processes use UID 10001, read-only filesystems, bounded tmpfs, no Linux capabilities, no-new-privileges, resource/log limits and exec-form commands. The worker currently probes the database every 15 seconds, updates its private container heartbeat only on success, handles SIGTERM/SIGINT and reports unhealthy when the heartbeat is stale. It has no credentials or network path configured for sending in the base isolated stack.

PostgreSQL uses an independent superuser bootstrap secret and creates a non-superuser `aion_app` role/database owner. This is a development migration owner, **not** the final least-privilege runtime identity. Separate production runtime/migrator grants, key injection, shared proxy, TLS, backup/restore, monitoring and provider setup remain release prerequisites. PostgreSQL 18 stores its versioned cluster beneath the mounted `/var/lib/postgresql` volume.

The [backend workflow](../../.github/workflows/backend.yml) runs the same checks and container smoke on a disposable Linux runner; no deployment or email secrets are required. Existing web CI remains separate. A workflow file is not evidence of a hosted run: see the [foundation verification record](../testing/backend-foundation.md).

Stop this local stack while preserving data:

```sh
docker compose -f deploy/compose.yaml -f deploy/compose.local.yaml down
```

Do not add `--volumes`, run host-wide prune commands, or restart unrelated projects as routine cleanup. No EC2/Cloudflare/Resend setup or public migration is performed by these development commands.
