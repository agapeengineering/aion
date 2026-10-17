import { describe, it, expect } from 'vitest';
import corpus from '../fixtures/calendar-clock/v1.json';
import { calculate, advanceDisplay, type Snapshot, type DisplayEvent, type DisplayState } from '../../packages/calendar/src/index';
describe('shared calendar contract', () => {
 for (const c of corpus.cases) it(c.id, () => expect(calculate(c.input)).toEqual(c.expected));
 for (const trace of corpus.traces) it(trace.id, () => {
  let state: DisplayState | null = null;
  for (const step of trace.steps) {
   const c = corpus.cases.find(x => x.id === step.caseId)!;
   const snapshot = calculate(c.input) as Snapshot;
   state = advanceDisplay(state, step.event as DisplayEvent, snapshot);
   expect(state.visible).toBe(step.expected.visible); expect(state.paused).toBe(step.expected.paused);
   const displayed = corpus.cases.find(x => x.id === step.expected.displaySubdayCaseId)!;
   expect(state.subday).toEqual(calculate(displayed.input));
   if ('exportCaseId' in step.expected) expect(state.exportSnapshot).toEqual(snapshot);
  }
 });
});
