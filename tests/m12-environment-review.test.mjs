import test from "node:test";
import assert from "node:assert/strict";
import { createHash, generateKeyPairSync, sign } from "node:crypto";
import { GitHubEnvironmentReviewVerifier } from "../services/publication/environment_review.mjs";

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
  return { ...f, bytes, blobSha, responses, gitCalls, hooks,
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
