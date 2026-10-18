# Local profile-sync verification

Date: 2026-10-17. Scope: local implementation of FR-017–021, not a public R2 release. Public R1 remains unchanged. See the [sync contract](../api/profile-contract.md), [account setup](../development/account-setup.md) and [accepted release gates](../requirements/backend-release-specification.md).

## Automated evidence

- Backend: Ruff, formatting, mypy, generated OpenAPI/schema freshness and **82 tests**, using real PostgreSQL in random disposable schemas. This includes all 66 unchanged shared calendar snapshot cases in Python; validation, owner and session isolation, Origin/CSRF, concurrent create, independent email-verified sessions, conditional writes, reset tombstones, idempotent retry and expired operation metadata. Existing authentication/Resend tests pass.
- Web: typecheck, fixture verification, production build and **91 unit tests**. Sync tests cover explicit import, restoring a fresh browser, separate guest data, scoped offline cache/reload/latest edits, owner/session changes before replay, unsupported/denied storage, lost-response retries, stale edit-form revision, keep-server/reapply, reset and concurrent-tab queue collision protection.
- Profile browser checks: **6 passed**, EN/ES in Chromium, Firefox and WebKit, against HTTPS + real FastAPI/PostgreSQL + local capture mail. Each journey signs in through an eight-digit captured code, imports explicitly, restores into an isolated browser context, exercises an open-form concurrent change, keeps the account version, makes an offline edit, resolves a second conflict by reapplying, resets both clients on refresh and signs out to restore the untouched guest calendar.
- Existing email-code browser checks: **9 passed** across the same engines. Existing R1 guest browser checks: **33 passed**. These include no guest API traffic, local export, offline operation, unknown/denied storage and ticking behavior.
- Profile comparison at 360px: no horizontal page overflow; automated WCAG A/AA axe checks pass in EN/ES across the three engines. These checks do not replace a human accessibility review or physical-device validation.

Browser sync tests create a second context by copying the already authenticated session cookie, without copying local storage. Separate backend tests verify independently issued sessions sharing one profile and rejecting stale writes. Tests use synthetic data and local capture only; no real provider mail is sent. Credential-bearing traces, videos and failure screenshots are disabled. The disposable browser stack has its own database volume and loopback ports, separate from a real-mail preview.

## Reproduction

Start the capture-only stack using [account setup](../development/account-setup.md), then:

```sh
AION_TEST_DATABASE_URL_FILE="$PWD/.local/backend/database-url-host" sh tools/check-backend.sh
pnpm check
pnpm test:e2e tests/e2e/web.spec.ts
# Rebuild capture UI after pnpm check restores the default guest build:
VITE_AION_AUTH=1 VITE_AION_AUTH_LOCAL=1 pnpm build
docker compose -f deploy/compose.yaml -f deploy/compose.local.yaml -f deploy/compose.auth.local.yaml up -d --build --wait
AION_AUTH_TESTS=1 AION_BASE_URL=https://127.0.0.1:18443 pnpm exec playwright test tests/e2e/auth.spec.ts tests/e2e/profile.spec.ts
```

Use `AION_INBOX_URL` to select a different local capture API (default `http://127.0.0.1:18025`). A separate disposable Compose project may override the HTTPS origin/ports and nginx redirect together. Never point browser mail tests at a Resend-enabled preview. Repeated runs must respect existing email/IP quotas; use a fresh disposable test project rather than weakening product limits. The backend CI runs the account and profile browser checks in Chromium; local verification also covered Firefox and WebKit. Hosted CI for this uncommitted change has not run.

## Manual walkthrough and remaining gates

On the local preview, create a guest calendar, sign in, explicitly save it to the account, then sign in in a separate browser and verify all five settings. Edit while offline, change another browser, reconnect and review both conflict choices. Reset the account calendar online, and verify the other browser clears on foreground/refresh. Sign out and verify the original guest calendar returns. Review the initial comparison/replacement and pending-edit sign-out warning with a human before release.

Reminder consent/preferences/outbox/unsubscribe/webhook handling and reset cancellation barriers are not implemented. Account export/deletion, re-verification/session management, shared phrase extraction for Python, public privacy/retention controls, runtime DB grants, proxy abuse attribution, performance/reference-host measurement, EC2 configuration, backups/recovery and Cloudflare cutover remain release work. Local tests do not establish public readiness, inbox deliverability, recovery or physical-device compatibility.

## Dedicated-page verification — 2026-10-18

Account controls now live on dedicated localized login/account pages. **27 account/browser checks passed** across Chromium, Firefox and WebKit: the existing nine auth checks now include empty-account creation, reload and signed-in login redirection; six sync journeys now also cover a different guest/account comparison; twelve navigation checks cover direct/protected routes, Back/Forward, page-preserving language changes, reload and 320px login accessibility. **33 guest browser checks** and **91 web units**, fixture verification, typecheck and production build also pass. The backend is unchanged by this navigation refinement.

Visual review inspected synthetic-data desktop login and empty-account screenshots. Local capture test data used a separate disposable database; the real Resend preview was preserved and then rebuilt with the updated UI. No real verification emails were sent during this work. Human review, hosted CI and public deployment remain pending. See [page behavior and scope](../design/account-pages.md).
