import { GitHubIdentityVerifier } from "./identity.mjs";

function id(value) {
  if (!Number.isSafeInteger(value) || value < 1) throw new Error("review_id_invalid");
  return String(value);
}

async function document(response, url) {
  if (response.status !== 200 || response.redirected || !response.body || response.headers.get("link")) {
    throw new Error("review_api_unavailable_or_incomplete");
  }
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 1_048_576) { await reader.cancel(); throw new Error("review_response_too_large"); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  const value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  const sha256 = "sha256:" + Array.from(digest, (v) => v.toString(16).padStart(2, "0")).join("");
  return { value, evidence: { url, bytes, sha256, size_bytes: size } };
}

export class GitHubEnvironmentReviewVerifier {
  #identity;
  #policy;
  #fetch;
  #credential;
  #clock;

  // All configuration/dependencies are internal. verify accepts the signed token,
  // never an externally supplied "verified" Job, reviewer or API document.
  constructor(identityPolicy, reviewPolicy, { credential, fetchApi = fetch, fetchKeys = fetch, clock = Date.now } = {}) {
    this.#identity = new GitHubIdentityVerifier(identityPolicy, { fetchKeys, clock });
    if (!reviewPolicy || Object.keys(reviewPolicy).sort().join() !== "environment_id,reviewer_ids,workflow_id" ||
        !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(identityPolicy.repository) ||
        !Array.isArray(reviewPolicy.reviewer_ids) || !reviewPolicy.reviewer_ids.length ||
        new Set(reviewPolicy.reviewer_ids).size !== reviewPolicy.reviewer_ids.length ||
        [reviewPolicy.environment_id, reviewPolicy.workflow_id, ...reviewPolicy.reviewer_ids].some(
          (value) => typeof value !== "string" || !/^[1-9][0-9]*$/.test(value)) ||
        typeof credential !== "string" || !credential || /[\r\n]/.test(credential) || typeof fetchApi !== "function") {
      throw new Error("review_policy_invalid");
    }
    this.#policy = { ...identityPolicy, ...reviewPolicy, reviewer_ids: [...reviewPolicy.reviewer_ids].sort() };
    this.#fetch = fetchApi;
    this.#credential = credential;
    this.#clock = clock;
  }

  async #get(path) {
    const url = "https://api.github.com/repos/" + this.#policy.repository + path;
    const response = await this.#fetch(url, { method: "GET", redirect: "error", cache: "no-store",
      signal: AbortSignal.timeout(10_000), headers: { Accept: "application/vnd.github+json",
        Authorization: "Bearer " + this.#credential, "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "sage-vista-publication" } });
    return document(response, url);
  }

  #run(run, identity) {
    if (!run || id(run.id) !== identity.job.run_id || run.run_attempt !== 1 ||
        id(run.repository?.id) !== identity.job.repository_id || run.repository.full_name !== this.#policy.repository ||
        id(run.workflow_id) !== this.#policy.workflow_id || run.head_branch !== "main" ||
        run.head_sha !== identity.code_commit || run.event !== "workflow_dispatch" || run.status !== "in_progress" ||
        run.conclusion !== null || id(run.actor?.id) !== identity.actor_id ||
        run.actor.type !== "User" || run.triggering_actor?.type !== "User" ||
        id(run.triggering_actor.id) !== identity.actor_id) throw new Error("review_run_mismatch");
  }

  async verify(token) {
    const identity = await this.#identity.verify(token);
    // GitHub review history has no attempt identifier. Do not attach old run-level
    // approvals to a rerun; a new authorization review requires a fresh run_id.
    if (identity.job.run_attempt !== 1) throw new Error("review_attempt_unprovable");
    const runPath = "/actions/runs/" + identity.job.run_id;
    const before = await this.#get(runPath);
    this.#run(before.value, identity);
    const environment = await this.#get("/environments/" + encodeURIComponent(identity.job.environment));
    const env = environment.value;
    if (!env || id(env.id) !== this.#policy.environment_id || env.name !== identity.job.environment ||
        !Array.isArray(env.protection_rules)) throw new Error("review_environment_mismatch");
    const rules = env.protection_rules.filter((rule) => rule?.type === "required_reviewers");
    if (rules.length !== 1 || rules[0].prevent_self_review !== true || !Array.isArray(rules[0].reviewers)) {
      throw new Error("review_protection_missing");
    }
    const configured = rules[0].reviewers.map((entry) => {
      if (entry?.type !== "User" || entry.reviewer?.type !== "User") throw new Error("review_user_required");
      return id(entry.reviewer.id);
    }).sort();
    if (JSON.stringify(configured) !== JSON.stringify(this.#policy.reviewer_ids)) throw new Error("review_allowlist_mismatch");
    const history = await this.#get(runPath + "/approvals");
    if (!Array.isArray(history.value)) throw new Error("review_history_invalid");
    const relevant = history.value.filter((review) => {
      if (!review || !Array.isArray(review.environments)) throw new Error("review_history_invalid");
      const seen = new Set();
      const matches = review.environments.map((entry) => {
        const entryId = id(entry.id);
        if (seen.has(entryId)) throw new Error("review_history_invalid");
        seen.add(entryId);
        const sameId = entryId === this.#policy.environment_id;
        const sameName = entry.name === identity.job.environment;
        if (sameId !== sameName) throw new Error("review_environment_mismatch");
        return sameId;
      });
      return matches.includes(true);
    });
    if (relevant.length !== 1 || relevant[0].state !== "approved" || relevant[0].user?.type !== "User") {
      throw new Error("review_approval_not_unique");
    }
    const approver = id(relevant[0].user.id);
    if (!configured.includes(approver) || approver === identity.actor_id) throw new Error("review_approver_forbidden");
    const after = await this.#get(runPath);
    this.#run(after.value, identity);
    const now = this.#clock();
    if (!Number.isSafeInteger(now) || now < identity.issued_at * 1000 || now >= identity.expires_at * 1000) {
      throw new Error("review_identity_expired");
    }
    // These are observations to archive and bind to a registered request later.
    // No PublicationAuthorization, approval_evidence_ref or permission is minted.
    return { identity, approver_id: approver, environment_id: this.#policy.environment_id,
      observed_at: new Date(now).toISOString(),
      documents: [before, environment, history, after].map((item) => item.evidence) };
  }
}
