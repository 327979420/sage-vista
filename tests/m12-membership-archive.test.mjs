import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, generateKeyPairSync, sign } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { MembershipArchiveSession } from '../services/publication/membership_archive.mjs';
import { LeaseStore } from '../services/publication/leases.mjs';

const NOW = Date.parse('2026-09-08T23:47:00Z');
const EPOCH = '11111111-1111-4111-8111-111111111111';
const SOURCE = 'https://eodhd.com/api/exchange-symbol-list/US?delisted=0&fmt=json';
const keys = generateKeyPairSync('rsa', { modulusLength: 2048 });
const jwk = { ...keys.publicKey.export({ format: 'jwk' }), kid: 'test', alg: 'RS256', use: 'sig' };
const identityPolicy = { repository: 'example/sage', repository_id: '123',
  workflow_ref: 'example/sage/.github/workflows/daily.yml@refs/heads/main', workflow_commit: 'a'.repeat(40),
  code_commit: 'b'.repeat(40), environment: 'production', subject: 'repo:example/sage:environment:production' };
const claims = { iss: 'https://token.actions.githubusercontent.com', aud: 'sage-vista-publication',
  sub: identityPolicy.subject, repository: identityPolicy.repository, repository_id: '123',
  workflow_ref: identityPolicy.workflow_ref, workflow_sha: identityPolicy.workflow_commit,
  sha: identityPolicy.code_commit, environment: 'production', ref: 'refs/heads/main', ref_type: 'branch',
  actor_id: '789', run_id: '456', run_attempt: '1', jti: 'signed-test',
  iat: NOW / 1000 - 30, nbf: NOW / 1000 - 30, exp: NOW / 1000 + 300 };
const JOB = { repository_id: '123', workflow_ref: identityPolicy.workflow_ref, workflow_commit: identityPolicy.workflow_commit,
  run_id: '456', run_attempt: 1, environment: 'production' };
function token(patch = {}) {
  const encode = v => Buffer.from(JSON.stringify(v)).toString('base64url');
  const input = encode({ alg: 'RS256', typ: 'JWT', kid: 'test' }) + '.' + encode({ ...claims, ...patch });
  return input + '.' + sign('RSA-SHA256', Buffer.from(input), keys.privateKey).toString('base64url');
}
function descriptor(raw) {
  const hash = createHash('sha256').update(raw).digest('hex');
  return { key: 'raw/' + hash, sha256: 'sha256:' + hash, size_bytes: raw.length };
}
const expected = desc => ({ sha256: desc.sha256, size_bytes: desc.size_bytes });

function fixture(t, patchPolicy = {}) {
  const db = new DatabaseSync(':memory:');
  t.after(() => db.close());
  const storage = { sql: { exec(sql, ...args) { return { toArray: () => db.prepare(sql).all(...args).map(row => ({ ...row })) }; } },
    transactionSync(callback) {
      db.exec('BEGIN IMMEDIATE');
      try { const result = callback(); assert.ok(!(result instanceof Promise)); db.exec('COMMIT'); return result; }
      catch (error) { db.exec('ROLLBACK'); throw error; }
    } };
  let now = NOW;
  const clock = () => now;
  const leases = new LeaseStore(storage, { clock });
  leases.initialize(EPOCH);
  const resource = 'daily/2026-09-08/config:1';
  const lease = leases.acquire(resource, JOB, EPOCH);
  const evidence = Buffer.from('Synthetic permission source; not a real data license.');
  const policy = { acquisition_evidence: descriptor(evidence), actor_id: '789', as_of: '2026-09-08', config_id: 'config:1',
    expires_at: NOW + 240000, job: JOB, lease_token: { epoch: EPOCH, fence: lease.lease.fence }, ...patchPolicy };
  const objects = new Map([[descriptor(evidence).key, evidence]]), calls = [];
  const hooks = {};
  const bucket = {
    async put(key, raw, options) {
      calls.push(['put', key]);
      assert.equal(options.onlyIf.get('If-None-Match'), '*');
      if (!objects.has(key)) objects.set(key, new Uint8Array(raw));
      await hooks.put?.(key);
    },
    async get(key) {
      calls.push(['get', key]);
      await hooks.get?.(key);
      const raw = objects.get(key);
      return raw === undefined ? null : { arrayBuffer: async () => new Uint8Array(raw).buffer };
    },
  };
  let verified = 0;
  const dependencies = { bucket, storage, clock, fetchKeys: async () => {
    verified++; return new Response(JSON.stringify({ keys: [jwk] }));
  } };
  const create = (sessionPolicy = policy) => new MembershipArchiveSession(identityPolicy, { ...dependencies, sessionPolicy });
  return { db, storage, leases, resource, policy, evidence, objects, bucket, calls, hooks, create,
    session: create(), setTime: ms => { now = ms; }, verified: () => verified,
    rows: () => db.prepare('SELECT * FROM m12_membership_raw_access').all() };
}

