import test from 'node:test';
import { spawnWithFileInput } from './m12-file-stdin.mjs';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { ExecutionTaskArchive } from '../services/publication/execution_archive.mjs';
import { LeaseStore } from '../services/publication/leases.mjs';

const EPOCH = '11111111-1111-4111-8111-111111111111';
const NOW = Date.parse('2026-09-07T00:00:00Z');
const JOB = { run_id: 'synthetic-local-1', run_attempt: 1 };
const IDENTITY = { job: JOB, issued_at: NOW / 1000, expires_at: NOW / 1000 + 3600 };
const DAILY = 'daily/2026-09-07/config:synthetic';
const TASK = 'execution-task:sha256:' + '1'.repeat(64);
const OTHER = 'execution-task:sha256:' + '2'.repeat(64);
const STEP = 'sha256:' + '3'.repeat(64);
const bytes = value => new TextEncoder().encode(value);
const token = value => ({ epoch: value.epoch, fence: value.lease.fence });

function binding(path) {
  const db = new DatabaseSync(path);
  return { db, sql: { exec(query, ...values) {
    return { toArray: () => db.prepare(query).all(...values).map(row => ({ ...row })) };
  } }, transactionSync(callback) {
    db.exec('BEGIN IMMEDIATE');
    try { const result = callback(); db.exec('COMMIT'); return result; }
    catch (error) { db.exec('ROLLBACK'); throw error; }
  } };
}
class FileBucket {
  puts = 0; failAt = null; afterGet = null;
  constructor(root) { this.root = root; }
  async put(key, value, options) {
    assert.equal(options.onlyIf.get('If-None-Match'), '*');
    this.puts++;
    if (this.puts === this.failAt) throw new Error('synthetic_interruption');
    const path = join(this.root, key);
    mkdirSync(dirname(path), { recursive: true });
    try { writeFileSync(path, value, { flag: 'wx' }); }
    catch (error) { if (error.code !== 'EEXIST') throw error; }
  }
  async get(key) {
    let value;
    try { value = readFileSync(join(this.root, key)); }
    catch (error) { if (error.code === 'ENOENT') return null; throw error; }
    if (this.afterGet) this.afterGet(key);
    return { arrayBuffer: async () => new Uint8Array(value).buffer };
  }
}
function setup(t, start = NOW) {
  const root = mkdtempSync(join(tmpdir(), 'm12-execution-'));
  let storage = binding(join(root, 'db.sqlite')), now = start;
  const bucket = new FileBucket(join(root, 'archive'));
  let leases = new LeaseStore(storage, { clock: () => now });
  leases.initialize(EPOCH);
  let store = new ExecutionTaskArchive(storage, bucket, { clock: () => now });
  store.initializeEmpty();
  const daily = token(leases.acquire(DAILY, JOB, EPOCH));
  t.after(() => { storage.db.close(); rmSync(root, { recursive: true, force: true }); });
  return { root, bucket, daily, get storage() { return storage; }, get leases() { return leases; },
    get store() { return store; }, setTime(value) { now = value; },
    restart() {
      storage.db.close(); storage = binding(join(root, 'db.sqlite'));
      leases = new LeaseStore(storage, { clock: () => now });
      store = new ExecutionTaskArchive(storage, bucket, { clock: () => now });
    },
    async register(id = TASK) {
      const current = await store.register(IDENTITY, daily, DAILY, id, bytes('synthetic root ' + id));
      return { current, owned: token(leases.acquire('execution/' + id, JOB, EPOCH)) };
    },
  };
}

test('complete original bytes and paired history survive restart', async t => {
  const env = setup(t);
  const { current, owned } = await env.register();
  const result = await env.store.appendPair(IDENTITY, owned, TASK, current, STEP,
    bytes('input'), bytes('original M08'), bytes('original M09'));
  assert.equal(result.revision, 1);
  env.restart();
  const read = await env.store.readTask(IDENTITY, owned, TASK);
  assert.deepEqual(read.current, result);
  assert.equal(read.objects.size, 4);
  const again = await env.store.appendPair(IDENTITY, owned, TASK, read.current, STEP,
    bytes('input'), bytes('original M08'), bytes('original M09'));
  assert.deepEqual(again, result);
  assert.throws(() => env.store.initializeEmpty(), /not_empty/);
});

