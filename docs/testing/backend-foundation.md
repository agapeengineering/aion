# Backend foundation verification

Date: 2026-10-17. Scope: foundation for accepted R2; **not a deployed account service**. Local measurements were first recorded in the working tree based on `d2f47a2`. The implementation and accepted SRS/ADR are now published at `4f94db988c717ec3ea42be88311d7dbc0f6e169b`; hosted evidence is recorded separately below. Actual commands: [backend setup](../development/backend-setup.md).

## Executed evidence

| Check | Actual result and scope |
| --- | --- |
| Locked installation and clean source copy | Python 3.14.7 / uv 0.11.19; final source copied to an independent directory without its environment/cache, locked installation and all lint/type/contract/**21 test** checks passed there as well as in the primary tree. |
| Ruff / mypy / API export | Lint, format, strict typing of production source and generated implemented OpenAPI drift checks passed. API has two health GET routes; no fake auth/profile handlers. |
| Pytest | **21 passed**: explicit/sanitized config, unsupported DSNs, offline liveness/503 readiness, API JSON errors, empty-schema/migrated/drift readiness, real-PostgreSQL upgrade/model parity/reapply/isolated downgrade+upgrade, non-superuser role, canonical identity uniqueness, session ownership FK/deletion cascade, challenge active uniqueness/resend invalidation/attempt bound, digest length and durable rate counters. Worker one-shot probe preserves an existing long-running worker heartbeat on both success/failure. |
| Container builds/start | Digest-pinned Python 3.14.7 / uv 0.11.19 / PostgreSQL 18.3 / unprivileged Nginx 1.30.1; native Linux ARM64 under Docker 29.4.0 / Compose 5.1.2. Migrations completed before API/worker startup. Web/API/worker/Postgres healthy; no mail keys or sending code. |
| Local stack smoke | Generic live/ready responses, proxy JSON 404/no-store, retained synthetic row after database stop/start and API/worker restart. Worker probe succeeds after recovery. Final smoke also passed API-upstream outage → JSON 503 with static UI still available, and bare `/api` JSON 404. Volume preserved; test row removed. This is not a backup restoration. |
| Existing web regression | `pnpm check`: fixture audit, TypeScript, **82 unit checks**, production build passed. `AION_BASE_URL=http://127.0.0.1:18080 pnpm test:e2e`: **33 passed** (11 each Chromium/Firefox/WebKit) against the local container proxy. Guest requests remain static/local, with unchanged web source. |
| Account study | Synthetic code error/success journey passed; nine states in each EN/ES at 320 CSS pixels: no horizontal overflow or selected axe WCAG 2 A/AA, 2.1 AA violations. No external resources or JS errors. Agent inspected desktop import and Spanish mobile deletion screens. No human/VoiceOver certification claimed. |
| Dependency advisory check | Runtime dependencies exported from the lock and checked with pip-audit 2.10.1: **no known vulnerabilities reported** at execution time. This does not scan the container OS or prove absence of vulnerabilities. |

The initial local DB test could not connect because Docker's internal bridge does not forward published ports; the loopback-only local override now explicitly enables that bridge for host tests. The base remains isolated/unpublished. An initial deprecated HTTPX test-client fallback was replaced with the installed Starlette-supported HTTPX2 development client. The one-shot worker probe was corrected to avoid removing the running worker's heartbeat; regression cases cover it.

## Critique and remaining gates

Agent reviewed secret loading/redaction, bounded connections/query/pool waits, lifecycle disposal, no startup auto-DDL, exact-revision readiness, explicit migrations/constraints, container UID/capabilities/readonly filesystem, scoped test cleanup, SQL parameter handling and runtime/contract separation. API-upstream failure now has a JSON 503 fallback rather than an HTML gateway error. Guest static pages do not depend on backend health after startup.

- Hosted Linux AMD64 backend CI now passes at the published implementation revision, including container build/start and outage/persistence checks; see the publication record below. Local ARM64 checks and hosted AMD64 checks are separate executed evidence. Neither establishes EC2 production readiness.
- Account UI/HTTP contract and component choices are design artifacts. Auth, authorization/CSRF, rate-limit enforcement, encrypted verification outbox, export/deletion, profile sync, Python calendar parity and reminder processing remain next slices; identity tables do not satisfy their acceptance criteria.
- Production needs distinct least-privilege runtime/migrator DB grants, exact Origin/trusted proxies, secure cookies, key injection/rotation, edge/log redaction, controlled email integration, off-instance backup/deletion reconciliation, host sizing/cost/access, actual TLS/cache/firewall and recovery evidence. No EC2, Resend or Cloudflare configuration changed.
- Existing R1 physical iPhone/Safari, VoiceOver/zoom and personal-use review gaps remain open. Neither the prototype nor local automated checks close them.
- No production release/uptime promise, provider delivery or off-host restore evidence is asserted. The current public R1 remains unchanged.

Before marking a released slice complete, attach the actual committed source, hosted check report, image identity and applicable human/release evidence. Preserve this local evidence as local evidence rather than relabeling it after publication.

## Publication and hosted verification

Implementation published on 2026-10-17: [`4f94db988c717ec3ea42be88311d7dbc0f6e169b`](https://github.com/agapeengineering/aion/commit/4f94db988c717ec3ea42be88311d7dbc0f6e169b). This includes the accepted R2 SRS/ADR and all foundation source, contracts, prototype, tests and workflow. This publication record is a later documentation-only update; it does not change the tested implementation.

- [Backend foundation CI](https://github.com/agapeengineering/aion/actions/runs/39071746973): **passed** on GitHub's Linux AMD64 runner. Locked setup, lint/format/types, generated API check, all 21 real-PostgreSQL/unit checks, runtime dependency audit, web build, backend/web container build/start, outage/recovery/persistence/proxy smoke and scoped cleanup succeeded.
- [Web CI](https://github.com/agapeengineering/aion/actions/runs/39071746992): **passed** at the same source revision, including formatting, fixture audit, typecheck, 82 unit checks, production build and 33 browser journeys.
- No public deployment, provider changes or real-user mail was performed. Human account-study review and later account/sync/reminder/security/recovery gates remain pending.
