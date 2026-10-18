# Profile sync contract

Implemented in the local opt-in account build; public R1 remains unchanged. Covers FR-017–021 of the accepted [R2 specification](../requirements/backend-release-specification.md). Authentication uses the existing [session, Origin and CSRF controls](authentication-contract.md). The generated [OpenAPI contract](openapi.json) describes the implemented schema.

## Routes and ownership

All paths are under `/api/v1`. Every profile request includes `X-Aion-Account: <expected user UUID>`. The server resolves ownership from the authenticated session and requires the header to match; the header never selects another user's data. This closes the race where a pending account-A upload reaches a browser whose cookie now belongs to B. Mismatch returns `409 account_changed` without returning B's profile.

`GET /profile` returns `{user_id, revision, profile}` and ETag `"profile-N"`. A never-saved account has revision zero and null profile. A reset profile is null with a positive revision. Responses are private, `no-store`, through the same-origin proxy.

`PUT /profile` accepts the entire version-1 profile:

```json
{"version":1,"birthDate":"2000-01-01","lifespanYears":90,"language":"en","unit":"weeks","hideRemaining":false}
```

Dates are Gregorian date-only strings; horizon must fit year 9999. Integers and booleans are strict, unknown fields are rejected, language is EN/ES and units are years/months/weeks/days/hours/minutes/seconds. Python consumes the unchanged shared calendar snapshot fixtures. Client validation uses the device's local day; server validation allows up to tomorrow's UTC date because a device can be a calendar day ahead. Invalid inputs return 422 without changing data.

`PUT` and `DELETE /profile` require exact `If-Match: "profile-N"`, UUID `Idempotency-Key`, `X-CSRF-Token` and configured Origin, alongside the expected-account header. Missing headers fail validation. Each successful mutation increments the revision under an owner-row lock, including the initial create. A stale revision returns 409 with `{error:{code:"profile_conflict"},current:{user_id,revision,profile}}` and the current ETag. Clients must ask before reapplying; there is no silent last-write-wins policy.

Matching retries reuse the same operation UUID/body/base and return the already committed result if it remains current. A different payload under the same UUID, or a retry after a later mutation, returns 409 with the latest state. Deduplication records contain keyed digests rather than previous private profile bodies and expire after 30 days. Monotonic revision checks still protect old requests after cleanup. Key rotation can require conflict review rather than silently accepting an unrecognizable old digest.

`DELETE` clears profile values and increments the retained revision atomically. It preserves identity, sessions and the separate guest calendar. It is online-only in the interface and never queued as an offline reset. Reminder enrollment does not exist yet; disabling consent/canceling reminder jobs must join this transaction before reminders are enabled.

## Browser behavior

Guest use makes no account API requests. Opening the dedicated `/login` or `/account` page (including Spanish equivalents), or an existing account marker, starts a session check. See the [page behavior](../design/account-pages.md). Sign-in reads the profile but never uploads guest settings. A device with guest settings receives an explicit comparison and choices to use the account, upload the device, or continue as guest. Replacing an existing account profile requires a second confirmation. A fresh browser with no guest settings restores its saved account calendar after signing in.

The guest key `aion:settings` stays separate. `aion:account` stores a versioned identity marker; `aion:profile:<owner UUID>` stores only that account's selected state, latest server snapshot and one latest desired pending edit with base revision and operation UUID. No bearer credential enters local storage. Unsupported formats remain untouched. Storage failures warn that pending changes may exist only in the open tab; unloading with unsaved memory-only changes prompts the browser's standard warning.

Refresh occurs at sign-in, foreground, reconnect and before a mutation, plus every 60 seconds while visible/online. No per-second sync. Offline edits update the account cache, never the guest calendar. Replay revalidates the session and owner, reads current state, and either submits conditionally or presents a comparison with “Keep account version” / “Reapply my device changes.” Lost-response retries preserve operation identity. Concurrent-tab pending writes are protected from overwriting each other's stored queue; a collision warns and retains the current tab's desired edit in memory.

Sign-out warns before discarding pending edits, revokes the session online and clears the account cache/marker; the guest calendar returns. Observed expiry, revocation or account mismatch clears the previous account state before any replay. Offline devices cannot learn revocation until reconnecting. Other devices observe profile reset on refresh; stale pending edits require explicit conflict review before recreation.

See [verification and limitations](../testing/profile-sync.md). Remaining account lifecycle, reminders and EC2 release gates are separate work.