test('interruption after M08 archive leaves orphan bytes and does not advance paired sequence', async t => {
  const env = setup(t);
  const { current, owned } = await env.register();
  env.bucket.failAt = env.bucket.puts + 3;
  await assert.rejects(env.store.appendPair(IDENTITY, owned, TASK, current, STEP,
    bytes('entry input'), bytes('M08 state'), bytes('M09 link')), /interruption/);
  assert.equal((await env.store.readTask(IDENTITY, owned, TASK)).current.revision, 0);
  assert.equal(readdirSync(join(env.root, 'archive/raw')).length, 3); // Root and two orphans retained.
  env.restart(); env.bucket.failAt = null;
  const result = await env.store.appendPair(IDENTITY, owned, TASK, current, STEP,
    bytes('entry input'), bytes('M08 state'), bytes('M09 link'));
  assert.equal(result.revision, 1);
  assert.equal(readdirSync(join(env.root, 'archive/raw')).length, 4);
});

test('lost reply retry reads persisted originals; missing registered bytes cannot be healed', async t => {
  const env = setup(t);
  const { current, owned } = await env.register();
  const result = await env.store.appendPair(IDENTITY, owned, TASK, current, STEP,
    bytes('input'), bytes('object'), bytes('link'));
  rmSync(join(env.root, 'archive', result.history[0].link.key));
  const puts = env.bucket.puts;
  await assert.rejects(env.store.appendPair(IDENTITY, owned, TASK, result, STEP,
    bytes('input'), bytes('object'), bytes('link')), /object_missing/);
  assert.equal(env.bucket.puts, puts);
});

test('pair and log deletion is detected by the durable head, never rebuilt', async t => {
  const env = setup(t);
  const { current, owned } = await env.register();
  await env.store.appendPair(IDENTITY, owned, TASK, current, STEP, bytes('i'), bytes('o'), bytes('l'));
  env.storage.db.exec('DELETE FROM m12_execution_pairs; DELETE FROM m12_execution_pair_log');
  env.restart();
  await assert.rejects(env.store.readTask(IDENTITY, owned, TASK), /recovery_required/);
});

test('independent tasks have independent histories, CAS and execution leases', async t => {
  const env = setup(t);
  const a = await env.register(), b = await env.register(OTHER);
  const first = await env.store.appendPair(IDENTITY, a.owned, TASK, a.current, STEP, bytes('i'), bytes('o'), bytes('l'));
  assert.equal((await env.store.readTask(IDENTITY, b.owned, OTHER)).current.revision, 0);
  await env.store.appendPair(IDENTITY, b.owned, OTHER, b.current, STEP, bytes('j'), bytes('p'), bytes('m'));
  await assert.rejects(env.store.appendPair(IDENTITY, a.owned, TASK, a.current, STEP, bytes('i'), bytes('o'), bytes('l')), /compare_failed/);
  await assert.rejects(env.store.appendPair(IDENTITY, a.owned, TASK, first, STEP, bytes('changed'), bytes('o'), bytes('l')), /step_conflict/);
  const foreign = { ...IDENTITY, job: { ...JOB, run_id: 'other' } };
  await assert.rejects(env.store.readTask(foreign, a.owned, TASK), /not_owned/);
  assert.equal(env.store.listTasks(IDENTITY, env.daily, DAILY).length, 2);
});

test('expiry after archive readback rolls back registration and retains orphan', async t => {
  const env = setup(t);
  env.bucket.afterGet = () => env.setTime(NOW + 300000);
  await assert.rejects(env.store.register(IDENTITY, env.daily, DAILY, TASK, bytes('root')), /stale/);
  assert.equal(env.storage.sql.exec('SELECT * FROM m12_execution_catalog').toArray().length, 0);
  assert.equal(readdirSync(join(env.root, 'archive/raw')).length, 1);
});

test('changed or missing original root is refused on register replay', async t => {
  const env = setup(t);
  const { current } = await env.register();
  await assert.rejects(env.store.register(IDENTITY, env.daily, DAILY, TASK, bytes('changed')), /root_conflict/);
  rmSync(join(env.root, 'archive', current.root.root.key));
  await assert.rejects(env.store.register(IDENTITY, env.daily, DAILY, TASK, bytes('synthetic root ' + TASK)), /object_missing/);
});


