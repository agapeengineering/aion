# Controlled Resend delivery from the local backend

The verification worker supports Resend HTTPS delivery. Routine development/CI still uses Mailpit and synthetic mail. Real sending is opt-in and limited to an explicit recipient allowlist. Reminder preferences, scheduling and verified suppression webhooks are implemented locally. Real reminders stay off until a reachable webhook and its signing secret are configured; see [reminder setup](reminders-setup.md). Account lifecycle is implemented locally; public accounts and independent recovery gates remain pending. This setup changes no DNS, provider account, billing or public deployment.

## Configuration

| Variable | Consumer | Meaning |
| --- | --- | --- |
| `AION_RESEND_ENABLED=true` | API + worker | Enable the controlled Resend mode; auth must be enabled and local capture disabled |
| `AION_RESEND_API_KEY_FILE=/run/secrets/resend_api_key` | Worker only | File containing a sending-only key restricted to the verified sending domain |
| `AION_EMAIL_FROM=Aion <aion@mail.agape.engineering>` | API + worker | Sender; frozen into each sealed queued request |
| `AION_EMAIL_REPLY_TO` | API + worker | A working monitored email address; required |
| `AION_RESEND_ALLOWED_RECIPIENTS` | API + worker | JSON array of exact test recipient addresses; nonempty, normalized; no wildcards |
| `AION_RESEND_WEBHOOK_SECRET_FILE` | API (+ worker when configured) | Private signing-secret mount for verified delivery/bounce/complaint callbacks; configure and verify reachability before public accounts |
| `AION_LOCAL_MAIL_CAPTURE=false` | API + worker | Prevent simultaneous local SMTP and Resend modes |

No raw API-key environment variable is supported. Never use a frontend `VITE_*` variable for credentials, paste keys in chat or commit them. The API does not mount the key. The provider's domain open/click tracking must remain disabled. Sender verification is a Resend/DNS prerequisite; configuring a string here does not verify a domain. A Reply-To must already receive mail; this setup does not create a mailbox.

## Prepare local files

From the root, after [local account setup](account-setup.md):

```sh
python3 tools/resend-local-config.py
# Edit .local/resend/settings.env: working Reply-To and allowed test recipients.
python3 tools/resend-local-config.py --set-key
```

The second command prompts in the terminal without echoing the key or putting it in shell history. It writes `.local/resend/api-key`, readable inside the non-root worker container, under a private mode-0700 directory. The default preparation command preserves existing files and leaves a new key file empty. It never enables delivery. Example non-secret settings (replace synthetic addresses with explicitly approved test destinations):

```dotenv
AION_EMAIL_FROM=Aion <aion@mail.agape.engineering>
AION_EMAIL_REPLY_TO=support@example.test
AION_RESEND_ALLOWED_RECIPIENTS=["tester@example.test"]
```

## Enable only for an approved integration test

```sh
# Build the account UI without the Mailpit-only notice.
VITE_AION_AUTH=1 pnpm build
# Layer this override LAST. Existing local TLS/auth/database settings are retained.
docker compose -f deploy/compose.yaml -f deploy/compose.local.yaml \
  -f deploy/compose.auth.local.yaml -f deploy/compose.resend.local.yaml \
  up -d --build --wait
```

Then open <https://127.0.0.1:18443>, choose Account and request a fresh code for an allowlisted recipient. It arrives at the real mailbox, not Mailpit. Verify it, reload the account page and sign out. The local preview also supports profile sync; reminders remain unavailable. The local HTTPS certificate is self-signed. The `localhost` alias redirects to the canonical IP origin. No resend smoke is performed automatically when files are prepared.

API requests for other recipients receive localized `email_not_allowed`; the worker also checks the allowlist immediately before sending. Removing a recipient prevents its pending dispatch. Encrypted jobs from capture mode lack a frozen Resend body and are never converted into real sends. Request a fresh code after changing modes. Starting the override may dispatch eligible previously queued Resend jobs, so review pending state and recipient settings before enabling.

To return to capture, rebuild with `VITE_AION_AUTH=1 VITE_AION_AUTH_LOCAL=1 pnpm build` and start only the first three Compose files. Docker secrets from a prior override can remain declared on stopped containers; inspect the resulting service configuration and recreate containers when changing modes. No credential belongs in the committed base Compose files.

## Delivery behavior and limits

