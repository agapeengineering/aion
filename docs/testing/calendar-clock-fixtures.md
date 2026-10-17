# Shared calendar and clock fixtures

Corpus: [v1.json](../../tests/fixtures/calendar-clock/v1.json). Contract: [calendar-clock-contract.md](../requirements/calendar-clock-contract.md) version 1.0.0. Related behavior: [R1 specification](../requirements/web-release-specification.md) FR-001–005, FR-009 and snapshot consistency under FR-011.

## Purpose and format

The corpus is language-neutral golden input/output data. It is not production domain logic, a web/native implementation or a complete application test harness. All dates are synthetic. No internal tracker or private planning context is needed to consume it.

Top-level keys:

- `formatVersion`: integer 1; identifies the JSON layout.
- `contractVersion`: `1.0.0`; identifies the calculation rules.
- `description`: corpus purpose.
- `cases`: uniquely named normalized input/error or input/full-result examples. Each has `id`, nonempty `requirements`, `input`, `expected`; some have optional `clockSource`.
- `traces`: uniquely named event sequences with `id`, nonempty `requirements`, `steps`. Each step has `event`, `caseId`, `expected`. References resolve to successful snapshots in `cases`.

Each successful result and error has the exact shape documented in the contract. `clockSource` carries a UTC `instant`, IANA `timeZone` and `utcOffsetSeconds`; it explains how the injected local clock was obtained for adapter checks. The arithmetic layer needs only `input.clock`. A port should test clock-source conversion separately from pure date calculations. The two DST snapshots can represent different elapsed instants even when local wall time repeats.

Trace expected state uses case-ID references to the independently audited numeric result. `displaySubdayCaseId` selects only the displayed ticking hours/minutes/seconds; it does not freeze the date-based model. `exportCaseId` identifies one fresh full result so an exporter cannot mix units sampled on opposite sides of midnight. Hide-remaining filtering and actual image rendering remain separate tests.

## Coverage and requirement mapping

| Group | Examples | Requirement IDs |
| --- | --- | --- |
| Birth/date validation and ordered failures | Empty/wrong-type/malformed/future birth; invalid leap date; invalid lifespan; clock failures; competing errors | FR-001, FR-002 |
| Calendar arithmetic | Jan 31 direct-month clamping, leap anniversaries, century rules, 90-year horizon | FR-002, FR-004 |
| Supported range | Year 0001; horizon at 9999; horizon overflow; reference long past horizon; unsafe integer | FR-001, FR-002, FR-005 |
| Grid boundaries | Birth day, six/seven days, final partial cell, whole-week horizon, exact horizon and beyond | FR-003, FR-005 |
| Clock totals | Consecutive seconds; minute/hour/midnight carry; horizon minus one second/at/past | FR-004, FR-005, FR-009 |
| Lifecycle/display | Pause over midnight, paused foreground, hidden catch-up, long sleep without ticks, clock correction | FR-009 |
| Clock adapter | US Pacific spring/fall DST and same instant in Pacific/Japan zones | FR-009 |
| Snapshot consistency | Export across midnight and a fresh export during paused display | FR-009, FR-011 |

## Reproducible audit

The maintainer-only audit uses Node built-ins and requires no package installation:

```sh
node tools/verify-calendar-clock-fixtures.mjs
node tools/verify-calendar-clock-fixtures.mjs --self-test
```

The second command also checks that the audit rejects five corrupted corpus variants: a wrong expected count, a wrong timezone offset, a wrong trace state, a duplicate snapshot ID and an unknown requirement ID. It changes only in-memory copies, never the committed golden file.

Prerequisites: Node with ESM/`structuredClone`/`node:assert` and Intl data for the named IANA zones; the recorded run used Node v26.0.0. This is an audit utility, not a choice of the eventual web toolchain or a replacement for its lockfile/CI. Run it from any directory; it resolves repository files relative to itself.

### How expected results were checked

1. The initial golden results were calculated once using Python 3.14.7 standard-library Gregorian `datetime.date` ordinals/date arithmetic and `calendar.monthrange`. Clock-source metadata used `zoneinfo`.
2. The separate delivered JavaScript audit computes civil ordinals using Gregorian leap-cycle integer arithmetic; it finds anniversary totals with binary search and inverts ordinals independently. It does not call the Python generator or use production application code. Clock-source metadata is cross-checked using Node Intl.
3. Hand-derived anchors supplement both methods: January 1→8 is seven days/one week; January 31→February 28 (2001) is 28 days; January 31→March 30 is only one completed direct-add month; 2000-01-01→2025-01-01 is 9132 days (25×365 plus seven leap days); 2025→2090 is 23741 days (65×365 plus sixteen leap days); the second immediately before the horizon has one second remaining; 2001→2029 spans an exact number of weeks.
4. The audit checks full expected objects, nonnegative remaining totals, grid-count partitions, named requirement references, trace transitions, duplicate IDs and timezone metadata. It rejects corrupted data in its self-test.

The one-time generator is intentionally not a routine golden-file update tool. Review contract changes and independently recompute affected expectations; never replace golden outputs with whatever an implementation currently returns. Arithmetic agreement between two audits is useful evidence, not proof of all possible dates or future application correctness.

## Audit record — 2026-10-17

- 66 snapshot cases; 12 traces containing 40 steps; six zoned source clocks.
- Both audit commands passed with Node v26.0.0, ICU 78.3 and timezone data 2026a.
- Five deliberately corrupted in-memory datasets were rejected.
- Expected values were independently cross-checked; no production TypeScript/Swift/Kotlin consumer, browser UI, actual timer, PNG renderer or native device behavior has been tested.
- UI content/visibility, storage, accessibility, supported browsers, performance and real-device release gates remain pending. No application release or build CI is claimed.

## Future consumer checks

A TypeScript, Swift or Kotlin implementation should load the same corpus, inject its local clock values, compare every success/error field, resolve every trace reference and check the display controller separately. Add true lifecycle and accessibility tests around the actual UI. Keep requirement IDs in failure reports. Record the tested implementation revision and environment; passing this standalone audit does not imply a consumer passed.
