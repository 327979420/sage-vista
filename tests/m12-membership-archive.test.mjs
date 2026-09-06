import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, generateKeyPairSync, sign } from 'node:crypto';
import { DatabaseSync } from 'node:sqlite';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { MembershipArchiveApi } from '../services/publication/membership_api.mjs';
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
    session: create(), api: new MembershipArchiveApi(identityPolicy, { ...dependencies, sessionPolicy: policy, enabled: true }), setTime: ms => { now = ms; }, verified: () => verified,
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


const PROTOCOL = 'm12-membership-archive/1';
const canonical = v => Array.isArray(v) ? v.map(canonical) : v && typeof v === 'object' ?
  Object.fromEntries(Object.keys(v).sort().map(k => [k, canonical(v[k])])) : v;
const wire = v => JSON.stringify(canonical(v));
const request = (op, value, jwt = token()) => new Request('https://coordinator.example.test/v1/membership/' + op,
  { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + jwt }, body: wire(value) });
const permit = { protocol: PROTOCOL, as_of: '2026-09-08', request_url: SOURCE };
const put = { protocol: PROTOCOL, ...RAW_DESC, bytes_base64: RAW.toString('base64') };
const get = { protocol: PROTOCOL, ...RAW_DESC };

test('API remains disabled without binding or rejects enabled missing policy', async () => {
  const api = new MembershipArchiveApi(null);
  assert.equal((await api.fetch(request('permit', permit))).status, 503);
  assert.throws(() => new MembershipArchiveApi(null, { enabled: true }), /policy_required/);
});

test('three fixed API routes perform actual byte session roundtrip', async t => {
  const f = fixture(t);
  const granted = await (await f.api.fetch(request('permit', permit))).json();
  assert.equal(granted.bytes_base64, f.evidence.toString('base64'));
  assert.equal(granted.as_of, permit.as_of);
  const stored = await f.api.fetch(request('put', put));
  assert.equal(stored.status, 200);
  assert.deepEqual(await stored.json(), { protocol: PROTOCOL, ...RAW_DESC });
  const loaded = await f.api.fetch(request('read', get));
  assert.equal(loaded.headers.get('Cache-Control'), 'no-store');
  assert.deepEqual(await loaded.json(), put);
});

test('API rejects route substitutions unknown fields duplicate JSON and noncanonical bytes', async t => {
  const f = fixture(t);
  for (const op of ['unknown', 'read?key=other']) assert.equal((await f.api.fetch(request(op, get))).status, 404);
  assert.equal((await f.api.fetch(new Request('https://coordinator.example.test/v1/membership/read'))).status, 405);
  for (const raw of [wire({ ...put, job: JOB }), '{"protocol":"x","protocol":"m12-membership-archive/1"}',
    wire(put) + ' ', wire({ ...put, bytes_base64: RAW.toString('base64') + '\n' }), wire({ ...get, size_bytes: true })]) {
    const req = request('put', put);
    assert.equal((await f.api.fetch(new Request(req.url, { method: 'POST', headers: req.headers, body: raw }))).status, 400);
  }
  assert.equal(f.calls.length, 0);
});

test('API verifies identity before requesting body and never echoes private errors', async t => {
  const f = fixture(t);
  const req = request('put', put, 'unsigned');
  Object.defineProperty(req, 'body', { get() { throw new Error('body_was_touched'); } });
  assert.equal((await f.api.fetch(req)).status, 401);
  const response = await f.api.fetch(request('read', get));
  assert.equal(response.status, 409);
  assert.deepEqual(await response.json(), { protocol: PROTOCOL, error: 'membership_archive_not_ready' });
  assert.equal(f.calls.length, 0);
});

test('API rechecks after response encoding; expired response cannot release bytes', async t => {
  const f = fixture(t);
  const original = globalThis.btoa;
  globalThis.btoa = value => {
    const result = original(value);
    if (value === f.evidence.toString('binary')) f.setTime(f.policy.expires_at);
    return result;
  };
  try { assert.equal((await f.api.fetch(request('permit', permit))).status, 409); }
  finally { globalThis.btoa = original; }
  assert.equal(f.calls.filter(call => call[0] === 'get').length, 1);
});

