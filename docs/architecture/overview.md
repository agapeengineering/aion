# Architecture overview

Status: initial design boundary; implementation, hosting and detailed design remain pending. Maintainer: Agape Engineering. Date: 2026-10-17.

Aion is one product repository with independently buildable clients as they are introduced. Web starts with React, TypeScript and Vite. No backend, API, authentication, account, database server, cloud sync or queue is required. No package versions/toolchain are selected by this documentation baseline.

Browser inputs and local settings feed calendar/clock domain logic, grid/statistics UI and local PNG generation. Personal data stays inside the browser. Treat local settings as untrusted input; validate schema versions and data. Only static application assets are requested; no private dates/settings in requests, logs or URLs. Self-host fonts when added.

The ticking display derives values from current local clock snapshots, not an accumulated interval count. Date-based domain calculations and visible per-second text updates are separate; do not redraw the grid every second. Refer to FR-009 and the calendar definitions in the reviewed specification.

Use a small pure calendar module with language-neutral fixtures; UI, storage and export depend on it. Keep dependencies directed toward the domain module. Do not share native calculation code through FFI just to reuse date formulas; future native ports can use shared fixtures.

## Decisions still needed

- Static hosting: select the deployment target and record cost, operating ownership, deployment/rollback and recovery before provisioning.
- Calendar model: executable calendar/clock fixture definitions and supported date range.
- Interface design: versioned coded prototype, responsive grid grouping, export dimensions and review findings.
- Build and verification: pinned web toolchain, lockfile, clean-checkout checks and CI.
- Future native phase: device baselines, ambient feasibility and actual platform scheduling.

Record accepted architecture decisions in `docs/architecture/decisions/`. No deployment or paid account action is authorized by this document.