test('SQL failure between pair and log rolls back head and both records', async t => {
  const env = setup(t);
  const { current, owned } = await env.register();
  env.storage.db.exec("CREATE TRIGGER fail_execution_pair_log BEFORE INSERT ON m12_execution_pair_log BEGIN SELECT RAISE(ABORT, 'synthetic SQL interruption'); END");
  await assert.rejects(env.store.appendPair(IDENTITY, owned, TASK, current, STEP, bytes('i'), bytes('o'), bytes('l')), /SQL interruption/);
  assert.deepEqual((await env.store.readTask(IDENTITY, owned, TASK)).current, current);
  assert.equal(readdirSync(join(env.root, 'archive/raw')).length, 4);
  env.storage.db.exec('DROP TRIGGER fail_execution_pair_log');
  const result = await env.store.appendPair(IDENTITY, owned, TASK, current, STEP, bytes('i'), bytes('o'), bytes('l'));
  assert.equal(result.revision, 1);
});

test('actual original Python producers recover frozen inputs and paired checkpoints after file and SQLite reopen', async t => {
  const python = value => {
    const result = spawnWithFileInput('python3', ['-B', '-W', 'error::ResourceWarning', 'tests/m12_execution_history_fixture.py'], Buffer.from(JSON.stringify(value)), {
      encoding: 'utf8', maxBuffer: 32 * 1024 * 1024,
      timeout: value.operation === 'fixed_execution' ? 45000 : 15000, killSignal: 'SIGKILL',
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONPATH: 'tests:.' },
    });
    assert.equal(result.status, 0, `operation=${value.operation} error=${result.error?.code ?? 'none'} signal=${result.signal ?? 'none'}\n${result.stderr}`);
    return JSON.parse(result.stdout);
  };
  const fixture = python({ operation: 'fixture' });
  const env = setup(t);
  await env.store.register(IDENTITY, env.daily, DAILY, fixture.task_id, new Uint8Array(Buffer.from(fixture.root_bytes, 'base64')));
  const owned = token(env.leases.acquire('execution/' + fixture.task_id, JOB, EPOCH));
  const read = async () => {
    const value = await env.store.readTask(IDENTITY, owned, fixture.task_id);
    return { snapshot: value.current, objects: Object.fromEntries([...value.objects].map(([key, raw]) => [key, Buffer.from(raw).toString('base64')])) };
  };
  const append = (snapshot, pair) => env.store.appendPair(IDENTITY, owned, fixture.task_id, snapshot, pair.step_id,
    ...['input_bytes', 'object_bytes', 'link_bytes'].map(key => new Uint8Array(Buffer.from(pair[key], 'base64'))));
  for (let index = 0; index < 4; index++) {
    let current = await read();
    let pair = python({ operation: 'prepare', ...current, request_bytes: fixture.request_bytes }).pairs[0];
    assert.ok(pair);
    if (index < 2) {
      // Both actual plan and actual exit object are archived before failure of
      // their M09 link. Restart loads the durable head, never the orphan list.
      env.bucket.failAt = env.bucket.puts + 3;
      await assert.rejects(append(current.snapshot, pair), /interruption/);
      env.restart(); env.bucket.failAt = null;
      current = await read();
      assert.equal(current.snapshot.revision, index);
      const recovered = python({ operation: 'restore', ...current });
      assert.deepEqual(recovered.holding_sessions, []);
      const replay = python({ operation: 'prepare', ...current, request_bytes: fixture.request_bytes }).pairs[0];
      assert.deepEqual(replay, pair);
      pair = replay;
    }
    await append(current.snapshot, pair);
  }
  env.restart();
  const current = await read();
  assert.equal(current.snapshot.revision, 4);
  const restored = python({ operation: 'restore', ...current });
  assert.deepEqual(restored.holding_sessions, [1, 2, 3]);
  assert.deepEqual(restored.entry_dates, ['2026-09-02']);
  assert.deepEqual(Object.values(restored.confirmed_through), ['2026-09-04']);
  const before = readdirSync(join(env.root, 'archive/raw')).sort().map(name => [name, readFileSync(join(env.root, 'archive/raw', name)).toString('base64')]);
  const retry = python({ operation: 'prepare', ...current,
    request_bytes: fixture.request_bytes, late_retry: true });
  assert.deepEqual(retry.pairs, []);
  assert.deepEqual(readdirSync(join(env.root, 'archive/raw')).sort().map(name => [name, readFileSync(join(env.root, 'archive/raw', name)).toString('base64')]), before);
  t.diagnostic(`original task retained ${before.length} immutable archive files and 4 paired records after restart`);
});