- HTTPS goes only to `https://api.resend.com/emails`, verifies server certificates and rejects redirects. A five-second socket timeout and bounded response read apply; no SDK-level retries or request/response-body logging. A queued request includes the original sender, Reply-To, recipient, localized subject/HTML/plain text and code, sealed at enqueue. The body is not rebuilt after a restart or configuration change.
- The outbox UUID yields `aion-verification/<UUID>` as the idempotency key on every attempt. Codes/jobs expire in ten minutes, well inside Resend's documented 24-hour idempotency window. Requests never resume after expiry. A provider-accepted message cannot be recalled.
- A durable pre-send uncertainty marker and attempt count survive a worker crash. An email advisory lock shared with challenge request/verify operations prevents concurrent dispatch and invalidation from interleaving; it spans the short provider call without holding a database transaction open over network I/O. Locks are released before returning a connection to the pool.
- Up to six attempts, exponential backoff with jitter, provider `Retry-After`, and job expiry. 429/5xx/network failures retry; permanent 4xx and payload/idempotency conflicts stop. A concurrent-idempotent-request conflict may retry. The worker processes at most five due jobs per pass to bound heartbeat delays.
- `accepted` plus provider message ID means Resend accepted the request, not inbox delivery. `sent` is local SMTP capture. `uncertain` means acceptance could not be established before retry/expiry/cancellation; do not automatically re-send that terminal job. Sensitive payloads are purged on acceptance or terminal state. Delivery metadata is removed with the challenge under the existing short retention.

This slice does not implement delivered/bounced/complained webhooks, persistent suppressions, reminders or their unsubscribe flows. Those remain public-release prerequisites where required by R2. Tests use injected provider responses and synthetic addresses; an approved live integration test separately verifies the actual key/domain/delivery. The existing key's account, permissions, provider quotas and DNS verification are not inferred from passing mocks.

References: [Resend send API](https://resend.com/docs/api-reference/emails/send-email), [idempotency](https://resend.com/docs/dashboard/emails/idempotency-keys).

## Verification evidence

Local checks cover actual PostgreSQL migrations/model agreement, regenerated schema diagrams, frozen provider requests, header/idempotency construction, 429/5xx/permanent/malformed responses, bounded Retry-After, recipient rejection, durable crash uncertainty, recovery with the same logical key, concurrent dispatch and expiry/purge. The full backend suite, lint/type/generated API/schema checks, web unit/build/format checks and nine capture-mode EN/ES browser/redirect journeys passed. Compose builds/migration/start and the layered Resend configuration were validated. Routine provider tests are mocked. The separately authorized live smoke below verifies the configured provider/domain and one recipient. No new runtime dependency was added. This records local verification; publication and hosted CI results are tied to the corresponding Git revision.

## Controlled live smoke — 2026-10-17

The operator supplied a scoped key through the local hidden-input helper. Resend reported the sending domain verified, sending enabled, and open/click tracking disabled. The local four-file Compose stack started healthy with the key mounted only in the worker. One explicitly approved recipient was used; no private recipient address, key, code or cookie is retained in this public record.

The API accepted the challenge (202). The worker obtained provider acceptance on the first attempt and purged the sealed payload; provider metadata subsequently reported `delivered`. The transient code from that message completed verification (200), identity access (200) and CSRF-protected logout (204). The smoke used a dedicated cookie jar and explicitly trusted only the generated local test certificate. Temporary smoke credentials/files were removed after logout. Provider-delivered status does not establish inbox placement or a human reading the message.

The local preview remains in allowlisted Resend mode for manual review. Request a fresh code in the browser; the smoke code is consumed and was bound to the smoke client's cookie. This is integration evidence for the working tree, not a public deployment or the remaining R2 lifecycle/webhook/recovery release gates. Hosted CI and commit/push remain separate actions.

The operator subsequently confirmed receiving the test email and confirmed that `support@agape.engineering` receives replies. The configured local Reply-To now uses that support alias; the single approved test-recipient allowlist remains in private local settings. The live smoke above used the earlier working Reply-To and is not evidence of a second send with the support alias.


The [verification email design](../design/verification-email.md) documents the EN/ES HTML and plain-text template, synthetic preview command and rendering evidence. Body branding is implemented in the application, separately from recipient-provider inbox avatars/BIMI.


Account confirmation uses the same sealed queue, sender, support Reply-To, recipient allowlist, budgets and idempotent provider adapter as login, with a distinct EN/ES purpose/template. No extra provider account/key is needed. Reflections remain deferred. Before **public account login** (independently of reminders), configure a reachable signature-verified webhook and verify suppression on bounce/complaint; API/worker configuration and provider callback reachability must be reviewed together. Local allowlisted sign-in success alone does not prove that production lifecycle.
