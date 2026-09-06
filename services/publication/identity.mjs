// Authentication only: no approval, lease, permission or production write here.
const ISSUER = "https://token.actions.githubusercontent.com";
const JWKS = ISSUER + "/.well-known/jwks";
const AUDIENCE = "sage-vista-publication";
const RSA = { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" };

function decode(segment) {
  if (!/^[A-Za-z0-9_-]+$/.test(segment) || segment.length % 4 === 1) throw new Error("oidc_encoding_invalid");
  const raw = atob(segment.replaceAll("-", "+").replaceAll("_", "/"));
  const encoded = btoa(raw).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
  if (encoded !== segment) throw new Error("oidc_encoding_invalid");
  return Uint8Array.from(raw, (char) => char.charCodeAt(0));
}

function object(segment) {
  const value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(decode(segment)));
  if (!value || Array.isArray(value) || typeof value !== "object") throw new Error("oidc_object_required");
  return value;
}

async function readKeys(response) {
  if (!response.ok || response.redirected || !response.body) throw new Error("oidc_keys_unavailable");
  const reader = response.body.getReader();
  let total = 0;
  const chunks = [];
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > 262_144) { await reader.cancel(); throw new Error("oidc_keys_too_large"); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const buffer = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { buffer.set(chunk, offset); offset += chunk.byteLength; }
  const document = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(buffer));
  if (!document || !Array.isArray(document.keys)) throw new Error("oidc_keys_invalid");
  return document.keys;
}

export class GitHubIdentityVerifier {
  #policy;
  #fetch;
  #clock;

  // Policy and dependencies are server-controlled, never request parameters.
  constructor(policy, { fetchKeys = fetch, clock = Date.now } = {}) {
    const fields = ["code_commit", "environment", "repository", "repository_id", "subject", "workflow_commit", "workflow_ref"];
    if (!policy || Object.keys(policy).sort().join() !== fields.join() ||
        fields.some((field) => typeof policy[field] !== "string" || !policy[field].trim()) ||
        !/^[1-9][0-9]*$/.test(policy.repository_id) ||
        !/^[a-f0-9]{40}$/.test(policy.code_commit) || !/^[a-f0-9]{40}$/.test(policy.workflow_commit) ||
        !policy.workflow_ref.startsWith(policy.repository + "/.github/workflows/") ||
        !policy.workflow_ref.endsWith("@refs/heads/main") ||
        typeof fetchKeys !== "function" || typeof clock !== "function") throw new Error("oidc_policy_invalid");
    this.#policy = Object.freeze({ ...policy });
    this.#fetch = fetchKeys;
    this.#clock = clock;
  }

  async verify(token) {
    if (typeof token !== "string" || token.length > 65_536) throw new Error("oidc_token_invalid");
    const parts = token.split(".");
    if (parts.length !== 3) throw new Error("oidc_token_invalid");
    const header = object(parts[0]);
    if (header.alg !== "RS256" || header.typ !== "JWT" || typeof header.kid !== "string" || !header.kid ||
        Object.keys(header).some((key) => !["alg", "typ", "kid", "x5t"].includes(key))) {
      throw new Error("oidc_header_invalid");
    }
    const claims = object(parts[1]);
    const signature = decode(parts[2]);
    // No URL from the JWT is followed; no stale-key fallback on an outage.
    const response = await this.#fetch(JWKS, { redirect: "error", cache: "no-store",
      signal: AbortSignal.timeout(10_000) });
    const keys = (await readKeys(response)).filter((key) => key?.kid === header.kid);
    if (keys.length !== 1) throw new Error("oidc_key_not_unique");
    const jwk = keys[0];
    if (jwk.kty !== "RSA" || jwk.alg !== "RS256" || jwk.use !== "sig" || "d" in jwk) {
      throw new Error("oidc_key_invalid");
    }
    const publicKey = await crypto.subtle.importKey("jwk", jwk, RSA, false, ["verify"]);
    if (publicKey.algorithm.modulusLength < 2048) throw new Error("oidc_key_too_small");
    if (!await crypto.subtle.verify(RSA, publicKey, signature, new TextEncoder().encode(parts[0] + "." + parts[1]))) {
      throw new Error("oidc_signature_invalid");
    }
    // Check time after key retrieval and signature verification, not before I/O.
    const clockMs = this.#clock();
    if (!Number.isSafeInteger(clockMs) || clockMs < 0) throw new Error("oidc_clock_invalid");
    const now = Math.floor(clockMs / 1000);
    if (![claims.exp, claims.nbf, claims.iat].every(Number.isSafeInteger) ||
        claims.nbf < 0 || claims.iat < 0 || claims.exp <= now || claims.nbf > now || claims.iat > now ||
        claims.iat >= claims.exp || claims.nbf >= claims.exp) throw new Error("oidc_time_invalid");
    const pinned = { iss: ISSUER, aud: AUDIENCE, ref: "refs/heads/main", ref_type: "branch",
      repository: this.#policy.repository, repository_id: this.#policy.repository_id,
      workflow_ref: this.#policy.workflow_ref, workflow_sha: this.#policy.workflow_commit,
      sha: this.#policy.code_commit, environment: this.#policy.environment, sub: this.#policy.subject };
    if (Object.entries(pinned).some(([key, value]) => claims[key] !== value) ||
        "job_workflow_ref" in claims || "job_workflow_sha" in claims) throw new Error("oidc_identity_mismatch");
    for (const field of ["run_id", "run_attempt", "actor_id"]) {
      if (typeof claims[field] !== "string" || !/^[1-9][0-9]*$/.test(claims[field])) throw new Error("oidc_run_invalid");
    }
    const attempt = Number(claims.run_attempt);
    if (!Number.isSafeInteger(attempt) || typeof claims.jti !== "string" || !claims.jti.trim()) {
      throw new Error("oidc_run_invalid");
    }
    return {
      job: { repository_id: claims.repository_id, workflow_ref: claims.workflow_ref,
        workflow_commit: claims.workflow_sha, run_id: claims.run_id, run_attempt: attempt,
        environment: claims.environment },
      code_commit: claims.sha, actor_id: claims.actor_id, subject: claims.sub,
      token_id: claims.jti, issued_at: claims.iat, expires_at: claims.exp,
    };
  }
}