test('async writes retain the original trusted identity deadline despite caller mutation', async t => {
  const env = setup(t);
  const identity = { ...IDENTITY, expires_at: IDENTITY.issued_at + 1 };
  env.bucket.afterGet = () => {
    identity.expires_at += 3600;
    env.setTime(NOW + 2000);
  };
  await assert.rejects(env.store.register(identity, env.daily, DAILY, TASK, bytes('original root')), /deadline_expired/);
  assert.equal(env.storage.sql.exec('SELECT * FROM m12_execution_catalog').toArray().length, 0);
});


test('registered source inventory to actual fixed computation and atomic result/pair receipt survives restart', async t => {
  const { ExecutionComputationSession } = await import('../services/publication/execution_session.mjs');
  const python = value => {
    const result = spawnWithFileInput('python3', ['-B', '-W', 'error::ResourceWarning', 'tests/m12_execution_history_fixture.py'], Buffer.from(JSON.stringify(value)), {
      encoding: 'utf8', maxBuffer: 32 * 1024 * 1024,
      timeout: value.operation === 'fixed_execution' ? 45000 : 15000, killSignal: 'SIGKILL',
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONPATH: 'tests:.' },
    });
    assert.equal(result.status, 0, `operation=${value.operation} error=${result.error?.code ?? 'none'} signal=${result.signal ?? 'none'}\n${result.stderr}`);
    return JSON.parse(result.stdout);
  };
  const fixture = python({ operation: 'source_fixture', prior_source: true });
  const start = Date.now(), env = setup(t, start);
  const rootIdentity = { ...IDENTITY, issued_at: Math.floor(start / 1000) - 1, expires_at: Math.floor(start / 1000) + 300 };
  await env.store.register(rootIdentity, env.daily, DAILY, fixture.task_id, new Uint8Array(Buffer.from(fixture.root_bytes, 'base64')));
  const identity = { ...rootIdentity, job: { repository_id: '1', workflow_ref: 'local/synthetic@main', workflow_commit: fixture.commit,
    run_id: '1', run_attempt: 1, environment: 'synthetic' }, code_commit: fixture.commit,
    actor_id: '1', subject: 'synthetic-only', token_id: 'synthetic-only' };
  const owned = token(env.leases.acquire('execution/' + fixture.task_id, identity.job, EPOCH));
  let session = new ExecutionComputationSession(env.storage, env.bucket, { clock: () => Date.now() });
  session.initializeEmpty();
  const prepared = await session.prepare(identity, owned, fixture.task_id, new Uint8Array(Buffer.from(fixture.request_bytes, 'base64')));
  const executed = python({ operation: 'fixed_execution', input_bytes: Buffer.from(prepared.input_bytes).toString('base64') });
  const output = new Uint8Array(Buffer.from(executed.output_bytes, 'base64'));
  const decoded = JSON.parse(new TextDecoder().decode(output));
  const inventory = JSON.parse(Buffer.from(decoded.inventory_bytes, 'base64'));
  assert.ok(inventory.records.some(ref => ref.id.startsWith('market:')));
  assert.ok(inventory.records.some(ref => ref.id.startsWith('universe:')));
  assert.ok(decoded.next_pair);
  let privateReads = 0;
  env.bucket.afterGet = () => { privateReads++; };
  await assert.rejects(session.accept(identity, { ...owned, fence: owned.fence + 1 }, prepared.input.sha256, output), /not_owned/);
  assert.equal(privateReads, 0);
  env.bucket.afterGet = null;
  await assert.rejects(session.accept(identity, owned, prepared.input.sha256, bytes(JSON.stringify({ ...decoded, input_sha256: 'sha256:' + '0'.repeat(64) }))), /binding_invalid/);
  const rootRef = JSON.parse(new TextDecoder().decode(prepared.input_bytes)).snapshot.root.root;
  const linkRaw = Buffer.from(decoded.next_pair.link_bytes, 'base64');
  const linkKey = 'raw/' + Buffer.from(await crypto.subtle.digest('SHA-256', linkRaw)).toString('hex');
  const outputRef = { key: 'raw/' + Buffer.from(await crypto.subtle.digest('SHA-256', output)).toString('hex') };
  for (const ref of [rootRef, prepared.input, outputRef]) {
    const path = join(env.root, 'archive', ref.key);
    const original = ref === outputRef ? output : readFileSync(path);
    for (const corrupt of [false, true]) {
      let injected = false;
      env.bucket.afterGet = key => {
        if (key === linkKey && !injected) {
          injected = true;
          if (corrupt) writeFileSync(path, bytes('corrupted original')); else rmSync(path);
        }
      };
      await assert.rejects(session.accept(identity, owned, prepared.input.sha256, output), /object_missing|mismatch/);
      assert.ok(injected);
      assert.equal(env.storage.sql.exec('SELECT revision FROM m12_execution_heads WHERE task_id=?', fixture.task_id).toArray()[0].revision, 0);
      assert.equal(env.storage.sql.exec('SELECT completed FROM m12_execution_validation_inputs').toArray()[0].completed, 0);
      env.bucket.afterGet = null;
      writeFileSync(path, original);
    }
  }
  env.storage.db.exec("CREATE TRIGGER fail_execution_result_log BEFORE INSERT ON m12_execution_validation_result_log BEGIN SELECT RAISE(ABORT, 'synthetic receipt interruption'); END");
  await assert.rejects(session.accept(identity, owned, prepared.input.sha256, output), /receipt interruption/);
  assert.equal(env.storage.sql.exec('SELECT revision FROM m12_execution_heads WHERE task_id=?', fixture.task_id).toArray()[0].revision, 0);
  assert.equal(env.storage.sql.exec('SELECT completed FROM m12_execution_validation_inputs').toArray()[0].completed, 0);
  env.storage.db.exec('DROP TRIGGER fail_execution_result_log');
  env.restart();
  session = new ExecutionComputationSession(env.storage, env.bucket, { clock: () => Date.now() });
  const receipt = await session.accept(identity, owned, prepared.input.sha256, output);
  assert.equal(receipt.snapshot.revision, 1);
  const frozenPair = Object.fromEntries(['input', 'object', 'link'].map(key => [key, readFileSync(join(env.root, 'archive', receipt.snapshot.history[0][key].key)).toString('base64')]));
  assert.equal(readFileSync(join(env.root, 'archive', receipt.snapshot.root.root.key)).toString('base64'), fixture.root_bytes);
  assert.deepEqual(await session.accept(identity, owned, prepared.input.sha256, output), receipt);
  // Restore fixture bytes only after proving accept never repairs them.
  const refs = [receipt.snapshot.root.root, ...['input', 'object', 'link'].map(key => receipt.snapshot.history[0][key])];
  for (const ref of refs) {
    const path = join(env.root, 'archive', ref.key), original = readFileSync(path);
    for (const corrupt of [false, true]) {
      if (corrupt) writeFileSync(path, bytes('corrupted original')); else rmSync(path);
      const puts = env.bucket.puts;
      await assert.rejects(session.accept(identity, owned, prepared.input.sha256, output), /object_missing|mismatch/);
      assert.equal(env.bucket.puts, puts);
      writeFileSync(path, original);
    }
  }
  const second = await session.prepare(identity, owned, fixture.task_id, new Uint8Array(Buffer.from(fixture.request_bytes, 'base64')));
  const after = python({ operation: 'fixed_execution', input_bytes: Buffer.from(second.input_bytes).toString('base64') });
  const afterBytes = new Uint8Array(Buffer.from(after.output_bytes, 'base64'));
  assert.equal(JSON.parse(new TextDecoder().decode(afterBytes)).next_pair, null);
  // Lose each promised historical original while saving the null-pair output.
  const outputKey = 'raw/' + Buffer.from(await crypto.subtle.digest('SHA-256', afterBytes)).toString('hex');
  for (const ref of refs) {
    const path = join(env.root, 'archive', ref.key), original = readFileSync(path);
    for (const corrupt of [false, true]) {
      let injected = false;
      env.bucket.afterGet = key => {
        if (key === outputKey && !injected) {
          injected = true;
          if (corrupt) writeFileSync(path, bytes('corrupted original')); else rmSync(path);
        }
      };
      await assert.rejects(session.accept(identity, owned, second.input.sha256, afterBytes), /object_missing|mismatch/);
      assert.ok(injected);
      assert.equal(env.storage.sql.exec('SELECT completed FROM m12_execution_validation_inputs WHERE input_sha=?', second.input.sha256).toArray()[0].completed, 0);
      env.bucket.afterGet = null;
      writeFileSync(path, original);
    }
  }
  const final = await session.accept(identity, owned, second.input.sha256, afterBytes);
  assert.equal(final.snapshot.revision, 1);
  assert.deepEqual(Object.fromEntries(['input', 'object', 'link'].map(key => [key, readFileSync(join(env.root, 'archive', final.snapshot.history[0][key].key)).toString('base64')])), frozenPair);
  assert.equal(readFileSync(join(env.root, 'archive', final.snapshot.root.root.key)).toString('base64'), fixture.root_bytes);
  env.storage.db.exec('DELETE FROM m12_execution_validation_results; DELETE FROM m12_execution_validation_result_log');
  await assert.rejects(session.accept(identity, owned, second.input.sha256, afterBytes), /recovery_required/);
});

