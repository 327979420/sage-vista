import test from "node:test";
import assert from "node:assert/strict";
import { createHash, generateKeyPairSync, sign } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { createInterface } from "node:readline";
import { DatabaseSync } from "node:sqlite";
import { GitHubEnvironmentReviewVerifier } from "../services/publication/environment_review.mjs";
import { ReviewedRequestArchive } from "../services/publication/review_archive.mjs";
import { AuthorizationPreparation } from "../services/publication/authorization_preparation.mjs";
import { AuthorizationValidationReturn } from "../services/publication/authorization_return.mjs";
import { AuthorizationValidationArchive } from "../services/publication/authorization_validation_archive.mjs";
import { AuthorizationRegistration } from "../services/publication/authorization_registration.mjs";
import { AuthorizationStore } from "../services/publication/authorization_store.mjs";
import { AuthorizationJobApi } from "../services/publication/authorization_api.mjs";
import { LeaseStore } from "../services/publication/leases.mjs";

async function registrationFixture(t, withHistory = true) {
  const f = await validationArchiveFixture(t, withHistory);
  const authorization = JSON.parse(Buffer.from(f.python.authorization_bytes, 'base64'));
  const policy = { actor_id: '789', approver_id: authorization.approver_id,
    request: Object.fromEntries(Object.keys(businessRequest).map(key => [key, authorization[key]])) };
  const create = (registrationPolicy = policy) => new AuthorizationRegistration(identityPolicy,
    { storage: f.storage, bucket: f.bucket, clock: f.options.clock, fetchKeys: f.options.fetchKeys, registrationPolicy });
  const register = (service = create()) => service.register(token(), f.leaseToken, f.sent.dispatch.dispatch_id, f.resultBytes());
  const rows = () => ({ index: f.db.prepare('SELECT * FROM m12_authorization_index').all(),
    head: f.db.prepare('SELECT * FROM m12_authorization_head').all(),
    consumption: f.db.prepare('SELECT * FROM m12_authorization_consumptions').all(),
    log: f.db.prepare("SELECT * FROM m12_authorization_log WHERE operation='register_authorization'").all() });
  return { ...f, policy, create, register, rows };
}

test('registration is disabled without a server policy and performs no storage or network work', async () => {
  const service = new AuthorizationRegistration(null);
  await assert.rejects(service.register('untrusted', {}, 'arbitrary', new Uint8Array()), /disabled/);
});

test('registration appends first grant and successor revoke with consumption and log atomically', async t => {
  for (const history of [false, true]) {
    const f = await registrationFixture(t, history);
    const result = await f.register();
    assert.equal(result.position, history ? 2 : 1);
    assert.equal(result.previous_ref?.id ?? null, history ? f.priorRef.id : null);
    const rows = f.rows();
    assert.equal(rows.index.length, result.position);
    assert.equal(rows.head[0].revision, result.position);
    assert.equal(rows.consumption.length, 1);
    assert.equal(rows.consumption[0].registration_json, rows.log[0].record_json);
    assert.deepEqual(JSON.parse(rows.consumption[0].registration_json), result);
    assert.equal(rows.log[0].occurred_ms, Date.parse(result.registered_at));
    assert.deepEqual(Buffer.from(f.objects.get(f.authorizationKey)), Buffer.from(f.python.authorization_bytes, 'base64'));
    assert.equal(JSON.parse(rows.index.at(-1).reference_json).id, result.return_record.authorization_ref.id);
    const reopened = new AuthorizationStore(f.storage, { clock: f.options.clock });
    const ticket = reopened.prepareValidation(f.job, f.leaseToken, f.sent.dispatch.approval_evidence_ref);
    assert.equal(ticket.expected_revision, result.position);
  }
});

test('registration binds every approved request field, reviewer and actor without alternate target', async t => {
  const f = await registrationFixture(t);
  const changes = [p => { p.actor_id = '790'; }, p => { p.approver_id = '998'; },
    ...Object.keys(f.policy.request).map(key => p => { p.request[key] = null; })];
  // Replace even originally-null fields with a distinct value.
  for (const key of Object.keys(f.policy.request).filter(key => f.policy.request[key] === null)) {
    changes.push(p => { p.request[key] = 'different'; });
  }
  for (const change of changes) {
    const wrong = structuredClone(f.policy); change(wrong);
    if (JSON.stringify(wrong) === JSON.stringify(f.policy)) continue;
    await assert.rejects(f.register(f.create(wrong)), /not_permitted/);
    assert.equal(f.rows().index.length, 1);
    assert.equal(f.rows().consumption.length, 0);
    assert.equal(f.rows().log.length, 0);
  }
  assert.ok(f.objects.has(f.authorizationKey)); // Orphan/read-verified bytes retained.
});

test('registration server policy is frozen and cannot be mutated by its constructor caller', async t => {
  const f = await registrationFixture(t);
  const service = f.create();
  f.policy.request.code_commit = '0'.repeat(40);
  f.policy.approver_id = '998';
  assert.equal((await f.register(service)).position, 2);
});

test('registration refuses duplicate and concurrent consumption of the original ticket', async t => {
  const f = await registrationFixture(t);
  const service = f.create();
  const outcomes = await Promise.allSettled([f.register(service), f.register(service)]);
  assert.equal(outcomes.filter(item => item.status === 'fulfilled').length, 1);
  assert.equal(f.rows().consumption.length, 1);
  assert.equal(f.rows().index.length, 2);
  await assert.rejects(f.register(service));
  assert.equal(f.rows().log.length, 1);
});

test('registration rolls back index head consumption and log at every failed write', async t => {
  for (const query of ['INSERT INTO m12_authorization_index', 'UPDATE m12_authorization_head',
    'INSERT INTO m12_authorization_consumptions', 'INSERT INTO m12_authorization_log']) {
    const f = await registrationFixture(t);
    await f.archiveValidation();
    const before = f.rows();
    const exec = f.storage.sql.exec;
    f.storage.sql.exec = (sql, ...args) => {
      if (sql.startsWith(query) && (query !== 'INSERT INTO m12_authorization_log' || sql.includes("'register_authorization'"))) {
        throw new Error('injected_registration_write_failure');
      }
      return exec(sql, ...args);
    };
    await assert.rejects(f.register(), /injected_registration_write_failure/);
    assert.deepEqual(f.rows(), before);
    f.storage.sql.exec = exec;
    assert.equal((await f.register()).position, 2);
  }
});

test('registration final lease expiry rolls back all writes and retains verified archive', async t => {
  const f = await registrationFixture(t);
  await f.archiveValidation();
  const before = f.rows(), exec = f.storage.sql.exec;
  f.storage.sql.exec = (sql, ...args) => {
    const result = exec(sql, ...args);
    if (sql.startsWith('INSERT INTO m12_authorization_consumptions')) f.state.now = (NOW + 300) * 1000;
    return result;
  };
  await assert.rejects(f.register());
  assert.deepEqual(f.rows(), before);
  assert.ok(f.objects.has(f.authorizationKey));
});

test('registration rejects return record corruption during its final transaction', async t => {
  const f = await registrationFixture(t);
  await f.archiveValidation();
  const before = f.rows();
  const raw = f.db.prepare('SELECT record_json FROM m12_authorization_returns').get().record_json;
  const exec = f.storage.sql.exec;
  f.storage.sql.exec = (sql, ...args) => {
    if (sql.startsWith('SELECT ticket_id FROM m12_authorization_consumptions WHERE')) {
      const changed = JSON.parse(raw); changed.actor_id = '998';
      f.db.prepare('UPDATE m12_authorization_returns SET record_json=?').run(JSON.stringify(changed));
    }
    return exec(sql, ...args);
  };
  await assert.rejects(f.register(), /recovery_required/);
  assert.deepEqual(f.rows(), before);
  assert.equal(f.db.prepare('SELECT record_json FROM m12_authorization_returns').get().record_json, raw);
});

test('registration consumption and log must remain paired on reopen', async t => {
  const f = await registrationFixture(t);
  await f.register();
  f.db.exec("DELETE FROM m12_authorization_log WHERE operation='register_authorization'");
  const reopened = new AuthorizationStore(f.storage, { clock: f.options.clock });
  assert.throws(() => reopened.prepareValidation(f.job, f.leaseToken, f.sent.dispatch.approval_evidence_ref), /recovery_required/);
});

test('first registration loses both consumption and log: historical recovery fails closed', async t => {
  const f = await registrationFixture(t, false);
  await f.register();
  assert.equal((await recoveryReader(f).recover(token(), f.sent.dispatch.dispatch_id, f.receiptKey)).current_history.revision, 1);
  const originalIndex = f.rows().index;
  f.db.exec("DELETE FROM m12_authorization_consumptions; DELETE FROM m12_authorization_log WHERE operation='register_authorization'");
  await assert.rejects(recoveryReader(f).recover(token(), f.sent.dispatch.dispatch_id, f.receiptKey), /recovery_required/);
  assert.deepEqual(f.rows().index, originalIndex);
  const reopened = new AuthorizationStore(f.storage, { clock: f.options.clock });
  assert.throws(() => reopened.prepareValidation(f.job, f.leaseToken, f.sent.dispatch.approval_evidence_ref), /recovery_required/);
});

test('two real registrations reject local pair loss at either index position', async t => {
  const f = await registrationFixture(t, false);
  const first = await f.register();
  // A second controlled GitHub source response, independently Python-validated.
  // Same local SQLite/R2, distinct control commit; no fabricated verified object.
  const request = { ...businessRequest, action: 'revoke', permissions: [],
    prior_authorization_ref: first.return_record.authorization_ref };
  const policy = { ...identityPolicy, code_commit: '9'.repeat(40) };
  const source = requestFixture(JSON.stringify(request));
  source.responses['/git/commits/' + policy.code_commit] = { ...source.commit, sha: policy.code_commit };
  source.data.run.head_sha = source.data.after.head_sha = policy.code_commit;
  const jwt = token({ sha: policy.code_commit });
  const options = { ...source.options, storage: f.storage, bucket: f.bucket };
  const preparation = new AuthorizationPreparation(policy, reviewPolicy, options);
  const sent = await preparation.dispatchValidationInput(jwt, f.leaseToken);
  const validated = validateWire(sent.input_bytes);
  assert.equal(validated.valid, true, validated.error);
  const raw = Buffer.from(JSON.stringify(canonical({ authorization_base64: validated.authorization_bytes,
    receipt_base64: validated.receipt_bytes })) + '\n');
  const service = new AuthorizationRegistration(policy, { ...options,
    registrationPolicy: { actor_id: '789', approver_id: '999', request } });
  const second = await service.register(jwt, f.leaseToken, sent.dispatch.dispatch_id, raw);
  assert.equal(second.position, 2);
  assert.equal((await recoveryReader(f).recover(token(), f.sent.dispatch.dispatch_id, f.receiptKey)).current_history.revision, 2);
  for (const record of [first, second]) {
    f.db.exec('SAVEPOINT paired_loss_probe');
    try {
      f.db.prepare('DELETE FROM m12_authorization_consumptions WHERE ticket_id=?').run(record.ticket_id);
      f.db.prepare("DELETE FROM m12_authorization_log WHERE operation='register_authorization' AND ticket_id=?").run(record.ticket_id);
      assert.equal(f.rows().consumption.length, 1); // Other registration remains intact.
      await assert.rejects(recoveryReader(f).recover(token(), f.sent.dispatch.dispatch_id, f.receiptKey), /recovery_required/);
    } finally {
      f.db.exec('ROLLBACK TO paired_loss_probe; RELEASE paired_loss_probe');
    }
    assert.equal(f.rows().consumption.length, 2);
    assert.equal((await recoveryReader(f).recover(token(), f.sent.dispatch.dispatch_id, f.receiptKey)).current_history.revision, 2);
  }
});

test('import baseline is an exact trusted prefix and missing boundary is never inferred', async t => {
  const f = await registrationFixture(t);
  const baseline = f.db.prepare('SELECT history_json FROM m12_authorization_import_baseline').get().history_json;
  for (const value of ['[]', JSON.stringify([{ ...JSON.parse(baseline)[0], previous_ref: f.priorRef }])]) {
    f.db.prepare('UPDATE m12_authorization_import_baseline SET history_json=?').run(value);
    await assert.rejects(f.register(), /recovery_required/);
    assert.equal(f.rows().consumption.length, 0);
  }
  f.db.prepare('UPDATE m12_authorization_import_baseline SET history_json=?').run(baseline);
  assert.equal((await f.register()).position, 2);
  f.db.exec('DELETE FROM m12_authorization_import_baseline');
  const reopened = new AuthorizationStore(f.storage, { clock: f.options.clock });
  assert.throws(() => reopened.prepareValidation(f.job, f.leaseToken, f.sent.dispatch.approval_evidence_ref), /recovery_required/);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM m12_authorization_import_baseline').get().n, 0);
});

const NOW = 1_788_652_800;
const keys = generateKeyPairSync("rsa", { modulusLength: 2048 });
const jwk = { ...keys.publicKey.export({ format: "jwk" }), kid: "test", alg: "RS256", use: "sig" };
const identityPolicy = { repository: "example/sage", repository_id: "123",
  workflow_ref: "example/sage/.github/workflows/authorize.yml@refs/heads/main", workflow_commit: "a".repeat(40),
  code_commit: "b".repeat(40), environment: "production", subject: "repo:example/sage:environment:production" };
const reviewPolicy = { environment_id: "10", workflow_id: "20", reviewer_ids: ["999"] };
const claims = { iss: "https://token.actions.githubusercontent.com", aud: "sage-vista-publication",
  sub: identityPolicy.subject, repository: identityPolicy.repository, repository_id: "123",
  workflow_ref: identityPolicy.workflow_ref, workflow_sha: identityPolicy.workflow_commit,
  sha: identityPolicy.code_commit, environment: "production", ref: "refs/heads/main", ref_type: "branch",
  actor_id: "789", run_id: "456", run_attempt: "1", jti: "signed-test", iat: NOW - 30, nbf: NOW - 30, exp: NOW + 300 };
function token(patch = {}) {
  const encode = (v) => Buffer.from(JSON.stringify(v)).toString("base64url");
  const input = encode({ alg: "RS256", typ: "JWT", kid: "test" }) + "." + encode({ ...claims, ...patch });
  return input + "." + sign("RSA-SHA256", Buffer.from(input), keys.privateKey).toString("base64url");
}

function fixture() {
  const user = (id) => ({ id, type: "User", login: "display-only" });
  const run = { id: 456, run_attempt: 1, repository: { id: 123, full_name: "example/sage" },
    workflow_id: 20, head_branch: "main", head_sha: identityPolicy.code_commit, event: "workflow_dispatch",
    status: "in_progress", conclusion: null, actor: user(789), triggering_actor: user(789) };
  const environment = { id: 10, name: "production", protection_rules: [{ type: "required_reviewers",
    prevent_self_review: true, reviewers: [{ type: "User", reviewer: user(999) }] }] };
  const reviews = [{ state: "approved", comment: "human-approved environment",
    environments: [{ id: 10, name: "production" }], user: user(999) }];
  const data = { run, environment, reviews, after: structuredClone(run) };
  const calls = [];
  const raws = [];
  const state = { now: NOW * 1000, override: null };
  const options = { credential: "local-test-credential", clock: () => state.now,
    fetchKeys: async () => new Response(JSON.stringify({ keys: [jwk] })),
    fetchApi: async (url, init) => {
      calls.push({ url, init });
      assert.equal(init.method, "GET");
      assert.equal(init.redirect, "error");
      assert.equal(init.headers.Authorization, "Bearer local-test-credential");
      assert.equal(init.headers["X-GitHub-Api-Version"], "2026-03-10");
      assert.ok(url.startsWith("https://api.github.com/repos/example/sage/"));
      if (state.override) return state.override(url);
      const value = url.endsWith("/approvals") ? data.reviews : url.includes("/environments/") ? data.environment :
        calls.length === 1 ? data.run : data.after;
      const raw = JSON.stringify(value, null, 2) + "\n";
      raws.push(raw);
      return new Response(raw);
    } };
  return { data, calls, raws, state, options,
    verifier: new GitHubEnvironmentReviewVerifier(identityPolicy, reviewPolicy, options) };
}

test("actual OIDC verification plus four GET observations preserve original evidence bytes", async () => {
  const f = fixture();
  const result = await f.verifier.verify(token());
  assert.equal(result.approver_id, "999");
  assert.equal(result.environment_id, "10");
  assert.equal(result.identity.job.run_attempt, 1);
  assert.equal(result.documents.length, 4);
  assert.equal("permissions" in result, false);
  assert.equal("approval_evidence_ref" in result, false);
  result.documents.forEach((item, i) => {
    assert.equal(new TextDecoder().decode(item.bytes), f.raws[i]);
    assert.equal(item.size_bytes, Buffer.byteLength(f.raws[i]));
    assert.equal(item.sha256, "sha256:" + createHash("sha256").update(f.raws[i]).digest("hex"));
    assert.equal(item.url, f.calls[i].url);
  });
});

test("unsigned identity JSON and bad signature cannot reach approval API", async () => {
  const f = fixture();
  await assert.rejects(f.verifier.verify({ job: claims, approver_id: "999" }));
  const parts = token().split(".");
  parts[2] = Buffer.alloc(256).toString("base64url");
  await assert.rejects(f.verifier.verify(parts.join(".")), /signature_invalid/);
  assert.equal(f.calls.length, 0);
});

test("rerun cannot borrow run-level approval, including rerun starting during API reads", async () => {
  const f = fixture();
  await assert.rejects(f.verifier.verify(token({ run_attempt: "2" })), /attempt_unprovable/);
  assert.equal(f.calls.length, 0);
  f.data.after.run_attempt = 2;
  await assert.rejects(f.verifier.verify(token()), /run_mismatch/);
});

