import test from 'node:test';
import assert from 'node:assert/strict';
import { initialRetryState, claimDecision, failureState, newYorkDay, JOB_BUDGET_MS } from '../services/publication/retry_policy.mjs';
const START = Date.parse('2026-09-07T14:00:00Z');
const claim = (state, now, extra = {}) => claimDecision(state, { now, jobStartedMs: now, mature: true, ...extra });
test('three starts share a New York day budget and fixed delays across jobs', () => {
  let state = initialRetryState(), now = START;
  for (const [index, delay] of [900000, 3600000, null].entries()) {
    const next = claim(state, now); assert.equal(next.claimable, true); state = next.next;
    assert.equal(state.attempts_today, index + 1);
    state = failureState(state, 'network_error', now);
    assert.equal(state.retry_at_ms, delay === null ? null : now + delay);
    if (delay !== null) {
      assert.equal(claim(state, now + delay - 1).reason, 'retry_delay'); now += delay;
    }
  }
  assert.equal(claim(state, now + 1).reason, 'daily_budget_exhausted');
  const tomorrow = START + 86400000;
  assert.equal(claim(state, tomorrow).reason, 'next_eod_required');
  assert.equal(claim(state, tomorrow, { eodMs: state.wait_for_eod_after_ms }).reason, 'next_eod_required');
  const next = claim(state, tomorrow, { eodMs: tomorrow });
  assert.equal(next.next.attempts_today, 1);
});
test('New York boundary follows DST rather than UTC midnight', () => {
  assert.equal(newYorkDay(Date.parse('2026-09-08T03:59:59Z')), '2026-09-07');
  assert.equal(newYorkDay(Date.parse('2026-09-08T04:00:00Z')), '2026-09-08');
  assert.equal(newYorkDay(Date.parse('2026-12-08T04:59:59Z')), '2026-12-07');
  assert.equal(newYorkDay(Date.parse('2026-12-08T05:00:00Z')), '2026-12-08');
});
test('immature tasks remain unchanged; exact ten minute boundary stops new claims', () => {
  const state = initialRetryState(), before = structuredClone(state);
  assert.equal(claim(state, START, { mature: false }).reason, 'immature');
  assert.deepEqual(state, before);
  assert.equal(claim(state, START + JOB_BUDGET_MS, { jobStartedMs: START }).reason, 'job_budget_exhausted');
  assert.equal(claim(state, START + JOB_BUDGET_MS - 1, { jobStartedMs: START }).claimable, true);
});
test('blocking conflicts never auto-resume and unknown failure reasons are rejected', () => {
  for (const reason of ['identity_conflict', 'contract_conflict', 'evidence_unavailable']) {
    const blocked = failureState(claim(initialRetryState(), START).next, reason, START);
    assert.equal(claim(blocked, START + 86400000, { eodMs: START + 86400000 }).reason, 'blocked');
  }
  assert.throws(() => failureState(claim(initialRetryState(), START).next, 'success', START), /reason_invalid/);
  assert.throws(() => claim(initialRetryState(), START, { eodMs: START + 1 }), /eod_future/);
});
