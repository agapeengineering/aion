# ADR-0002: Optional account backend and same-origin EC2 deployment

Agape Engineering accepted this decision on 17 October 2026. The account and sync deployment went live on 18 November 2026. [R2 specification](../../requirements/backend-release-specification.md) · [Account release](../../releases/web-accounts.md)

## Context

R1 stores all settings on-device. Optional verified accounts would enable cross-device settings recovery and explicitly requested daily/weekly email reflections. These introduce server-side personal data, session and authorization boundaries, durable scheduling, email processing and recovery obligations. Guest functionality must remain complete without accounts. Stable requirement IDs FR-014–026 and NFR-006–014 define the accepted behavior and acceptance gates; this ADR does not duplicate their full rules.

## Decision

- Add `apps/backend` to the existing monorepo: Python/FastAPI, uv lockfile, SQLAlchemy/Alembic and pytest. Keep React/TypeScript/Vite in `apps/web` and preserve the calendar contract/shared fixture corpus. Pin supported compatible dependencies at implementation time.
- Implement one modular backend with auth, profiles, reminders, email adapters/templates, calendar and database/configuration modules. Select maintained compatible security components for the specified email-code/session flow; do not introduce custom cryptographic protocols. No general identity platform, microservices or admin dashboard initially.
- Use one app-owned PostgreSQL database/role and durable outbox. One Python worker executes scheduling and delivery; API/worker run the same reviewed image with different entrypoints. Job claims/leases, constraints and retries live in PostgreSQL. Scheduling is not attached to every API process or a volatile request background task. Start without Redis/Celery.
- Product Docker Compose services: `web` (built static UI server), `api`, `worker`, `postgres`. Keep persistent data in named volumes, DB/worker private, app containers non-root with measured resource/log limits and health checks. Host bootstrap and cross-product routing belong in a separate infrastructure repository referencing product artifacts.
- The 2026-11-18 amendment gives Aion a dedicated Caddy origin proxy on the shared EC2 instance. Cloudflare Tunnel connects to its private HTTPS listener and verifies its certificate. Aion can roll back its routing and trust configuration independently of other applications on the host.
- The canonical origin is `https://aion.agape.engineering`. Caddy sends `/api` and `/api/*` to FastAPI and all other paths to the static web server, including `/` and `/es`. The public API is served at `/api/v1` on that same origin. Unknown API routes return JSON. API responses bypass the CDN cache, and authenticated writes require origin and CSRF validation.
- Migrate web serving from Workers Static Assets to the EC2 static container at a rehearsed cutover; Cloudflare remains DNS/proxy/CDN with encrypted authenticated origin traffic. Explicitly replace the existing Worker custom-domain attachment, preserve old static artifacts and verify origin reachability/TLS/cache controls before public auth is enabled. Do not expose an origin-bypass route that defeats access/rate controls.
- Use Resend through a replaceable server-side adapter. Prefer a suitably owned Agape Engineering team administered through an existing login; team/plan eligibility and incremental costs are verified before configuration. Selected sending domain: `mail.agape.engineering`; sender: `Aion <aion@mail.agape.engineering>`. Configure real support contact, domain authentication, application/environment credentials, signed webhooks and opt-out without open/click tracking.
- Keep one versioned phrase bank consumed by both runtimes and run the unchanged shared calendar corpus against Python as well as TypeScript. Web clocks use device timezone; emails use saved reminder timezone and label their snapshot.

Planned layout:

```text
apps/backend/
  src/aion/{auth,profiles,reminders,email,calendar}/
  src/aion/{main,config,database,worker}.py
  migrations/
  tests/
  pyproject.toml
  uv.lock
  Dockerfile
deploy/
  compose.yaml
```

Exact image versions, security libraries, reverse proxy selection, Linux distribution, host sizing/region and configuration names are implementation decisions requiring verified compatibility and a costed host plan; they are not already provisioned by this record. Web and backend images release independently with a documented compatibility window.

## Alternatives considered

| Alternative | Reason not selected |
| --- | --- |
| Continue static-only | Retains maximum on-device privacy but does not provide account sync or scheduled email. Remains available as guest behavior. |
| Keep static hosting and expose a separate API hostname | Valid independent hosting option; requires extra cross-origin cookie/CORS policy and a split-host operational model. Same-origin EC2 routing fits this release's containerized operating model. |
| Managed identity/database plus distributed queue | Can outsource operations, but adds integrations, cost and migration boundaries for a small single-host application. Revisit if volume or identity/security requirements outgrow the selected maintained components. |

## Costs, custody and recovery

The single host is a shared failure domain. Budget EC2/storage/IP/egress, independent encrypted backup storage, email and optional monitoring; this ADR does not specify a subscription or authorize an unbounded upgrade. Verify actual sending/domain/team limits, reserve verification capacity ahead of optional reminders and surface degraded behavior without silently dropping sync writes. Maintainers own patching, access, domain/email reputation, support, data retention and response; no high-availability or 24/7 human-response promise.

R2 privacy notices must identify profile storage, processors, email-derived information, local caches and backup expiry. Keep source/configuration portable: ordinary PostgreSQL, Docker images, generated OpenAPI and replaceable email adapter. Export/deletion and off-instance encrypted backup/deletion-ledger recovery are required before account launch. No end-to-end encryption claim.

Record clean source/image digests, schema compatibility, configuration references and actual deploy/restore timings per release. Restore with sends disabled; reconcile deletions/suppressions and invalidate restored auth state/stale jobs. Rollback must retain a compatible API/data service or use explicit maintenance mode; returning the hostname to R1 static assets alone does not restore accounts or stop the backend worker.

## Status and revisit triggers

ADR-0002 governs the account release. ADR-0001 documents the historical static guest deployment. Preserve each release record when updating product, API, verification and operations documentation.

Revisit when measured resource contention, missed recovery or scheduling targets, email volume, authentication requirements or independent availability needs exceed this topology.