test("API run identities, branch, code, workflow and origin must match signed identity", async () => {
  for (const patch of [{ id: 457 }, { repository: { id: 124, full_name: "example/sage" } },
    { workflow_id: 21 }, { head_branch: "other" }, { head_sha: "c".repeat(40) }, { event: "push" },
    { status: "completed", conclusion: "success" }, { actor: { id: 999, type: "User" } },
    { triggering_actor: { id: 999, type: "User" } }, { run_attempt: 2 }]) {
    const f = fixture();
    Object.assign(f.data.run, patch);
    await assert.rejects(f.verifier.verify(token()), /run_mismatch/);
  }
});

test("fixed environment ID/name and prevention of self-review are mandatory", async () => {
  for (const change of [(e) => { e.id = 11; }, (e) => { e.name = "other"; },
    (e) => { e.protection_rules = []; }, (e) => { e.protection_rules[0].prevent_self_review = false; },
    (e) => { e.protection_rules.push(structuredClone(e.protection_rules[0])); }]) {
    const f = fixture(); change(f.data.environment);
    await assert.rejects(f.verifier.verify(token()));
  }
});

test("only the exact fixed user allowlist can protect the environment", async () => {
  for (const change of [(r) => { r[0].reviewer.id = 998; }, (r) => { r[0].type = "Team"; },
    (r) => { r[0].reviewer.type = "Bot"; }, (r) => { r.push(structuredClone(r[0])); },
    (r) => { r.length = 0; }]) {
    const f = fixture(); change(f.data.environment.protection_rules[0].reviewers);
    await assert.rejects(f.verifier.verify(token()));
  }
});

test("no, rejected, duplicate or conflicting approvals fail closed", async () => {
  for (const change of [(r) => { r.length = 0; }, (r) => { r[0].state = "rejected"; },
    (r) => { r.push(structuredClone(r[0])); }, (r) => { r.push({ ...r[0], state: "rejected" }); }]) {
    const f = fixture(); change(f.data.reviews);
    await assert.rejects(f.verifier.verify(token()), /approval_not_unique/);
  }
});

test("stable reviewer ID beats display login, and initiator cannot approve self", async () => {
  const f = fixture();
  f.data.reviews[0].user.id = 998;
  await assert.rejects(f.verifier.verify(token()), /approver_forbidden/);
  const self = fixture();
  self.data.reviews[0].user.id = 789;
  self.data.environment.protection_rules[0].reviewers[0].reviewer.id = 789;
  const v = new GitHubEnvironmentReviewVerifier(identityPolicy, { ...reviewPolicy, reviewer_ids: ["789"] }, self.options);
  await assert.rejects(v.verify(token()), /approver_forbidden/);
});

test("other environment reviews cannot substitute; every environment entry is checked", async () => {
  for (const environments of [[{ id: 11, name: "other" }], [{ id: 11, name: "production" }],
    [{ id: 10, name: "other" }], [{ id: 10, name: "production" }, { id: 10, name: "production" }],
    [{ id: 10, name: "production" }, { id: 11, name: "production" }]]) {
    const f = fixture(); f.data.reviews[0].environments = environments;
    await assert.rejects(f.verifier.verify(token()));
  }
  const f = fixture();
  f.data.reviews.push({ state: "rejected", environments: [{ id: 11, name: "other" }], user: { id: 998, type: "User" } });
  await f.verifier.verify(token());
});

test("API outage, redirected/paged/oversized/invalid bodies never yield observations", async () => {
  for (const make of [() => new Response("outage", { status: 503 }),
    () => { throw new Error("network_error"); }, () => new Response("{"),
    () => new Response("{}", { headers: { Link: '<https://attacker.invalid>; rel="next"' } }),
    () => ({ status: 200, redirected: true }), () => new Response(" ".repeat(1_048_577))]) {
    const f = fixture(); f.state.override = make;
    await assert.rejects(f.verifier.verify(token()));
  }
});

test("identity expiring during approval fetch is not accepted", async () => {
  const f = fixture();
  const original = f.options.fetchApi;
  const v = new GitHubEnvironmentReviewVerifier(identityPolicy, reviewPolicy, { ...f.options,
    fetchApi: async (...args) => { const result = await original(...args); f.state.now = claims.exp * 1000; return result; } });
  await assert.rejects(v.verify(token()), /identity_expired/);
});

test("policy is copied, unsafe API IDs and caller-selected endpoints are unavailable", async () => {
  const f = fixture();
  const source = { ...reviewPolicy, reviewer_ids: [...reviewPolicy.reviewer_ids] };
  const v = new GitHubEnvironmentReviewVerifier(identityPolicy, source, f.options);
  source.reviewer_ids[0] = "998";
  await v.verify(token());
  f.data.run.id = Number.MAX_SAFE_INTEGER + 1;
  f.calls.length = 0;
  await assert.rejects(v.verify(token()), /id_invalid/);
  for (const invalid of [{}, { ...reviewPolicy, reviewer_ids: [] }, { ...reviewPolicy, reviewer_ids: ["999", "999"] },
    { ...reviewPolicy, environment_id: "../x" }, { ...reviewPolicy, url: "https://attacker.invalid" }]) {
    assert.throws(() => new GitHubEnvironmentReviewVerifier(identityPolicy, invalid, f.options), /policy_invalid/);
  }
});

function requestFixture(raw = '{"action":"grant","reason":"冻结请求"}\n') {
  const f = fixture();
  const bytes = Buffer.from(raw);
  const blobSha = createHash("sha1").update(Buffer.concat([Buffer.from(`blob ${bytes.length}\0`), bytes])).digest("hex");
  const rootSha = "c".repeat(40);
  const configSha = "d".repeat(40);
  const responses = {
    ["/git/commits/" + identityPolicy.code_commit]: { sha: identityPolicy.code_commit, tree: { sha: rootSha } },
    ["/git/trees/" + rootSha]: { sha: rootSha, truncated: false,
      tree: [{ path: "config", type: "tree", mode: "040000", sha: configSha }] },
    ["/git/trees/" + configSha]: { sha: configSha, truncated: false,
      tree: [{ path: "publication-authorization-request.json", type: "blob", mode: "100644", sha: blobSha, size: bytes.length }] },
    ["/git/blobs/" + blobSha]: { sha: blobSha, encoding: "base64", size: bytes.length,
      content: bytes.toString("base64").match(/.{1,16}/g).join("\n") + "\n" },
  };
  const gitCalls = [];
  const hooks = { afterBlob: null, override: null };
  const options = { ...f.options, fetchApi: async (url, init) => {
    const path = new URL(url).pathname.replace("/repos/example/sage", "");
    if (!path.startsWith("/git/")) return f.options.fetchApi(url, init);
    gitCalls.push({ url, init });
    assert.equal(init.method, "GET");
    assert.equal(init.redirect, "error");
    assert.equal(init.headers.Authorization, "Bearer local-test-credential");
    if (path.startsWith("/git/blobs/") && hooks.afterBlob) hooks.afterBlob();
    if (hooks.override) return hooks.override(path);
    assert.ok(path in responses, path);
    return new Response(JSON.stringify(responses[path], null, 2) + "\n");
  } };
  return { ...f, options, bytes, blobSha, responses, gitCalls, hooks,
    commit: responses["/git/commits/" + identityPolicy.code_commit],
    root: responses["/git/trees/" + rootSha], tree: responses["/git/trees/" + configSha],
    blob: responses["/git/blobs/" + blobSha],
    verifier: new GitHubEnvironmentReviewVerifier(identityPolicy, reviewPolicy, options) };
}

test("request is read only through signed commit, fixed tree path and verified original blob", async () => {
  const f = requestFixture();
  const result = await f.verifier.verifyRequest(token(), { path: "attacker.json", body: "ignored" });
  assert.equal(result.review.approver_id, "999");
  assert.equal(result.request.source_commit, identityPolicy.code_commit);
  assert.equal(result.request.path, "config/publication-authorization-request.json");
  assert.equal(result.request.blob_sha, f.blobSha);
  assert.deepEqual(Buffer.from(result.request.bytes), f.bytes);
  assert.equal(result.request.sha256, "sha256:" + createHash("sha256").update(f.bytes).digest("hex"));
  assert.equal(result.documents.length, 5);
  assert.equal(f.gitCalls.length, 4);
  assert.equal(f.calls.length, 5);
  assert.ok(f.gitCalls.every(({ url }) => !url.includes("main") && !url.includes("attacker")));
  for (const item of result.documents) {
    assert.equal(item.size_bytes, item.bytes.length);
    assert.equal(item.sha256, "sha256:" + createHash("sha256").update(item.bytes).digest("hex"));
  }
});

test("no approved environment means no request fetch", async () => {
  const f = requestFixture();
  f.data.reviews.length = 0;
  await assert.rejects(f.verifier.verifyRequest(token()), /approval_not_unique/);
  assert.equal(f.gitCalls.length, 0);
});

test("commit/tree mismatches, truncated and missing/duplicate paths reject", async () => {
  for (const change of [(f) => { f.commit.sha = "e".repeat(40); }, (f) => { f.commit.tree.sha = "main"; },
    (f) => { f.root.sha = "e".repeat(40); }, (f) => { f.root.truncated = true; },
    (f) => { delete f.tree.truncated; }, (f) => { f.root.tree = []; },
    (f) => { f.tree.tree = []; }, (f) => { f.tree.tree.push({ ...f.tree.tree[0] }); }]) {
    const f = requestFixture(); change(f);
    await assert.rejects(f.verifier.verifyRequest(token()));
  }
});

test("symlinks, executable files, submodules and directory substitutions are rejected", async () => {
  for (const [type, mode] of [["blob", "120000"], ["blob", "100755"], ["commit", "160000"], ["tree", "040000"]]) {
    const f = requestFixture();
    Object.assign(f.tree.tree[0], { type, mode });
    await assert.rejects(f.verifier.verifyRequest(token()), /regular_file_required/);
  }
  const f = requestFixture(); f.root.tree[0].type = "blob";
  await assert.rejects(f.verifier.verifyRequest(token()), /regular_file_required/);
});

test("wrong blob identity, encoding, declared size and bytes cannot replace frozen request", async () => {
  for (const change of [(f) => { f.blob.sha = "e".repeat(40); }, (f) => { f.blob.encoding = "utf-8"; },
    (f) => { f.blob.size++; }, (f) => { f.blob.content = "!!!!"; },
    (f) => { f.blob.content = Buffer.from("x").toString("base64"); },
    (f) => { f.blob.content = Buffer.alloc(f.bytes.length, 65).toString("base64"); }]) {
    const f = requestFixture(); change(f);
    await assert.rejects(f.verifier.verifyRequest(token()));
  }
});

test("empty/oversized/unsafe request sizes are rejected before fetching a blob", async () => {
  for (const size of [0, 65_537, -1, 1.5, true, Number.MAX_SAFE_INTEGER + 1]) {
    const f = requestFixture(); f.tree.tree[0].size = size;
    await assert.rejects(f.verifier.verifyRequest(token()), /size_invalid/);
    assert.equal(f.gitCalls.length, 3);
  }
});

test("new rerun or token expiry during source fetch prevents request return", async () => {
  const rerun = requestFixture();
  rerun.hooks.afterBlob = () => { rerun.data.after.run_attempt = 2; };
  await assert.rejects(rerun.verifier.verifyRequest(token()), /run_mismatch/);
  const expired = requestFixture();
  expired.hooks.afterBlob = () => { expired.state.now = claims.exp * 1000; };
  await assert.rejects(expired.verifier.verifyRequest(token()), /identity_expired/);
});

test("source outage fails closed; API-provided blob URL is never followed", async () => {
  const missing = requestFixture();
  missing.hooks.override = () => new Response("not found", { status: 404 });
  await assert.rejects(missing.verifier.verifyRequest(token()), /unavailable/);
  const f = requestFixture();
  f.tree.tree[0].url = "https://attacker.invalid/blob";
  f.commit.tree.url = "https://attacker.invalid/tree";
  await f.verifier.verifyRequest(token());
  assert.ok(f.gitCalls.every(({ url }) => url.startsWith("https://api.github.com/repos/example/sage/git/")));
});

test("source binding does not pretend opaque bytes satisfy a request contract", async () => {
  const f = requestFixture("not a request JSON\n");
  const result = await f.verifier.verifyRequest(token());
  assert.deepEqual(Buffer.from(result.request.bytes), f.bytes);
  assert.equal("authorization_id" in result, false);
  assert.equal("permissions" in result, false);
  // Subsequent Python request validation is mandatory; no JSON parser or grant
  // constructor is hidden inside this source adapter.
});

function archiveFixture(raw) {
  const f = requestFixture(raw);
  const objects = new Map();
  const state = { failAt: null, corruptRead: false, afterPut: null, beforeGet: null, puts: 0, gets: 0 };
  const bucket = {
    async put(key, bytes, options) {
      assert.equal(options.onlyIf.get("If-None-Match"), "*");
      state.puts++;
      const prior = objects.has(key);
      if (!prior) objects.set(key, new Uint8Array(bytes));
      if (state.afterPut) state.afterPut(key);
      if (state.puts === state.failAt) throw new Error("write_response_lost");
      return prior ? null : { key };
    },
    async get(key) {
      state.gets++;
      if (state.beforeGet) await state.beforeGet(key);
      if (!objects.has(key)) return null;
      const original = new Uint8Array(objects.get(key));
      if (state.corruptRead) original[0] ^= 1;
      return { arrayBuffer: async () => original.buffer };
    },
  };
  return { ...f, bucket, objects, archiveState: state,
    archive: new ReviewedRequestArchive(identityPolicy, reviewPolicy, { ...f.options, bucket }) };
}

test("archive binds every role and original byte before issuing evidence reference", async () => {
  const f = archiveFixture();
  const result = await f.archive.archive(token());
  const bundleBytes = f.objects.get(result.bundle.key);
  const hash = "sha256:" + createHash("sha256").update(bundleBytes).digest("hex");
  assert.equal(result.approval_evidence_ref.id, "approval-observation:" + hash);
  assert.equal(result.approval_evidence_ref.content_fingerprint, hash);
  assert.equal(result.bundle.key, "authority/" + hash.slice(7) + ".json");
  const bundle = JSON.parse(new TextDecoder().decode(bundleBytes));
  assert.equal(bundle.kind, "github_environment_approval_observation");
  assert.equal(bundle.documents.length, 9);
  assert.equal(new Set(bundle.documents.map((d) => d.role)).size, 9);
  for (const item of [bundle.request, ...bundle.documents]) {
    const bytes = f.objects.get(item.key);
    assert.equal(item.size_bytes, bytes.length);
    assert.equal(item.sha256, "sha256:" + createHash("sha256").update(bytes).digest("hex"));
  }
  assert.deepEqual(Buffer.from(f.objects.get(bundle.request.key)), f.bytes);
  assert.equal(bundle.identity.job.run_id, "456");
  assert.equal(bundle.approver_id, "999");
  assert.equal(bundle.environment_id, "10");
  assert.equal(bundle.request.source_commit, identityPolicy.code_commit);
  assert.equal(f.archiveState.puts, 11);
  assert.equal(f.archiveState.gets, 11);
  assert.equal(bundleBytes.includes(Buffer.from("local-test-credential")), false);
  assert.equal(bundleBytes.includes(Buffer.from(token())), false);
  assert.equal("authorization_id" in result, false);
});

test("same observations replay to same reference and byte keys without overwriting", async () => {
  const f = archiveFixture();
  const first = await f.archive.archive(token());
  const saved = new Map([...f.objects].map(([key, value]) => [key, Buffer.from(value)]));
  const next = await f.archive.archive(token());
  assert.deepEqual(next, first);
  assert.equal(f.objects.size, saved.size);
  for (const [key, value] of saved) assert.deepEqual(Buffer.from(f.objects.get(key)), value);
  next.request_source.bytes.fill(0);
  assert.deepEqual(Buffer.from((await f.archive.archive(token())).request_source.bytes), f.bytes);
});

test("unverified JSON, failed review and bad source cannot cause any archive writes", async () => {
  const f = archiveFixture();
  await assert.rejects(f.archive.archive({ request_source: { bytes: "forged", source_commit: identityPolicy.code_commit } }));
  f.data.reviews.length = 0;
  await assert.rejects(f.archive.archive(token()));
  assert.equal(f.objects.size, 0);
  const badSource = archiveFixture();
  badSource.blob.content = Buffer.alloc(badSource.bytes.length, 65).toString("base64");
  await assert.rejects(badSource.archive.archive(token()), /blob_sha_mismatch/);
  assert.equal(badSource.objects.size, 0);
});


test("partial raw failure returns no bundle and retry resumes immutable objects", async () => {
  const f = archiveFixture();
  f.archiveState.failAt = 4;
  await assert.rejects(f.archive.archive(token()), /write_response_lost/);
  assert.ok([...f.objects.keys()].every((key) => key.startsWith("raw/")));
  const saved = new Map([...f.objects].map(([key, value]) => [key, Buffer.from(value)]));
  f.archiveState.failAt = null;
  const result = await f.archive.archive(token());
  assert.ok(f.objects.has(result.bundle.key));
  for (const [key, value] of saved) assert.deepEqual(Buffer.from(f.objects.get(key)), value);
});

test("lost bundle write response is not success and can retry by original bytes", async () => {
  const f = archiveFixture();
  f.archiveState.failAt = 11;
  await assert.rejects(f.archive.archive(token()), /write_response_lost/);
  const bundleKey = [...f.objects.keys()].find((key) => key.startsWith("authority/"));
  assert.ok(bundleKey);
  const original = Buffer.from(f.objects.get(bundleKey));
  f.archiveState.failAt = null;
  const result = await f.archive.archive(token());
  assert.equal(result.bundle.key, bundleKey);
  assert.deepEqual(Buffer.from(f.objects.get(bundleKey)), original);
});

test("corrupted existing raw object or readback never produces an evidence reference", async () => {
  const f = archiveFixture();
  const rawKey = "raw/" + createHash("sha256").update(f.bytes).digest("hex");
  const corrupt = new Uint8Array(f.bytes); corrupt[0] ^= 1;
  f.objects.set(rawKey, corrupt);
  await assert.rejects(f.archive.archive(token()), /hash_mismatch/);
  assert.deepEqual(f.objects.get(rawKey), corrupt);
  const read = archiveFixture(); read.archiveState.corruptRead = true;
  await assert.rejects(read.archive.archive(token()), /hash_mismatch/);
  assert.ok([...read.objects.keys()].every((key) => key.startsWith("raw/")));
});