test('local fixed runner checkpoints actual receipts and resumes after checkpoint SQL interruption', async t => {
  const { ExecutionComputationSession } = await import('../services/publication/execution_session.mjs');
  const { ExecutionScheduler } = await import('../services/publication/execution_scheduler.mjs');
  const { LocalExecutionRunner } = await import('../services/publication/local_execution_runner.mjs');
  const { spawnSync } = await import('node:child_process');
  const pythonPath = spawnSync('python3', ['-c', 'import sys;print(sys.executable)'], { encoding: 'utf8', timeout: 5000 });
  assert.equal(pythonPath.status, 0);
  const pythonExecutable = pythonPath.stdout.trim();
  const source = spawnWithFileInput(pythonExecutable, ['-B', 'tests/m12_execution_history_fixture.py'], Buffer.from(JSON.stringify({ operation: 'source_fixture', prior_source: true })), {
    encoding: 'utf8', timeout: 15000, killSignal: 'SIGKILL',
    maxBuffer: 32 * 1024 * 1024, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONPATH: 'tests:.' },
  });
  assert.equal(source.status, 0, source.stderr);
  const fixture = JSON.parse(source.stdout), start = Date.now(), env = setup(t, start);
  const rootIdentity = { ...IDENTITY, issued_at: Math.floor(start / 1000) - 1, expires_at: Math.floor(start / 1000) + 300 };
  await env.store.register(rootIdentity, env.daily, DAILY, fixture.task_id, new Uint8Array(Buffer.from(fixture.root_bytes, 'base64')));
  const identity = { ...rootIdentity, job: { repository_id: '1', workflow_ref: 'local/synthetic@main', workflow_commit: fixture.commit,
    run_id: '2', run_attempt: 1, environment: 'synthetic' }, code_commit: fixture.commit,
    actor_id: '1', subject: 'synthetic-only', token_id: 'synthetic-only' };
  const owned = token(env.leases.acquire('execution/' + fixture.task_id, identity.job, EPOCH));
  new ExecutionScheduler(env.storage, env.bucket).initializeEmpty();
  new ExecutionComputationSession(env.storage, env.bucket).initializeEmpty();
  const request = new Uint8Array(Buffer.from(fixture.request_bytes, 'base64'));
  let runner = new LocalExecutionRunner(env.storage, env.bucket, { pythonExecutable });
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 100);
  try {
    const cancelled = await runner.runTask(identity, owned, fixture.task_id, request, { signal: abort.signal });
    assert.equal(cancelled.status, 'queued'); assert.equal(cancelled.outcome, 'cancelled');
  } finally { clearTimeout(timer); }
  assert.equal(new ExecutionScheduler(env.storage, env.bucket).list()[0].schedule.state.attempts_today, 0);
  env.storage.db.exec("CREATE TRIGGER fail_checkpoint BEFORE INSERT ON m12_execution_schedule_log WHEN json_extract(NEW.record_json,'$.kind')='checkpoint' BEGIN SELECT RAISE(ABORT, 'synthetic checkpoint interruption'); END");
  await assert.rejects(runner.runTask(identity, owned, fixture.task_id, request), /checkpoint interruption/);
  const pending = new ExecutionScheduler(env.storage, env.bucket).list()[0];
  assert.equal(pending.snapshot.revision, 1);
  assert.equal(pending.schedule.kind, 'dispatch');
  assert.ok(pending.schedule.dispatch_input_sha);
  env.storage.db.exec('DROP TRIGGER fail_checkpoint');
  env.restart();
  runner = new LocalExecutionRunner(env.storage, env.bucket, { pythonExecutable });
  const result = await runner.runTask(identity, owned, fixture.task_id, request);
  assert.equal(result.status, 'caught_up_for_input');
  assert.equal(result.checkpoint.state.attempts_today, 1);
  assert.equal(result.checkpoint.state.state, 'queued');
  assert.equal(result.checkpoint.state.reason, 'no_new_execution_pair');
  assert.equal(result.checkpoint.checkpoint_snapshot.revision, 1);
  const rows = env.storage.sql.exec('SELECT record_json FROM m12_execution_schedule_events').toArray().map(row => JSON.parse(row.record_json));
  const checkpoints = rows.filter(row => row.kind === 'checkpoint');
  assert.equal(checkpoints.length, 2);
  assert.deepEqual(checkpoints.map(row => [row.receipt.source_snapshot.revision, row.receipt.snapshot.revision]), [[0, 1], [1, 1]]);
  assert.equal(rows.filter(row => row.kind === 'claim').length, 1);
  assert.equal(readFileSync(join(env.root, 'archive', result.checkpoint.receipt.snapshot.root.root.key)).toString('base64'), fixture.root_bytes);
  const original = result.checkpoint.receipt.snapshot.history[0].object;
  rmSync(join(env.root, 'archive', original.key));
  const puts = env.bucket.puts;
  await assert.rejects(new ExecutionScheduler(env.storage, env.bucket).checkpoint(identity, owned, fixture.task_id,
    result.checkpoint.position, result.checkpoint.input_sha), /object_missing/);
  assert.equal(env.bucket.puts, puts);
});

