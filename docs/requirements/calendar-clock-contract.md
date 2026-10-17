# Calendar and clock calculation contract

Contract version: **1.0.0**. Format version: **1**. Status: specified and fixture-audited; application implementations pending. Scope: calculation detail for [R1 requirements](web-release-specification.md) FR-001–005 and FR-009, plus snapshot consistency under FR-011. This contract refines those requirements without adding a backend or requesting a birth time.

## Inputs and supported range

A calculation accepts the following normalized, language-neutral data:

```json
{
  "birthDate": "2000-01-01",
  "lifespanYears": 90,
  "clock": { "date": "2025-01-01", "time": "12:00:00" }
}
```

- `birthDate` and `clock.date`: exact ASCII `YYYY-MM-DD`, valid proleptic Gregorian dates from `0001-01-01` through `9999-12-31`, with no year zero. No locale parsing, whitespace trimming or timestamp parsing in this layer.
- `lifespanYears`: a positive JSON integer within the JavaScript safe-integer range (at most 9007199254740991); strings, booleans, null, fractions and non-finite numbers are invalid. The horizon year must also be at most 9999. The form supplies the 90-year initial default; the calculation layer does not silently replace missing/invalid input with 90.
- `clock.time`: exact ASCII `HH:mm:ss`, 00:00:00–23:59:59; no fractions, leap seconds or `24:00:00`.
- The clock adapter obtains one current instant and converts it to a local date/time in the device's current zone. Pass one coherent snapshot into the calculation; never read the clock separately for different counters. The pure model itself does not read the system clock, resolve a zone, access storage, localize or schedule timers.
- The date range is an arithmetic limit, not a promise that the UI renders hundreds of thousands of cells simultaneously. The performance acceptance workload remains a 90-year horizon. Design the overview so larger valid horizons do not force an unbounded interactive DOM.

Examples use synthetic dates only. Personal dates must not appear in requests, telemetry, diagnostic logs or fixture files.

## Validation and errors

Return the first error in this order. Validation occurs before deriving statistics or allocating a grid. Errors are stable codes; the UI maps them to localized field text.

| Order | Condition | Result |
| --- | --- | --- |
| 1 | Missing/null/malformed/invalid local date or time | `{"error":{"field":"clock","code":"INVALID_CLOCK"}}` |
| 2 | Missing/null/malformed/invalid birth date | `{"error":{"field":"birthDate","code":"INVALID_BIRTH_DATE"}}` |
| 3 | Birth date later than the snapshot date | `{"error":{"field":"birthDate","code":"FUTURE_BIRTH_DATE"}}` |
| 4 | Missing/invalid lifespan integer | `{"error":{"field":"lifespanYears","code":"INVALID_LIFESPAN"}}` |
| 5 | Birth year plus lifespan exceeds 9999 | `{"error":{"field":"lifespanYears","code":"HORIZON_OUT_OF_RANGE"}}` |

A birth date equal to the snapshot date is valid. These codes define normalized domain input; a form may separately report multiple missing fields. An invalid clock is an environment failure, not a reason to ask the user to change their birth date. No partial success result accompanies an error.

## Calendar operations

Let B be birth date, T the local snapshot date and H the horizon. Adding the lifespan to B preserves month/day except that February 29 clamps to February 28 when the target year is not leap. Add directly from B, not through repeated year additions. Gregorian leap years are divisible by 4 except centuries not divisible by 400.

`days(A,Z)` is the difference in Gregorian civil-date ordinals. Do not obtain it by dividing local elapsed milliseconds by 86400000: daylight-saving transitions can have a different elapsed duration.

Completed calendar years from A to Z are the largest nonnegative n such that A plus n years is <= Z, clamping to the target month's last day. Completed calendar months use the same rule with direct month addition from the original A. They do not iterate a previously clamped date: January 31 + two months is March 31, not March 28. Calculate each unit separately; totals are not a decomposition to add together.

| Total | Lived | Remaining |
| --- | --- | --- |
| Years | Completed calendar years B→T | Completed calendar years T→H, or zero when T >= H |
| Months | Completed calendar months B→T | Completed calendar months T→H, or zero when T >= H |
| Days | `days(B,T)` | `max(0,days(T,H))` |
| Weeks | `floor(livedDays/7)` | `floor(remainingDays/7)` |

The date-based remaining days/weeks/calendar units describe civil-date distances. They need not equal the floor of the ticking seconds divided by a fixed unit duration. For example, at 23:59:59 on the day before H there is one civil day of distance but one approximate second remaining. Make these semantics legible in the interface rather than implying precision the inputs do not contain.

## Ticking approximate totals

From the same snapshot, let `q = hour*3600 + minute*60 + second`:

```text
livedSeconds     = livedDays*86400 + q
remainingSeconds = max(0, days(T,H)*86400 - q)
hours            = floor(seconds/3600)
minutes          = floor(seconds/60)
```