test("expiry mid-archive or after bundle write aborts without promoting or deleting orphans", async () => {
  for (const afterBundle of [false, true]) {
    const f = archiveFixture();
    f.archiveState.afterPut = (key) => {
      if (!afterBundle || key.startsWith("authority/")) f.state.now = claims.exp * 1000;
    };
    await assert.rejects(f.archive.archive(token()), /archive_identity_expired/);
    assert.ok(f.objects.size > 0);
    assert.equal([...f.objects.keys()].some((key) => key.startsWith("authority/")), afterBundle);
  }
});

test("fresh changed observation creates another bundle and preserves earlier evidence", async () => {
  const f = archiveFixture();
  const first = await f.archive.archive(token());
  const oldBytes = Buffer.from(f.objects.get(first.bundle.key));
  f.data.reviews[0].comment = "different observed comment";
  f.state.now += 1000;
  const second = await f.archive.archive(token());
  assert.notEqual(second.approval_evidence_ref.id, first.approval_evidence_ref.id);
  assert.deepEqual(Buffer.from(f.objects.get(first.bundle.key)), oldBytes);
  // A changed observation is not a second authorization. DO run/request
  // deduplication and grant registration are not implemented in this adapter.
});

const businessRequest = { action: "grant", prior_authorization_ref: null,
  config_ref: { id: "config-1", content_fingerprint: "sha256:" + "f".repeat(64) }, code_commit: "e".repeat(40),
  publication_mode: "research_only", scope: "complex_multifactor_main", effective_from: "2026-09-06",
  valid_until: null, permissions: ["prepare", "publish", "notify", "rollback"], reason: "冻结研究服务请求" };

async function pythonArchive() {
  const f = archiveFixture(JSON.stringify(businessRequest, null, 2) + "\n");
  const result = await f.archive.archive(token());
  return { bundle: JSON.parse(new TextDecoder().decode(f.objects.get(result.bundle.key))),
    bundle_bytes: Buffer.from(f.objects.get(result.bundle.key)).toString("base64"),
    reference: result.approval_evidence_ref,
    objects: Object.fromEntries([...f.objects].filter(([key]) => key.startsWith("raw/"))
      .map(([key, bytes]) => [key, Buffer.from(bytes).toString("base64")])) };
}

function resealArchive(input) {
  const stable = (value) => Array.isArray(value) ? value.map(stable) : value && typeof value === "object" ?
    Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])])) : value;
  const bytes = Buffer.from(JSON.stringify(stable(input.bundle)));
  const hash = "sha256:" + createHash("sha256").update(bytes).digest("hex");
  input.bundle_bytes = bytes.toString("base64");
  input.reference = { id: "approval-observation:" + hash, content_fingerprint: hash };
}

function checkPython(input) {
  const script = `
import base64, json, sys
from services.contracts.validation import ContractError, publication_approval_archive_body, publication_ticket_history, validate_contract, validate_contracts
from services.publication.authorization import build_publication_authorization, build_publication_authorization_from_archive, build_publication_authorization_for_ticket
v = json.load(sys.stdin)
archive = {"bundle_bytes": base64.b64decode(v["bundle_bytes"]), "objects": {k:base64.b64decode(b) for k,b in v["objects"].items()}}
try:
    if "ticket" in v:
        history_bytes = [base64.b64decode(raw) for raw in v["history_bytes"]]
        payload = build_publication_authorization_for_ticket(archive, v["reference"], v["ticket"], history_bytes, generated_at="2026-09-06T00:00:00Z")
    elif v.get("factory"):
        payload = build_publication_authorization_from_archive(archive, v["reference"], history=[], generated_at="2026-09-06T00:00:00Z", **v.get("unexpected_factory_kwargs", {}))
    bound = publication_approval_archive_body(archive, v["reference"])
    evidence = {**bound, "approval_evidence_ref":v["reference"], "history":[], "approval_archive":archive}
    if "ticket" in v:
        evidence.update(validation_ticket=v["ticket"], history_bytes=history_bytes,
                        history=publication_ticket_history(v["ticket"], history_bytes, job=bound["job"], approval_evidence_ref=v["reference"]))
    for key in v.get("drop_evidence", []):
        del evidence[key]
    evidence.update(v.get("replace_evidence", {}))
    if not v.get("factory") and "ticket" not in v:
        payload = build_publication_authorization(evidence, generated_at="2026-09-06T00:00:00Z")
    validate_contract("PublicationAuthorization", payload, publication_authorization_evidence=evidence)
    validate_contracts([("PublicationAuthorization", payload)], publication_authorization_evidence=evidence)
    print(json.dumps({"valid":True, "code_commit":payload["code_commit"], "approval_evidence_ref":payload["approval_evidence_ref"]}))
except (ContractError, TypeError) as exc:
    if isinstance(exc, TypeError) and not v.get("unexpected_factory_kwargs"):
        raise
    print(json.dumps({"valid":False, "error":str(exc)}))
`;
  const result = spawnSync("python3", ["-c", script], { input: JSON.stringify(input), encoding: "utf-8",
    cwd: new URL("..", import.meta.url) });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test("actual JavaScript archive bytes bind through Python builder, single and collection entry", async () => {
  const input = await pythonArchive();
  const result = checkPython(input);
  assert.equal(result.valid, true, result.error);
  assert.equal(result.code_commit, businessRequest.code_commit);
  assert.notEqual(result.code_commit, input.bundle.request.source_commit);
  assert.deepEqual(result.approval_evidence_ref, input.reference);
});

test("Python rejects changed bundle reference and missing/extra/corrupt original bytes", async () => {
  const original = await pythonArchive();
  for (const change of [(v) => { v.reference.content_fingerprint = "sha256:" + "0".repeat(64); },
    (v) => { delete v.objects[v.bundle.request.key]; },
    (v) => { v.objects["raw/" + "0".repeat(64)] = Buffer.from("extra").toString("base64"); },
    (v) => { v.objects[v.bundle.documents[1].key] = Buffer.from("changed").toString("base64"); }]) {
    const input = structuredClone(original); change(input);
    assert.equal(checkPython(input).valid, false);
  }
});

test("Python rejects resealed bundle kind/version/role/URL and byte-metadata substitutions", async () => {
  const original = await pythonArchive();
  for (const change of [(b) => { b.version = true; }, (b) => { b.kind = "other"; }, (b) => { b.extra = 1; },
    (b) => { b.documents.pop(); }, (b) => { b.documents.reverse(); },
    (b) => { b.documents[1].url = "https://attacker.invalid/env"; },
    (b) => { b.documents[1].size_bytes = true; }, (b) => { b.identity.job.run_attempt = true; }]) {
    const input = structuredClone(original); change(input.bundle); resealArchive(input);
    assert.equal(checkPython(input).valid, false);
  }
});

test("Python rejects summary identities/time that disagree with original API/source bytes", async () => {
  const original = await pythonArchive();
  for (const change of [(b) => { b.identity.job.run_id = "457"; }, (b) => { b.approver_id = "998"; },
    (b) => { b.environment_id = "11"; }, (b) => { b.identity.actor_id = "790"; },
    (b) => { b.request.source_commit = "a".repeat(40); },
    (b) => { b.observed_at = new Date(claims.exp * 1000).toISOString(); }]) {
    const input = structuredClone(original); change(input.bundle); resealArchive(input);
    assert.equal(checkPython(input).valid, false);
  }
});

test("Python checks API originals even when their descriptor and bundle hashes are resigned", async () => {
  const original = await pythonArchive();
  for (const [role, change] of [
    ["review_history", (v) => { v[0].user.id = 998; }],
    ["review_history", (v) => { v[0].environments.push({ id: 11, name: "production" }); }],
    ["run_before_review", (v) => { v.id = 457; }],
    ["run_after_source", (v) => { v.status = "completed"; }],
    ["source_config_tree", (v) => { v.tree[0].mode = "120000"; }],
    ["request_blob", (v) => { v.content = Buffer.from("replaced").toString("base64"); }],
  ]) {
    const input = structuredClone(original);
    const descriptor = input.bundle.documents.find((d) => d.role === role);
    const document = JSON.parse(Buffer.from(input.objects[descriptor.key], "base64").toString());
    change(document);
    const bytes = Buffer.from(JSON.stringify(document));
    const hash = "sha256:" + createHash("sha256").update(bytes).digest("hex");
    Object.assign(descriptor, { key: "raw/" + hash.slice(7), sha256: hash, size_bytes: bytes.length });
    input.objects[descriptor.key] = bytes.toString("base64");
    const used = new Set([input.bundle.request.key, ...input.bundle.documents.map((d) => d.key)]);
    input.objects = Object.fromEntries(Object.entries(input.objects).filter(([key]) => used.has(key)));
    resealArchive(input);
    assert.equal(checkPython(input).valid, false);
  }
});

test("archive-backed Python evidence cannot omit source context or substitute Job/approver", async () => {
  const original = await pythonArchive();
  for (const missing of [["source_commit"], ["request_source"], ["source_commit", "request_source"]]) {
    assert.equal(checkPython({ ...original, drop_evidence: missing }).valid, false);
  }
  for (const replacement of [{ approver_id: "998" }, { job: { ...original.bundle.identity.job, run_id: "457" } },
    { job: { ...original.bundle.identity.job, run_attempt: true } }]) {
    assert.equal(checkPython({ ...original, replace_evidence: replacement }).valid, false);
  }
});

function readerInput(value) {
  return { factory: true, reference: value.approval_evidence_ref,
    bundle_bytes: Buffer.from(value.approval_archive.bundle_bytes).toString("base64"),
    objects: Object.fromEntries(Object.entries(value.approval_archive.objects)
      .map(([key, bytes]) => [key, Buffer.from(bytes).toString("base64")])) };
}

test("controlled read supplies actual R2 readbacks to mandatory Python archive constructor", async () => {
  const f = archiveFixture(JSON.stringify(businessRequest));
  const read = await f.archive.readForValidation(token());
  assert.deepEqual(Object.keys(read).sort(), ["approval_archive", "approval_evidence_ref"]);
  const rawCount = Object.keys(read.approval_archive.objects).length;
  assert.equal(f.archiveState.gets, 11 + 1 + rawCount);
  const result = checkPython(readerInput(read));
  assert.equal(result.valid, true, result.error);
  assert.equal(result.code_commit, businessRequest.code_commit);
});

test("controlled read has no caller-selected reference/JSON route and excludes unrelated orphans", async () => {
  const f = archiveFixture(JSON.stringify(businessRequest));
  await assert.rejects(f.archive.readForValidation({ approval_evidence_ref: { id: "forged" } }));
  assert.equal(f.objects.size, 0);
  const orphan = "raw/" + createHash("sha256").update("orphan").digest("hex");
  f.objects.set(orphan, new TextEncoder().encode("orphan"));
  const result = await f.archive.readForValidation(token(), { reference: "ignored", request: "forged" });
  assert.equal(orphan in result.approval_archive.objects, false);
  assert.equal(checkPython(readerInput(result)).valid, true);
});

test("missing/corrupt bundle on fresh read fails despite successful earlier archive", async () => {
  for (const corrupt of [false, true]) {
    const f = archiveFixture(JSON.stringify(businessRequest));
    f.archiveState.beforeGet = (key) => {
      if (f.archiveState.gets !== 12) return;
      if (corrupt) f.objects.get(key)[0] ^= 1;
      else f.objects.delete(key);
    };
    await assert.rejects(f.archive.readForValidation(token()), /missing|hash_mismatch/);
  }
});

test("original reread failure never returns a partial Python validation input", async () => {
  for (const corrupt of [false, true]) {
    const f = archiveFixture(JSON.stringify(businessRequest));
    f.archiveState.beforeGet = (key) => {
      if (f.archiveState.gets !== 13) return;
      if (corrupt) f.objects.get(key)[0] ^= 1;
      else throw new Error("r2_read_unavailable");
    };
    await assert.rejects(f.archive.readForValidation(token()), /unavailable|hash_mismatch/);
  }
});

test("identity expiry while reading bundle or final original rejects the result", async () => {
  for (const last of [false, true]) {
    const f = archiveFixture(JSON.stringify(businessRequest));
    f.archiveState.beforeGet = () => {
      const rawCount = [...f.objects.keys()].filter((key) => key.startsWith("raw/")).length;
      if (f.archiveState.gets === (last ? 12 + rawCount : 12)) f.state.now = claims.exp * 1000;
    };
    await assert.rejects(f.archive.readForValidation(token()), /archive_identity_expired/);
  }
});

test("mandatory Python constructor cannot replace request, source or approver via kwargs", async () => {
  const f = archiveFixture(JSON.stringify(businessRequest));
  const input = readerInput(await f.archive.readForValidation(token()));
  for (const replacement of [{ request: {} }, { approver_id: "998" }, { job: {} }, { source_commit: "a".repeat(40) }]) {
    assert.equal(checkPython({ ...input, unexpected_factory_kwargs: replacement }).valid, false);
  }
  const missing = structuredClone(input);
  delete missing.objects[Object.keys(missing.objects)[0]];
  assert.equal(checkPython(missing).valid, false);
});

test("mutating returned readback cannot rewrite archive or affect a later verified read", async () => {
  const f = archiveFixture(JSON.stringify(businessRequest));
  const first = await f.archive.readForValidation(token());
  const expectedRef = structuredClone(first.approval_evidence_ref);
  first.approval_archive.bundle_bytes.fill(0);
  Object.values(first.approval_archive.objects)[0].fill(0);
  first.approval_evidence_ref.id = "forged";
  const second = await f.archive.readForValidation(token());
  assert.deepEqual(second.approval_evidence_ref, expectedRef);
  assert.equal(checkPython(readerInput(second)).valid, true);
});

function priorAuthorization() {
  const job = { repository_id: "123", workflow_ref: identityPolicy.workflow_ref, workflow_commit: identityPolicy.workflow_commit,
    run_id: "400", run_attempt: 1, environment: "production" };
  const evidence = { request: businessRequest, approver_id: "999", job, history: [],
    approval_evidence_ref: { id: "approval-observation:sha256:" + "8".repeat(64), content_fingerprint: "sha256:" + "8".repeat(64) } };
  const result = spawnSync("python3", ["-c", "import json,sys; from services.publication.authorization import build_publication_authorization; print(json.dumps(build_publication_authorization(json.load(sys.stdin), generated_at='2026-09-06T00:00:00Z'),sort_keys=True,separators=(',',':'),ensure_ascii=False))"],
    { input: JSON.stringify(evidence), encoding: "utf-8", cwd: new URL("..", import.meta.url) });
  assert.equal(result.status, 0, result.stderr);
  return Buffer.from(result.stdout);
}

function preparationFixture(t, withHistory = true) {
  const priorBytes = priorAuthorization();
  const prior = JSON.parse(priorBytes.toString());
  const priorRef = { id: prior.authorization_id, content_fingerprint: prior.content_fingerprint };
  const request = withHistory ? { ...businessRequest, action: "revoke", permissions: [], prior_authorization_ref: priorRef } : businessRequest;
  const f = archiveFixture(JSON.stringify(request));
  const db = new DatabaseSync(":memory:");
  t.after(() => db.close());
  let transactionSequence = 0;
  const storage = { sql: { exec(query, ...args) {
    const rows = db.prepare(query).all(...args);
    return { toArray: () => rows.map((row) => ({ ...row })) };
  } }, transactionSync(callback) {
    // Local SQLite equivalent of nested transactionSync; production uses the
    // DO API, never transaction SQL statements through sql.exec.
    const savepoint = "test_transaction_" + (++transactionSequence);
    db.exec("SAVEPOINT " + savepoint);
    try { const result = callback(); assert.ok(!(result instanceof Promise)); db.exec("RELEASE " + savepoint); return result; }
    catch (error) { db.exec("ROLLBACK TO " + savepoint); db.exec("RELEASE " + savepoint); throw error; }
  } };
  const lease = new LeaseStore(storage, { clock: f.options.clock });
  const epoch = "11111111-1111-4111-8111-111111111111";
  lease.initialize(epoch);
  const job = { ...prior.job, run_id: "456" };
  const held = lease.acquire("publish/global", job, epoch);
  const leaseToken = { epoch, fence: held.lease.fence };
  const preparation = new AuthorizationPreparation(identityPolicy, reviewPolicy, { ...f.options, storage, bucket: f.bucket });
  const historyKey = "authority/" + prior.content_fingerprint.slice(7) + ".json";
  if (withHistory) {
    f.objects.set(historyKey, new Uint8Array(priorBytes));
    storage.transactionSync(() => {
      storage.sql.exec("INSERT INTO m12_authorization_index VALUES (1, ?, ?, NULL)", JSON.stringify(priorRef),
        JSON.stringify({ key: historyKey, sha256: "sha256:" + createHash("sha256").update(priorBytes).digest("hex"), size_bytes: priorBytes.length }));
      storage.sql.exec("UPDATE m12_authorization_head SET revision = 1, head_json = ?", JSON.stringify(priorRef));
      // Explicit trusted synthetic import prefix; never inferred by production.
      storage.sql.exec("UPDATE m12_authorization_import_baseline SET history_json=? WHERE singleton=1",
        JSON.stringify([{ reference: priorRef, archive: { key: historyKey,
          sha256: "sha256:" + createHash("sha256").update(priorBytes).digest("hex"), size_bytes: priorBytes.length }, previous_ref: null }]));
    });
  }
  return { ...f, db, storage, lease, job, leaseToken, preparation, historyKey, priorBytes, priorRef };
}

function ticketInput(value) {
  return { ...readerInput(value), ticket: value.validation_ticket,
    history_bytes: value.history_bytes.map((bytes) => Buffer.from(bytes).toString("base64")) };
}

test("internal preparation reads full stored history and Python constructs its valid successor", async (t) => {
  const f = preparationFixture(t);
  const input = await f.preparation.prepare(token(), f.leaseToken);
  assert.equal(input.validation_ticket.expected_revision, 1);
  assert.deepEqual(input.validation_ticket.expected_head_ref, f.priorRef);
  assert.deepEqual(Buffer.from(input.history_bytes[0]), f.priorBytes);
  const result = checkPython(ticketInput(input));
  assert.equal(result.valid, true, result.error);
  assert.equal(result.code_commit, businessRequest.code_commit);
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, 1);
});

