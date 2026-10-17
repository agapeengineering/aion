# Aion — web release specification

Version: **1.2.0**. Status: reviewed R1 scope/behavior implemented for early web 0.1.0; verification scope/remaining human-device checks are recorded separately. Maintained by Agape Engineering. Updated 2026-10-17. See the [web verification record](../testing/web-verification.md) and [release notes](../releases/0.1.0.md) for actual evidence and remaining limits.

This document is the authoritative discovery brief, product definition, requirements and verification map for the first web release. See the [product overview](../product/README.md) and [architecture overview](../architecture/overview.md). Acceptance targets describe intended behavior, not measured results or shipped features.

## Problem and product rationale

A life calendar that requires deliberate visits can be easy to forget. Aion aims to make finite time visible during ordinary device use, with a week grid, a clearly labeled chosen lifespan and simple time summaries. Native widgets and supported wallpaper updates are the longer-term ambient surfaces; the first web release offers manual wallpaper export.

The product is a small free/open-source utility, designed for personal reflection. It does not claim a novel market, predict death or require growth/revenue targets. Its success is a usable, reproducibly released product on each advertised platform. Public downloads and capabilities must match actual release evidence.

### Alternatives and tradeoffs

| Direction | Benefit | Limitation |
| --- | --- | --- |
| Use an existing application or contribute upstream | Avoids maintaining another application | The experience and ambient capabilities may differ from this product's intended scope. |
| Static wallpaper/manual export | Simple, private and visible during device use | Requires manual replacement to stay current; this is the first web release's ambient bridge. |
| Local application with native ambient surfaces | Customizable presentation and supported automatic refresh | Requires platform-specific implementation, distribution and maintenance. |

Aion follows the third direction incrementally, beginning with web and manual export. Ambient usefulness remains a hypothesis to validate in actual use; no market-demand, retention or user-study result is asserted here.

## Product definition

### Product promise and journeys

A quiet reminder that life is finite, with the present week as its anchor. English and Spanish have equal functional scope.

**R1 journey:** open the web app → enter birth date and a chosen lifespan (90 years initially) → view the life grid and lived/remaining statistics → adjust settings or hide remaining numbers → export a simple PNG → optionally apply it as wallpaper manually. Reopening in the same browser restores local settings. Another browser/device requires entering the settings again. Reset starts over.

**Later native journey:** install the app → configure once → add a supported widget or enable supported wallpaper integration → encounter updated information during normal device use. Device/OS constraints must be validated. R1 manual export does not fulfill the entire native ambient promise.

### Priorities

| Priority | R1 scope |
| --- | --- |
| Must | Birth date and editable 90-year horizon; lived/current/future grid; all seven lived/remaining time units; weeks default; ticking approximate countdown with pause/resume; hide remaining figures; local save/edit/reset; EN/ES; small original phrase bank; simple local PNG export; accessible responsive UI; source/license/README, privacy explanation, support route and verified public deployment. |
| Should | Polished export presets/safe margins and restrained visual refinement, after correctness and accessibility. |
| Later | Automatic wallpaper updates, native widgets/local notifications, iOS/Android/macOS/Windows/Linux distribution, native settings import/export, installable offline PWA, dark theme and richer export controls. |

Excluded: backend, authentication, accounts, cloud sync, AI, coaching, journals, goals, streaks, advertising, paid tiers/subscriptions, demographic/medical life-expectancy prediction and scheduled web notifications. No third-party product analytics is planned.

Web ships first. Native release sequence and supported device versions are determined per release; the roadmap is not a simultaneous launch promise. Development uses small reviewable changes, without a fixed launch deadline.

### Release acceptance and ownership

Agape Engineering maintainers own requirement review, release decisions and maintenance. R1 requires verified Must requirements, a public working application and a usable exported wallpaper. Native platforms are advertised only after usable downloadable artifacts exist and supported ambient behavior has real-device evidence.

Original source is [MIT licensed](../../LICENSE). Runtime React and self-hosted fonts retain the licenses in [third-party notices](../../THIRD_PARTY_NOTICES.md). Review licenses/notices when dependencies or assets change. Hosting/deployment/recovery, release support contact and later platform signing/distribution arrangements must be ready before their applicable releases.

