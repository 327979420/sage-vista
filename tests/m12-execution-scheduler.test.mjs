import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { ExecutionTaskArchive } from '../services/publication/execution_archive.mjs';
import { ExecutionScheduler } from '../services/publication/execution_scheduler.mjs';
import { LeaseStore } from '../services/publication/leases.mjs';
const START = Date.parse('2026-09-07T14:00:00Z');
const EPOCH = '11111111-1111-4111-8111-111111111111';
const TASK = 'execution-task:sha256:' + '1'.repeat(64);
const SECOND = 'execution-task:sha256:' + '2'.repeat(64);
const DAILY = 'daily/2026-09-07/config:test';
const job = id => ({ run_id: id, run_attempt: 1 });
const token = handle => ({ epoch: handle.epoch, fence: handle.lease.fence });
function setup(t, adapter = async () => ({ mature: true, eod_ms: START })) {
  const dir = mkdtempSync(join(tmpdir(), 'm12-schedule-'));
  let now = START, storage, tasks, leases, scheduler;
  const objects = new Map();
  const bucket = { async put(key, value) { if (!objects.has(key)) objects.set(key, new Uint8Array(value)); },
    async get(key) { const value = objects.get(key); return value ? { arrayBuffer: async () => new Uint8Array(value).buffer } : null; } };
  const reopen = () => {
    if (storage) storage.db.close();
    const db = new DatabaseSync(join(dir, 'db.sqlite'));
    storage = { db, sql: { exec(query, ...args) { return { toArray: () => db.prepare(query).all(...args).map(row => ({ ...row })) }; } },
      transactionSync(fn) { db.exec('BEGIN IMMEDIATE'); try { const value = fn(); db.exec('COMMIT'); return value; } catch (error) { db.exec('ROLLBACK'); throw error; } } };
    leases = new LeaseStore(storage, { clock: () => now });
    tasks = new ExecutionTaskArchive(storage, bucket, { clock: () => now });
    scheduler = new ExecutionScheduler(storage, bucket, { clock: () => now, readiness: adapter });
  };
  reopen(); leases.initialize(EPOCH); tasks.initializeEmpty(); scheduler.initializeEmpty();
  t.after(() => { storage.db.close(); rmSync(dir, { recursive: true, force: true }); });
  const identity = name => ({ job: job(name), issued_at: Math.floor(now / 1000) - 1, expires_at: Math.floor(now / 1000) + 3600 });
  return { get scheduler() { return scheduler; }, get storage() { return storage; }, get leases() { return leases; }, objects,
    setTime(value) { now = value; }, reopen, identity,
    acquire(id, name) { const actor = identity(name); return { actor, owned: token(leases.acquire('execution/' + id, actor.job, EPOCH)) }; },
    async register(id = TASK) {
      const actor = identity('daily'), owned = token(leases.acquire(DAILY, actor.job, EPOCH));
      return tasks.register(actor, owned, DAILY, id, new TextEncoder().encode('synthetic root ' + id));
    } };
}
test('persistent full task discovery, idempotent claim and restart do not reset attempts', async t => {
  const env = setup(t); await env.register(); await env.register(SECOND);
  assert.equal(env.scheduler.list().length, 2);
  const { actor, owned } = env.acquire(TASK, 'one');
  const claim = await env.scheduler.claim(actor, owned, TASK);
  assert.equal(claim.attempt.state.attempts_today, 1);
  env.reopen();
  assert.deepEqual(await env.scheduler.claim(actor, owned, TASK), claim);
  await env.scheduler.fail(actor, owned, TASK, claim.attempt.position, 'network_error');
  env.setTime(START + 900000 - 1);
  const next = env.acquire(TASK, 'two');
  assert.equal((await env.scheduler.claim(next.actor, next.owned, TASK)).reason, 'retry_delay');
  env.setTime(START + 900000);
  assert.equal((await env.scheduler.claim(next.actor, next.owned, TASK)).attempt.state.attempts_today, 2);
});
test('one job budget survives reopen and cannot reset by choosing another task', async t => {
  const env = setup(t); await env.register(); await env.register(SECOND);
  const first = env.acquire(TASK, 'one'); await env.scheduler.claim(first.actor, first.owned, TASK);
  env.reopen(); env.setTime(START + 600000);
  const next = env.acquire(SECOND, 'one');
  assert.equal((await env.scheduler.claim(next.actor, next.owned, SECOND)).reason, 'job_budget_exhausted');
  assert.equal(env.scheduler.list().find(item => item.snapshot.root.task_id === SECOND).schedule, null);
});
test('lost runner requires new fence, records failure before retry and rejects old writer', async t => {
  const env = setup(t); await env.register();
  const first = env.acquire(TASK, 'one');
  const claim = await env.scheduler.claim(first.actor, first.owned, TASK);
  await assert.rejects(env.scheduler.recover(first.actor, first.owned, TASK), /new_fence/);
  env.setTime(START + 300000);
  const second = env.acquire(TASK, 'two');
  assert.equal((await env.scheduler.claim(second.actor, second.owned, TASK)).reason, 'recovery_required');
  const recovered = await env.scheduler.recover(second.actor, second.owned, TASK);
  assert.equal(recovered.state.retry_at_ms, START + 300000 + 900000);
  await assert.rejects(env.scheduler.fail(first.actor, first.owned, TASK, claim.attempt.position, 'network_error'), /not_owned/);
  assert.equal((await env.scheduler.claim(second.actor, second.owned, TASK)).reason, 'retry_delay');
});
test('immature and absent trusted adapter do not claim or consume attempts', async t => {
  for (const adapter of [null, async () => ({ mature: false, eod_ms: null })]) {
    const env = setup(t, adapter); await env.register(); const claim = env.acquire(TASK, 'one');
    assert.equal((await env.scheduler.claim(claim.actor, claim.owned, TASK)).claimed, false);
    assert.equal(env.scheduler.list()[0].schedule, null);
  }
});
test('lost paired journal records fail closed; failed SQL append rolls back', async t => {
  const env = setup(t); await env.register(); const first = env.acquire(TASK, 'one');
  env.storage.db.exec("CREATE TRIGGER fail_schedule BEFORE INSERT ON m12_execution_schedule_log BEGIN SELECT RAISE(ABORT, 'synthetic log failure'); END");
  await assert.rejects(env.scheduler.claim(first.actor, first.owned, TASK), /log failure/);
  assert.equal(env.storage.db.prepare('SELECT revision FROM m12_execution_schedule_head').get().revision, 0);
  env.storage.db.exec('DROP TRIGGER fail_schedule');
  await env.scheduler.claim(first.actor, first.owned, TASK);
  env.storage.db.exec('DELETE FROM m12_execution_schedule_events; DELETE FROM m12_execution_schedule_log');
  env.reopen(); assert.throws(() => env.scheduler.list(), /recovery_required/);
});
test('async readiness cannot bypass source readback or lease expiry', async t => {
  for (const failure of ['root', 'lease']) {
    let env;
    env = setup(t, async () => {
      if (failure === 'root') env.objects.clear();
      else env.setTime(START + 300000);
      return { mature: true, eod_ms: START };
    });
    await env.register(); const first = env.acquire(TASK, 'one');
    await assert.rejects(env.scheduler.claim(first.actor, first.owned, TASK), /object_missing|not_owned/);
    assert.equal(env.scheduler.list()[0].schedule, null);
  }
});
test('blocked is not automatically reclaimed on another day', async t => {
  const env = setup(t); await env.register(); const first = env.acquire(TASK, 'one');
  const claim = await env.scheduler.claim(first.actor, first.owned, TASK);
  await env.scheduler.fail(first.actor, first.owned, TASK, claim.attempt.position, 'contract_conflict');
  env.setTime(START + 86400000); const next = env.acquire(TASK, 'two');
  assert.equal((await env.scheduler.claim(next.actor, next.owned, TASK)).reason, 'blocked');
});

