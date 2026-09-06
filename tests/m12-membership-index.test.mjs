import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { MembershipObservationIndex } from '../services/publication/membership_index.mjs';
import { LeaseStore } from '../services/publication/leases.mjs';

const NOW = Date.parse('2026-09-08T23:48:00Z');
const EPOCH = '11111111-1111-4111-8111-111111111111';
const JOB = { repository_id: '123', workflow_ref: 'repo/workflow@refs/heads/main', workflow_commit: 'a'.repeat(40),
  run_id: '456', run_attempt: 1, environment: 'production' };
const ID = { job: JOB, issued_at: NOW / 1000 - 60, expires_at: NOW / 1000 + 600 };
const resource = (day = '2026-09-08', config = 'config:1') => 'daily/' + day + '/' + config;
const archive = digit => ({ key: 'raw/' + digit.repeat(64), sha256: 'sha256:' + digit.repeat(64), size_bytes: 500 });

function binding(path = ':memory:') {
  const db = new DatabaseSync(path);
  return { db, sql: { exec(query, ...args) { const rows = db.prepare(query).all(...args); return { toArray: () => rows.map(row => ({ ...row })) }; } },
    transactionSync(callback) {
      db.exec('BEGIN IMMEDIATE');
      try { const value = callback(); db.exec('COMMIT'); return value; }
      catch (error) { db.exec('ROLLBACK'); throw error; }
    } };
}
function setup(t, path) {
  const storage = binding(path); t.after(() => storage.db.close());
  const state = { now: NOW }, clock = () => state.now;
  const leases = new LeaseStore(storage, { clock }); leases.initialize(EPOCH);
  const store = new MembershipObservationIndex(storage, { clock });
  const token = (r = resource(), job = JOB) => { const value = leases.acquire(r, job, EPOCH); return { epoch: value.epoch, fence: value.lease.fence }; };
  return { storage, store, leases, state, clock, token };
}
function add(f, { day = '2026-09-08', item = archive('a'), expected, r = resource(day), identity = ID, token = f.token(r) } = {}) {
  return f.store.append(identity, token, r, { as_of: day, observation_archive: item,
    expected_index: expected ?? f.store.readCurrent(identity, token, r) });
}

test('membership index requires explicit empty setup and refuses automatic recovery', t => {
  const f = setup(t), token = f.token();
  assert.throws(() => f.store.readCurrent(ID, token, resource()), /recovery_required/);
  f.store.initializeEmpty();
  assert.deepEqual(f.store.readCurrent(ID, token, resource()), { revision: 0, head: null, history: [] });
  assert.throws(() => f.store.initializeEmpty(), /not_empty/);
  f.storage.db.exec('DELETE FROM m12_membership_head');
  new MembershipObservationIndex(f.storage, { clock: f.clock });
  assert.throws(() => f.store.readCurrent(ID, token, resource()), /recovery_required/);
  assert.throws(() => f.store.initializeEmpty(), /not_empty/);
});

test('membership index atomically appends paired records and returns detached idempotent history', t => {
  const f = setup(t); f.store.initializeEmpty();
  const first = add(f);
  assert.deepEqual(first, { revision: 1, head: archive('a'), history: [archive('a')] });
  assert.deepEqual(add(f), first);
  assert.equal(f.storage.db.prepare('SELECT count(*) AS n FROM m12_membership_index_log').get().n, 1);
  first.history[0].size_bytes = 1;
  assert.equal(f.store.readCurrent(ID, f.token(), resource()).history[0].size_bytes, 500);
  assert.throws(() => add(f, { item: archive('b') }), /date_conflict/);
});

test('membership index survives file-backed close and reopen', t => {
  const directory = mkdtempSync(join(tmpdir(), 'sage-membership-index-'));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const path = join(directory, 'index.sqlite'), first = binding(path);
  const leases = new LeaseStore(first, { clock: () => NOW }); leases.initialize(EPOCH);
  const store = new MembershipObservationIndex(first, { clock: () => NOW }); store.initializeEmpty();
  const h = leases.acquire(resource(), JOB, EPOCH), token = { epoch: h.epoch, fence: h.lease.fence };
  const expected = store.readCurrent(ID, token, resource());
  const current = store.append(ID, token, resource(), { expected_index: expected, as_of: '2026-09-08', observation_archive: archive('a') });
  first.db.close();
  const second = binding(path); t.after(() => second.db.close());
  const reopened = new MembershipObservationIndex(second, { clock: () => NOW });
  assert.deepEqual(reopened.readCurrent(ID, token, resource()), current);
});

test('membership index compares one global root across date and configuration leases', t => {
  const f = setup(t); f.store.initializeEmpty();
  const old = f.store.readCurrent(ID, f.token(), resource());
  const nextResource = resource('2026-09-09', 'config:2'); f.token(nextResource);
  add(f);
  assert.throws(() => add(f, { expected: old, day: '2026-09-09', r: nextResource, item: archive('b') }), /compare_failed/);
  const current = add(f, { day: '2026-09-09', r: nextResource, item: archive('b') });
  assert.equal(current.revision, 2);
  assert.throws(() => add(f, { expected: current, item: archive('c') }), /date_conflict/);
  assert.throws(() => add(f, { day: '2026-09-10', item: archive('a') }), /duplicate_observation/);
});

