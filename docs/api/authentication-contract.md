# Authentication contract

Status: **signup/login implemented locally behind explicit flags; not deployed or human-approved UI**. Reverification and broader account lifecycle remain planned. Baseline: accepted R2 FR-014–016/026, NFR-008/014. Date: 2026-10-17.

The [OpenAPI export](openapi.json) is generated exclusively from FastAPI. Implemented routes: health, POST `/auth/challenges` (login purpose only), POST `/auth/verify`, GET `/me`, GET `/auth/csrf`, POST `/auth/logout`. All use the `/api/v1` prefix. The examples below distinguish implemented login from planned lifecycle operations. See [local setup](../development/account-setup.md) and [verification evidence](../testing/email-code-auth.md).

## Browser journey and identity

The local UI now uses dedicated `/login` and `/account` pages, with `/es/login` and `/es/account` equivalents; see the [implemented page design](../design/account-pages.md). Passwordless code, session and CSRF behavior is unchanged. The interaction study below is an earlier behavior prototype, not the current page layout.

The [EN/ES interaction study](../design/account-flow.html) uses only synthetic data and local memory. No network, account, persistence or delivery occurs. Cover guest → email → code → new/existing profile choice; account/cached/offline/conflicting states; session revocation, sign-out and deletion/reverification. Prototype comparisons intentionally show different 90/95-year horizons. Human review remains pending.

Trim email whitespace and validate with a maintained email validator. R2 uses a documented case-insensitive identity policy: lower-case normalized addresses, no Gmail-specific dot removal or plus-address rewriting. No display-name input. Reject unsupported internationalized local parts initially with a localized field error; internationalized domains may normalize to ASCII. Domain-level validation is not mailbox ownership verification. The email code is the ownership check; do not use SMTP probing or account-existence responses.

Sessions use 32 random bytes from Python's `secrets`, an opaque URL-safe encoding, and a stored SHA-256 digest. This is a random reference into PostgreSQL, not a JWT or client-readable identity record. No auth token is placed in local storage, URL parameters or JSON response bodies. Low-entropy verification codes require keyed HMAC protection and constant-time comparison, not plain SHA-256. See [security component review](../architecture/backend-security-components.md).

## Request/response contract

All examples are synthetic and use the canonical `/api/v1` base. Login fields are implemented; explicitly marked future operations are not available. Sensitive response bodies and cookies must be `Cache-Control: no-store`; proxy/CDN caches must bypass API routes.

### Request a challenge

`POST /auth/challenges`, exact same-origin `Origin` required. Request:

```json
{"email":"person@example.test","language":"en","purpose":"login"}
```

Generic `202` for valid requests regardless of whether the account exists, with a newly generated opaque `challenge_id`, `expires_in: 600`, `resend_after: 60`. The response must never reveal an existing user/profile. Set/rotate a separate challenge-browser binding cookie `__Host-aion_challenge`; Secure, HttpOnly, SameSite=Lax, Path=/, no Domain. Its secret is never returned as JSON. The ID alone cannot verify a code from a different browser. For **future re-verification**, require an existing session, use its current email and `purpose: reverify`; do not allow substitution of another email/user ID.

Code: eight random decimal digits, ten-minute expiry, five attempts per challenge; 60-second resend cooldown, three sends/email/hour, 20/IP/hour. Add bounded wrong-code budgets across challenges (initial limits: 15/email/hour and 100/IP/hour); resends never reset these budgets. Counters/atomic consume live in PostgreSQL, with keyed subjects, bounded retention and race tests. Rate-limited requests return 429 with safe `Retry-After`; the same thresholds apply to existing/new destinations. Configure trusted proxy identities before relying on client IP; never trust arbitrary forwarded headers.

Requesting a new challenge invalidates previous same-email/purpose challenges atomically, including already expired but unconsumed records protected by the initial partial unique index. Expired/invalidated outbox mail must not send. Queue the code in a sealed expiring outbox payload, never log/echo it or send from a request background task. Migration `0002_verification` adds the sealed `verification_mail` outbox. The worker defaults to local Mailpit capture. An opt-in, allowlisted Resend adapter uses a sealed immutable provider payload, stable idempotency key, bounded retry and separate accepted/uncertain metadata; see [Resend setup](../development/resend-setup.md). Real sending requires explicit local configuration.