Use the corresponding lived/remaining seconds for each total. Hours/minutes/seconds are integer nominal 24-hour-day approximations, not physical elapsed times or a prediction. No actual birth/death instant is known. Values fit within safe integer bounds over the supported date range.

At ordinary consecutive wall-clock seconds, lived seconds increase by one and remaining seconds decrease by one until zero. At DST jumps, repeated hours, timezone changes or manual clock changes they can jump, including backward. That behavior is intentional in the reviewed civil-clock model; do not accumulate interval ticks or silently switch to an elapsed-instant formula. Native ports must use the same convention. An exact-instant model would require a recorded requirement change.

While visible and running, refresh numeric text about once per second, derived from a fresh snapshot. The timer is a refresh opportunity, not the time source. Do not require every tick to run in a sleeping/hidden browser. Refresh immediately on foreground/show/resume and handle local date/timezone changes from the current clock. Do not animate/redraw the grid every second or announce every numeric update to screen readers.

## Grid and horizon boundaries

Let `D = days(B,H)` and `N = ceil(D/7)`. Cell indices are zero-based, from 0 through N−1. Cell i covers the half-open interval `[B+7*i, min(B+7*(i+1),H))`.

- If T < H: `elapsedCells=floor(livedDays/7)`, `currentIndex=elapsedCells`, `futureCells=N-elapsedCells-1`.
- If T >= H: `elapsedCells=N`, `currentIndex=null`, `futureCells=0`.
- `currentStart`/`currentEndExclusive` are the current interval dates, or both null with no current cell.
- `finalCellDays=((D-1) mod 7)+1` (1–7). A shortened final cell is not an additional completed seven-day lived week. At horizon, all selected-horizon cells have elapsed while the lived summary continues beyond that horizon.
- Always: `elapsedCells + futureCells + (currentIndex is null ? 0 : 1) = totalCells`.
- `horizonState` is `before` for T < H, `reached` for the whole civil date T = H, and `passed` for T > H. Remaining totals are all zero on/after H. The grid has no current cell at H, including midnight.

A wrapped 52-cell row represents week blocks, not exactly one age year. Layout can group or virtualize the grid without changing these intervals or counts.

## Output shape

Successful output has exactly `horizonDate`, `horizonState`, `lived`, `remaining` and `grid`. Each totals object contains `years`, `months`, `weeks`, `days`, `hours`, `minutes`, `seconds`. Grid fields are `totalCells`, `elapsedCells`, `currentIndex`, `futureCells`, `currentStart`, `currentEndExclusive`, `finalCellDays`. Counts are nonnegative integers; current fields are nullable as described above. No NaN, Infinity, localized strings or floating durations are valid results.

The [JSON corpus](../../tests/fixtures/calendar-clock/v1.json) contains full expected outputs. Consumers should compare numeric/null/date fields, not a locale's formatted text. Do not use a fixture's expected values as production computation code.

## Display pause, visibility and export sequences

Calculation snapshots remain pure. The fixtures separately describe a minimal display state: `visible`, `paused`, and the snapshot supplying displayed ticking subday totals. The date-based calendar/grid model may refresh independently; pausing freezes only the displayed lived/remaining hours/minutes/seconds, not time itself or local settings.

| Event | State and sampling rule |
| --- | --- |
| `load` | First event; visible/running. Display this snapshot's subday totals. |
| `tick` | Sample current time; if visible/running display this snapshot. Hidden tabs need not update display. Paused counters retain their frozen snapshot. |
| `pause` | Visible/running only. Sample once and freeze this snapshot's subday totals; set paused. |
| `resume` | Visible/paused only. Clear pause and display a fresh current snapshot; never replay missed seconds. |
| `hide` | Set hidden; leave displayed subday totals unchanged. |
| `show` | Set visible; display current snapshot if running, or the frozen snapshot if paused. Also represents wake/foreground catch-up, even without a preceding hide event. |
| `export` | Visible only. Calculate a fresh coherent snapshot for preview/export, even when the on-screen ticking display is paused. It does not unpause the display. Label the static image with its reference date; the export preview must make its current values visible before saving. |

Clock traces refer to snapshot case IDs rather than repeating their numeric outputs. Each expected step specifies `visible`, `paused`, `displaySubdayCaseId`; an export also specifies `exportCaseId`. The live domain result for the event is its `caseId`. Requirements for hiding figures, PNG rendering, localization, accessibility and actual browser lifecycle events still need their own implementation tests; these data sequences are not browser evidence.

## Versioning and verification

The [fixture guide](../testing/calendar-clock-fixtures.md) explains shape, coverage and reproducible audit. Contract/formula changes require a versioned decision, affected requirement/fixture updates and review before implementation. Existing expected values must not be regenerated merely to make a failing application test green. Dates/clock inputs are injected into future TypeScript, Swift and Kotlin consumers; shared JSON does not require a shared binary or FFI.