## Software requirements

Requirement IDs are stable. Every row is Must/R1 unless explicitly marked Later. Calendar/clock fixtures and a coded prototype must precede the affected production implementation.

| ID | Actor/trigger and required behavior | Acceptance and verification |
| --- | --- | --- |
| FR-001 | First visit asks for birth date and chosen lifespan; horizon defaults to 90 years. | No personal birth date is prefilled. Empty/invalid/future dates and nonpositive/noninteger horizon values show EN/ES field errors; no invalid model is saved. A date equal to today is valid. Valid input shows results. Test form and domain validation. |
| FR-002 | Editing birth date/horizon recalculates consistently. | Gregorian civil dates; horizon is the birth anniversary plus the chosen number of years. February 29 maps to February 28 in non-leap years. Values outside the date engine's documented supported range produce a field error, never a crash. Fixtures cover leap days and month/year boundaries. |
| FR-003 | Render lived, current and future week blocks. | Blocks begin at birth and advance by seven civil days. Total cells = ceiling(days from birth to horizon / 7), with a final shortened cell if necessary. For each cell interval [start, end), elapsed if today >= end, current if start <= today < end, future otherwise. No current cell once today >= horizon. A text legend/current-interval description agrees with the grid. Test birth day, six/seven days, final partial interval and horizon boundary. |
| FR-004 | Show lived and remaining statistics in all seven requested units, defaulting to weeks. | Statistics section makes all seven units available for both directions, while weeks is the primary summary. Unit changes do not alter the model. Years/months are completed calendar units, weeks completed seven-day units, days civil-date differences; hours/minutes/seconds are approximate clock-aware totals, including the current time of day, and tick while visible (FR-009). Test every unit and label in both languages. |
| FR-005 | At/past horizon, retain a useful lived-time view. | Remaining values clamp to zero; lived values continue from birth to today without being capped at the horizon. Explain that the chosen horizon has passed and offer editing, without predicting death or showing negative values. Test exact boundary and older-than-horizon input. |
| FR-006 | Let users hide remaining-time figures. | Toggle removes remaining numbers from visible statistics, accessible descriptions and exported PNG while retaining lived statistics and the horizon assumption. It does not hide future grid cells; the UI describes it as hiding figures. Persist the preference. Test DOM/accessibility output and exported image. |
| FR-007 | Save settings locally and restore on reopen. | Store versioned birth date, horizon, language, primary unit and remaining-figure visibility. Reload restores valid settings. Denied/full/corrupt/unsupported storage warns clearly and retains a usable in-memory session; it never claims that saving succeeded. Recoverable malformed data does not crash or silently overwrite unknown newer data. Test storage failures. |
| FR-008 | Edit and reset local settings explicitly. | Edit preserves unrelated preferences. Reset asks for confirmation; cancel leaves data intact, confirm clears Aion-owned storage/session data and returns to onboarding. Other origin storage is untouched. Existing downloaded PNGs are unaffected and explained. Test edit, cancel, reset, reload. |
| FR-009 | Show a ticking countdown while visible and recover correct values after interruption. | Update approximate seconds once per second while the page is visible and running; lived time advances and remaining time decreases, with minutes/hours derived from the same clock snapshot. Derive values from the current clock, never accumulated timer ticks. Recompute on local date change, foreground/resume and detected timezone/clock change. Hidden tabs may suspend ticking; immediately show current values on return. Clamp remaining time to zero at/past the horizon. Supply a pause/resume display control; resume jumps to current values. Do not announce every tick to screen readers or animate the grid each second. Test fake-clock ticks, pause/resume, sleep/background recovery, midnight, clock/timezone changes and horizon crossing. |
| FR-010 | Supply equivalent EN/ES behavior and original read-only phrases. | Language switch retains personal settings and updates controls, statistics, errors, export labels and privacy/assumption copy. Small original bilingual phrase bank lives in source; no journal input, notifications or attributed quotations. Exercise both locales with long text. |
| FR-011 | Export a simple PNG entirely on device. | A basic phone/desktop output choice and preview produce a readable PNG of the current grid, reference date, assumption and chosen visible summary. Respect FR-006; omit literal birth date from the image. No personal generation request or automatic wallpaper installation. Display save/export failure with retry while preserving settings; test dimensions/decoding, both locales and no personal network traffic. Exact preset dimensions are design-stage decisions. |
| FR-012 | Publish an honest usable web release. | Actual HTTPS URL, accessible EN/ES app, linked source/license/README, data-handling explanation and monitored support route exist. Reproduce the build at its release revision, retain rollback instructions and verify core setup/reload/reset/export on the actual deployment. No native download links until real releases exist. |
| FR-013 | Later native ambient surfaces work without reopening the main app. | Later, not R1: on each advertised device/OS, setup then demonstrate the supported widget or wallpaper advancing across a local date boundary without opening Aion. Include sleep/resume, settings changes and platform limitations. Real-device evidence is required; no automatic iPhone wallpaper capability is assumed. |

