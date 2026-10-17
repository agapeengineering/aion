# Web verification — 0.1.0

Date: 2026-10-17. This record describes executable and agent inspection evidence, not a certification or human acceptance.

## Automated checks

- Calendar fixture audit: 66 snapshots, 12 clock traces/40 steps, six zoned source clocks; five deliberately corrupted datasets rejected.
- Application unit tests: **82 passed**, including every shared calendar snapshot/display trace and storage validation/denied-write/newer-format handling.
- TypeScript check and production build: passed with Node 24.19.0 and pnpm 11.25.0.
- Browser suite: **33 passed on Cloudflare HTTPS staging and again on the production Workers hostname**, 11 journeys in each of Chromium, Firefox and WebKit (Playwright 1.64.1).
- EN/ES setup, invalid/future dates and focus, edit/reload, privacy/modal escape, reset cancel/confirm and preservation of unrelated origin storage.
- Seven counter units, ticking/pause/resume/date catch-up, remaining zero beyond horizon and exact final-week interval exploration.
- Hidden remaining figures persist and are omitted from statistics/accessibility summary/export; a real downloaded PNG has valid signature/dimensions. Phone and desktop previews have their specified dimensions.
- Denied writes, unknown newer schema preservation, local tab synchronization and offline-after-load editing/export.
- Network inspection checks only same-origin HTTP/assets and local same-origin blob previews, no personal input in requests and no page exceptions.
- Selected axe WCAG 2 A/AA and 2.1 AA checks pass for initial/configured Spanish layouts at 320 CSS pixels in all three engines. This is automated evidence only.
- Runtime dependency audit: no known vulnerabilities reported by `pnpm audit --prod` at verification time.

The first browser pass found a low-contrast statistics label, which was corrected. WebKit cannot load HTTP Wrangler assets with the production `upgrade-insecure-requests` policy; the same built app passes over real HTTPS without weakening that policy. Vite-preview tests alone do not establish production-header behavior.

## Performance and visual inspection

On an Apple M1 / macOS 27.2 using Chromium 156.0.8078.4 and a production build, measured form submit through two animation frames across 20 90-year-calendar updates: maximum **33.1 ms**, mean **28.3 ms**. This is a conservative visible-update measure below the 200 ms acceptance budget; it is not a network-load benchmark or promise for all devices.

Agent inspected onboarding/desktop calendar, Spanish mobile/narrow layouts and actual desktop wallpaper output. The per-second counter does not repaint the canvas grid. Fonts are self-hosted and licenses are bundled.

## Requirement traceability

| Requirements | Evidence | Status |
| --- | --- | --- |
| FR-001–005 | Shared corpus consumer tests + browser validation/horizon/week exploration | Passed in automated scope |
| FR-006 | Persisted toggle, DOM absence, canvas accessibility summary and inspected exported text/PNG | Passed in automated scope |
| FR-007–008 | Unit storage failure/format tests + reload/reset/cross-tab browser flows | Passed in automated scope |
| FR-009 | Shared controller sequences + real app fake-clock ticking/pause/resume | Passed in automated scope |
| FR-010 | EN/ES UI/error/content/route checks | Passed in automated scope; human copy review remains |
| FR-011 | Actual PNG download/signature/dimensions, both formats, offline and hidden-figure checks | Passed in automated scope |
| FR-012 | CI/source/license/deploy/rollback/live evidence | See release record for actual deployment |
| FR-013 | Native ambient integration | Later; not claimed |
| NFR-001 | Self-hosted assets, request inspection, CSP, no backend/analytics | Passed in tested journeys |
| NFR-002 | Axe + keyboard/modal/focus/contrast/visual inspection | Partial: VoiceOver and human accessibility review pending |
| NFR-003 | Chromium/Firefox/WebKit engines, responsive 320px and 390px views | Partial: physical iPhone and actual Safari device matrix pending |
| NFR-004 | 20 measured M1 updates, no per-second grid paint | Passed for recorded workload |
| NFR-005 | Offline-after-load and browser reset/storage denial | Passed in tested journeys |

## Remaining validation

The product-owner walkthrough, actual physical iPhone/Safari/VoiceOver testing, browser zoom checks and seven-day personal ambient-use exercise have not happened. Native applications, widgets, automatic wallpaper, offline first-load installation and 24/7 uptime alerting are not part of this web release. Record these limits in public release notes rather than presenting browser emulation or agent inspection as human/device validation.