test('synthetic bridge timeout retains a Python stack and reaps the stalled child', async () => {
  const result = spawnWithFileInput('python3', ['-B', 'tests/m12_execution_history_fixture.py'], Buffer.from(JSON.stringify({ operation: 'diagnostic_stall' })), {
    encoding: 'utf8', timeout: 1500, killSignal: 'SIGKILL',
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONPATH: 'tests:.' },
  });
  assert.equal(result.error.code, 'ETIMEDOUT');
  assert.equal(result.signal, 'SIGKILL');
  assert.match(result.stderr, /Timeout.*\nThread/s);
  assert.match(result.stderr, /m12_execution_history_fixture.py/);
  assert.equal(result.stdout, '');
});

test('fixture stdin is a finite read-only regular file preserving exact large bytes', () => {
  const raw = Buffer.concat([Buffer.from('原件\u0000\r\n 100.0 '), Buffer.alloc(1024 * 1024, 0xab)]);
  const result = spawnWithFileInput('python3', ['-B', '-c',
    'import sys,os,stat,fcntl,hashlib,json; raw=sys.stdin.buffer.read(); print(json.dumps({"regular":stat.S_ISREG(os.fstat(0).st_mode),"readonly":fcntl.fcntl(0,fcntl.F_GETFL)&os.O_ACCMODE==os.O_RDONLY,"size":len(raw),"sha":hashlib.sha256(raw).hexdigest(),"eof":sys.stdin.buffer.read()==b""}))'], raw,
    { encoding: 'utf8', timeout: 15000, killSignal: 'SIGKILL' });
  assert.equal(result.status, 0, result.stderr);
  const read = JSON.parse(result.stdout);
  assert.equal(read.regular, true); assert.equal(read.readonly, true); assert.equal(read.eof, true);
  assert.equal(read.size, raw.length);
  return crypto.subtle.digest('SHA-256', raw).then(hash => assert.equal(read.sha, Buffer.from(hash).toString('hex')));
});