### Calendar definitions and invariants

Exact inputs, supported date range, validation codes, rounding, direct calendar addition, horizon/grid intervals, nominal ticking totals and pause/visibility/export snapshot semantics are defined in the subordinate [calendar and clock contract](calendar-clock-contract.md) version 1.0.0. The [shared JSON corpus](../../tests/fixtures/calendar-clock/v1.json) and [audit record](../testing/calendar-clock-fixtures.md) make these rules executable as expectations for future implementations.

The reviewed behavior remains: civil-date day/week/calendar totals, approximate nominal 24-hour-day subday totals that tick from the local clock, half-open birth-anchored week blocks, and zero remaining values on/after the chosen horizon. DST/clock/timezone changes can jump approximate values; the contract specifies that behavior rather than assuming an exact birth/death instant. No production implementation is verified by the standalone corpus audit.

### Quality, privacy and compatibility targets

The following are adopted acceptance targets, not measured results. Record any later change as a requirement change.

| ID | Requirement and measurement conditions | Verification |
| --- | --- | --- |
| NFR-001 | No birth date, horizon or derived personal statistics in URLs, app requests, telemetry or logs. Self-host fonts and ship phrase/assets locally. Hosting access logs are disclosed separately. | Inspect network and console during setup/edit/reload/export/reset in both languages, including error cases. |
| NFR-002 | Applicable WCAG 2.2 AA behavior for the R1 web journey, with keyboard operation, visible focus, labeled errors, non-color grid cues, screen-reader summary and no per-cell tab-stop wall. At 200% text zoom and 320 CSS-pixel width, controls/content remain usable; a documented scrollable grid detail may be used. | Manual keyboard/VoiceOver checks plus automated checks and contrast/layout inspection; no claim of certification from scans alone. |
| NFR-003 | Browser baseline: stable Safari/iOS Safari, Chrome, Edge and Firefox available at release; core journey works on iPhone Safari and MacBook Safari, with Chrome/Firefox desktop checks. Record exact versions/devices before claiming support. | Browser/device matrix covering setup, save/reload, edit, reset, locales and PNG save. Emulation alone does not establish physical-device compatibility. |
| NFR-004 | Local response budget: on a reference MacBook Air M1 (record OS/browser versions with results), a 90-year grid updates within 200 ms after valid settings change, excluding download/save dialogs, measured with a production build over 20 repetitions. Use lightweight once-per-second text updates for running visible counters, with no frame loop or per-second grid redraw; paused/hidden counters need no ticking work. | Record timings and revision; investigate missed target. This is not a remote-uptime SLO. |
| NFR-005 | Local operations remain usable if the network disappears after app assets load. First-ever offline load/installability is not promised for R1. There is no cloud backup or cross-device recovery; cleared browser data is recoverable only by re-entering settings. | Disconnect-after-load journey; clear/deny storage checks and truthful privacy/help copy. |

### State, failure and data boundaries

