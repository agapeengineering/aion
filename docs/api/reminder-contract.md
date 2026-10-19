# Reminder API and dispatch contract

Implemented locally under `/api/v1`. See [generated OpenAPI](openapi.json) for exact schemas. All API responses are non-cacheable. Guest calendar use does not call this API.

| Route | Behavior |
| --- | --- |
| `GET /reminder-preferences` | Session plus `X-Aion-Account` owner check. Returns revision, saved preferences, next due instant, runtime/content availability and suppression state. Absent settings have revision zero. |
| `PUT /reminder-preferences` | Same owner, CSRF and Origin checks as profile mutation; exact `If-Match: "reminders-N"`. Conflict returns current state for explicit reload. Enabled saves require explicit consent to notice `2026-10-18`, a complete profile, available runtime and no suppression. |
| `GET /unsubscribe/{token}` | Scoped opaque capability shows localized confirmation; never mutates consent. |
| `POST /unsubscribe/{token}` | Confirmation or standards-compatible one-click POST. No login required; disables consent and cancels pending jobs atomically. Repeat is harmless. Re-enrollment rotates the token. |
| `POST /webhooks/resend` | Raw-body Svix signature/timestamp verification; bounded body; atomic event-ID deduplication. Persist processing before acknowledgment. No browser session required. |

Defaults: weekly, Sunday (`weekday=6`, Monday zero), `09:00`, selected IANA timezone, profile language. Phrase preference is available only for a published approved slot; the initial empty bank allows calendar-only enrollment. Settings edits are online and server-confirmed; no offline enrollment queue. Signing out leaves a subscription active and the UI states this. Profile reset pauses reminders; changes cancel obsolete queued snapshots.

Each schedule stores UTC next-due plus local rule. Gaps resolve to the next valid local minute, folds use the first occurrence. Jobs are unique per owner/local date; late schedules over one hour are advanced without catch-up. Payloads are sealed and frozen for retries with a stable provider idempotency key. Up to six attempts use bounded jitter/backoff and provider retry guidance. Ambiguous acceptance is retained as uncertain, never silently treated as unsent. Payloads are purged on acceptance/cancellation/expiry, including while reminders are disabled. Metadata expires after 30 days.

Dispatch, preference/profile mutation, reset, unsubscribe and suppression share a per-email advisory barrier. Workers recheck consent, profile revision, suppression, content version and expiry immediately before I/O. Once a stop operation commits, no later dispatch begins; previously provider-accepted mail cannot be recalled. Leases and `SKIP LOCKED` permit crash recovery/concurrent workers without duplicate logical jobs.

Hard bounce, complaint and provider suppression create a minimal independent keyed email suppression and pause reminders; verification dispatch also respects it. Delivered status never reverses suppression. Webhooks from another sender in a shared Resend team are ignored unless their provider ID is already known to Aion. No full webhook body or recipient is retained in the event table. Account deletion/export and backup reconciliation are still pending, not implied by database cascade constraints.