### Verify / re-verify

`POST /auth/verify`, exact Origin and matching challenge-browser cookie required:

```json
{"challenge_id":"00000000-0000-4000-8000-000000000001","code":"12345678"}
```

The displayed code is for the prototype only; no production challenge accepts a fixed test code. In one transaction lock the challenge, check purpose/browser/attempt/expiry budgets and consume once; create a verified user only for a first successful login. Concurrent verification must produce only one successful consumption/session issuance. A new session always replaces an attacker-supplied prior session cookie, preventing fixation.

Success: `200` with current user identity and the next-step profile-presence flag. Set `__Host-aion_session` with Secure/HttpOnly/SameSite=Lax/Path=/ and no Domain; absolute expiry <=30 days, idle expiry <=7 days. Creation/login does not upload guest settings or opt in to reminders. Invalid/expired/replayed/wrong-browser codes receive the same stable `verification_failed` code, without account-existence details; bad format is 422, abuse limits 429. Transaction rollback must not reset recorded failed-attempt budgets.

**Planned, not implemented:** `POST /auth/reverify` consumes a separately purposed, session-bound challenge and updates only the current session's re-verification timestamp, never another identity's account or the signup flow. Export/deletion require re-verification within ten minutes. HTTP GET and mail-link visits never establish a login or delete/change an account.

### Session access and anti-CSRF

Planned operations: `GET /me`, `GET /sessions`, `DELETE /sessions/{id}`, `DELETE /sessions` (revoke all, including current), `POST /auth/logout`. Session responses expose opaque record IDs, creation/last-use times and a current-session flag, never token digests, CSRF digests or cookies. Access is always scoped to the authenticated owner; an unauthorized session ID is indistinguishable from missing.

Authenticated writes require exact Origin plus a session-bound anti-CSRF nonce in `X-CSRF-Token`; SameSite alone is insufficient. The CSRF nonce is intentionally readable by same-origin JavaScript and is **not** a login credential. Authenticated `GET /auth/csrf` supplies it after reload; it must not expose the session cookie, change identity or invalidate other tabs' current CSRF state. The synchronizer-token pattern derives an opaque nonce with HMAC-SHA256 over the high-entropy session credential under an independent CSRF key; its SHA-256 digest is stored with the session. It stays stable across tabs/reloads, is compared in constant time and is never accepted as authentication. Logout/revoke clears the relevant cookie/cache; revoking all invalidates every server session. Cached data on an already offline device cannot be erased remotely.

Expect 401 for missing/expired/revoked auth, 403 for CSRF/origin/reverification failure, 422 for invalid fields, 429 for limits and 503 for temporary failure. Login challenge endpoints, signature-verified webhooks and scoped unsubscribe capabilities have narrowly documented authentication exceptions. Do not add blanket CORS, shared-domain cookies, debug tracebacks, request-body logging or public interactive API docs.

## Verification and remaining release gates

Use real PostgreSQL and two synthetic users. Cover concurrent/replayed/expired/bound challenges; persistent resend/guess limits; session fixation, idle/absolute expiry, CSRF and Origin; cross-user access/revocation; recent re-verification; cache clearing/sign-out; import not automatic; outbox crash/expiry/uncertain send; privacy and retention/deletion. Only controlled allowlisted provider smoke after local/CI checks; no real sending is needed to review this contract.

Reverification, session listing/revocation management, export and account deletion remain unavailable; health checks do not claim their implementation. Native token/redirect flows, password recovery and account merging remain outside this browser contract.

## Implemented rate-window and retention details

Send/verify counters use atomic fixed UTC hourly windows with keyed email/IP identifiers; this is not a sliding-window guarantee. Resend cooldown and per-challenge attempt limits apply independently. Cleanup purges pending expired sealed payloads, removes challenges 24 hours after expiry, removes expired/revoked sessions after seven days and removes expired rate buckets. Authentication is disabled by default. Public enablement still requires trusted proxy/IP configuration, restricted runtime database grants, provider delivery/retry evidence and complete R2 lifecycle/privacy/recovery gates.
