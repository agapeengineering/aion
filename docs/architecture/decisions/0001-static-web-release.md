# ADR-0001: Local web application on Cloudflare Static Assets

Status: accepted. Date: 2026-10-17. Maintainer: Agape Engineering.

## Context

R1 is a private-on-device life calendar, with no user-data service or cross-device accounts. It needs a public static host, reliable HTTPS, reproducible builds and safe rollback. The web implementation must match the calendar/clock contract and keep both languages and fonts available locally after loading.

## Decision

Use React 19 + TypeScript + Vite in `apps/web`, with pure calculation/display-state logic in `packages/calendar`. Plain CSS variables implement the product's bone, charcoal and terracotta palette. Use a memoized canvas-based grid with separate accessible text and keyboard week selection: this avoids thousands of interactive DOM elements and per-second grid painting.

Deploy the built `apps/web/dist` directory through Wrangler 4 to Cloudflare Workers Static Assets. No custom request handler, API bindings, database, account service or analytics is added. English is `/`; `/es` has a static Spanish HTML entry and the same bilingual application. Self-host Inter/Geist Mono and bundle their licenses. The content policy restricts execution to local scripts/fonts and disables app connections; blob image URLs support local export. Inline styles are allowed for canvas dimensions; inline scripts are not allowed.

Production is `aion.agape.engineering` with an additional platform URL; staging uses a separate named static deployment. Version metadata identifies the source revision and whether the build was dirty. Production must be built from a clean committed tree. Domain/account access was checked before publication; unrelated DNS/services are untouched.

## Alternatives

- Shared self-managed host: useful for operational learning, but unnecessary maintenance for this local-only static product; not adopted here.
- Account/sync service: introduces data custody and recovery obligations without improving the core two-input calculation; excluded.

## Cost and ownership

No new paid integration, database, storage product, domain purchase or account enrollment is selected. Static delivery uses the existing Cloudflare account/zone and its applicable asset allowance. This is not a billing cap or a claim that every Cloudflare feature is free. Review actual account usage/costs monthly; do not enable paid runtime features without a new decision. Maintainers own deployment, support via GitHub Issues, dependency review and recovery. Both static environments can be rebuilt from source without private user data.

## Recovery and limits

Promote the same local built assets after staging checks; retain exact revision/version metadata. Rehearse static rollback on staging and use the deployment runbook. There is no server-side user state or database restore. This release does not promise an offline first visit, native widgets/automatic wallpaper, physical-device coverage, high availability or exact biological elapsed/remaining time. Revisit hosting if runtime requirements or actual costs change.
