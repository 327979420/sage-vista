import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import { GitHubIdentityVerifier } from "../services/publication/identity.mjs";

const NOW = 1_788_652_800;
const key = generateKeyPairSync("rsa", { modulusLength: 2048 });
const otherKey = generateKeyPairSync("rsa", { modulusLength: 2048 });
const jwk = { ...key.publicKey.export({ format: "jwk" }), kid: "test-key", alg: "RS256", use: "sig" };
const policy = {
  repository: "example/sage", repository_id: "123", workflow_ref: "example/sage/.github/workflows/publication.yml@refs/heads/main",
  workflow_commit: "a".repeat(40), code_commit: "b".repeat(40), environment: "production",
  subject: "repo:example/sage:environment:production",
};
const claims = {
  iss: "https://token.actions.githubusercontent.com", aud: "sage-vista-publication",
  sub: policy.subject, repository: policy.repository, repository_id: policy.repository_id,
  ref: "refs/heads/main", ref_type: "branch", workflow_ref: policy.workflow_ref,
  workflow_sha: policy.workflow_commit, sha: policy.code_commit, environment: policy.environment,
  run_id: "456", run_attempt: "2", actor_id: "789", jti: "unique-test-token", iat: NOW - 30,
  nbf: NOW - 30, exp: NOW + 300,
};
const encode = (value) => Buffer.from(JSON.stringify(value)).toString("base64url");
function token(body = claims, header = { alg: "RS256", typ: "JWT", kid: "test-key" }, privateKey = key.privateKey) {
  const input = encode(header) + "." + encode(body);
  return input + "." + sign("RSA-SHA256", Buffer.from(input), privateKey).toString("base64url");
}
const response = (keys = [jwk]) => new Response(JSON.stringify({ keys }), { headers: { "Content-Type": "application/json" } });
const verifier = (options = {}) => new GitHubIdentityVerifier(policy,
  { clock: () => NOW * 1000, fetchKeys: async () => response(), ...options });

test("valid RSA signature maps signed Job only, preserving large numeric-string run IDs", async () => {
  let calls = 0;
  const v = verifier({ fetchKeys: async (url, options) => {
    calls++;
    assert.equal(url, "https://token.actions.githubusercontent.com/.well-known/jwks");
    assert.equal(options.redirect, "error");
    assert.equal(options.cache, "no-store");
    assert.ok(options.signal instanceof AbortSignal);
    return response();
  } });
  const result = await v.verify(token({ ...claims, run_id: "900719925474099312345" }));
  assert.deepEqual(result, { job: { repository_id: "123", workflow_ref: policy.workflow_ref,
    workflow_commit: policy.workflow_commit, run_id: "900719925474099312345", run_attempt: 2,
    environment: "production" }, code_commit: policy.code_commit, actor_id: "789",
  subject: policy.subject, token_id: claims.jti, issued_at: claims.iat, expires_at: claims.exp });
  assert.equal(calls, 1);
  assert.equal("permissions" in result, false);
});

test("modified payload and signature signed by another key are rejected", async () => {
  const parts = token().split(".");
  parts[1] = encode({ ...claims, actor_id: "999" });
  await assert.rejects(verifier().verify(parts.join(".")), /signature_invalid/);
  await assert.rejects(verifier().verify(token(claims, undefined, otherKey.privateKey)), /signature_invalid/);
  parts[2] = Buffer.alloc(256).toString("base64url");
  await assert.rejects(verifier().verify(parts.join(".")), /signature_invalid/);
});

test("every pinned identity claim mismatch is rejected even with valid signature", async () => {
  for (const field of ["iss", "aud", "sub", "repository", "repository_id", "ref", "ref_type", "workflow_ref", "workflow_sha", "sha", "environment"]) {
    for (const replacement of [claims[field] + "x", null]) {
      await assert.rejects(verifier().verify(token({ ...claims, [field]: replacement })), /identity_mismatch/, field);
    }
  }
  await assert.rejects(verifier().verify(token({ ...claims, aud: [claims.aud] })), /identity_mismatch/);
});

test("algorithm confusion, embedded keys, remote URLs and critical header extensions fail before fetching", async () => {
  let calls = 0;
  const v = verifier({ fetchKeys: async () => { calls++; return response(); } });
  for (const header of [
    { alg: "none" }, { alg: "HS256" }, { alg: "PS256" }, { typ: "not-JWT" },
    { kid: "" }, { jku: "https://attacker.invalid/keys" }, { jwk },
    { x5u: "https://attacker.invalid/cert" }, { crit: ["b64"], b64: false },
  ]) {
    await assert.rejects(v.verify(token(claims, { alg: "RS256", typ: "JWT", kid: "test-key", ...header })), /header_invalid/);
  }
  assert.equal(calls, 0);
});