States: first visit → valid configured view ↔ editing; invalid input stays in the form; storage failure keeps a session-only configured view; confirmed reset returns to first visit. Export failures do not discard the model. Birth date is private personal data; store only on the user's device until reset/browser removal, with no server retention. Downloaded wallpaper remains under the user's control.

No auth/session token, API contract, backend retry, database migration, account deletion or server restore requirement applies because there is no user-data service. Local schema evolution must validate versioned settings. Multi-tab behavior: react to a valid storage event, use the latest successfully stored complete settings record, and reset on a clear event; no merging or cross-device sync. Preserve current in-memory data if another tab supplies malformed/newer unsupported data and show a warning. Test these events before release.

## Verification map and evidence status

| Test group | Requirements | Planned evidence |
| --- | --- | --- |
| Calendar fixtures | FR-001–005, FR-009 | Shared input/output cases for date validation, leap/month ends, block boundaries, horizon passed and date/timezone changes. Define shared fixtures before implementation, including ticking, pause/resume and background recovery. |
| Settings/browser journey | FR-001–010, NFR-005 | Setup/edit/reload/reset/hide/unit/locale/storage failure/multi-tab end-to-end checks. |
| Export and privacy | FR-006, FR-011, NFR-001 | Decodable PNGs, dimension/content inspection and network/log checks. |
| Interface and compatibility | FR-003–012, NFR-002–004 | Coded-prototype review, mobile/desktop browser matrix, accessibility and measured local response. |
| Release | FR-012 | Source/license, exact revision/build, authorized deployment, rollback, live smoke and support links. |
| Ambient native validation | FR-013 | Future physical-device date-refresh evidence; not a web gate. |

The calendar/clock corpus arithmetic and display-sequence expectations have passed a standalone fixture audit (see linked audit record). The application consumer and web journeys are implemented and checked within the scope recorded in [web verification](../testing/web-verification.md); physical-device/human validation remains explicitly **pending**. A test plan is not a passing test. Release quality requirements remain gates on software; they need not be executed to review this specification.

## Design decisions

| Decision | Rationale or implication |
| --- | --- |
| Local-only settings; no accounts/cloud sync | Two inputs recreate the core timeline in another browser; no server stores private user data. |
| Editable 90-year default | The horizon is a user-chosen visualization assumption, not a prediction. |
| Birth-anchored seven-day blocks | Grid calculations must not silently equate a calendar year with 52 weeks. |
| Seven summary units; weeks primary | Make scale explorable while labeling date-only approximations clearly. |
| Ticking countdown | Visible subday values derive from a current clock snapshot, with pause/resume and interruption recovery. |
| Hide remaining numbers, retain future cells | Controls the numerical display without removing the life-grid structure. |
| Manual web PNG export; later native automatic surfaces | Keeps web useful while respecting platform-specific integration requirements. |

## Remaining design and verification work

- Calendar/clock contract, shared expectations and TypeScript consumer tests are implemented and checked.
- Coded prototype and implemented EN/ES states are agent-inspected and browser-tested; the product-owner walkthrough remains pending.
- Pinned web toolchain, lockfile and local/CI checks are supplied; record actual CI run evidence per release.
- Cloudflare Static Assets is selected in ADR-0001, with deployment/rollback/recovery and operating ownership documented.
- Observe the early web release and complete remaining human/device validation before scheduling native integrations.
- Validate native ambient behavior on actual devices and record limitations before advertising it.

Completed versus pending scope is distinguished in the linked verification/release records. Numerical quality targets and product changes are maintained alongside affected tests and design decisions.

## Revision history

- 1.0 — Initial reviewed R1 baseline: local-only web application, seven time units, ticking countdown and manual PNG export.
- 1.0.1 — Editorial cleanup for public contributors; removed internal task references, personal planning context and private workflow details. Requirement IDs and product behavior unchanged.

- 1.1.0 — Specify the subordinate calendar/clock contract, supported input range and shared golden fixtures with an independent audit; no application implementation or release implied.

- 1.2.0 — Implement early web R1 with reproducible checks, explicit browser-engine evidence and remaining human/device validation; adopt Cloudflare Static Assets in ADR-0001.
