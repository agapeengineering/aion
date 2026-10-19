# Local email reminders

Status: implemented and tested locally; no public reminder service is deployed. Account export/deletion, public infrastructure and release gates remain separate work. See the [local verification record](../testing/email-reminders.md), [reminder contract](../api/reminder-contract.md) and [phrase strategy](../content/phrase-bank.md).

## Capture-only preview

Generate local database/auth configuration as described in [account setup](account-setup.md), then build the account UI and layer the reminder override:

```sh
VITE_AION_AUTH=1 VITE_AION_AUTH_LOCAL=1 pnpm build
docker compose -f deploy/compose.yaml -f deploy/compose.local.yaml -f deploy/compose.auth.local.yaml -f deploy/compose.reminders.local.yaml up -d --build --wait
```

Open `https://127.0.0.1:18443` and the synthetic inbox at `http://127.0.0.1:18025`. Use only `@example.test` addresses. This override is capture-only: never layer it onto the Resend preview or deploy it publicly. Create an account calendar, explicitly enable reminders and consent, then save. Sunday 09:00 is the default; choose a near-future daily time to exercise delivery. Keep the worker running. Enrollment always targets a future occurrence, never an immediate send. Sign-out does not unsubscribe; pause in Account or confirm the unsubscribe link.

The approved weekly collection is initially empty. Calendar-only reminders work; attributed passage enrollment becomes available when that scheduled week's approved slot exists. Missing weeks are skipped without fallback or backlog. Preview templates without sending using `uv run --project apps/backend --locked python tools/preview-reminder-email.py`.

## Controlled Resend readiness

Keep `AION_REMINDERS_ENABLED=false` until these operational prerequisites exist. Existing allowlisted sign-in email can continue independently.

1. Expose same-origin `POST /api/v1/webhooks/resend` on the intended HTTPS environment, before SPA fallback. Do not expose the local Docker stack to the internet.
2. Configure a Resend webhook for `email.sent`, `email.delivered`, `email.bounced`, `email.complained`, `email.suppressed`, `email.failed`, and `email.delivery_delayed`. Tracking remains disabled. Preserve raw request bytes and Svix headers.
3. Store its signing secret in a private file, mount it read-only into **both API and worker**, and set `AION_RESEND_WEBHOOK_SECRET_FILE=/run/secrets/resend_webhook_secret`. Never put its value in source, chat or command arguments. Keep the provider API key mounted only in the worker.
4. Verify authenticated callbacks, duplicate/out-of-order handling and hard-bounce/complaint suppression on the deployed endpoint. A syntactically valid secret is not evidence that callbacks can reach it.
5. Keep the existing explicit recipient allowlist and support Reply-To. Only then enable `AION_REMINDERS_ENABLED=true` in API and worker for an authorized controlled test. Broad public sending requires the remaining R2 deployment/privacy/recovery gates.

Startup refuses real reminders without a readable valid webhook signing secret. This gate alone does not establish production readiness. Suppression identifiers survive user deletion; application-managed metadata is pruned after 30 days. Key rotation must preserve encrypted pending payloads/unsubscribe tokens or explicitly cancel affected jobs and re-enroll users. Reconciliation after a restored backup remains a release gate; do not run restored queues automatically.

## Checks

Backend checks exercise PostgreSQL schedules, DST, concurrency, consent barriers, retries, expiry, suppression and signatures. Browser smoke uses capture-only mail and synthetic accounts:

```sh
AION_AUTH_TESTS=1 AION_REMINDER_TESTS=1 AION_BASE_URL=https://127.0.0.1:18443 pnpm exec playwright test tests/e2e/reminders.spec.ts
```

The full delivery smoke advances only its newly created synthetic accounts and requires an explicitly disposable `AION_REMINDER_SMOKE_PROJECT=aion-profile-tests` (or CI's disposable foundation project). Never use it against a real account database. No test makes an external email request.
