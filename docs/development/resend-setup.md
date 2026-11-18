# Resend delivery for Aion accounts

The verification worker supports Resend HTTPS delivery. Routine development and CI use Mailpit and synthetic mail. The controlled live smoke uses an explicit recipient allowlist. Public account delivery requires separate opt-in and the release verification below. Scheduled reminders stay disabled for the account launch. See [reminder setup](reminders-setup.md).

## Configuration

| Variable | Consumer | Meaning |
| --- | --- | --- |
| `AION_RESEND_ENABLED=true` | API + worker | Requires enabled auth and disabled local capture |
| `AION_RESEND_API_KEY_FILE=/run/secrets/resend_api_key` | Worker only | File containing a sending-only key restricted to the verified sending domain |
| `AION_EMAIL_FROM=Aion <aion@mail.agape.engineering>` | API + worker | Sender; frozen into each sealed queued request |
| `AION_EMAIL_REPLY_TO` | API + worker | A working monitored email address; required |
| `AION_RESEND_ALLOWED_RECIPIENTS` | API + worker | JSON array of exact test recipient addresses; nonempty, normalized; no wildcards |
| `AION_RESEND_PUBLIC_ACCOUNTS=true` | API + worker | Explicit production opt-in, with canonical HTTPS origin, no test allowlist and reminders disabled |
| `AION_RESEND_DAILY_LIMIT` | API + worker | Positive UTC daily budget for verification attempts; required for public mode |
| `AION_RESEND_WEBHOOK_SECRET_FILE` | API + worker in public mode | Private signing-secret file for verified delivery, bounce and complaint callbacks |
| `AION_RECOVERY_JOURNAL_SOCKET` and `AION_RECOVERY_JOURNAL_EPOCH_FILE` | API + worker settings | Required for public mode. Mount the host socket directory only in the API and the epoch file in both services |
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

Signed webhooks persist delivery evidence and apply suppressions for eligible bounces and complaints. New suppressions in public mode wait for an independent journal write. Routine tests use injected provider responses and synthetic addresses.

References: [Resend send API](https://resend.com/docs/api-reference/emails/send-email), [idempotency](https://resend.com/docs/dashboard/emails/idempotency-keys).

## Prepare production account delivery

1. Verify the dedicated sending domain and its provider quota. Create a separate **Sending Access** key scoped to `mail.agape.engineering` in Resend. Provision it as a worker-only read-only file using the operator's protected secret channel. [Resend API key permissions](https://resend.com/changelog/new-api-key-permissions)
2. Configure both services for `https://aion.agape.engineering` with the verified sender and a working support Reply-To. Set a verification-mail daily budget with headroom for shared account traffic and provider limits. The worker reserves one slot before each outbound attempt, including retries whose previous outcomes are unknown. When the budget is full, new challenges receive `429` and a `Retry-After` value through the next UTC window.
3. Configure HTTPS callbacks at `/api/v1/webhooks/resend` for delivered, bounced and complained events. Mount the separately generated webhook secret. Verify the endpoint with Resend and confirm that a signed callback commits its event, that a bounce or complaint suppresses future dispatch, and that invalid signatures and replays are handled as specified. [Webhook and suppression contract](../api/reminder-contract.md)
4. Establish and verify the [write-ahead recovery journal](../operations/backend-recovery.md#write-ahead-journal-for-account-host-loss). With public mode still off, run the approved allowlisted smoke from the candidate worker with the scoped key. Verify delivery, browser code exchange, logout and callback handling. Clear test queue state before serving public accounts.

## Prepare an EC2 worker delivery test

The staging override `deploy/staging/compose.resend.yaml` prepares an approved allowlisted test with a reviewed backend image. Set `AION_RESEND_SETTINGS_FILE` to an operator-private file containing the sender, working Reply-To, exact recipient allowlist and positive daily limit. Set `AION_RESEND_WORKER_KEY_FILE` to a sending-only, domain-scoped credential file under a mode-0700 directory. The file uses mode 0444 so the non-root worker can read its read-only bind mount.

After configuring the journal, validate the merged configuration from the extracted package directory.

```sh
docker compose -p aion-staging --env-file images.env \
  -f compose.yaml -f compose.journal.yaml -f compose.resend.yaml config --quiet
```

The override gives only the worker the provider credential and an outbound delivery network. The API receives sender and allowlist settings and keeps its private network connections. The override explicitly disables capture, public account delivery and scheduled reminders. A production release needs the separately reviewed canonical-origin routing and signed-callback configuration before public mode can be enabled.

## Verification evidence

Local checks cover actual PostgreSQL migrations/model agreement, regenerated schema diagrams, frozen provider requests, header/idempotency construction, 429/5xx/permanent/malformed responses, bounded Retry-After, recipient rejection, durable crash uncertainty, recovery with the same logical key, concurrent dispatch and expiry/purge. The full backend suite, lint/type/generated API/schema checks, web unit/build/format checks and nine capture-mode EN/ES browser/redirect journeys passed. Compose builds/migration/start and the layered Resend configuration were validated. Routine provider tests are mocked. The separately authorized live smoke below verifies the configured provider/domain and one recipient. No new runtime dependency was added. This records local verification; publication and hosted CI results are tied to the corresponding Git revision.

## Controlled live smoke — 2026-10-17

The operator supplied a scoped key through the local hidden-input helper. Resend reported the sending domain verified, sending enabled, and open/click tracking disabled. The local four-file Compose stack started healthy with the key mounted only in the worker. One explicitly approved recipient was used; no private recipient address, key, code or cookie is retained in this public record.

The API accepted the challenge (202). The worker obtained provider acceptance on the first attempt and purged the sealed payload; provider metadata subsequently reported `delivered`. The transient code from that message completed verification (200), identity access (200) and CSRF-protected logout (204). The smoke used a dedicated cookie jar and explicitly trusted only the generated local test certificate. Temporary smoke credentials/files were removed after logout. Provider-delivered status does not establish inbox placement or a human reading the message.

The local preview remains in allowlisted Resend mode for manual review. Request a fresh code in the browser; the smoke code is consumed and was bound to the smoke client's cookie. This is integration evidence for the working tree, not a public deployment or the remaining R2 lifecycle/webhook/recovery release gates. Hosted CI and commit/push remain separate actions.

The operator subsequently confirmed receiving the test email and confirmed that `support@agape.engineering` receives replies. The configured local Reply-To now uses that support alias; the single approved test-recipient allowlist remains in private local settings. The live smoke above used the earlier working Reply-To and is not evidence of a second send with the support alias.


The [verification email design](../design/verification-email.md) documents the EN/ES HTML and plain-text template, synthetic preview command and rendering evidence. Body branding is implemented in the application, separately from recipient-provider inbox avatars/BIMI.


Account confirmation uses the same sealed queue, sender, support Reply-To, recipient allowlist, budgets and idempotent provider adapter as login, with a distinct EN/ES purpose/template. No extra provider account/key is needed. Reflections remain deferred. Before **public account login** (independently of reminders), configure a reachable signature-verified webhook and verify suppression on bounce/complaint; API/worker configuration and provider callback reachability must be reviewed together. Local allowlisted sign-in success alone does not prove that production lifecycle.

On the Free, Pro and Scale plans, Resend publishes a 30-day retention period for sent messages and logs. Account deletion in Aion does not recall mail already delivered. The operator can request early removal of individual sent messages through Resend support using the provider message IDs. [Provider retention and deletion](https://resend.com/security/gdpr/)
