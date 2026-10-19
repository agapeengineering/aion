# Dedicated login and account pages

Navigation update accepted 2026-10-18. Implemented locally in the opt-in account build; public R1 is unchanged. Passwordless email-code authentication and the [profile sync contract](../api/profile-contract.md) remain unchanged.

| English | Spanish | Purpose |
| --- | --- | --- |
| `/login` | `/es/login` | Email, then eight-digit verification code; no password |
| `/account` | `/es/account` | Signed-in identity, calendar choice and sync status, sign-out |
| `/` | `/es` | Immediately usable guest/account calendar |

Account navigation uses a normal link with client-side navigation for unmodified clicks. Direct links, reload, browser Back/Forward and opening in another tab work through the existing SPA fallback. A session check resolves `/account` to `/login` when signed out and `/login` to `/account` when signed in, replacing the history entry to avoid redirect loops. Verification ends on the account page. No email, code, session token or arbitrary return destination enters the URL. Language switching preserves the page. Page changes update the document title, move focus to the main heading and scroll to the top; code entry keeps its existing input focus behavior.

The sync controller stays mounted across calendar/account navigation, retaining pending edits even if local storage is unavailable. Back-to-calendar and brand links do not reload the app. Account UI is omitted when the account build flag is off; guest use makes no account API requests.

## Calendar states

- Neither calendar exists: a short create-calendar explanation and one primary setup action; no empty comparison cards. Setup returns to the calendar's birth date/lifespan form with account saving selected.
- Only guest data exists: show the device calendar and an explicit save-to-account action, with the option to continue locally.
- Only account data exists: signing in restores it; show a compact account summary and sync status.
- Both calendars differ: show both, choose account or replace it with the device; replacement retains its second confirmation and revision checks.
- Both match: offer use-account without redundant comparison or replacement controls.
- Already selected: show the account summary and saved/pending/error state. After an account reset, setup remains available.
- Conflict: retain both versions and explicit keep/reapply actions. Show retry when a refresh fails or cache access needs attention, rather than as a permanent healthy-state control.

Guest data remains separate; login alone never uploads it. Sign-out warns before discarding pending account edits. Reminders and remaining account lifecycle controls will be added only when implemented.

## Verification

`tests/e2e/account-pages.spec.ts` covers direct/protected routes, EN/ES page-preserving language changes, Back/Forward, reload, narrow layout and automated accessibility. Updated authentication tests verify empty-account setup, account persistence after reload and signed-in login redirection. Updated sync tests cover device-only import, separate-browser restoration, a different-guest comparison, concurrent open forms, offline conflicts, reset and guest restoration after sign-out. Capture mail is synthetic and isolated from real Resend configuration. [Local setup](../development/account-setup.md).

## Account management refinement — 2026-10-18

The account page retains the paper/serif design and profile choice panel. Beneath it, an active-session list shows creation/last-active times and a current-session label, without fingerprinting/IP labels. Other sessions can be revoked individually; sign-out everywhere has an explicit confirmation that includes unsynced edits.

A separate data section offers export and deletion. Both open an inline confirmation region, focus its heading, then use a fresh eight-digit email code. Reverification rotates the current credential without changing account identity and lasts ten minutes, including after reload. Export downloads saved server JSON; deletion additionally requires a checked irreversible-action acknowledgment. Confirmed deletion/revoke-all returns to login with a clear status message and preserves the separate guest calendar. Offline and failed actions remain visibly unconfirmed; no destructive offline queue.

Scheduled reflections are deferred. Normal account builds do not render reminder enrollment. The code remains behind an explicit capture-test flag for future resumption. Human walkthrough and actual-device checks remain distinct from browser-engine automation.