test("expiry, future issue/not-before and invalid time types fail closed", async () => {
  for (const patch of [{ exp: NOW }, { exp: NOW - 1 }, { nbf: NOW + 1 }, { iat: NOW + 1 },
    { exp: "9999999999" }, { nbf: false }, { iat: 1.5 }, { iat: -1 }, { nbf: -1 }]) {
    await assert.rejects(verifier().verify(token({ ...claims, ...patch })), /time_invalid/);
  }
  await verifier().verify(token({ ...claims, iat: NOW, nbf: NOW, exp: NOW + 1 }));
});

test("expiration is checked after awaited key retrieval", async () => {
  let now = NOW;
  const v = verifier({ clock: () => now * 1000, fetchKeys: async () => {
    now = claims.exp;
    return response();
  } });
  await assert.rejects(v.verify(token()), /time_invalid/);
});

test("run/attempt/actor encoding and reusable-workflow substitution are rejected", async () => {
  for (const patch of [{ run_id: 456 }, { run_id: "" }, { actor_id: "x" }, { run_attempt: "02" },
    { run_attempt: 2 }, { run_attempt: "9007199254740992" }, { jti: null }, { jti: " " }]) {
    await assert.rejects(verifier().verify(token({ ...claims, ...patch })), /run_invalid/);
  }
  for (const field of ["job_workflow_ref", "job_workflow_sha"]) {
    await assert.rejects(verifier().verify(token({ ...claims, [field]: "substituted" })), /identity_mismatch/);
  }
});

test("unknown and duplicate kid, wrong JWK purpose/algorithm and private key are rejected", async () => {
  for (const keys of [[], [{ ...jwk, kid: "other" }], [jwk, jwk]]) {
    await assert.rejects(verifier({ fetchKeys: async () => response(keys) }).verify(token()), /key_not_unique/);
  }
  for (const patch of [{ kty: "oct" }, { alg: "HS256" }, { use: "enc" }, { d: "private" }]) {
    await assert.rejects(verifier({ fetchKeys: async () => response([{ ...jwk, ...patch }]) }).verify(token()), /key_invalid/);
  }
});

test("signing key rotation fetches current keys, with no outage fallback", async () => {
  let keys = [jwk];
  let outage = false;
  const v = verifier({ fetchKeys: async () => {
    if (outage) throw new Error("jwks_network_unavailable");
    return response(keys);
  } });
  await v.verify(token());
  keys = [{ ...otherKey.publicKey.export({ format: "jwk" }), kid: "rotated", use: "sig", alg: "RS256" }];
  await v.verify(token(claims, { typ: "JWT", alg: "RS256", kid: "rotated" }, otherKey.privateKey));
  await assert.rejects(v.verify(token()), /key_not_unique/);
  outage = true;
  await assert.rejects(v.verify(token(claims, { typ: "JWT", alg: "RS256", kid: "rotated" }, otherKey.privateKey)), /network_unavailable/);
});

test("bad, oversized, redirected or unavailable key responses never authenticate", async () => {
  for (const make of [() => new Response("down", { status: 503 }),
    () => new Response("invalid JSON"), () => new Response("{}"),
    () => new Response(" ".repeat(262_145)), () => new Response(null, { status: 204 }),
    () => ({ ok: true, redirected: true })]) {
    await assert.rejects(verifier({ fetchKeys: async () => make() }).verify(token()));
  }
});

test("malformed JWT, base64 padding, noncanonical base64 and oversized token reject", async () => {
  for (const malformed of [null, "", "a.b", "a.b.c.d", token() + "=", "x".repeat(65_537),
    "e30=.e30.x", "_w.e30.abc", "Zh.e30.abc", encode([]) + ".e30.abc"]) {
    await assert.rejects(verifier().verify(malformed));
  }
});

test("server policy is fixed against caller mutation; unspecified policy cannot authenticate", async () => {
  const source = { ...policy };
  const v = new GitHubIdentityVerifier(source, { clock: () => NOW * 1000, fetchKeys: async () => response() });
  source.environment = "attacker";
  const result = await v.verify(token());
  result.job.repository_id = "attacker";
  assert.equal((await v.verify(token())).job.repository_id, policy.repository_id);
  for (const invalid of [null, {}, { ...policy, code_commit: "main" }, { ...policy, repository_id: 123 },
    { ...policy, workflow_ref: "foreign/workflow@refs/heads/main" }, { ...policy, extra: "ignored" }]) {
    assert.throws(() => new GitHubIdentityVerifier(invalid), /policy_invalid/);
  }
});

test("RSA keys under 2048 bits and invalid server clock are rejected", async () => {
  const weak = generateKeyPairSync("rsa", { modulusLength: 1024 });
  const weakJwk = { ...weak.publicKey.export({ format: "jwk" }), kid: jwk.kid, alg: "RS256", use: "sig" };
  await assert.rejects(verifier({ fetchKeys: async () => response([weakJwk]) }).verify(token(claims, undefined, weak.privateKey)), /key_too_small/);
  for (const time of [NaN, -1, 1.5, Infinity]) {
    await assert.rejects(verifier({ clock: () => time }).verify(token()), /clock_invalid/);
  }
});
