// Internal execution scheduling journal. No RPC, scanner, or M10 completion API.
// readiness is installed only by a trusted fixed adapter; absent => not runnable.
import { ExecutionComputationSession } from './execution_session.mjs';
import { ExecutionTaskArchive } from './execution_archive.mjs';
import { initialRetryState, claimDecision, failureState, JOB_BUDGET_MS } from './retry_policy.mjs';
const ordered = value => Array.isArray(value) ? value.map(ordered) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, ordered(value[key])])) : value;
const encode = value => JSON.stringify(ordered(value));
const same = (a, b) => encode(a) === encode(b);

export class ExecutionScheduler {
  #storage; #tasks; #readiness; #session;
  constructor(storage, bucket, { clock = Date.now, readiness = null } = {}) {
    if (readiness !== null && typeof readiness !== 'function') throw new Error('execution_readiness_adapter_invalid');
    this.#storage = storage;
    this.#tasks = new ExecutionTaskArchive(storage, bucket, { clock });
    this.#readiness = readiness;
    this.#session = new ExecutionComputationSession(storage, bucket, { clock });
    storage.transactionSync(() => {
      this.#sql('CREATE TABLE IF NOT EXISTS m12_execution_schedule_head (singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL)');
      this.#sql('CREATE TABLE IF NOT EXISTS m12_execution_schedule_events (position INTEGER PRIMARY KEY, record_json TEXT NOT NULL)');
      this.#sql('CREATE TABLE IF NOT EXISTS m12_execution_schedule_log (position INTEGER PRIMARY KEY, record_json TEXT NOT NULL)');
    });
  }
  #sql(query, ...args) { return this.#storage.sql.exec(query, ...args).toArray(); }
  initializeEmpty() {
    this.#storage.transactionSync(() => {
      for (const suffix of ['head', 'events', 'log']) {
        if (this.#sql('SELECT * FROM m12_execution_schedule_' + suffix + ' LIMIT 1').length) throw new Error('execution_schedule_not_empty');
      }
      this.#sql('INSERT INTO m12_execution_schedule_head VALUES (1,0)');
    });
  }
  #history() {
    const head = this.#sql('SELECT revision FROM m12_execution_schedule_head WHERE singleton=1')[0];
    const rows = this.#sql('SELECT * FROM m12_execution_schedule_events ORDER BY position');
    const logs = this.#sql('SELECT * FROM m12_execution_schedule_log ORDER BY position');
    if (!head || head.revision !== rows.length || !same(rows, logs)) throw new Error('execution_schedule_recovery_required');
    return rows.map((row, index) => {
      if (row.position !== index + 1) throw new Error('execution_schedule_history_invalid');
      return { position: row.position, ...JSON.parse(row.record_json) };
    });
  }
  #append(history, record) {
    if (!same(history, this.#history())) throw new Error('execution_schedule_compare_failed');
    const position = history.length + 1, raw = encode(record);
    this.#sql('INSERT INTO m12_execution_schedule_events VALUES (?,?)', position, raw);
    this.#sql('INSERT INTO m12_execution_schedule_log VALUES (?,?)', position, raw);
    this.#sql('UPDATE m12_execution_schedule_head SET revision=? WHERE singleton=1', position);
    return { position, ...record };
  }
  #latest(history, taskId) { return history.filter(row => row.task_id === taskId).at(-1); }
  #attemptDeadline(identity, token, taskId) {
    const latest = this.#latest(this.#history(), taskId);
    return (latest?.state.state === 'running' || latest?.kind === 'checkpoint') && same(latest.job, identity.job) && same(latest.token, token)
      ? Math.min(identity.expires_at, latest.original_expires_at) * 1000 : identity.expires_at * 1000;
  }
  list() {
    // No caller-supplied complete list and no current-day ranking filter.
    const tasks = this.#tasks.registeredTasks();
    const history = this.#history();
    if (history.some(row => row.task_id && !tasks.some(task => task.root.task_id === row.task_id))) throw new Error('execution_schedule_orphan');
    return tasks.map(snapshot => ({ snapshot,
      schedule: this.#latest(history, snapshot.root.task_id) ?? null }));
  }
  async claim(identity, token, taskId) {
    identity = structuredClone(identity); token = structuredClone(token);
    const prior = this.#latest(this.#history(), taskId);
    if (prior?.state.state === 'running' && same(prior.job, identity.job) && same(prior.token, token)) {
      identity.expires_at = Math.min(identity.expires_at, prior.original_expires_at);
    }
    const initial = await this.#tasks.readTask(identity, token, taskId);
    const budget = this.#tasks.withCurrentTask(identity, token, taskId, initial.current, ({ now }) => {
      const history = this.#history();
      const existing = history.find(row => row.kind === 'job_start' && same(row.job, identity.job));
      if (existing) return existing;
      return this.#append(history, { kind: 'job_start', job: identity.job, started_ms: now });
    });
    const gate = this.#tasks.withCurrentTask(identity, token, taskId, initial.current, ({ now }) => {
      const latest = this.#latest(this.#history(), taskId);
      return claimDecision(latest?.state ?? initialRetryState(), { now, jobStartedMs: budget.started_ms, mature: true });
    });
    if (!gate.claimable && !['running', 'next_eod_required'].includes(gate.reason)) return { claimed: false, reason: gate.reason };
    if (!this.#readiness) return { claimed: false, reason: 'readiness_unavailable' };
    const ready = await this.#readiness(initial, { deadline_ms: Math.min(budget.started_ms + JOB_BUDGET_MS, identity.expires_at * 1000) });
    if (!ready || Object.keys(ready).sort().join() !== 'eod_ms,mature' || typeof ready.mature !== 'boolean') throw new Error('execution_readiness_invalid');
    const reread = await this.#tasks.readTask(identity, token, taskId);
    if (!same(initial.current, reread.current)) throw new Error('execution_schedule_compare_failed');
    return this.#tasks.withCurrentTask(identity, token, taskId, reread.current, ({ now }) => {
      const history = this.#history(), latest = this.#latest(history, taskId);
      if (latest?.state.state === 'running') {
        if (same(latest.job, identity.job) && same(latest.token, token)) {
          if (now >= budget.started_ms + JOB_BUDGET_MS) return { claimed: false, reason: 'job_budget_exhausted' };
          return { claimed: true, attempt: latest }; // lost response, no extra attempt
        }
        return { claimed: false, reason: 'recovery_required' };
      }
      const decision = claimDecision(latest?.state ?? initialRetryState(), {
        now, jobStartedMs: budget.started_ms, mature: ready.mature, eodMs: ready.eod_ms,
      });
      if (!decision.claimable) return { claimed: false, reason: decision.reason };
      const attempt = this.#append(history, { kind: 'claim', task_id: taskId, job: identity.job, token,
        original_expires_at: identity.expires_at, started_ms: now, job_started_ms: budget.started_ms,
        previous_position: latest?.position ?? null, source_snapshot: reread.current, state: decision.next });
      return { claimed: true, attempt };
    }, { resolveDeadlineMs: () => this.#attemptDeadline(identity, token, taskId) });
  }
  async fail(identity, token, taskId, attemptPosition, reason) {
    identity = structuredClone(identity); token = structuredClone(token);
    const prior = this.#latest(this.#history(), taskId);
    if (prior?.state.state === 'running') identity.expires_at = Math.min(identity.expires_at, prior.original_expires_at);
    const { current } = await this.#tasks.readTask(identity, token, taskId);
    return this.#tasks.withCurrentTask(identity, token, taskId, current, ({ now }) => {
      const history = this.#history(), latest = this.#latest(history, taskId);
      if (!latest || latest.position !== attemptPosition || latest.state.state !== 'running' ||
          !same(latest.job, identity.job) || !same(latest.token, token)) throw new Error('execution_attempt_not_owned');
      if (now >= latest.original_expires_at * 1000) throw new Error('execution_attempt_expired');
      return this.#append(history, { kind: 'failure', task_id: taskId, job: identity.job, token,
        previous_position: latest.position, occurred_ms: now, source_snapshot: latest.source_snapshot,
        snapshot: current, state: failureState(latest.state, reason, now) });
    }, { resolveDeadlineMs: () => this.#attemptDeadline(identity, token, taskId) });
  }
  assertRunning(taskId, position, identity, token) {
    // Synchronous guard for the existing session's final owned transaction.
    const latest = this.#latest(this.#history(), taskId);
    if (!latest || latest.position !== position || latest.state.state !== 'running' ||
        !same(latest.job, identity.job) || !same(latest.token, token)) throw new Error('execution_attempt_not_owned');
  }
  async settle(identity, token, taskId, outcome) {
    identity = structuredClone(identity); token = structuredClone(token);
    if (!['budget_exhausted', 'cancelled', 'computation_timeout', 'computation_invalid', 'contract_conflict'].includes(outcome)) throw new Error('execution_stop_outcome_invalid');
    let prior = this.#latest(this.#history(), taskId);
    if (prior?.state.state === 'running') {
      if (!same(prior.job, identity.job) || !same(prior.token, token)) throw new Error('execution_attempt_not_owned');
      identity.expires_at = Math.min(identity.expires_at, prior.original_expires_at);
      if (prior.dispatch_input_sha) {
        const actual = await this.#session.readRecovery(identity, token, taskId, prior.dispatch_input_sha);
        if (actual.completed) {
          await this.checkpoint(identity, token, taskId, prior.position, prior.dispatch_input_sha);
          prior = this.#latest(this.#history(), taskId);
        }
      }
    }
    const { current } = await this.#tasks.readTask(identity, token, taskId);
    return this.#tasks.withCurrentTask(identity, token, taskId, current, ({ now }) => {
      const history = this.#history(), latest = this.#latest(history, taskId);
      if (!same(latest ?? null, prior ?? null)) throw new Error('execution_schedule_compare_failed');
      const yielding = ['budget_exhausted', 'cancelled'].includes(outcome);
      let state = latest?.state ?? initialRetryState();
      // Never erase a prior blocked/retry/EOD gate by yielding a later request.
      if (yielding && state.state !== 'running' && latest) return latest;
      if (!yielding && state.state !== 'running') {
        const budget = history.find(row => row.kind === 'job_start' && same(row.job, identity.job));
        const decision = claimDecision(state, { now, jobStartedMs: budget?.started_ms ?? now, mature: true });
        if (!decision.claimable) return latest ?? null;
        state = decision.next; // A failed readiness computation consumes an attempt too.
      }
      state = yielding ? { ...state, state: 'queued', reason: outcome, retry_at_ms: null, wait_for_eod_after_ms: null }
        : failureState(state, outcome === 'computation_timeout' ? 'runner_lost' : outcome === 'contract_conflict' ? 'contract_conflict' : 'evidence_unavailable', now);
      return this.#append(history, { kind: yielding ? 'yield' : 'failure', task_id: taskId,
        job: identity.job, token, previous_position: latest?.position ?? null, occurred_ms: now,
        source_snapshot: latest?.source_snapshot ?? current, snapshot: current,
        checkpoint_snapshot: current, last_receipt: latest?.receipt ?? latest?.last_receipt ?? null,
        abandoned_input_sha: latest?.dispatch_input_sha ?? null, state });
    }, { resolveDeadlineMs: () => this.#attemptDeadline(identity, token, taskId) });
  }
  async bindDispatch(identity, token, taskId, attemptPosition, inputSha, outputBytes) {
    identity = structuredClone(identity); token = structuredClone(token);
    identity.expires_at = Math.min(identity.expires_at, this.#attemptDeadline(identity, token, taskId) / 1000);
    const proof = await this.#session.inspect(identity, token, inputSha, outputBytes);
    return this.#tasks.withCurrentTask(identity, token, taskId, proof.source_snapshot, () => {
      const history = this.#history(), latest = this.#latest(history, taskId);
      if (!latest || latest.state.state !== 'running' || !same(latest.job, identity.job) || !same(latest.token, token)) throw new Error('execution_attempt_not_owned');
      if (latest.dispatch_input_sha === inputSha) return latest;
      if (latest.position !== attemptPosition || latest.dispatch_input_sha || !same(latest.checkpoint_snapshot ?? latest.source_snapshot, proof.source_snapshot)) throw new Error('execution_dispatch_conflict');
      const { position, ...retained } = latest;
      return this.#append(history, { ...retained, kind: 'dispatch', previous_position: position, dispatch_input_sha: inputSha });
    }, { resolveDeadlineMs: () => this.#attemptDeadline(identity, token, taskId) });
  }
  async checkpoint(identity, token, taskId, attemptPosition, inputSha) {
    identity = structuredClone(identity); token = structuredClone(token);
    identity.expires_at = Math.min(identity.expires_at, this.#attemptDeadline(identity, token, taskId) / 1000);
    const completed = await this.#session.readCompleted(identity, token, inputSha);
    const { receipt } = completed;
    return this.#tasks.withCurrentTask(identity, token, taskId, receipt.snapshot, ({ now }) => {
      const history = this.#history(), latest = this.#latest(history, taskId);
      if (latest?.kind === 'checkpoint' && latest.input_sha === inputSha && same(latest.job, identity.job) && same(latest.token, token)) return latest;
      if (!latest || latest.position !== attemptPosition || latest.state.state !== 'running' ||
          !same(latest.job, identity.job) || !same(latest.token, token)) throw new Error('execution_attempt_not_owned');
      if (latest.dispatch_input_sha !== inputSha) throw new Error('execution_checkpoint_dispatch_missing');
      if (!same(latest.checkpoint_snapshot ?? latest.source_snapshot, receipt.source_snapshot)) throw new Error('execution_checkpoint_source_conflict');
      const { position, ...retained } = latest;
      const state = completed.has_next_pair ? latest.state : { ...latest.state, state: 'queued',
        reason: 'no_new_execution_pair', retry_at_ms: null, wait_for_eod_after_ms: now };
      return this.#append(history, { ...retained, kind: 'checkpoint', previous_position: position,
        dispatch_input_sha: null, input_sha: inputSha, receipt, checkpoint_snapshot: receipt.snapshot, occurred_ms: now, state });
    }, { resolveDeadlineMs: () => this.#attemptDeadline(identity, token, taskId) });
  }
  async recover(identity, token, taskId) {
    identity = structuredClone(identity); token = structuredClone(token);
    const prior = this.#latest(this.#history(), taskId);
    const initial = await this.#tasks.readTask(identity, token, taskId);
    this.#tasks.withCurrentTask(identity, token, taskId, initial.current, () => {
      if (!prior || prior.state.state !== 'running') throw new Error('execution_running_attempt_required');
      if (token.epoch !== prior.token.epoch || token.fence <= prior.token.fence) throw new Error('execution_recovery_new_fence_required');
    });
    const proofSha = prior.dispatch_input_sha ?? prior.input_sha;
    const proof = proofSha ? await this.#session.readRecovery(identity, token, taskId, proofSha) : null;
    const { current } = await this.#tasks.readTask(identity, token, taskId);
    return this.#tasks.withCurrentTask(identity, token, taskId, current, ({ now }) => {
      const history = this.#history(), latest = this.#latest(history, taskId);
      if (!same(prior, latest) || !same(initial.current, current)) throw new Error('execution_schedule_compare_failed');
      if (proof && !same(proof.snapshot, current)) throw new Error('execution_checkpoint_source_conflict');
      const completedDispatch = prior.dispatch_input_sha && proof?.completed;
      if (completedDispatch && !same(prior.checkpoint_snapshot ?? prior.source_snapshot, proof.source_snapshot)) throw new Error('execution_checkpoint_source_conflict');
      const state = completedDispatch ? { ...prior.state, state: 'queued', retry_at_ms: null,
        reason: proof.has_next_pair ? 'checkpoint_recovered' : 'no_new_execution_pair',
        wait_for_eod_after_ms: proof.has_next_pair ? null : now }
        : failureState(prior.state, 'runner_lost', now);
      return this.#append(history, { kind: completedDispatch ? 'recovery_checkpoint' : 'recovery', task_id: taskId,
        job: identity.job, token, previous_position: latest.position, occurred_ms: now,
        source_snapshot: latest.source_snapshot, snapshot: current, checkpoint_snapshot: current,
        receipt: proof?.completed ? proof.receipt : null,
        recovered_input_sha: completedDispatch ? prior.dispatch_input_sha : null,
        abandoned_input_sha: completedDispatch ? null : prior.dispatch_input_sha ?? null, state });
    });
  }
}