test("first grant preparation has an explicitly empty complete history", async (t) => {
  const f = preparationFixture(t, false);
  const input = await f.preparation.prepare(token(), f.leaseToken);
  assert.deepEqual(input.history_bytes, []);
  assert.equal(input.validation_ticket.expected_revision, 0);
  assert.equal(checkPython(ticketInput(input)).valid, true);
});

test("missing or corrupted R2 history refuses partial preparation", async (t) => {
  for (const corrupt of [false, true]) {
    const f = preparationFixture(t);
    if (corrupt) f.objects.get(f.historyKey)[0] ^= 1;
    else f.objects.delete(f.historyKey);
    await assert.rejects(f.preparation.prepare(token(), f.leaseToken), /missing|hash_mismatch/);
  }
});

test("head change during R2 history read invalidates the prepared ticket", async (t) => {
  const f = preparationFixture(t);
  f.archiveState.beforeGet = (key) => {
    if (key !== f.historyKey) return;
    f.storage.transactionSync(() => {
      f.storage.sql.exec("DELETE FROM m12_authorization_index");
      f.storage.sql.exec("UPDATE m12_authorization_head SET revision = 0, head_json = NULL");
    });
  };
  await assert.rejects(f.preparation.prepare(token(), f.leaseToken), /registration_recovery_required/);
});

test("lease takeover during history read rejects old owner even while OIDC token is valid", async (t) => {
  const f = preparationFixture(t);
  f.archiveState.beforeGet = (key) => {
    if (key !== f.historyKey) return;
    f.lease.release("publish/global", f.job, f.leaseToken);
    f.lease.acquire("publish/global", { ...f.job, run_id: "457" }, f.leaseToken.epoch);
  };
  await assert.rejects(f.preparation.prepare(token(), f.leaseToken), /not_owned/);
});

test("identity expiry after the final history read stops preparation", async (t) => {
  const f = preparationFixture(t);
  f.archiveState.beforeGet = (key) => { if (key === f.historyKey) f.state.now = claims.exp * 1000; };
  await assert.rejects(f.preparation.prepare(token(), f.leaseToken), /preparation_identity_expired/);
});

test("Python rejects truncated/replaced history, stale head and ticket identity substitutions", async (t) => {
  const f = preparationFixture(t);
  const original = ticketInput(await f.preparation.prepare(token(), f.leaseToken));
  for (const change of [(v) => { v.history_bytes = []; }, (v) => { v.history_bytes.push(v.history_bytes[0]); },
    (v) => { v.history_bytes[0] = Buffer.from("{}").toString("base64"); },
    (v) => { v.ticket.expected_revision = 0; }, (v) => { v.ticket.expected_head_ref = null; },
    (v) => { v.ticket.owner_job.run_id = "457"; }, (v) => { v.ticket.fence = true; },
    (v) => { v.ticket.approval_evidence_ref = f.priorRef; },
    (v) => { v.ticket.history[0].previous_ref = f.priorRef; }]) {
    const input = structuredClone(original); change(input);
    assert.equal(checkPython(input).valid, false);
  }
});

test("ticket path requires both ticket and bytes and cannot downgrade by removing archive context", async (t) => {
  const f = preparationFixture(t);
  const original = ticketInput(await f.preparation.prepare(token(), f.leaseToken));
  for (const drop of [["validation_ticket"], ["history_bytes"], ["approval_archive"], ["request_source", "source_commit"]]) {
    assert.equal(checkPython({ ...original, drop_evidence: drop }).valid, false);
  }
});

function validateWire(raw, times = [NOW * 1000, NOW * 1000]) {
  const script = `
import base64, json, sys
from services.contracts.validation import ContractError
from services.publication.authorization_validation import validate_authorization_input
v=json.load(sys.stdin)
times=iter(v['times'])
try:
    result=validate_authorization_input(base64.b64decode(v['input']), clock=lambda:next(times))
    print(json.dumps({'valid':True, **{key:base64.b64encode(raw).decode('ascii') for key,raw in result.items()}}))
except ContractError as exc:
    print(json.dumps({'valid':False,'error':str(exc)}))
`;
  const result = spawnSync("python3", ["-c", script], { input: JSON.stringify({ input: Buffer.from(raw).toString("base64"), times }),
    encoding: "utf-8", cwd: new URL("..", import.meta.url) });
  assert.equal(result.status, 0, result.stderr);
  const value = JSON.parse(result.stdout);
  if (!value.valid) return value;
  return { ...value, receipt: JSON.parse(Buffer.from(value.receipt_bytes, "base64")),
    authorization: JSON.parse(Buffer.from(value.authorization_bytes, "base64")) };
}

const sha = (bytes) => "sha256:" + createHash("sha256").update(bytes).digest("hex");
const canonical = (value) => value && typeof value === "object" ? Array.isArray(value) ? value.map(canonical) :
  Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])])) : value;

test("controlled validation wire produces receipt bound to full input, ticket and exact authorization bytes", async (t) => {
  for (const withHistory of [false, true]) {
    const f = preparationFixture(t, withHistory);
    const raw = await f.preparation.prepareValidationInput(token(), f.leaseToken);
    const input = JSON.parse(Buffer.from(raw));
    const result = validateWire(raw);
    assert.equal(result.valid, true, result.error);
    const { receipt, authorization } = result;
    assert.deepEqual(Object.keys(receipt).sort(), ["protocol", "verdict", "validated_at", "input_sha256", "input_size_bytes",
      "ticket_id", "ticket_sha256", "approval_evidence_ref", "authorization_ref", "authorization_archive"].sort());
    assert.equal(receipt.protocol, "m12-authorization-validation/1");
    assert.equal(receipt.verdict, "valid");
    assert.equal(receipt.validated_at, new Date(NOW * 1000).toISOString());
    assert.equal(authorization.generated_at, new Date(NOW * 1000).toISOString().replace(".000Z", "Z"));
    assert.equal(receipt.input_sha256, sha(raw));
    assert.equal(receipt.input_size_bytes, raw.length);
    assert.equal(receipt.ticket_id, input.validation_ticket.ticket_id);
    assert.equal(receipt.ticket_sha256, sha(JSON.stringify(canonical(input.validation_ticket))));
    assert.deepEqual(receipt.approval_evidence_ref, input.approval_evidence_ref);
    assert.deepEqual(receipt.authorization_ref, { id: authorization.authorization_id, content_fingerprint: authorization.content_fingerprint });
    const authBytes = Buffer.from(result.authorization_bytes, "base64");
    assert.deepEqual(receipt.authorization_archive, { key: "authority/" + authorization.content_fingerprint.slice(7) + ".json",
      sha256: sha(authBytes), size_bytes: authBytes.length });
    assert.equal(authorization.action, withHistory ? "revoke" : "grant");
    assert.equal(authorization.code_commit, businessRequest.code_commit);
    assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, withHistory ? 1 : 0);
    assert.equal(f.objects.has(receipt.authorization_archive.key), false);
  }
});

test("receipt distinguishes exact wire bytes while same inputs retain contract identity", async (t) => {
  const f = preparationFixture(t);
  const raw = await f.preparation.prepareValidationInput(token(), f.leaseToken);
  const first = validateWire(raw), replay = validateWire(raw);
  assert.deepEqual(first, replay);
  const later = validateWire(raw, [(NOW + 1) * 1000, (NOW + 2) * 1000]);
  assert.equal(later.valid, true, later.error);
  assert.equal(later.authorization_bytes, first.authorization_bytes);
  assert.notEqual(later.receipt.validated_at, first.receipt.validated_at);
  const spaced = Buffer.from(JSON.stringify(JSON.parse(Buffer.from(raw)), null, 2));
  const second = validateWire(spaced);
  assert.equal(second.valid, true);
  assert.notEqual(second.receipt.input_sha256, first.receipt.input_sha256);
  assert.equal(second.receipt.ticket_sha256, first.receipt.ticket_sha256);
  assert.equal(second.authorization_bytes, first.authorization_bytes);
});

test("validation wire rejects open fields, fallback shapes and noncanonical base64", async (t) => {
  const f = preparationFixture(t);
  const original = JSON.parse(Buffer.from(await f.preparation.prepareValidationInput(token(), f.leaseToken)));
  for (const change of [(v) => { v.protocol = "m12-authorization-validation/2"; }, (v) => { v.valid = true; },
    (v) => { delete v.validation_ticket; }, (v) => { delete v.history_base64; }, (v) => { delete v.approval_archive; },
    (v) => { v.history_base64 = {}; }, (v) => { v.approval_archive.objects = []; },
    (v) => { v.approval_archive.bundle_bytes = v.approval_archive.bundle_base64; },
    (v) => { v.approval_archive.bundle_base64 += "\n"; }, (v) => { v.approval_archive.bundle_base64 = "e31="; },
    (v) => { v.history_base64[0] = 3; }, (v) => { v.history_base64[0] = "中文"; }]) {
    const input = structuredClone(original); change(input);
    const result = validateWire(Buffer.from(JSON.stringify(input)));
    assert.equal(result.valid, false);
    assert.equal("receipt_bytes" in result, false);
    assert.equal("authorization_bytes" in result, false);
  }
  for (const raw of [Buffer.from('{"protocol":1,"protocol":2}'), Buffer.from('{"number":NaN}'),
    Buffer.from([0xff]), Buffer.from("[]")]) assert.equal(validateWire(raw).valid, false);
});

test("wire transport cannot bypass archived originals and complete history validation", async (t) => {
  const f = preparationFixture(t);
  const original = JSON.parse(Buffer.from(await f.preparation.prepareValidationInput(token(), f.leaseToken)));
  for (const change of [(v) => { v.history_base64 = []; }, (v) => { v.history_base64[0] = Buffer.from("{}").toString("base64"); },
    (v) => { delete v.approval_archive.objects[Object.keys(v.approval_archive.objects)[0]]; },
    (v) => { v.validation_ticket.owner_job.run_id = "457"; }, (v) => { v.validation_ticket.fence = true; },
    (v) => { v.approval_evidence_ref = f.priorRef; }]) {
    const input = structuredClone(original); change(input);
    assert.equal(validateWire(Buffer.from(JSON.stringify(input))).valid, false);
  }
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, 1);
});

test("Python computation rejects future start, expiry during validation and backwards or invalid clock", async (t) => {
  const f = preparationFixture(t);
  const raw = await f.preparation.prepareValidationInput(token(), f.leaseToken);
  for (const times of [[NOW * 1000 - 1, NOW * 1000], [NOW * 1000, (NOW + 300) * 1000],
    [(NOW + 300) * 1000, (NOW + 300) * 1000], [NOW * 1000 + 1, NOW * 1000], [true], [0.1]]) {
    const result = validateWire(raw, times);
    assert.equal(result.valid, false);
    assert.match(result.error, /frozen time window|clock/);
    assert.equal("receipt_bytes" in result, false);
  }
  assert.equal(validateWire(raw, [NOW * 1000, (NOW + 300) * 1000 - 1]).valid, true);
});

test("Python module command emits only the two base64 artifacts and fails with empty stdout", async (t) => {
  const f = preparationFixture(t);
  const raw = await f.preparation.prepareValidationInput(token(), f.leaseToken);
  // Only the local test clock is patched; the actual module stdin/stdout path runs.
  const script = `import time,runpy; time.time_ns=lambda:${NOW * 1000}*1000000; runpy.run_module('services.publication.authorization_validation',run_name='__main__')`;
  const invoke = (input) => spawnSync("python3", ["-c", script], { input, cwd: new URL("..", import.meta.url) });
  const result = invoke(raw);
  assert.equal(result.status, 0, result.stderr.toString());
  assert.equal(result.stderr.length, 0);
  const output = JSON.parse(result.stdout);
  assert.deepEqual(Object.keys(output).sort(), ["authorization_base64", "receipt_base64"]);
  const expected = validateWire(raw);
  assert.equal(output.receipt_base64, expected.receipt_bytes);
  assert.equal(output.authorization_base64, expected.authorization_bytes);
  for (const bad of [Buffer.from("{}"), Buffer.from("private-invalid-input")]) {
    const failure = invoke(bad);
    assert.equal(failure.status, 1);
    assert.equal(failure.stdout.length, 0);
    assert.equal(failure.stderr.toString(), "authorization validation failed\n");
  }
});

function isValidationWire(f, key) {
  try { return JSON.parse(Buffer.from(f.objects.get(key))).protocol === "m12-authorization-validation/1"; }
  catch { return false; }
}
const dispatchCount = (f) => f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_dispatches").get().n;

test("internal dispatch archives actual full input before transactional binding and matches Python receipt", async (t) => {
  const f = preparationFixture(t);
  let readAfterWrite = false;
  f.archiveState.beforeGet = (key) => {
    if (isValidationWire(f, key)) {
      assert.equal(dispatchCount(f), 0);
      readAfterWrite = true;
    }
  };
  const result = await f.preparation.dispatchValidationInput(token(), f.leaseToken);
  assert.equal(readAfterWrite, true);
  const { dispatch, input_bytes: raw } = result;
  assert.equal(dispatchCount(f), 1);
  assert.deepEqual(dispatch.input_archive, { key: "raw/" + sha(raw).slice(7), sha256: sha(raw), size_bytes: raw.length });
  assert.deepEqual(f.objects.get(dispatch.input_archive.key), raw);
  const receipt = validateWire(raw).receipt;
  assert.equal(receipt.input_sha256, dispatch.input_archive.sha256);
  assert.equal(receipt.input_size_bytes, dispatch.input_archive.size_bytes);
  assert.equal(receipt.ticket_sha256, dispatch.ticket_sha256);
  assert.equal(receipt.ticket_id, dispatch.ticket_id);
  assert.deepEqual(receipt.approval_evidence_ref, dispatch.approval_evidence_ref);
  assert.equal(dispatch.source_commit, identityPolicy.code_commit);
  assert.equal(dispatch.identity_expires_at, claims.exp);
  assert.equal(dispatch.identity_issued_at, claims.iat);
  assert.deepEqual(dispatch.owner_job, JSON.parse(Buffer.from(raw)).validation_ticket.owner_job);
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, 1);
  raw[0] ^= 1;
  dispatch.input_archive.size_bytes++;
  const saved = JSON.parse(f.db.prepare("SELECT dispatch_json FROM m12_authorization_dispatches").get().dispatch_json);
  assert.equal(saved.input_archive.size_bytes + 1, dispatch.input_archive.size_bytes);
  assert.notDeepEqual(f.objects.get(saved.input_archive.key), raw);
});

test("uncertain input write leaves only an orphan, and consistent retry records exactly one dispatch", async (t) => {
  const f = preparationFixture(t);
  let inputKey;
  f.archiveState.afterPut = (key) => {
    if (isValidationWire(f, key)) { inputKey = key; throw new Error("input_write_response_lost"); }
  };
  await assert.rejects(f.preparation.dispatchValidationInput(token(), f.leaseToken), /input_write_response_lost/);
  assert.ok(f.objects.has(inputKey));
  assert.equal(dispatchCount(f), 0);
  f.archiveState.afterPut = null;
  const result = await f.preparation.dispatchValidationInput(token(), f.leaseToken);
  assert.equal(result.dispatch.input_archive.key, inputKey);
  assert.equal(dispatchCount(f), 1);
  const replay = await f.preparation.dispatchValidationInput(token(), f.leaseToken);
  assert.deepEqual(replay, result);
  assert.equal(dispatchCount(f), 1);
});

test("missing or corrupt persisted validation input cannot be recorded as dispatched", async (t) => {
  for (const corrupt of [false, true]) {
    const f = preparationFixture(t);
    f.archiveState.beforeGet = (key) => {
      if (!isValidationWire(f, key)) return;
      if (corrupt) f.objects.get(key)[0] ^= 1;
      else f.objects.delete(key);
    };
    await assert.rejects(f.preparation.dispatchValidationInput(token(), f.leaseToken), /missing|hash_mismatch/);
    assert.equal(dispatchCount(f), 0);
  }
});

test("head or lease change while archiving validation input prevents its dispatch registration", async (t) => {
  for (const takeover of [false, true]) {
    const f = preparationFixture(t);
    f.archiveState.beforeGet = (key) => {
      if (!isValidationWire(f, key)) return;
      if (takeover) {
        f.lease.release("publish/global", f.job, f.leaseToken);
        f.lease.acquire("publish/global", { ...f.job, run_id: "457" }, f.leaseToken.epoch);
      } else {
        f.storage.transactionSync(() => {
          f.storage.sql.exec("DELETE FROM m12_authorization_index");
          f.storage.sql.exec("UPDATE m12_authorization_head SET revision=0,head_json=NULL");
        });
      }
    };
    await assert.rejects(f.preparation.dispatchValidationInput(token(), f.leaseToken), takeover ? /not_owned/ : /registration_recovery_required/);
    assert.equal(dispatchCount(f), 0);
  }
});

test("identity expiration after archived input readback leaves no dispatch record", async (t) => {
  const f = preparationFixture(t);
  f.archiveState.beforeGet = (key) => { if (isValidationWire(f, key)) f.state.now = claims.exp * 1000; };
  await assert.rejects(f.preparation.dispatchValidationInput(token(), f.leaseToken), /dispatch_identity_expired/);
  assert.equal(dispatchCount(f), 0);
});

