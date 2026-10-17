# Backend security component review

Date: 2026-10-17. Scope: foundation selection/design review, not proof of implemented authentication. Follow the [accepted SRS](../requirements/backend-release-specification.md) and [auth examples](../api/authentication-contract.md).

## Components selected for the foundation

- Python 3.14.7, FastAPI 0.143.3 / Starlette 1.8.0, Pydantic Settings 2.16.0: supported interpreter/framework/request/configuration validation. Auth/session cookies, CSRF/Origin enforcement and account authorization still require explicit implementation and tests; framework installation does not supply those automatically.
- SQLAlchemy 2.1.5 / Psycopg 3.3.6 and Alembic 1.20.0: typed persistence, parameterized queries and reviewed explicit migrations. PostgreSQL 18.3 supplies transactions/constraints/locking. No SQLite substitute for identity/concurrency tests.
- Python's maintained `secrets`, `hashlib`, `hmac` and constant-time comparison are the standard primitives for opaque random session references and keyed challenge digests. No home-grown cipher, JWT implementation or password hashing is introduced. There is no code generator/verifier or authenticated route in the foundation.

The application must own and test account orchestration: one-use atomic challenges, per-purpose/browser binding, global abuse budgets, revocation, cross-account access and expiry. This is security-sensitive maintained application logic; it is not represented as an audited turnkey identity service. Record the threat review and test evidence before public account release.

## Alternatives and next-slice dependencies

1. **FastAPI Users:** maintained security/dependency fixes, but the upstream project is in maintenance mode and its packaged password/transport defaults do not implement this exact browser-bound email-code and retention flow. Adopting it would still require custom orchestration. Not installed for the foundation. [Upstream status](https://github.com/fastapi-users/fastapi-users).
2. **Authlib:** useful for OAuth/OIDC/standards-based OTP, while R2 excludes social login and requires random emailed challenges rather than shared-secret TOTP. Not selected merely to add another dependency. [Project scope](https://authlib.org/).
3. **Existing framework plus narrow maintained security components:** chosen for the specified opaque-session design. At the accounts slice, pin/review `cryptography` for Fernet/MultiFernet sealing of temporary verification payloads (50.0.2 reviewed, Apache-2.0 OR BSD-3-Clause), and `email-validator` (2.3.0 reviewed, Unlicense) for address validation/normalization. Recheck compatibility and advisories at adoption; they are intentionally not unused production dependencies in this foundation. Select a compatible maintained CSRF component or documented standard session-bound pattern and review its license before implementing the planned nonce endpoint. [Fernet documentation](https://cryptography.io/en/stable/fernet/), [email validator](https://github.com/JoshData/python-email-validator).

Interpreter/framework/ORM and tools are pinned in `pyproject.toml`/`uv.lock`; Docker base indexes are pinned by digest for both ARM64 and AMD64. Lockfile pins are reproducibility evidence, not a vulnerability-free guarantee. HTTPX2 2.13.1 is the development test client supported by the installed Starlette; its HTTPX fallback emits a deprecation warning and was removed.

## Boundaries before account release

- No default credentials, mail provider keys or external sender exists. Local generated credentials stay under an ignored owner-private directory and are never printed. Local Compose file secrets are mounts, not an encrypted secret manager; a host/Docker administrator can read them.
- Non-superuser application DB owner is adequate for this disposable schema/migration foundation. Before public accounts, use separate migration and runtime grants so the API cannot alter schemas or perform host/role administration; test the actual grants. Container/network separation is not a separate failure domain.
- Disable access logging for this local foundation; sanitize operational errors. Before real token-bearing routes, verify edge/server error-log and query-path redaction as well as application logging. Never enable raw request, SQL parameter or webhook-body logging to diagnose authentication.
- Production requires key injection/rotation/recovery, exact trusted proxy/Origin rules, secure cookies/CSRF, rate-limit and two-user tests, encrypted backup/deletion reconciliation and a reviewed controlled provider integration. Local HTTP is not a production cookie/TLS test.

The account interaction study has no remote resources, writes, real codes or storage. Human walkthrough and production browser/cookie/device verification remain pending.
