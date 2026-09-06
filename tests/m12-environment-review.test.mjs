import test from "node:test";
import assert from "node:assert/strict";
import { createHash, generateKeyPairSync, sign } from "node:crypto";
import { spawnSync } from "node:child_process";
import { DatabaseSync } from "node:sqlite";
import { GitHubEnvironmentReviewVerifier } from "../services/publication/environment_review.mjs";
import { ReviewedRequestArchive } from "../services/publication/review_archive.mjs";
import { AuthorizationPreparation } from "../services/publication/authorization_preparation.mjs";
import { AuthorizationValidationReturn } from "../services/publication/authorization_return.mjs";
import { AuthorizationValidationArchive } from "../services/publication/authorization_validation_archive.mjs";
import { LeaseStore } from "../services/publication/leases.mjs";

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
  const storage = { sql: { exec(query, ...args) {
    const rows = db.prepare(query).all(...args);
    return { toArray: () => rows.map((row) => ({ ...row })) };
  } }, transactionSync(callback) {
    db.exec("BEGIN IMMEDIATE");
    try { const result = callback(); assert.ok(!(result instanceof Promise)); db.exec("COMMIT"); return result; }
    catch (error) { db.exec("ROLLBACK"); throw error; }
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
  await assert.rejects(f.preparation.prepare(token(), f.leaseToken), /ticket_history_changed/);
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
    await assert.rejects(f.preparation.dispatchValidationInput(token(), f.leaseToken), /history_changed|not_owned/);
    assert.equal(dispatchCount(f), 0);
  }
});

test("identity expiration after archived input readback leaves no dispatch record", async (t) => {
  const f = preparationFixture(t);
  f.archiveState.beforeGet = (key) => { if (isValidationWire(f, key)) f.state.now = claims.exp * 1000; };
  await assert.rejects(f.preparation.dispatchValidationInput(token(), f.leaseToken), /dispatch_identity_expired/);
  assert.equal(dispatchCount(f), 0);
});

async function returnFixture(t) {
  const f = preparationFixture(t);
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

async function validationArchiveFixture(t) {
  const f = await returnFixture(t);
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
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_log").get().n, 2);
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
    const orphan = new Uint8Array(f.objects.get(key));
    assert.ok(orphan.length);
    assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, 1);
    f.archiveState.afterPut = null;
    await f.archiveValidation();
    assert.deepEqual(f.objects.get(key), orphan);
    assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_log").get().n, 2);
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
  assert.equal(f.db.prepare("SELECT COUNT(*) AS n FROM m12_authorization_index").get().n, 1);
});