async function returnFixture(t, withHistory = true) {
  const f = preparationFixture(t, withHistory);
  const sent = await f.preparation.dispatchValidationInput(token(), f.leaseToken);
  const python = validateWire(sent.input_bytes);
  assert.equal(python.valid, true, python.error);
  const result = { authorization_base64: python.authorization_bytes, receipt_base64: python.receipt_bytes };
  const receiver = new AuthorizationValidationReturn(identityPolicy,
    { storage: f.storage, bucket: f.bucket, clock: f.options.clock, fetchKeys: f.options.fetchKeys });
  const resultBytes = () => Buffer.from(JSON.stringify(canonical(result)) + "\n");
  return { ...f, sent, python, result, resultBytes, receiver,
    verify: (jwt = token(), id = sent.dispatch.dispatch_id, bytes = resultBytes()) => receiver.verify(jwt, f.leaseToken, id, bytes) };
}

function changeReceipt(f, change) {
  const receipt = JSON.parse(Buffer.from(f.result.receipt_base64, "base64"));
  change(receipt);
  f.result.receipt_base64 = Buffer.from(JSON.stringify(canonical(receipt))).toString("base64");
}

test("actual signed return reads persistent input and matches Python artifacts without consuming or appending", async (t) => {
  const f = await returnFixture(t);
  const gets = f.archiveState.gets;
  const result = await f.verify();
  assert.equal(f.archiveState.gets, gets + 1);
  assert.deepEqual(result.dispatch, f.sent.dispatch);
  assert.deepEqual(result.input_bytes, f.sent.input_bytes);
  assert.equal(Buffer.from(result.receipt_bytes).toString("base64"), f.python.receipt_bytes);
  assert.equal(Buffer.from(result.authorization_bytes).toString("base64"), f.python.authorization_bytes);
  assert.deepEqual(result.identity.job, f.job);
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, 1);
  assert.equal(dispatchCount(f), 1);
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_log").get().n, 2);
  result.input_bytes[0] ^= 1;
  result.dispatch.input_archive.size_bytes++;
  assert.deepEqual((await f.verify()).input_bytes, f.sent.input_bytes);
});

test("return rejects unverified claims, wrong signature, pinned workflow changes and other run or actor", async (t) => {
  const f = await returnFixture(t);
  for (const jwt of [{ job: f.job }, token().slice(0, -8) + "AAAAAAAA",
    token({ sha: "c".repeat(40) }), token({ workflow_sha: "c".repeat(40) }), token({ environment: "other" }),
    token({ run_id: "457" }), token({ run_attempt: "2" }), token({ actor_id: "888" })]) {
    await assert.rejects(f.verify(jwt));
  }
  const unknown = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  await assert.rejects(f.verify(token(), unknown), /dispatch_missing/);
  const unavailable = new AuthorizationValidationReturn(identityPolicy,
    { storage: f.storage, bucket: f.bucket, clock: f.options.clock, fetchKeys: async () => new Response("down", { status: 503 }) });
  await assert.rejects(unavailable.verify(token(), f.leaseToken, f.sent.dispatch.dispatch_id, f.resultBytes()), /keys_unavailable/);
  const changedPolicy = new AuthorizationValidationReturn({ ...identityPolicy, code_commit: "c".repeat(40) },
    { storage: f.storage, bucket: f.bucket, clock: f.options.clock, fetchKeys: f.options.fetchKeys });
  await assert.rejects(changedPolicy.verify(token({ sha: "c".repeat(40) }), f.leaseToken,
    f.sent.dispatch.dispatch_id, f.resultBytes()), /dispatch_identity_mismatch/);
});

test("return receipt must bind original input, ticket, approval and exact authorization output bytes", async (t) => {
  const f = await returnFixture(t);
  const original = structuredClone(f.result);
  for (const change of [(r) => { r.input_sha256 = "sha256:" + "0".repeat(64); }, (r) => { r.input_size_bytes++; },
    (r) => { r.ticket_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"; }, (r) => { r.ticket_sha256 = "sha256:" + "0".repeat(64); },
    (r) => { r.approval_evidence_ref = f.priorRef; }, (r) => { r.verdict = "invalid"; }, (r) => { r.extra = true; },
    (r) => { r.authorization_archive.size_bytes++; }, (r) => { r.authorization_archive.sha256 = "sha256:" + "0".repeat(64); },
    (r) => { r.authorization_archive.key = "authority/" + "0".repeat(64) + ".json"; },
    (r) => { r.authorization_ref = f.priorRef; }]) {
    Object.assign(f.result, original); changeReceipt(f, change);
    await assert.rejects(f.verify());
  }
  Object.assign(f.result, original);
  const auth = JSON.parse(Buffer.from(f.result.authorization_base64, "base64"));
  auth.reason = "changed output";
  f.result.authorization_base64 = Buffer.from(JSON.stringify(canonical(auth))).toString("base64");
  await assert.rejects(f.verify(), /output_mismatch/);
  for (const change of [(value) => { value.job.run_id = "457"; },
    (value) => { value.approval_evidence_ref = f.priorRef; }, (value) => { value.prior_authorization_ref = null; },
    (value) => { value.authorization_id = f.priorRef.id; }]) {
    Object.assign(f.result, original);
    const changed = JSON.parse(Buffer.from(f.result.authorization_base64, "base64"));
    change(changed);
    const bytes = Buffer.from(JSON.stringify(canonical(changed)));
    f.result.authorization_base64 = bytes.toString("base64");
    changeReceipt(f, (r) => { r.authorization_archive.sha256 = sha(bytes); r.authorization_archive.size_bytes = bytes.length; });
    await assert.rejects(f.verify(), /output_mismatch/);
  }
});

test("return artifact protocol refuses duplicate keys, noncanonical bytes and alternate success shapes", async (t) => {
  const f = await returnFixture(t);
  const original = structuredClone(f.result);
  for (const bytes of [Buffer.from("{}\n"), Buffer.from('{"valid":true}\n'),
    Buffer.from('{"receipt_base64":"","receipt_base64":""}\n'), Buffer.from([0xff]),
    Buffer.from(JSON.stringify(f.result, null, 2) + "\n"), Buffer.from("\ufeff" + f.resultBytes().toString())]) {
    await assert.rejects(f.verify(token(), f.sent.dispatch.dispatch_id, bytes));
  }
  for (const change of [() => { f.result.receipt_base64 += "\n"; },
    () => { f.result.receipt_base64 = Buffer.from(Buffer.from(f.result.receipt_base64, "base64").toString() + "\n").toString("base64"); },
    () => { f.result.authorization_base64 = "e31="; },
    () => { f.result.receipt_base64 = Buffer.from('{"verdict":"valid","verdict":"valid"}').toString("base64"); }]) {
    Object.assign(f.result, original); change();
    await assert.rejects(f.verify());
  }
});

test("other dispatch for the same job cannot borrow a previous input receipt", async (t) => {
  const f = await returnFixture(t);
  f.state.now += 1000;
  const next = await f.preparation.dispatchValidationInput(token(), f.leaseToken);
  assert.notEqual(next.dispatch.dispatch_id, f.sent.dispatch.dispatch_id);
  await assert.rejects(f.verify(token(), next.dispatch.dispatch_id), /receipt_mismatch/);
});

test("missing or damaged stored input and dispatch log refuse return verification", async (t) => {
  for (const corrupt of ["missing", "bytes", "log"]) {
    const f = await returnFixture(t);
    if (corrupt === "missing") f.objects.delete(f.sent.dispatch.input_archive.key);
    if (corrupt === "bytes") f.objects.get(f.sent.dispatch.input_archive.key)[0] ^= 1;
    if (corrupt === "log") f.db.exec("DELETE FROM m12_authorization_log WHERE operation='dispatch_validation'");
    await assert.rejects(f.verify());
  }
});

test("return rechecks live head, owner and log after input readback", async (t) => {
  for (const change of ["head", "lease", "log"]) {
    const f = await returnFixture(t);
    f.archiveState.beforeGet = (key) => {
      if (key !== f.sent.dispatch.input_archive.key) return;
      if (change === "head") f.db.exec("DELETE FROM m12_authorization_index; UPDATE m12_authorization_head SET revision=0,head_json=NULL");
      if (change === "log") f.db.exec("DELETE FROM m12_authorization_log WHERE operation='dispatch_validation'");
      if (change === "lease") {
        f.lease.release("publish/global", f.job, f.leaseToken);
        f.lease.acquire("publish/global", { ...f.job, run_id: "457" }, f.leaseToken.epoch);
      }
    };
    await assert.rejects(f.verify(), /history_changed|not_owned|recovery_required/);
  }
});

test("return time and renewed OIDC cannot outlive frozen dispatch, ticket or current lease", async (t) => {
  const f = await returnFixture(t);
  const original = structuredClone(f.result);
  for (const stamp of [new Date(NOW * 1000 - 1).toISOString(), new Date(NOW * 1000 + 1).toISOString(),
    new Date(claims.exp * 1000).toISOString(), new Date(NOW * 1000).toISOString().replace(".000Z", "Z")]) {
    Object.assign(f.result, original); changeReceipt(f, (r) => { r.validated_at = stamp; });
    await assert.rejects(f.verify(), /return_time_invalid/);
  }
  Object.assign(f.result, original);
  f.archiveState.beforeGet = (key) => { if (key === f.sent.dispatch.input_archive.key) f.state.now = claims.exp * 1000; };
  await assert.rejects(f.verify(token({ exp: claims.exp + 300 })), /deadline_expired|expired_before_commit|stale/);
});

test("return copies caller output bytes before identity and storage awaits", async (t) => {
  const f = await returnFixture(t);
  const bytes = f.resultBytes();
  const pending = f.verify(token(), f.sent.dispatch.dispatch_id, bytes);
  bytes.fill(0);
  const result = await pending;
  assert.equal(Buffer.from(result.authorization_bytes).toString("base64"), f.python.authorization_bytes);
});

async function validationArchiveFixture(t, withHistory = true) {
  const f = await returnFixture(t, withHistory);
  const validator = new AuthorizationValidationArchive(identityPolicy,
    { storage: f.storage, bucket: f.bucket, clock: f.options.clock, fetchKeys: f.options.fetchKeys });
  const receiptKey = "raw/" + sha(Buffer.from(f.python.receipt_bytes, "base64")).slice(7);
  return { ...f, receiptKey, authorizationKey: f.python.receipt.authorization_archive.key,
    archiveValidation: (jwt = token(), bytes = f.resultBytes()) => validator.archive(jwt, f.leaseToken, f.sent.dispatch.dispatch_id, bytes) };
}

test("validation archive internally verifies and writes then separately reads both unchanged original artifacts", async (t) => {
  const f = await validationArchiveFixture(t);
  const puts = f.archiveState.puts, gets = f.archiveState.gets;
  const result = await f.archiveValidation();
  assert.equal(f.archiveState.puts, puts + 2);
  assert.equal(f.archiveState.gets, gets + 5); // Input read + two put readbacks + two independent reads.
  assert.deepEqual(result.authorization_archive, f.python.receipt.authorization_archive);
  assert.deepEqual(result.validation_receipt_archive, { key: f.receiptKey,
    sha256: sha(Buffer.from(f.python.receipt_bytes, "base64")), size_bytes: Buffer.from(f.python.receipt_bytes, "base64").length });
  assert.equal(Buffer.from(result.authorization_bytes).toString("base64"), f.python.authorization_bytes);
  assert.equal(Buffer.from(result.receipt_bytes).toString("base64"), f.python.receipt_bytes);
  assert.deepEqual(result.authorization_bytes, f.objects.get(f.authorizationKey));
  assert.deepEqual(result.receipt_bytes, f.objects.get(f.receiptKey));
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, 1);
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_log").get().n, 3);
  result.authorization_bytes[0] ^= 1;
  result.validation_receipt_archive.size_bytes++;
  const replay = await f.archiveValidation();
  assert.equal(Buffer.from(replay.authorization_bytes).toString("base64"), f.python.authorization_bytes);
  assert.notEqual(replay.validation_receipt_archive.size_bytes, result.validation_receipt_archive.size_bytes);
});

test("claimed verified JSON, invalid signature and changed stdout cannot write validation artifacts", async (t) => {
  const f = await validationArchiveFixture(t);
  const puts = f.archiveState.puts;
  await assert.rejects(f.archiveValidation(token(), { valid: true, receipt: f.python.receipt }));
  await assert.rejects(f.archiveValidation(token().slice(0, -8) + "AAAAAAAA"));
  await assert.rejects(f.archiveValidation(token(), Buffer.from('{"valid":true}\n')));
  assert.equal(f.archiveState.puts, puts);
  assert.equal(f.objects.has(f.authorizationKey), false);
  assert.equal(f.objects.has(f.receiptKey), false);
});

test("uncertain artifact write remains unregistered and retry retains exact original bytes", async (t) => {
  for (const failed of ["authorization", "receipt"]) {
    const f = await validationArchiveFixture(t);
    const key = failed === "authorization" ? f.authorizationKey : f.receiptKey;
    f.archiveState.afterPut = (written) => { if (written === key) throw new Error("artifact_write_response_lost"); };
    await assert.rejects(f.archiveValidation(), /artifact_write_response_lost/);
    assert.equal(recordedReturns(f).length, 0);
    assert.equal(recordedReturnLogs(f).length, 0);
    const orphan = new Uint8Array(f.objects.get(key));
    assert.ok(orphan.length);
    assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, 1);
    f.archiveState.afterPut = null;
    await f.archiveValidation();
    assert.deepEqual(f.objects.get(key), orphan);
    assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_log").get().n, 3);
  }
});

test("existing authorization key with conflicting bytes is preserved and blocks receipt write", async (t) => {
  const f = await validationArchiveFixture(t);
  const conflict = new Uint8Array([1, 2, 3]);
  f.objects.set(f.authorizationKey, conflict);
  await assert.rejects(f.archiveValidation(), /size_mismatch|hash_mismatch/);
  assert.deepEqual(f.objects.get(f.authorizationKey), conflict);
  assert.equal(f.objects.has(f.receiptKey), false);
});

test("late missing or corrupt artifacts fail the independent final read instead of returning old memory", async (t) => {
  for (const object of ["authorization", "receipt"]) for (const corrupt of [false, true]) {
    const f = await validationArchiveFixture(t);
    const key = object === "authorization" ? f.authorizationKey : f.receiptKey;
    let reads = 0;
    f.archiveState.beforeGet = (read) => {
      if (read !== key || ++reads !== 2) return;
      if (corrupt) f.objects.get(key)[0] ^= 1;
      else f.objects.delete(key);
    };
    await assert.rejects(f.archiveValidation(), /missing|hash_mismatch/);
    assert.equal(reads, 2);
    assert.equal(recordedReturns(f).length, 0);
    assert.equal(recordedReturnLogs(f).length, 0);
    assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, 1);
  }
});

test("head, lease or dispatch log change during artifact I/O prevents successful return", async (t) => {
  for (const change of ["head", "lease", "log"]) for (const finalRead of [false, true]) {
    const f = await validationArchiveFixture(t);
    const key = finalRead ? f.receiptKey : f.authorizationKey;
    let reads = 0;
    f.archiveState.beforeGet = (read) => {
      if (read !== key || ++reads !== (finalRead ? 2 : 1)) return;
      if (change === "head") f.db.exec("DELETE FROM m12_authorization_index; UPDATE m12_authorization_head SET revision=0,head_json=NULL");
      if (change === "log") f.db.exec("DELETE FROM m12_authorization_log WHERE operation='dispatch_validation'");
      if (change === "lease") {
        f.lease.release("publish/global", f.job, f.leaseToken);
        f.lease.acquire("publish/global", { ...f.job, run_id: "457" }, f.leaseToken.epoch);
      }
    };
    await assert.rejects(f.archiveValidation(), /history_changed|not_owned|recovery_required/);
    if (!finalRead) assert.equal(f.objects.has(f.receiptKey), false);
  }
});

test("expired original window during either write or final read cannot be extended by fresh OIDC", async (t) => {
  for (const finalRead of [false, true]) {
    const f = await validationArchiveFixture(t);
    const key = finalRead ? f.receiptKey : f.authorizationKey;
    let reads = 0;
    f.archiveState.beforeGet = (read) => {
      if (read === key && ++reads === (finalRead ? 2 : 1)) f.state.now = claims.exp * 1000;
    };
    await assert.rejects(f.archiveValidation(token({ exp: claims.exp + 300 })), /deadline_expired|stale|expired_before_commit/);
    if (!finalRead) assert.equal(f.objects.has(f.receiptKey), false);
    assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, 1);
  }
});

test("later valid revalidation reuses authorization bytes and preserves both validation receipts", async (t) => {
  const f = await validationArchiveFixture(t);
  const first = await f.archiveValidation();
  f.state.now = (NOW + 2) * 1000;
  const later = validateWire(f.sent.input_bytes, [(NOW + 1) * 1000, (NOW + 2) * 1000]);
  assert.equal(later.valid, true, later.error);
  f.result.authorization_base64 = later.authorization_bytes;
  f.result.receipt_base64 = later.receipt_bytes;
  const second = await f.archiveValidation();
  assert.deepEqual(second.authorization_archive, first.authorization_archive);
  assert.deepEqual(second.authorization_bytes, first.authorization_bytes);
  assert.notEqual(second.validation_receipt_archive.key, first.validation_receipt_archive.key);
  assert.ok(f.objects.has(first.validation_receipt_archive.key));
  assert.ok(f.objects.has(second.validation_receipt_archive.key));
  assert.equal(recordedReturns(f).length, 2);
  assert.equal(recordedReturnLogs(f).length, 2);
  assert.notDeepEqual(first.return_record, second.return_record);
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, 1);
});