test('three attempts persist across jobs and midnight still requires a new verified EOD', async t => {
  let eod = START;
  const env = setup(t, async () => ({ mature: true, eod_ms: eod }));
  await env.register();
  let now = START;
  for (let i = 0; i < 3; i++) {
    env.setTime(now); const owner = env.acquire(TASK, 'job-' + i);
    const claim = await env.scheduler.claim(owner.actor, owner.owned, TASK);
    assert.equal(claim.attempt.state.attempts_today, i + 1);
    await env.scheduler.fail(owner.actor, owner.owned, TASK, claim.attempt.position, 'provider_5xx');
    env.reopen(); now += i === 0 ? 900000 : 3600000;
  }
  env.setTime(START + 86400000); const tomorrow = env.acquire(TASK, 'tomorrow');
  assert.equal((await env.scheduler.claim(tomorrow.actor, tomorrow.owned, TASK)).reason, 'next_eod_required');
  eod = START + 86400000;
  assert.equal((await env.scheduler.claim(tomorrow.actor, tomorrow.owned, TASK)).attempt.state.attempts_today, 1);
});
test('renewed identity cannot extend the original running attempt deadline', async t => {
  const env = setup(t); await env.register();
  const owner = env.acquire(TASK, 'one'); owner.actor.expires_at = START / 1000 + 1;
  const claim = await env.scheduler.claim(owner.actor, owner.owned, TASK);
  env.setTime(START + 1000);
  const renewed = { ...owner.actor, expires_at: START / 1000 + 3600 };
  await assert.rejects(env.scheduler.claim(renewed, owner.owned, TASK), /deadline_expired/);
  await assert.rejects(env.scheduler.fail(renewed, owner.owned, TASK, claim.attempt.position, 'network_error'), /deadline_expired/);
});

test('concurrent short attempt constrains longer replay at entry and final transaction clock', async t => {
  for (const boundary of ['entry', 'commit']) {
    let env, owner, nested = false, inner, reads = 0;
    env = setup(t, async () => {
      if (!nested) {
        nested = true;
        inner = await env.scheduler.claim({ ...owner.actor, expires_at: START / 1000 + 1 }, owner.owned, TASK);
        assert.equal(inner.claimed, true);
        env.setTime(START + (boundary === 'entry' ? 1000 : 999));
        if (boundary === 'commit') {
          const original = env.storage.sql.exec;
          env.storage.sql.exec = (query, ...args) => {
            const result = original(query, ...args);
            if (query === 'SELECT * FROM m12_execution_schedule_events ORDER BY position' && ++reads === 2) env.setTime(START + 1000);
            return result;
          };
        }
      }
      return { mature: true, eod_ms: START };
    });
    await env.register(); owner = env.acquire(TASK, 'one');
    await assert.rejects(env.scheduler.claim(owner.actor, owner.owned, TASK), /deadline_expired/);
    if (boundary === 'commit') assert.equal(reads, 2);
    assert.deepEqual(env.scheduler.list()[0].schedule, inner.attempt);
  }
});
