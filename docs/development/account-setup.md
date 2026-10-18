# Local email-code signup/login

This opt-in preview uses real PostgreSQL, HTTPS cookies and a local SMTP capture inbox. It does not configure Resend, send external email or change the deployed R1 site. Complete [backend setup](backend-setup.md) first, including disposable local database configuration and web dependencies.

From the repository root:

```sh
python3 tools/auth-local-config.py
VITE_AION_AUTH=1 VITE_AION_AUTH_LOCAL=1 pnpm build
docker compose -f deploy/compose.yaml -f deploy/compose.local.yaml -f deploy/compose.auth.local.yaml up -d --build --wait
```

Open <https://127.0.0.1:18443>. The HTTPS `localhost:18443` alias redirects to this canonical origin; auth cookies and Origin checks use one host. Its self-signed local certificate produces a browser warning; accept it for this loopback preview only. Cookies retain Secure/HttpOnly and the `__Host-` prefix. Open Account, use a synthetic address such as `person@example.test`, and read its eight-digit code in <http://127.0.0.1:18025>. The same flow signs up a verified new account or logs in an existing account. A code expires after ten minutes and works only in the browser that requested it. Logout revokes the current session while preserving the local calendar.

Capture delivery accepts only `@example.test` recipients. The inbox has bounded ephemeral storage and no forwarding/relay configuration. Do not enter real personal addresses or calendar data. Mailpit is a development dependency, never a production component. The generated key bundle and TLS files live under ignored `.local/auth/`; the helper preserves existing keys and never prints them. Reconcile expired/incomplete test certificates explicitly. Losing keys invalidates outstanding verification mail/challenges/CSRF state; production rotation needs a separate runbook.

The default build omits account controls; the backend defaults to authentication disabled. The local account override explicitly enables auth and capture, mounts independent HMAC/CSRF/encryption keys and requires the exact HTTPS origin. Rebuild both frontend and image after source changes. Never reuse this capture override, test certificate, migration-role credentials or permissive development grants in production.

## Checks

```sh
AION_TEST_DATABASE_URL_FILE="$PWD/.local/backend/database-url-host" sh tools/check-backend.sh
AION_AUTH_TESTS=1 AION_BASE_URL=https://127.0.0.1:18443 pnpm exec playwright test tests/e2e/auth.spec.ts
```

Browser tests use unique synthetic recipients and poll the local capture API. Authentication tests disable screenshots/traces/videos to avoid recording codes or cookies. The default web regression build remains `pnpm check` followed by `pnpm test:e2e`. See [authentication contract](../api/authentication-contract.md), [database diagram](../architecture/database.md) and [verification record](../testing/email-code-auth.md).

Remaining work includes provider delivery/idempotency, trusted proxy client IPs, restricted runtime DB grants, re-verification/session management, export/deletion, sync, reminders, recovery and R2 release gates. A local sign-in is not the complete account release.