function executePythonJob(f, changes = {}) {
  const script = `
import base64, json, sys
from unittest.mock import patch
from services.contracts.validation import ContractError
from services.publication.authorization_execution import execute_authorization_validation
v=json.load(sys.stdin)
prepared=v['prepared']
prepared['input_bytes']=base64.b64decode(prepared['input_bytes'])
if v.get('mutable_input'): prepared['input_bytes']=bytearray(prepared['input_bytes'])
for name in v.get('drop',[]): prepared.pop(name, None)
calls=[]
class Transport:
    def prepare(self):
        calls.append('prepare')
        if v.get('prepare_error'): raise RuntimeError('prepare transport failure')
        return prepared
    def return_result(self, dispatch_id, lease_token, result_bytes):
        calls.append({'dispatch_id':dispatch_id,'lease_token':lease_token,'result_bytes':base64.b64encode(result_bytes).decode('ascii')})
        if v.get('return_error'): raise RuntimeError('return response lost')
        return {'claimed_success':True} if v.get('bad_response') else b'opaque-server-response'
try:
    with patch('time.time_ns', return_value=v['now_ms']*1000000):
        response=execute_authorization_validation(Transport(), **v.get('kwargs',{}))
    print(json.dumps({'ok':True,'response':base64.b64encode(response).decode('ascii'),'calls':calls}))
except (ContractError, RuntimeError, TypeError) as exc:
    if isinstance(exc, TypeError) and not v.get('kwargs'): raise
    print(json.dumps({'ok':False,'error':str(exc),'calls':calls}))
`;
  const prepared = { dispatch_id: f.sent.dispatch.dispatch_id, lease_token: f.leaseToken,
    input_sha256: sha(f.sent.input_bytes), input_size_bytes: f.sent.input_bytes.length,
    input_bytes: Buffer.from(f.sent.input_bytes).toString("base64"), ...changes.prepared };
  const result = spawnSync("python3", ["-c", script], { input: JSON.stringify({ ...changes, prepared, now_ms: changes.now_ms ?? NOW * 1000 }),
    encoding: "utf-8", cwd: new URL("..", import.meta.url) });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test("fixed executor takes transport bytes through the real single Python output path and B3f accepts them", async (t) => {
  const f = await validationArchiveFixture(t);
  const executed = executePythonJob(f);
  assert.equal(executed.ok, true, executed.error);
  assert.equal(executed.calls[0], "prepare");
  assert.equal(executed.calls.length, 2);
  const sent = executed.calls[1];
  assert.equal(sent.dispatch_id, f.sent.dispatch.dispatch_id);
  assert.deepEqual(sent.lease_token, f.leaseToken);
  const output = Buffer.from(sent.result_bytes, "base64");
  assert.deepEqual(output, f.resultBytes());
  const archived = await f.archiveValidation(token(), output);
  assert.equal(Buffer.from(archived.authorization_bytes).toString("base64"), f.python.authorization_bytes);
  assert.equal(Buffer.from(executed.response, "base64").toString(), "opaque-server-response");
});

test("fixed executor rejects missing, extra or altered transport input and lease before return", async (t) => {
  const f = await validationArchiveFixture(t);
  for (const changes of [{ drop: ["input_sha256"] }, { prepared: { extra: true } }, { prepared: { input_size_bytes: true } },
    { prepared: { input_sha256: "sha256:" + "0".repeat(64) } }, { mutable_input: true },
    { prepared: { dispatch_id: "not-a-dispatch" } }, { prepared: { lease_token: { ...f.leaseToken, fence: true } } },
    { prepared: { lease_token: { ...f.leaseToken, fence: f.leaseToken.fence + 1 } } },
    { prepared: { lease_token: { ...f.leaseToken, epoch: "22222222-2222-4222-8222-222222222222" } } }]) {
    const result = executePythonJob(f, changes);
    assert.equal(result.ok, false);
    assert.deepEqual(result.calls, ["prepare"]);
  }
});

test("self-consistent transport hashes cannot bypass actual archive, history and ticket validation", async (t) => {
  const f = await validationArchiveFixture(t);
  for (const change of [(v) => { v.history_base64 = []; }, (v) => { v.approval_archive.objects = {}; },
    (v) => { v.validation_ticket.owner_job.run_id = "457"; }, (v) => { v.protocol = "other"; }]) {
    const input = JSON.parse(Buffer.from(f.sent.input_bytes)); change(input);
    const bytes = Buffer.from(JSON.stringify(input));
    const result = executePythonJob(f, { prepared: { input_bytes: bytes.toString("base64"), input_sha256: sha(bytes), input_size_bytes: bytes.length } });
    assert.equal(result.ok, false);
    assert.deepEqual(result.calls, ["prepare"]);
  }
});

test("fixed execution cannot substitute a validator, executable or caller-provided success bytes", async (t) => {
  const f = await validationArchiveFixture(t);
  for (const kwargs of [{ validator: "accept_all" }, { command: "true" }, { result_bytes: "valid" }, { input_bytes: "{}" }]) {
    const result = executePythonJob(f, { kwargs });
    assert.equal(result.ok, false);
    assert.deepEqual(result.calls, []);
  }
});

test("fixed execution stops before submitting expired validation and never fabricates a failure receipt", async (t) => {
  const f = await validationArchiveFixture(t);
  const result = executePythonJob(f, { now_ms: claims.exp * 1000 });
  assert.equal(result.ok, false);
  assert.match(result.error, /frozen time window/);
  assert.deepEqual(result.calls, ["prepare"]);
});

test("prepare and uncertain return failures propagate without automatic resubmission", async (t) => {
  const f = await validationArchiveFixture(t);
  for (const changes of [{ prepare_error: true }, { return_error: true }]) {
    const result = executePythonJob(f, changes);
    assert.equal(result.ok, false);
    assert.equal(result.calls.length, changes.prepare_error ? 1 : 2);
    assert.match(result.error, /transport failure|response lost/);
  }
});

test("transport response stays opaque bytes and cannot become a claimed authorization success", async (t) => {
  const f = await validationArchiveFixture(t);
  const valid = executePythonJob(f);
  assert.equal(valid.ok, true);
  assert.equal(Buffer.from(valid.response, "base64").toString(), "opaque-server-response");
  const invalid = executePythonJob(f, { bad_response: true });
  assert.equal(invalid.ok, false);
  assert.equal(invalid.calls.length, 2);
  assert.match(invalid.error, /raw bytes/);
});

test("HTTPS transport carries actual fixed Python output through its closed wire envelope to B3f", async (t) => {
  const f = await validationArchiveFixture(t);
  const script = `
import base64, io, json, sys
from email.message import Message
from unittest.mock import patch
from services.publication.authorization_execution import execute_authorization_validation
from services.publication.authorization_transport import AuthorizationHttpsTransport
v=json.load(sys.stdin)
calls=[]
class Response(io.BytesIO):
    def __init__(self, raw, url):
        super().__init__(raw)
        self.status=200
        self.url=url
        self.headers=Message()
        self.headers['Content-Type']='application/json'
        self.headers['Content-Length']=str(len(raw))
    def geturl(self): return self.url
class Opener:
    def open(self, request, timeout):
        calls.append({'url':request.full_url,'authorization':request.get_header('Authorization'),'body':base64.b64encode(request.data).decode('ascii') if request.data is not None else None})
        if 'actions.githubusercontent.com' in request.full_url:
            raw=json.dumps({'value':v['token']}).encode()
        elif request.full_url.endswith('/prepare'):
            raw=json.dumps(v['prepared']).encode()
        else:
            raw=b'{"state":"pending"}'
        return Response(raw,request.full_url)
transport=AuthorizationHttpsTransport('https://coordinator.example.test', {'GITHUB_ACTIONS':'true','ACTIONS_ID_TOKEN_REQUEST_URL':'https://run.actions.githubusercontent.com/token?api-version=2.0','ACTIONS_ID_TOKEN_REQUEST_TOKEN':'local-request-credential'}, opener=Opener())
with patch('time.time_ns',return_value=v['now_ms']*1000000):
    response=execute_authorization_validation(transport)
print(json.dumps({'calls':calls,'response':base64.b64encode(response).decode('ascii')}))
`;
  const prepared = { protocol: "m12-authorization-job/1", dispatch_id: f.sent.dispatch.dispatch_id, lease_token: f.leaseToken,
    input_sha256: sha(f.sent.input_bytes), input_size_bytes: f.sent.input_bytes.length,
    input_base64: Buffer.from(f.sent.input_bytes).toString("base64") };
  const executed = spawnSync("python3", ["-c", script], { input: JSON.stringify({ prepared, token: token(), now_ms: NOW * 1000 }),
    encoding: "utf-8", cwd: new URL("..", import.meta.url) });
  assert.equal(executed.status, 0, executed.stderr);
  const output = JSON.parse(executed.stdout);
  assert.equal(output.calls.length, 4);
  assert.equal(output.calls[0].authorization, "Bearer local-request-credential");
  assert.equal(output.calls[2].authorization, "Bearer local-request-credential");
  assert.equal(output.calls[1].authorization, "Bearer " + token());
  assert.equal(output.calls[3].authorization, "Bearer " + token());
  assert.equal(output.calls[3].url, "https://coordinator.example.test/v1/authorization/return");
  const returned = JSON.parse(Buffer.from(output.calls[3].body, "base64"));
  assert.equal(returned.dispatch_id, f.sent.dispatch.dispatch_id);
  assert.deepEqual(returned.lease_token, f.leaseToken);
  const resultBytes = Buffer.from(returned.result_base64, "base64");
  assert.deepEqual(resultBytes, f.resultBytes());
  const archived = await f.archiveValidation(token(), resultBytes);
  assert.equal(Buffer.from(archived.authorization_bytes).toString("base64"), f.python.authorization_bytes);
});

function apiFixture(t, patch = {}) {
  const f = preparationFixture(t);
  const api = new AuthorizationJobApi(identityPolicy, reviewPolicy,
    { ...f.options, storage: f.storage, bucket: f.bucket, leaseEpoch: f.leaseToken.epoch, enabled: true, ...patch });
  return { ...f, api };
}
function apiRequest(path, raw = "{}", jwt = token(), headers = {}) {
  return new Request("https://coordinator.example.test/v1/authorization/" + path,
    { method: "POST", headers: { "Authorization": "Bearer " + jwt, "Content-Type": "application/json", ...headers }, body: raw });
}

test("job API is disabled by default without touching network or storage", async () => {
  const storage = new Proxy({}, { get() { throw new Error("storage must not be touched"); } });
  const api = new AuthorizationJobApi(null, null, { storage });
  const result = await api.fetch(apiRequest("prepare"));
  assert.equal(result.status, 503);
  assert.equal((await result.json()).error, "authorization_jobs_disabled");
  assert.equal(result.headers.get("Cache-Control"), "no-store");
});

test("prepare route obtains server epoch lease only after archived approval readback", async (t) => {
  const f = apiFixture(t);
  f.lease.release("publish/global", f.job, f.leaseToken);
  let checked = 0;
  f.archiveState.beforeGet = (key) => {
    try {
      if (JSON.parse(Buffer.from(f.objects.get(key))).kind !== "github_environment_approval_observation") return;
    } catch { return; }
    assert.equal(f.db.prepare("SELECT owner_json FROM m12_leases WHERE resource='publish/global'").get().owner_json, null);
    checked++;
  };
  const result = await f.api.fetch(apiRequest("prepare"));
  assert.equal(result.status, 200, await result.clone().text());
  const prepared = await result.json();
  assert.ok(checked >= 2);
  assert.equal(prepared.lease_token.epoch, f.leaseToken.epoch);
  assert.equal(prepared.lease_token.fence, f.leaseToken.fence + 1);
  assert.deepEqual(Object.keys(prepared).sort(), ["protocol", "dispatch_id", "lease_token", "input_base64", "input_sha256", "input_size_bytes"].sort());
  const raw = Buffer.from(prepared.input_base64, "base64");
  assert.equal(prepared.input_sha256, sha(raw));
  assert.equal(prepared.input_size_bytes, raw.length);
  assert.equal(validateWire(raw).valid, true);
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, 1);
});

test("job API does not initialize a missing epoch or preempt another owner", async (t) => {
  for (const missing of [false, true]) {
    const f = apiFixture(t);
    if (missing) f.db.exec("DELETE FROM m12_lease_epoch");
    else {
      f.lease.release("publish/global", f.job, f.leaseToken);
      f.lease.acquire("publish/global", { ...f.job, run_id: "457" }, f.leaseToken.epoch);
    }
    const result = await f.api.fetch(apiRequest("prepare"));
    assert.equal(result.status, 409);
    assert.equal(dispatchCount(f), 0);
    if (missing) assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_lease_epoch").get().n, 0);
    else assert.equal(JSON.parse(f.db.prepare("SELECT owner_json FROM m12_leases WHERE resource='publish/global'").get().owner_json).run_id, "457");
  }
});

test("job routes refuse wrong method/path/identity and private body before any archival writes", async (t) => {
  const f = apiFixture(t);
  const puts = f.archiveState.puts;
  const requests = [new Request("https://coordinator.example.test/v1/authorization/prepare"), apiRequest("prepare?epoch=other"),
    apiRequest("initialize"), apiRequest("prepare", "{}", token({ run_attempt: "bogus" })),
    apiRequest("prepare", "{}", "unsigned"), apiRequest("prepare", "{\"epoch\":\"user-selected\"}"),
    apiRequest("prepare", "{}", token(), { "Content-Type": "text/plain" }),
    apiRequest("return", '{"protocol":"m12-authorization-job/1","protocol":"m12-authorization-job/1"}'),
    apiRequest("return", '{"valid":true}'), apiRequest("return", "{}", token(), { "Content-Encoding": "gzip" })];
  for (const request of requests) {
    const result = await f.api.fetch(request);
    assert.notEqual(result.status, 200);
    assert.deepEqual(Object.keys(await result.json()).sort(), ["error", "protocol"]);
  }
  assert.equal(f.archiveState.puts, puts);
});

test("return route archives valid artifacts but never consumes or registers authority", async (t) => {
  const f = apiFixture(t);
  const prepared = await (await f.api.fetch(apiRequest("prepare"))).json();
  const python = validateWire(Buffer.from(prepared.input_base64, "base64"));
  const raw = Buffer.from(JSON.stringify(canonical({ authorization_base64: python.authorization_bytes, receipt_base64: python.receipt_bytes })) + "\n");
  const payload = { protocol: "m12-authorization-job/1", dispatch_id: prepared.dispatch_id, lease_token: prepared.lease_token,
    result_base64: raw.toString("base64") };
  const first = await f.api.fetch(apiRequest("return", JSON.stringify(canonical(payload))));
  assert.equal(first.status, 200, await first.clone().text());
  const ack = await first.json();
  assert.equal(ack.state, "archived_pending_registration");
  assert.equal(ack.dispatch_id, prepared.dispatch_id);
  assert.deepEqual(ack.authorization_archive, python.receipt.authorization_archive);
  assert.ok(f.objects.has(ack.validation_receipt_archive.key));
  const replay = await f.api.fetch(apiRequest("return", JSON.stringify(canonical(payload))));
  assert.deepEqual(await replay.json(), ack);
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, 1);
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_log").get().n, 3);
  const wrong = { ...payload, lease_token: { ...prepared.lease_token, fence: true } };
  assert.equal((await f.api.fetch(apiRequest("return", JSON.stringify(canonical(wrong))))).status, 400);
  payload.result_base64 = Buffer.from('{"valid":true}\n').toString("base64");
  assert.equal((await f.api.fetch(apiRequest("return", JSON.stringify(canonical(payload))))).status, 409);
});

test("job request reads enforce byte limit and a total body-read timer", async (t) => {
  const f = apiFixture(t);
  let cancelled = false;
  const stream = new ReadableStream({ pull() {}, cancel() { cancelled = true; } });
  const request = new Request("https://coordinator.example.test/v1/authorization/return", { method: "POST",
    headers: { "Authorization": "Bearer " + token(), "Content-Type": "application/json" }, body: stream, duplex: "half" });
  assert.equal((await f.api.fetch(request)).status, 400);
  assert.equal(cancelled, true);
  const tooLarge = apiRequest("return", "{}", token(), { "Content-Length": String(4 * 1024 * 1024 + 1) });
  assert.equal((await f.api.fetch(tooLarge)).status, 400);
  assert.equal(dispatchCount(f), 0);
});

test("actual Python HTTP client and fixed executor round trip through prepare status renew and return routes", async (t) => {
  const f = apiFixture(t);
  const script = `
import base64,io,json,sys
from email.message import Message
from unittest.mock import patch
from services.publication.authorization_execution import execute_authorization_validation
from services.publication.authorization_transport import AuthorizationHttpsTransport
class Response(io.BytesIO):
    def __init__(self,value,url):
        super().__init__(base64.b64decode(value['body']))
        self.status=value['status']; self.url=url; self.headers=Message()
        for k,v in value['headers'].items(): self.headers[k]=v
    def geturl(self): return self.url
class Opener:
    def open(self,request,timeout):
        print(json.dumps({'url':request.full_url,'headers':dict(request.header_items()),'body':base64.b64encode(request.data).decode('ascii') if request.data else None}),flush=True)
        value=json.loads(sys.stdin.readline())
        return Response(value,request.full_url)
class ControlledTransport(AuthorizationHttpsTransport):
    def prepare(self):
        value=super().prepare()
        assert self.status()['state']=='dispatch_current'
        assert self.renew()['state']=='dispatch_current'
        return value
transport=ControlledTransport('https://coordinator.example.test',{'GITHUB_ACTIONS':'true','ACTIONS_ID_TOKEN_REQUEST_URL':'https://run.actions.githubusercontent.com/token?api-version=2.0','ACTIONS_ID_TOKEN_REQUEST_TOKEN':'local-request-credential'},opener=Opener())
with patch('time.time_ns',return_value=${NOW * 1000}*1000000):
    result=execute_authorization_validation(transport)
print(json.dumps({'finished':True,'response':base64.b64encode(result).decode('ascii')}),flush=True)
`;
  const child = spawn("python3", ["-u", "-c", script], { cwd: new URL("..", import.meta.url), stdio: ["pipe", "pipe", "pipe"] });
  t.after(() => { if (child.exitCode === null) child.kill(); });
  let stderr = "", finished;
  child.stderr.on("data", (data) => { stderr += data; });
  const exited = new Promise((resolve, reject) => { child.on("error", reject); child.on("exit", resolve); });
  const lines = createInterface({ input: child.stdout });
  const paths = [];
  for await (const line of lines) {
    const request = JSON.parse(line);
    if (request.finished) { finished = JSON.parse(Buffer.from(request.response, "base64")); child.stdin.end(); continue; }
    const url = new URL(request.url);
    let result;
    if (url.hostname.endsWith(".actions.githubusercontent.com")) {
      result = new Response(JSON.stringify({ value: token() }), { headers: { "Content-Type": "application/json" } });
    } else {
      paths.push(url.pathname);
      result = await f.api.fetch(new Request(request.url, { method: "POST", headers: request.headers, body: Buffer.from(request.body, "base64") }));
    }
    const body = Buffer.from(await result.arrayBuffer()).toString("base64");
    child.stdin.write(JSON.stringify({ status: result.status, headers: Object.fromEntries(result.headers), body }) + "\n");
  }
  assert.equal(await exited, 0, stderr);
  assert.deepEqual(paths, ["/v1/authorization/prepare", "/v1/authorization/status", "/v1/authorization/renew", "/v1/authorization/return"]);
  assert.equal(finished.state, "archived_pending_registration");
  assert.ok(f.objects.has(finished.authorization_archive.key));
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, 1);
});