const RAW = Buffer.from('unregistered private response bytes\n');
const RAW_DESC = descriptor(RAW);
const save = (f, service = f.session, jwt = token()) => service.put(jwt, RAW_DESC.key, RAW, expected(RAW_DESC));
const read = (f, service = f.session, jwt = token()) => service.read(jwt, RAW_DESC.key, expected(RAW_DESC));

test('default disabled constructs no bindings or network', async () => {
  const session = new MembershipArchiveSession(null);
  await assert.rejects(session.acquisitionEvidence('bad', '2026-09-08', SOURCE), /disabled/);
  await assert.rejects(session.put('bad', RAW_DESC.key, RAW, expected(RAW_DESC)), /disabled/);
  await assert.rejects(session.read('bad', RAW_DESC.key, expected(RAW_DESC)), /disabled/);
});

test('fresh signed identity gets fixed evidence, actual write/readback and persistent own read', async t => {
  const f = fixture(t);
  assert.deepEqual(Buffer.from(await f.session.acquisitionEvidence(token(), '2026-09-08', SOURCE)), f.evidence);
  assert.deepEqual(await save(f), RAW_DESC);
  assert.deepEqual(Buffer.from(await read(f, f.create())), RAW);
  assert.equal(f.verified(), 3);
  assert.equal(f.rows().length, 1);
  assert.deepEqual(f.calls.map(call => call[0]), ['get', 'get', 'put', 'get', 'get', 'get']);
  const { key, ...want } = f.policy.acquisition_evidence;
  assert.deepEqual(Buffer.from(await f.session.read(token(), key, want)), f.evidence);
});

test('hash knowledge alone does not permit another object read', async t => {
  const f = fixture(t);
  f.objects.set(RAW_DESC.key, RAW);
  await assert.rejects(read(f), /not_owned/);
  assert.equal(f.calls.length, 0);
  await save(f); // Actual possession+write/readback grants only this session access.
  assert.deepEqual(Buffer.from(await read(f)), RAW);
});

test('wrong Job actor code workflow or token signature cannot touch objects', async t => {
  const f = fixture(t);
  for (const change of [{ run_id: '457' }, { run_attempt: '2' }, { actor_id: '790' },
    { sha: 'c'.repeat(40) }, { workflow_sha: 'c'.repeat(40) }, { repository_id: '124' }, { exp: NOW / 1000 }]) {
    await assert.rejects(save(f, f.session, token(change)));
  }
  const parts = token().split('.'); parts[2] = Buffer.alloc(256).toString('base64url');
  await assert.rejects(save(f, f.session, parts.join('.')), /signature/);
  assert.equal(f.calls.length, 0);
  assert.equal(f.rows().length, 0);
});

test('source/date substitution and missing or corrupt permit bytes fail', async t => {
  const f = fixture(t);
  for (const [day, url] of [['2026-09-09', SOURCE], ['2026-09-08', SOURCE + '&type=common_stock']]) {
    await assert.rejects(f.session.acquisitionEvidence(token(), day, url), /target_mismatch/);
  }
  assert.equal(f.calls.length, 0);
  f.objects.set(f.policy.acquisition_evidence.key, Buffer.from('tampered'));
  await assert.rejects(f.session.acquisitionEvidence(token(), '2026-09-08', SOURCE), /mismatch/);
  f.objects.clear();
  await assert.rejects(f.session.acquisitionEvidence(token(), '2026-09-08', SOURCE), /missing/);
});

test('policy is frozen; another session cannot borrow access even with same Job', async t => {
  const f = fixture(t);
  const original = structuredClone(f.policy);
  await save(f);
  f.policy.actor_id = '790'; f.policy.job = { ...JOB, run_id: '457' };
  assert.deepEqual(Buffer.from(await read(f)), RAW);
  const other = f.create({ ...original, expires_at: original.expires_at - 1 });
  await assert.rejects(read(f, other), /not_owned/);
});

test('changed identity code policy cannot borrow stored ownership', async t => {
  const f = fixture(t);
  await save(f);
  // A fresh server instance pinned to a different execution commit has a distinct binding.
  const different = new MembershipArchiveSession({ ...identityPolicy, code_commit: 'c'.repeat(40) }, {
    sessionPolicy: f.policy, storage: f.storage, bucket: f.bucket, clock: () => NOW,
    fetchKeys: async () => new Response(JSON.stringify({ keys: [jwk] })),
  });
  await assert.rejects(read(f, different, token({ sha: 'c'.repeat(40) })), /not_owned/);
});

test('mutating caller bytes during signature I/O cannot change archived object', async t => {
  const f = fixture(t);
  const raw = new Uint8Array(RAW);
  const pending = f.session.put(token(), RAW_DESC.key, raw, expected(RAW_DESC));
  raw.fill(0);
  await pending;
  assert.deepEqual(Buffer.from(await read(f)), RAW);
});