test('real Python collector and HTTPS client use all three API routes for success and failure archival', async t => {
  for (const valid of [true, false]) {
    const f = fixture(t);
    const raw = valid ? Buffer.from('[{"Code":"A","Type":"Common Stock","Exchange":"NYSE","Name":"A","Country":"USA","Currency":"USD"}]\n') : Buffer.from('[{');
    const code = `
import io,json,sys,base64
from datetime import datetime,timezone
from email.message import Message
from unittest.mock import patch
from services.scanner import eodhd
from services.market_data.membership_collection import collect_membership
from services.publication.membership_transport import MembershipArchiveTransport
class Response(io.BytesIO):
 def __init__(self,raw,url,status=200):
  super().__init__(raw);self.url=url;self.status=status;self.headers=Message()
  self.headers['Content-Type']='application/json';self.headers['Content-Length']=str(len(raw))
 def geturl(self):return self.url
class Opener:
 def open(self,req,timeout):
  print(json.dumps({'request':True,'url':req.full_url,'token':req.get_header('Authorization'),'body':None if req.data is None else req.data.decode()}),flush=True)
  result=json.loads(sys.stdin.readline())
  return Response(result['body'].encode(),req.full_url,result['status'])
env={'GITHUB_ACTIONS':'true','ACTIONS_ID_TOKEN_REQUEST_URL':'https://run.actions.githubusercontent.com/token','ACTIONS_ID_TOKEN_REQUEST_TOKEN':'synthetic'}
client=MembershipArchiveTransport('https://coordinator.example.test',env,opener=Opener())
raw=base64.b64decode('${raw.toString('base64')}')
with patch.object(eodhd,'token',return_value='fake-provider-token'),patch.object(eodhd,'_membership_open',side_effect=lambda req:Response(raw,req.full_url)),patch.object(eodhd,'datetime') as clock:
 clock.now.side_effect=[datetime(2026,9,8,23,47,tzinfo=timezone.utc),datetime(2026,9,8,23,48,tzinfo=timezone.utc)]
 result=collect_membership('2026-09-08',authorize=client.authorize,archive=client)
print(json.dumps({'completed':True,'failure':result.failure,'key':result.observation_key}),flush=True)
`;
    const child = spawn('python3', ['-B', '-c', code], { cwd: process.cwd(), env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' }, stdio: ['pipe', 'pipe', 'pipe'] });
    t.after(() => { if (child.exitCode === null) child.kill(); });
    let chain = Promise.resolve(), final, stderr = '';
    const operations = [];
    child.stderr.on('data', data => { stderr += data; });
    const lines = createInterface({ input: child.stdout });
    lines.on('line', line => {
      chain = chain.then(async () => {
        const value = JSON.parse(line);
        if (value.completed) { final = value; return; }
        let result;
        if (value.url.startsWith('https://run.actions.githubusercontent.com/')) {
          result = { status: 200, body: JSON.stringify({ value: token({ jti: 'fresh-' + operations.length }) }) };
        } else {
          operations.push(new URL(value.url).pathname);
          const response = await f.api.fetch(new Request(value.url, { method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: value.token }, body: value.body }));
          result = { status: response.status, body: await response.text() };
        }
        child.stdin.write(JSON.stringify(result) + '\n');
      }).catch(error => { child.kill(); throw error; });
    });
    const status = await new Promise((resolve, reject) => { child.once('error', reject); child.once('exit', resolve); });
    await chain;
    assert.equal(status, 0, stderr);
    assert.equal(final.failure, valid ? null : 'membership_response_json_invalid');
    assert.equal(operations.length, 7);
    assert.equal(operations[0], '/v1/membership/permit');
    const observation = JSON.parse(Buffer.from(f.objects.get(final.key)));
    assert.deepEqual(Buffer.from(f.objects.get(observation.response.key)), raw);
    assert.equal(f.rows().length, 3);
    assert.equal(observation.failure, final.failure);
  }
});