async function controlFixture(t, jwt = token()) {
  const f = apiFixture(t);
  const prepared = await (await f.api.fetch(apiRequest('prepare', '{}', jwt))).json();
  const payload = { protocol: 'm12-authorization-job/1', dispatch_id: prepared.dispatch_id, lease_token: prepared.lease_token };
  const request = (route, patch = {}, jwt = token()) => apiRequest(route, JSON.stringify(canonical({ ...payload, ...patch })), jwt);
  const leaseRow = () => ({ ...f.db.prepare("SELECT * FROM m12_leases WHERE resource='publish/global'").get() });
  const renewCount = () => f.db.prepare("SELECT COUNT(*) AS n FROM m12_lease_log WHERE operation='renew'").get().n;
  return { ...f, prepared, payload, request, leaseRow, renewCount };
}

test('status reads current frozen dispatch across API reopen without lease renewal or success claims', async (t) => {
  const f = await controlFixture(t);
  const before = f.leaseRow(), puts = f.archiveState.puts;
  const result = await f.api.fetch(f.request('status'));
  assert.equal(result.status, 200);
  const value = await result.json();
  assert.deepEqual(Object.keys(value).sort(), ['dispatch_id', 'lease_expires_at', 'lease_token', 'protocol', 'state', 'validation_expires_at']);
  assert.equal(value.state, 'dispatch_current');
  const reopened = new AuthorizationJobApi(identityPolicy, reviewPolicy,
    { ...f.options, storage: f.storage, bucket: f.bucket, enabled: true, leaseEpoch: f.leaseToken.epoch });
  assert.deepEqual(await (await reopened.fetch(f.request('status'))).json(), value);
  assert.deepEqual(f.leaseRow(), before);
  assert.equal(f.renewCount(), 0);
  assert.equal(f.archiveState.puts, puts);
  assert.equal(dispatchCount(f), 1);
});

test('renew extends only lease while preserving original dispatch bytes and validation deadline', async (t) => {
  const f = await controlFixture(t);
  const rows = () => f.db.prepare('SELECT dispatch_json FROM m12_authorization_dispatches').all();
  const original = rows();
  const expiry = JSON.parse(original[0].dispatch_json).expires_at;
  f.state.now += 60_000;
  const result = await f.api.fetch(f.request('renew', {}, token({ iat: NOW + 60, exp: NOW + 600 })));
  assert.equal(result.status, 200);
  const value = await result.json();
  assert.equal(value.lease_expires_at, new Date((NOW + 360) * 1000).toISOString());
  assert.equal(value.validation_expires_at, expiry);
  assert.deepEqual(value.lease_token, f.prepared.lease_token);
  assert.deepEqual(rows(), original);
  assert.equal(f.renewCount(), 1);
  f.state.now = (NOW + 300) * 1000;
  for (const route of ['status', 'renew']) {
    assert.equal((await f.api.fetch(f.request(route, {}, token({ iat: NOW + 300, exp: NOW + 600 })))).status, 409);
  }
  assert.equal(f.renewCount(), 1);
});

test('fresh JWT cannot revive original dispatch identity deadline before lease expiry', async (t) => {
  const f = await controlFixture(t, token({ exp: NOW + 90 }));
  f.state.now = (NOW + 91) * 1000;
  for (const route of ['status', 'renew']) {
    assert.equal((await f.api.fetch(f.request(route, {}, token({ iat: NOW + 90, exp: NOW + 600 })))).status, 409);
  }
  assert.equal(f.renewCount(), 0);
});

test('control routes bind original actor Job epoch fence and dispatch and accept no extra controls', async (t) => {
  const f = await controlFixture(t);
  const before = f.leaseRow();
  for (const route of ['status', 'renew']) {
    for (const patch of [{ actor_id: '999' }, { run_id: '457' }, { run_attempt: '2' }, { sha: 'c'.repeat(40) }]) {
      assert.notEqual((await f.api.fetch(f.request(route, {}, token(patch)))).status, 200);
    }
    for (const patch of [{ dispatch_id: '22222222-2222-4222-8222-222222222222' },
      { lease_token: { ...f.leaseToken, fence: f.leaseToken.fence + 1 } },
      { lease_token: { ...f.leaseToken, epoch: '22222222-2222-4222-8222-222222222222' } },
      { lease_token: { ...f.leaseToken, fence: true } }, { result_base64: '' }, { ttl: 600 }, { valid: true }]) {
      assert.notEqual((await f.api.fetch(f.request(route, patch))).status, 200);
    }
    assert.equal((await f.api.fetch(f.request(route + '?retry=true'))).status, 404);
  }
  assert.deepEqual(f.leaseRow(), before);
  assert.equal(f.renewCount(), 0);
});

test('control refuses missing input and state changes during original input readback', async (t) => {
  for (const failure of ['missing', 'head', 'owner']) {
    const f = await controlFixture(t);
    const dispatch = JSON.parse(f.db.prepare('SELECT dispatch_json FROM m12_authorization_dispatches').get().dispatch_json);
    if (failure === 'missing') f.objects.delete(dispatch.input_archive.key);
    else f.archiveState.beforeGet = (key) => {
      if (key !== dispatch.input_archive.key) return;
      if (failure === 'head') f.db.exec('UPDATE m12_authorization_head SET revision=revision+1');
      else f.lease.release('publish/global', f.job, f.leaseToken);
    };
    assert.equal((await f.api.fetch(f.request('renew'))).status, 409);
    assert.equal(f.renewCount(), 0);
  }
});

test('failure or deadline crossing after renew mutation rolls back lease and renewal log', async (t) => {
  for (const failure of ['sql', 'deadline']) {
    const f = await controlFixture(t);
    f.state.now += 60_000;
    const before = f.leaseRow();
    const exec = f.storage.sql.exec;
    let reached = false;
    f.storage.sql.exec = (query, ...args) => {
      const result = exec(query, ...args);
      if (query.includes('INSERT INTO m12_lease_log') && args[1] === 'renew') {
        reached = true;
        if (failure === 'sql') throw new Error('simulated failure after log insertion');
        f.state.now = (NOW + 300) * 1000;
      }
      return result;
    };
    assert.equal((await f.api.fetch(f.request('renew'))).status, 409);
    assert.equal(reached, true);
    assert.deepEqual(f.leaseRow(), before);
    assert.equal(f.renewCount(), 0);
  }
});

test('status after artifact return does not infer receipt or authorization registration', async (t) => {
  const f = await controlFixture(t);
  const python = validateWire(Buffer.from(f.prepared.input_base64, 'base64'));
  const raw = Buffer.from(JSON.stringify(canonical({ authorization_base64: python.authorization_bytes, receipt_base64: python.receipt_bytes })) + '\n');
  const returned = await f.api.fetch(f.request('return', { result_base64: raw.toString('base64') }));
  assert.equal((await returned.json()).state, 'archived_pending_registration');
  const status = await (await f.api.fetch(f.request('status'))).json();
  assert.equal(status.state, 'dispatch_current');
  assert.equal('authorization_archive' in status, false);
  assert.equal('validation_receipt_archive' in status, false);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM m12_authorization_index').get().n, 1);
});

test('fixed cancellable process produces the sole validator bytes accepted by return archival', async (t) => {
  const f = await validationArchiveFixture(t);
  const script = `
import base64,runpy,subprocess,sys,time
from unittest.mock import patch
from services.publication.authorization_process import AuthorizationValidationProcess
real=subprocess.Popen
# Test-only clock harness: actual fixed worker script and sole validator run.
def launch(command,**options):
    assert command[0]==sys.executable and command[1]=='-I'
    assert command[2].endswith('/services/publication/authorization_validation_worker.py')
    harness="import runpy,time;time.time_ns=lambda:${NOW * 1000}*1000000;runpy.run_path("+repr(command[2])+",run_name='__main__')"
    return real([command[0],'-I','-c',harness],**options)
with patch('subprocess.Popen',side_effect=launch):
    with AuthorizationValidationProcess(sys.stdin.buffer.read()) as child:
        end=time.monotonic()+5
        while time.monotonic()<end:
            value=child.poll()
            if value is not None:
                print(base64.b64encode(value).decode('ascii'))
                break
            time.sleep(0.005)
        else: raise AssertionError('validation did not complete')
`;
  const executed = spawnSync('python3', ['-c', script], { cwd: new URL('..', import.meta.url),
    input: f.sent.input_bytes, maxBuffer: 4 * 1024 * 1024, timeout: 10_000 });
  assert.equal(executed.status, 0, executed.stderr?.toString());
  const raw = Buffer.from(executed.stdout.toString().trim(), 'base64');
  assert.deepEqual(raw, f.resultBytes());
  const archived = await f.archiveValidation(token(), raw);
  assert.equal(Buffer.from(archived.authorization_bytes).toString('base64'), f.python.authorization_bytes);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM m12_authorization_index').get().n, 1);
});

test('supervisor renews during fixed validation and returns through actual local job routes', { timeout: 15_000 }, async (t) => {
  const f = apiFixture(t);
  const script = `
import base64,io,json,subprocess,sys
from email.message import Message
from unittest.mock import patch
from services.publication import authorization_supervision as supervisor
from services.publication.authorization_transport import AuthorizationHttpsTransport
class Response(io.BytesIO):
    def __init__(self,value,url):
        super().__init__(base64.b64decode(value['body']))
        self.status=value['status'];self.url=url;self.headers=Message()
        for k,v in value['headers'].items():self.headers[k]=v
    def geturl(self):return self.url
class Opener:
    def open(self,request,timeout):
        print(json.dumps({'url':request.full_url,'headers':dict(request.header_items()),'body':base64.b64encode(request.data).decode() if request.data else None}),flush=True)
        return Response(json.loads(sys.stdin.readline()),request.full_url)
real=subprocess.Popen
def launch(command,**options):
    assert command[1]=='-I' and command[2].endswith('/authorization_validation_worker.py')
    harness="import runpy,time;time.sleep(0.2);time.time_ns=lambda:${NOW * 1000}*1000000;runpy.run_path("+repr(command[2])+",run_name='__main__')"
    return real([command[0],'-I','-c',harness],**options)
transport=AuthorizationHttpsTransport('https://coordinator.example.test',{'GITHUB_ACTIONS':'true','ACTIONS_ID_TOKEN_REQUEST_URL':'https://run.actions.githubusercontent.com/token?api-version=2.0','ACTIONS_ID_TOKEN_REQUEST_TOKEN':'local-request-credential'},opener=Opener())
with patch('time.time_ns',return_value=${NOW * 1000}*1000000),patch('subprocess.Popen',side_effect=launch),patch.object(supervisor,'HEARTBEAT_SECONDS',0.04),patch.object(supervisor,'CONTROL_WAIT_SECONDS',2),patch.object(supervisor,'POLL_SECONDS',0.005):
    result=supervisor.execute_supervised_authorization_validation(transport)
print(json.dumps({'finished':True,'response':base64.b64encode(result).decode()}),flush=True)
`;
  const child = spawn('python3', ['-u', '-c', script], { cwd: new URL('..', import.meta.url), stdio: ['pipe', 'pipe', 'pipe'] });
  t.after(() => { if (child.exitCode === null) child.kill(); });
  let stderr = '', finished;
  child.stderr.on('data', (data) => { stderr += data; });
  const exited = new Promise((resolve, reject) => { child.on('error', reject); child.on('exit', resolve); });
  const paths = [];
  for await (const line of createInterface({ input: child.stdout })) {
    const request = JSON.parse(line);
    if (request.finished) { finished = JSON.parse(Buffer.from(request.response, 'base64')); child.stdin.end(); continue; }
    const url = new URL(request.url);
    let response;
    if (url.hostname.endsWith('.actions.githubusercontent.com')) {
      response = new Response(JSON.stringify({ value: token() }), { headers: { 'Content-Type': 'application/json' } });
    } else {
      paths.push(url.pathname);
      response = await f.api.fetch(new Request(request.url, { method: 'POST', headers: request.headers, body: Buffer.from(request.body, 'base64') }));
    }
    child.stdin.write(JSON.stringify({ status: response.status, headers: Object.fromEntries(response.headers),
      body: Buffer.from(await response.arrayBuffer()).toString('base64') }) + '\n');
  }
  assert.equal(await exited, 0, stderr);
  assert.deepEqual(paths.slice(0, 2), ['/v1/authorization/prepare', '/v1/authorization/status']);
  assert.ok(paths.includes('/v1/authorization/renew'));
  assert.deepEqual(paths.slice(-2), ['/v1/authorization/status', '/v1/authorization/return']);
  assert.equal(finished.state, 'archived_pending_registration');
  assert.ok(f.objects.has(finished.authorization_archive.key));
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM m12_authorization_index').get().n, 1);
});

const recordedReturns = (f) => f.db.prepare('SELECT * FROM m12_authorization_returns ORDER BY receipt_key').all();
const recordedReturnLogs = (f) => f.db.prepare("SELECT * FROM m12_authorization_log WHERE operation='archive_validation'").all();

test('return record follows final readbacks and replay across adapter reopen retains original record', async (t) => {
  const f = await validationArchiveFixture(t);
  let checked = 0;
  f.archiveState.beforeGet = (key) => {
    if (key === f.authorizationKey || key === f.receiptKey) {
      assert.equal(recordedReturns(f).length, 0);
      checked++;
    }
  };
  const first = await f.archiveValidation();
  assert.equal(checked, 4);
  const rows = recordedReturns(f), logs = recordedReturnLogs(f);
  assert.equal(rows.length, 1);
  assert.equal(logs.length, 1);
  assert.equal(rows[0].record_json, logs[0].record_json);
  const record = JSON.parse(rows[0].record_json);
  assert.deepEqual(first.return_record, record);
  assert.equal(record.state, 'archived_pending_registration');
  assert.equal(record.dispatch_id, f.sent.dispatch.dispatch_id);
  assert.deepEqual(record.authorization_archive, first.authorization_archive);
  assert.deepEqual(record.validation_receipt_archive, first.validation_receipt_archive);
  assert.deepEqual(record.input_archive, f.sent.dispatch.input_archive);
  assert.equal(record.actor_id, claims.actor_id);
  first.return_record.authorization_archive.size_bytes++;
  f.archiveState.beforeGet = null;
  f.state.now += 1000;
  const reopened = new AuthorizationValidationArchive(identityPolicy, { ...f.options, storage: f.storage, bucket: f.bucket });
  const replay = await reopened.archive(token(), f.leaseToken, f.sent.dispatch.dispatch_id, f.resultBytes());
  assert.deepEqual(replay.return_record, record);
  assert.deepEqual(recordedReturns(f), rows);
  assert.deepEqual(recordedReturnLogs(f), logs);
  assert.equal(f.db.prepare('SELECT revision FROM m12_authorization_head').get().revision, 1);
});

test('return record row or log write failure rolls back paired state while preserving archive bytes', async (t) => {
  for (const operation of ['row', 'log']) {
    const f = await validationArchiveFixture(t);
    const exec = f.storage.sql.exec;
    f.storage.sql.exec = (query, ...args) => {
      const result = exec(query, ...args);
      if ((operation === 'row' && query.startsWith('INSERT INTO m12_authorization_returns')) ||
          (operation === 'log' && query.includes("VALUES ('archive_validation'"))) throw new Error('return_record_write_failed');
      return result;
    };
    await assert.rejects(f.archiveValidation(), /return_record_write_failed/);
    assert.equal(recordedReturns(f).length, 0);
    assert.equal(recordedReturnLogs(f).length, 0);
    const authorization = new Uint8Array(f.objects.get(f.authorizationKey));
    const receipt = new Uint8Array(f.objects.get(f.receiptKey));
    f.storage.sql.exec = exec;
    await f.archiveValidation();
    assert.equal(recordedReturns(f).length, 1);
    assert.equal(recordedReturnLogs(f).length, 1);
    assert.deepEqual(f.objects.get(f.authorizationKey), authorization);
    assert.deepEqual(f.objects.get(f.receiptKey), receipt);
  }
});

test('state changes after return log insertion prevent commit and roll back the record', async (t) => {
  for (const change of ['head', 'lease', 'epoch', 'expiry']) {
    const f = await validationArchiveFixture(t);
    const exec = f.storage.sql.exec;
    let reached = false;
    f.storage.sql.exec = (query, ...args) => {
      const result = exec(query, ...args);
      if (query.includes("VALUES ('archive_validation'")) {
        reached = true;
        if (change === 'head') f.db.exec('UPDATE m12_authorization_head SET revision=revision+1');
        if (change === 'lease') f.lease.release('publish/global', f.job, f.leaseToken);
        if (change === 'epoch') f.db.exec("UPDATE m12_lease_epoch SET epoch='22222222-2222-4222-8222-222222222222'");
        if (change === 'expiry') f.state.now = (NOW + 300) * 1000;
      }
      return result;
    };
    await assert.rejects(f.archiveValidation());
    assert.equal(reached, true);
    assert.equal(recordedReturns(f).length, 0);
    assert.equal(recordedReturnLogs(f).length, 0);
    assert.equal(f.db.prepare('SELECT revision FROM m12_authorization_head').get().revision, 1);
    assert.ok(f.objects.has(f.authorizationKey));
    assert.ok(f.objects.has(f.receiptKey));
  }
});