test('membership index lost pairs head or genesis fail closed without source reconstruction', t => {
  for (const sql of ['DELETE FROM m12_membership_index_log', 'DELETE FROM m12_membership_index',
    'DELETE FROM m12_membership_head', 'DELETE FROM m12_membership_genesis',
    'UPDATE m12_membership_index_log SET record_json=\'{}\'',
    'DELETE FROM m12_membership_index; DELETE FROM m12_membership_index_log']) {
    const f = setup(t); f.store.initializeEmpty(); add(f);
    f.storage.db.exec(sql);
    assert.throws(() => f.store.readCurrent(ID, f.token(), resource()));
    assert.throws(() => add(f));
    assert.throws(() => f.store.initializeEmpty());
  }
});

test('membership index rolls back every partial write and expiry during final commit guard', t => {
  for (const point of ['INSERT INTO m12_membership_index VALUES', 'INSERT INTO m12_membership_index_log',
    'UPDATE m12_membership_head', 'expiry']) {
    const f = setup(t); f.store.initializeEmpty();
    const token = f.token(), empty = f.store.readCurrent(ID, token, resource());
    const original = f.storage.sql.exec;
    f.storage.sql.exec = (sql, ...args) => {
      if (point !== 'expiry' && sql.startsWith(point)) throw new Error('injected_write_failure');
      const value = original(sql, ...args);
      if (point === 'expiry' && sql.startsWith('UPDATE m12_membership_head')) f.state.now = NOW + 300000;
      return value;
    };
    assert.throws(() => add(f, { expected: empty, token }), /injected_write_failure|expired_before_commit/);
    f.storage.sql.exec = original;
    assert.equal(f.storage.db.prepare('SELECT revision FROM m12_membership_head').get().revision, 0);
    assert.equal(f.storage.db.prepare('SELECT count(*) AS n FROM m12_membership_index').get().n, 0);
    assert.equal(f.storage.db.prepare('SELECT count(*) AS n FROM m12_membership_index_log').get().n, 0);
  }
});

test('membership index rejects wrong owner stale fence and expired identity on reads and writes', t => {
  const f = setup(t); f.store.initializeEmpty();
  const token = f.token(), empty = f.store.readCurrent(ID, token, resource());
  for (const identity of [{ ...ID, job: { ...JOB, run_id: 'other' } }, { ...ID, expires_at: NOW / 1000 },
    { ...ID, issued_at: NOW / 1000 + 1 }, { ...ID, expires_at: true }]) {
    assert.throws(() => f.store.readCurrent(identity, token, resource()));
    assert.throws(() => add(f, { identity, expected: empty, token }));
  }
  f.leases.release(resource(), JOB, token); const next = f.token();
  assert.notEqual(next.fence, token.fence);
  assert.throws(() => add(f, { expected: empty, token }), /stale/);
});

test('membership index cannot accept alternate resource malformed descriptor or extra fields', t => {
  const f = setup(t); f.store.initializeEmpty(); const token = f.token();
  const input = { expected_index: f.store.readCurrent(ID, token, resource()), as_of: '2026-09-08', observation_archive: archive('a') };
  for (const wrong of [{ ...input, allowed: true }, { ...input, as_of: '2026-09-31' },
    { ...input, observation_archive: { ...archive('a'), size_bytes: true } },
    { ...input, observation_archive: { ...archive('a'), key: 'raw/' + 'b'.repeat(64) } },
    { ...input, expected_index: { ...input.expected_index, revision: 1 } }]) {
    assert.throws(() => f.store.append(ID, token, resource(), wrong));
  }
  assert.throws(() => f.store.append(ID, token, 'publish/global', input));
});

test('membership persisted index feeds actual Python source replay and rejects a missing original', t => {
  const script = `import base64,json
from tests.test_m12_membership_identity import observation,symbol,evidence,D1,D2
from services.market_data.membership_identity import build_observed_membership
values=[observation(D1,[symbol()]),observation(D2,[symbol()])]
e=evidence(*values)
result=build_observed_membership(e,as_of=D2)
print(json.dumps({'index':e['current_index'],'originals':[{k:base64.b64encode(v).decode() for k,v in x.items()} for x in values],'instrument_id':result.members[0]['instrument_id']}))`;
  const prepared = spawnSync('python3', ['-B', '-c', script], { encoding: 'utf8' });
  assert.equal(prepared.status, 0, prepared.stderr);
  const fixture = JSON.parse(prepared.stdout), f = setup(t); f.store.initializeEmpty();
  for (let i = 0; i < 2; i++) add(f, { day: i ? '2026-09-09' : '2026-09-08', item: fixture.index.history[i] });
  fixture.index = f.store.readCurrent(ID, f.token(), resource());
  const replay = `import sys,json,base64
from services.market_data.membership_identity import build_observed_membership
v=json.load(sys.stdin)
e={'current_index':v['index'],'observations':[{k:base64.b64decode(x) for k,x in item.items()} for item in v['originals']]}
print(build_observed_membership(e,as_of='2026-09-09').members[0]['instrument_id'])`;
  const result = spawnSync('python3', ['-B', '-c', replay], { input: JSON.stringify(fixture), encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr); assert.equal(result.stdout.trim(), fixture.instrument_id);
  fixture.originals.pop();
  assert.notEqual(spawnSync('python3', ['-B', '-c', replay], { input: JSON.stringify(fixture), encoding: 'utf8' }).status, 0);
});