test('archive failures retain orphan but never grant new ownership', async t => {
  for (const kind of ['put', 'get']) {
    const f = fixture(t);
    f.hooks[kind] = async key => { if (key === RAW_DESC.key) throw new Error('storage_failure'); };
    await assert.rejects(save(f), /storage_failure/);
    assert.ok(f.objects.has(RAW_DESC.key));
    assert.equal(f.rows().length, 0);
  }
});

test('session or JWT expiry during write leaves orphan unowned', async t => {
  for (const expiry of ['session', 'identity']) {
    const f = fixture(t, { expires_at: NOW + (expiry === 'session' ? 100000 : 400000) });
    f.hooks.put = () => {
      if (expiry === 'identity') {
        f.setTime(NOW + 60000);
        f.leases.renew(f.resource, JOB, f.policy.lease_token); // Lease outlives the old JWT.
      }
      f.setTime(NOW + (expiry === 'session' ? 100000 : 300000));
    };
    await assert.rejects(save(f));
    assert.ok(f.objects.has(RAW_DESC.key));
    assert.equal(f.rows().length, 0);
  }
});

test('fence takeover during write or read cannot succeed', async t => {
  for (const operation of ['write', 'read']) {
    const f = fixture(t, { expires_at: NOW + 600000 });
    if (operation === 'read') await save(f);
    f.hooks.get = key => {
      if (key !== RAW_DESC.key) return;
      f.setTime(NOW + 301000);
      f.leases.acquire(f.resource, { ...JOB, run_id: '457' }, EPOCH);
    };
    await assert.rejects(operation === 'write' ? save(f) : read(f));
    assert.equal(f.rows().length, operation === 'write' ? 0 : 1);
  }
});

test('expiry at final SQL guard rolls back ownership insert', async t => {
  const f = fixture(t);
  const exec = f.storage.sql.exec;
  f.storage.sql.exec = (sql, ...args) => {
    const result = exec(sql, ...args);
    if (sql.startsWith('INSERT INTO m12_membership_raw_access')) f.setTime(f.policy.expires_at);
    return result;
  };
  await assert.rejects(save(f), /deadline/);
  assert.equal(f.rows().length, 0);
  assert.ok(f.objects.has(RAW_DESC.key));
});

test('idempotent and concurrent same-byte writes preserve one descriptor and reject corruption', async t => {
  const f = fixture(t);
  await Promise.all([save(f), save(f)]);
  assert.equal(f.rows().length, 1);
  assert.deepEqual(Buffer.from(await read(f)), RAW);
  f.objects.set(RAW_DESC.key, Buffer.from('corruption'));
  await assert.rejects(read(f), /mismatch/);
  await assert.rejects(save(f), /mismatch/);
});

test('only bounded raw keys and exact descriptors accepted including empty failure body', async t => {
  const f = fixture(t);
  await assert.rejects(f.session.put(token(), 'authority/' + 'a'.repeat(64) + '.json', RAW, expected(RAW_DESC)), /descriptor/);
  await assert.rejects(f.session.put(token(), RAW_DESC.key, RAW, { ...expected(RAW_DESC), extra: true }), /descriptor/);
  await assert.rejects(f.session.put(token(), RAW_DESC.key, RAW, { ...expected(RAW_DESC), size_bytes: 32 * 1024 * 1024 + 2 }), /descriptor/);
  assert.equal(f.calls.length, 0);
  const empty = new Uint8Array(), desc = descriptor(empty);
  await f.session.put(token(), desc.key, empty, expected(desc));
  assert.equal((await f.session.read(token(), desc.key, expected(desc))).length, 0);
});


test('missing permit blocks writes; missing paired access log blocks reads and replay', async t => {
  const f = fixture(t);
  f.objects.delete(f.policy.acquisition_evidence.key);
  await assert.rejects(save(f), /missing/);
  assert.equal(f.objects.has(RAW_DESC.key), false);
  f.objects.set(f.policy.acquisition_evidence.key, f.evidence);
  await save(f);
  f.db.exec('DELETE FROM m12_membership_raw_log');
  await assert.rejects(read(f), /access_conflict/);
  await assert.rejects(save(f), /access_conflict/);
});

test('log write failure rolls back access; read-time ownership loss never releases bytes', async t => {
  const f = fixture(t);
  const exec = f.storage.sql.exec;
  f.storage.sql.exec = (sql, ...args) => {
    if (sql.startsWith('INSERT INTO m12_membership_raw_log')) throw new Error('log_failed');
    return exec(sql, ...args);
  };
  await assert.rejects(save(f), /log_failed/);
  assert.equal(f.rows().length, 0);
  f.storage.sql.exec = exec;
  await save(f);
  f.hooks.get = key => { if (key === RAW_DESC.key) f.db.exec('DELETE FROM m12_membership_raw_access'); };
  await assert.rejects(read(f), /access_conflict/);
});