test('partial loss of a return row or log is rejected without recreating evidence', async (t) => {
  for (const table of ['m12_authorization_returns', 'm12_authorization_log']) {
    const f = await validationArchiveFixture(t);
    await f.archiveValidation();
    f.db.exec(table.endsWith('_log') ? "DELETE FROM m12_authorization_log WHERE operation='archive_validation'" : 'DELETE FROM m12_authorization_returns');
    const rows = recordedReturns(f), logs = recordedReturnLogs(f);
    await assert.rejects(f.archiveValidation(), /recovery_required/);
    assert.deepEqual(recordedReturns(f), rows);
    assert.deepEqual(recordedReturnLogs(f), logs);
  }
});

test('conflicting return record is preserved and cannot be silently rewritten on replay', async (t) => {
  const f = await validationArchiveFixture(t);
  await f.archiveValidation();
  const record = JSON.parse(recordedReturns(f)[0].record_json);
  record.authorization_archive.size_bytes++;
  const raw = JSON.stringify(record);
  f.db.prepare('UPDATE m12_authorization_returns SET record_json=?').run(raw);
  f.db.prepare("UPDATE m12_authorization_log SET record_json=? WHERE operation='archive_validation'").run(raw);
  await assert.rejects(f.archiveValidation(), /record_conflict/);
  assert.equal(recordedReturns(f)[0].record_json, raw);
  assert.equal(recordedReturnLogs(f)[0].record_json, raw);
});

test('surviving return record prevents silent empty-head initialization after partial loss', async (t) => {
  const f = await validationArchiveFixture(t);
  await f.archiveValidation();
  f.db.exec('DELETE FROM m12_authorization_head; DELETE FROM m12_authorization_index; DELETE FROM m12_authorization_tickets; DELETE FROM m12_authorization_dispatches; DELETE FROM m12_authorization_log');
  new AuthorizationValidationArchive(identityPolicy, { ...f.options, storage: f.storage, bucket: f.bucket });
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM m12_authorization_head').get().n, 0);
  assert.equal(recordedReturns(f).length, 1);
});

function recoveryReader(f, patch = {}) {
  return new AuthorizationValidationReturn(identityPolicy, { ...f.options, storage: f.storage, bucket: f.bucket,
    recoveryEpoch: f.leaseToken.epoch, ...patch });
}
const freshRecoveryToken = () => token({ iat: NOW + 301, nbf: NOW + 301, exp: NOW + 601 });

test('recovery reads expired historical return after lease takeover without reviving authority', async (t) => {
  const f = await validationArchiveFixture(t);
  const archived = await f.archiveValidation();
  f.state.now = (NOW + 301) * 1000;
  f.lease.acquire('publish/global', { ...f.job, run_id: '457' }, f.leaseToken.epoch);
  const leases = f.db.prepare('SELECT * FROM m12_leases').all(), logs = f.db.prepare('SELECT * FROM m12_authorization_log').all();
  const puts = f.archiveState.puts;
  const result = await recoveryReader(f).recover(freshRecoveryToken(), f.sent.dispatch.dispatch_id, f.receiptKey);
  assert.deepEqual(result.return_record, archived.return_record);
  assert.deepEqual(result.authorization_bytes, archived.authorization_bytes);
  assert.deepEqual(result.receipt_bytes, archived.receipt_bytes);
  assert.equal(result.current_history.revision, 1);
  assert.deepEqual(f.db.prepare('SELECT * FROM m12_leases').all(), leases);
  assert.deepEqual(f.db.prepare('SELECT * FROM m12_authorization_log').all(), logs);
  assert.equal(f.archiveState.puts, puts);
  result.return_record.actor_id = 'changed';
  assert.equal((await recoveryReader(f).recover(freshRecoveryToken(), f.sent.dispatch.dispatch_id, f.receiptKey)).return_record.actor_id, claims.actor_id);
});

test('recovery permits a later intact authority head without making historical return current permission', async (t) => {
  const f = await registrationFixture(t);
  const registered = await f.register();
  const result = await recoveryReader(f).recover(token(), f.sent.dispatch.dispatch_id, f.receiptKey);
  assert.equal(result.current_history.revision, 2);
  assert.equal(result.validation_ticket.expected_revision, 1);
  assert.deepEqual(result.return_record, registered.return_record);
});

test('recovery requires configured epoch fresh original identity and exact receipt selection', async (t) => {
  const f = await validationArchiveFixture(t);
  await f.archiveValidation();
  const gets = f.archiveState.gets;
  const disabled = recoveryReader(f, { recoveryEpoch: undefined });
  await assert.rejects(disabled.recover(token(), f.sent.dispatch.dispatch_id, f.receiptKey), /not_configured/);
  for (const jwt of ['unsigned', token({ actor_id: '999' }), token({ run_id: '457' }), token({ run_attempt: '2' }), token({ sha: 'c'.repeat(40) })]) {
    await assert.rejects(recoveryReader(f).recover(jwt, f.sent.dispatch.dispatch_id, f.receiptKey));
  }
  await assert.rejects(recoveryReader(f, { recoveryEpoch: '22222222-2222-4222-8222-222222222222' }).recover(token(), f.sent.dispatch.dispatch_id, f.receiptKey));
  await assert.rejects(recoveryReader(f).recover(token(), f.sent.dispatch.dispatch_id, 'raw/' + '0'.repeat(64)), /unavailable/);
  assert.equal(f.archiveState.gets, gets);
  f.state.now = (NOW + 301) * 1000;
  await assert.rejects(recoveryReader(f).recover(token(), f.sent.dispatch.dispatch_id, f.receiptKey), /time_invalid/);
});

test('recovery rejects missing row or paired logs without inferring safe replay', async (t) => {
  for (const target of ['return', 'return_log', 'dispatch_log', 'ticket_log']) {
    const f = await validationArchiveFixture(t);
    await f.archiveValidation();
    if (target === 'return') f.db.exec('DELETE FROM m12_authorization_returns');
    else {
      const operation = { return_log: 'archive_validation', dispatch_log: 'dispatch_validation', ticket_log: 'prepare_validation' }[target];
      f.db.prepare('DELETE FROM m12_authorization_log WHERE operation=?').run(operation);
    }
    const records = recordedReturns(f), logs = recordedReturnLogs(f), puts = f.archiveState.puts;
    await assert.rejects(recoveryReader(f).recover(token(), f.sent.dispatch.dispatch_id, f.receiptKey));
    assert.deepEqual(recordedReturns(f), records);
    assert.deepEqual(recordedReturnLogs(f), logs);
    assert.equal(f.archiveState.puts, puts);
  }
});

test('recovery actually reads input authorization and receipt and fails on missing or corrupt originals', async (t) => {
  for (const role of ['input', 'authorization', 'receipt']) for (const corrupt of [false, true]) {
    const f = await validationArchiveFixture(t);
    await f.archiveValidation();
    const key = role === 'input' ? f.sent.dispatch.input_archive.key : role === 'authorization' ? f.authorizationKey : f.receiptKey;
    if (corrupt) f.objects.get(key)[0] ^= 1;
    else f.objects.delete(key);
    const records = recordedReturns(f), puts = f.archiveState.puts;
    await assert.rejects(recoveryReader(f).recover(token(), f.sent.dispatch.dispatch_id, f.receiptKey), /missing|hash_mismatch/);
    assert.deepEqual(recordedReturns(f), records);
    assert.equal(f.archiveState.puts, puts);
  }
});

test('recovery fails if record epoch head or fresh identity changes during final original read', async (t) => {
  for (const change of ['record', 'epoch', 'head', 'identity']) {
    const f = await validationArchiveFixture(t);
    await f.archiveValidation();
    f.archiveState.beforeGet = (key) => {
      if (key !== f.receiptKey) return;
      if (change === 'record') f.db.exec('DELETE FROM m12_authorization_returns');
      if (change === 'epoch') f.db.exec("UPDATE m12_lease_epoch SET epoch='22222222-2222-4222-8222-222222222222'");
      if (change === 'head') f.db.exec('UPDATE m12_authorization_head SET revision=2');
      if (change === 'identity') f.state.now = (NOW + 300) * 1000;
    };
    await assert.rejects(recoveryReader(f).recover(token(), f.sent.dispatch.dispatch_id, f.receiptKey));
  }
});

test('recovery selects each legitimate validation receipt rather than an arbitrary latest result', async (t) => {
  const f = await validationArchiveFixture(t);
  const first = await f.archiveValidation();
  f.state.now = (NOW + 2) * 1000;
  const later = validateWire(f.sent.input_bytes, [(NOW + 1) * 1000, (NOW + 2) * 1000]);
  f.result.authorization_base64 = later.authorization_bytes;
  f.result.receipt_base64 = later.receipt_bytes;
  const second = await f.archiveValidation();
  for (const expected of [first, second]) {
    const result = await recoveryReader(f).recover(token(), f.sent.dispatch.dispatch_id, expected.validation_receipt_archive.key);
    assert.deepEqual(result.return_record, expected.return_record);
    assert.deepEqual(result.receipt_bytes, expected.receipt_bytes);
  }
  assert.equal(recordedReturns(f).length, 2);
});

test('recovery reuses artifact relationship checks even when altered receipt hash and record agree', async (t) => {
  const f = await validationArchiveFixture(t);
  await f.archiveValidation();
  const receipt = JSON.parse(Buffer.from(f.objects.get(f.receiptKey)));
  receipt.ticket_id = '22222222-2222-4222-8222-222222222222';
  const bytes = Buffer.from(JSON.stringify(canonical(receipt))), hash = sha(bytes), key = 'raw/' + hash.slice(7);
  f.objects.set(key, new Uint8Array(bytes));
  const record = JSON.parse(recordedReturns(f)[0].record_json);
  record.validation_receipt_archive = { key, sha256: hash, size_bytes: bytes.length };
  const raw = JSON.stringify(record);
  f.db.prepare('UPDATE m12_authorization_returns SET receipt_key=?,record_json=?').run(key, raw);
  f.db.prepare("UPDATE m12_authorization_log SET record_json=? WHERE operation='archive_validation'").run(raw);
  await assert.rejects(recoveryReader(f).recover(token(), f.sent.dispatch.dispatch_id, key), /receipt_mismatch/);
});

test('recovery HTTP route returns only authenticated historical archive verification', async (t) => {
  const f = await validationArchiveFixture(t);
  const saved = await f.archiveValidation();
  const api = new AuthorizationJobApi(identityPolicy, reviewPolicy,
    { ...f.options, storage: f.storage, bucket: f.bucket, enabled: true, leaseEpoch: f.leaseToken.epoch });
  const payload = { protocol: 'm12-authorization-job/1', dispatch_id: f.sent.dispatch.dispatch_id, receipt_key: f.receiptKey };
  f.state.now = (NOW + 301) * 1000;
  const puts = f.archiveState.puts;
  const response = await api.fetch(apiRequest('recover', JSON.stringify(canonical(payload)), freshRecoveryToken()));
  assert.equal(response.status, 200);
  const value = await response.json();
  assert.deepEqual(Object.keys(value).sort(), ['authorization_archive', 'dispatch_id', 'input_sha256', 'protocol', 'recorded_at', 'state', 'validation_receipt_archive']);
  assert.equal(value.state, 'archived_return_verified');
  assert.deepEqual(value.authorization_archive, saved.authorization_archive);
  assert.equal(value.input_sha256, f.sent.dispatch.input_archive.sha256);
  assert.equal(f.archiveState.puts, puts);
  assert.equal(recordedReturns(f).length, 1);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM m12_authorization_index').get().n, 1);
});

test('recovery HTTP route stays disabled by default and rejects external epoch lease and missing evidence', async (t) => {
  const disabled = new AuthorizationJobApi(null, null);
  assert.equal((await disabled.fetch(apiRequest('recover'))).status, 503);
  const f = await validationArchiveFixture(t);
  await f.archiveValidation();
  const api = new AuthorizationJobApi(identityPolicy, reviewPolicy,
    { ...f.options, storage: f.storage, bucket: f.bucket, enabled: true, leaseEpoch: f.leaseToken.epoch });
  const payload = { protocol: 'm12-authorization-job/1', dispatch_id: f.sent.dispatch.dispatch_id, receipt_key: f.receiptKey };
  for (const patch of [{ epoch: f.leaseToken.epoch }, { lease_token: f.leaseToken }, { valid: true }, { receipt_key: '../private' }]) {
    assert.equal((await api.fetch(apiRequest('recover', JSON.stringify(canonical({ ...payload, ...patch }))))).status, 400);
  }
  assert.equal((await api.fetch(apiRequest('recover', JSON.stringify(canonical(payload)), token({ actor_id: '999' })))).status, 409);
  f.objects.delete(f.receiptKey);
  const missing = await api.fetch(apiRequest('recover', JSON.stringify(canonical(payload))));
  assert.equal(missing.status, 409);
  assert.deepEqual(Object.keys(await missing.json()).sort(), ['error', 'protocol']);
});

test('journaled supervised client recovers a lost return response with a new client and no resend', { timeout: 15_000 }, async (t) => {
  const f = apiFixture(t);
  const script = `
import base64,io,json,subprocess,sys,tempfile
from email.message import Message
from unittest.mock import patch
from services.publication.authorization_supervision import execute_supervised_authorization_validation,AuthorizationSupervisionError
from services.publication.authorization_recovery import RecoverableAuthorizationTransport
class Response(io.BytesIO):
    def __init__(self,value,url):
        super().__init__(base64.b64decode(value['body']))
        self.status=value['status'];self.url=url;self.headers=Message()
        for k,v in value['headers'].items():self.headers[k]=v
    def geturl(self):return self.url
class Opener:
    def open(self,request,timeout):
        print(json.dumps({'url':request.full_url,'headers':dict(request.header_items()),'body':base64.b64encode(request.data).decode() if request.data else None}),flush=True)
        return Response(json.loads(sys.stdin.readline()),request.full_url)
real=subprocess.Popen
def launch(command,**options):
    assert command[1]=='-I' and command[2].endswith('/authorization_validation_worker.py')
    harness="import runpy,time;time.time_ns=lambda:${NOW * 1000}*1000000;runpy.run_path("+repr(command[2])+",run_name='__main__')"
    return real([command[0],'-I','-c',harness],**options)
env={'GITHUB_ACTIONS':'true','ACTIONS_ID_TOKEN_REQUEST_URL':'https://run.actions.githubusercontent.com/token?api-version=2.0','ACTIONS_ID_TOKEN_REQUEST_TOKEN':'local-request-credential'}
with tempfile.TemporaryDirectory(prefix='m12-rpc-recovery-') as directory:
    transport=RecoverableAuthorizationTransport('https://coordinator.example.test',env,recovery_directory=directory,opener=Opener())
    with patch('time.time_ns',return_value=${NOW * 1000}*1000000),patch('subprocess.Popen',side_effect=launch):
        try:execute_supervised_authorization_validation(transport)
        except AuthorizationSupervisionError:pass
        else:raise AssertionError('expected lost return response')
    assert transport.recovery_id
    recovered=RecoverableAuthorizationTransport('https://coordinator.example.test',env,recovery_directory=directory,opener=Opener())
    result=recovered.recover(transport.recovery_id)
print(json.dumps({'finished':True,'response':base64.b64encode(result).decode()}),flush=True)
`;
  const child = spawn('python3', ['-u', '-c', script], { cwd: new URL('..', import.meta.url), stdio: ['pipe', 'pipe', 'pipe'] });
  t.after(() => { if (child.exitCode === null) child.kill(); });
  let stderr = '', finished, lost = false;
  child.stderr.on('data', (data) => { stderr += data; });
  const exited = new Promise((resolve, reject) => { child.on('error', reject); child.on('exit', resolve); });
  const paths = [];
  for await (const line of createInterface({ input: child.stdout })) {
    const request = JSON.parse(line);
    if (request.finished) { finished = JSON.parse(Buffer.from(request.response, 'base64')); child.stdin.end(); continue; }
    const url = new URL(request.url);
    let response;
    if (url.hostname.endsWith('.actions.githubusercontent.com')) {
      response = new Response(JSON.stringify({ value: lost ? freshRecoveryToken() : token() }), { headers: { 'Content-Type': 'application/json' } });
    } else {
      paths.push(url.pathname);
      response = await f.api.fetch(new Request(request.url, { method: 'POST', headers: request.headers, body: Buffer.from(request.body, 'base64') }));
      if (url.pathname.endsWith('/return')) {
        assert.equal(response.status, 200, await response.clone().text());
        assert.equal(recordedReturns(f).length, 1);
        lost = true;
        f.state.now = (NOW + 301) * 1000;
        f.lease.acquire('publish/global', { ...f.job, run_id: '457' }, f.leaseToken.epoch);
        response = new Response('{}', { status: 503, headers: { 'Content-Type': 'application/json' } });
      }
    }
    child.stdin.write(JSON.stringify({ status: response.status, headers: Object.fromEntries(response.headers),
      body: Buffer.from(await response.arrayBuffer()).toString('base64') }) + '\n');
  }
  assert.equal(await exited, 0, stderr);
  assert.equal(paths.filter((path) => path.endsWith('/return')).length, 1);
  assert.equal(paths.filter((path) => path.endsWith('/prepare')).length, 1);
  assert.equal(paths.at(-1), '/v1/authorization/recover');
  assert.equal(finished.state, 'archived_return_verified');
  assert.equal(recordedReturns(f).length, 1);
  assert.equal(f.db.prepare('SELECT COUNT(*) AS n FROM m12_authorization_index').get().n, 1);
  assert.equal(JSON.parse(f.db.prepare("SELECT owner_json FROM m12_leases WHERE resource='publish/global'").get().owner_json).run_id, '457');
});
