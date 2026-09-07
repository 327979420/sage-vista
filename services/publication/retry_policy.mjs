// Fixed M12 operational policy, not maturity, source, or M10 validation.
export const JOB_BUDGET_MS = 600_000;
const DELAYS = [900_000, 3_600_000];
const TEMPORARY = new Set(['rate_limited', 'provider_5xx', 'network_error', 'market_pending', 'runner_lost']);
const BLOCKING = new Set(['identity_conflict', 'contract_conflict', 'evidence_unavailable']);
function instant(now) {
  if (!Number.isSafeInteger(now) || now < 0 || !Number.isFinite(new Date(now + JOB_BUDGET_MS).getTime())) throw new Error('retry_time_invalid');
}
export function newYorkDay(now) {
  instant(now);
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
  const get = type => parts.find(part => part.type === type).value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}
export function initialRetryState() {
  return { state: 'queued', day: null, attempts_today: 0, retry_at_ms: null, wait_for_eod_after_ms: null, reason: null };
}
// eodMs is the latest actually verified EOD dispatch instant, never a predicted
// calendar time. A timer alone cannot release the third-failure EOD gate.
export function claimDecision(state, { now, jobStartedMs, mature, eodMs = null }) {
  instant(now); instant(jobStartedMs);
  if (typeof mature !== 'boolean' || now < jobStartedMs) throw new Error('retry_claim_context_invalid');
  if (eodMs !== null) { instant(eodMs); if (eodMs > now) throw new Error('retry_eod_future'); }
  if (now >= jobStartedMs + JOB_BUDGET_MS) return { claimable: false, reason: 'job_budget_exhausted' };
  if (!mature) return { claimable: false, reason: 'immature' };
  if (!['queued', 'retry_wait'].includes(state.state)) return { claimable: false, reason: state.state };
  const day = newYorkDay(now), attempts = state.day === day ? state.attempts_today : 0;
  if (attempts >= 3) return { claimable: false, reason: 'daily_budget_exhausted' };
  if (state.retry_at_ms !== null && now < state.retry_at_ms) return { claimable: false, reason: 'retry_delay' };
  if (state.wait_for_eod_after_ms !== null && (eodMs === null || eodMs <= state.wait_for_eod_after_ms)) return { claimable: false, reason: 'next_eod_required' };
  return { claimable: true, next: { state: 'running', day, attempts_today: attempts + 1,
    retry_at_ms: null, wait_for_eod_after_ms: null, reason: null } };
}
export function failureState(state, reason, now) {
  instant(now);
  if (state.state !== 'running' || !Number.isSafeInteger(state.attempts_today) || state.attempts_today < 1 || state.attempts_today > 3) throw new Error('retry_running_required');
  if (BLOCKING.has(reason)) return { ...state, state: 'blocked', reason };
  if (!TEMPORARY.has(reason)) throw new Error('retry_reason_invalid');
  const delay = DELAYS[state.attempts_today - 1];
  return { ...state, state: 'retry_wait', reason,
    retry_at_ms: delay === undefined ? null : now + delay,
    wait_for_eod_after_ms: delay === undefined ? now : null };
}
