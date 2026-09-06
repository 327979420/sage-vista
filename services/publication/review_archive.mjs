import { ImmutableArchive } from "./archive.mjs";
import { GitHubEnvironmentReviewVerifier } from "./environment_review.mjs";

const ROLES = ["run_before_review", "environment", "review_history", "run_after_review",
  "source_commit", "source_root_tree", "source_config_tree", "request_blob", "run_after_source"];

// Encoding a byte-archive inventory, not a second business contract validator.
function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

async function digest(bytes) {
  const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return "sha256:" + Array.from(hash, (v) => v.toString(16).padStart(2, "0")).join("");
}

export class ReviewedRequestArchive {
  #verifier;
  #archive;
  #clock;

  constructor(identityPolicy, reviewPolicy, { bucket, clock = Date.now, ...dependencies } = {}) {
    this.#verifier = new GitHubEnvironmentReviewVerifier(identityPolicy, reviewPolicy, { ...dependencies, clock });
    this.#archive = new ImmutableArchive(bucket);
    this.#clock = clock;
  }

  #alive(observation) {
    const now = this.#clock();
    if (!Number.isSafeInteger(now) || now < Date.parse(observation.observed_at) ||
        now >= observation.review.identity.expires_at * 1000) throw new Error("review_archive_identity_expired");
  }

  async archive(token) {
    // There is deliberately no method accepting caller-provided verified JSON.
    const observation = await this.#verifier.verifyRequest(token);
    const { request, review } = observation;
    const originals = [...review.documents, ...observation.documents];
    if (originals.length !== ROLES.length) throw new Error("review_archive_inventory_incomplete");
    const saveRaw = async (original) => {
      this.#alive(observation);
      return this.#archive.put("raw/" + original.sha256.slice(7), original.bytes,
        { sha256: original.sha256, size_bytes: original.size_bytes });
    };
    const requestObject = await saveRaw(request);
    const documents = [];
    for (let i = 0; i < originals.length; i++) {
      const stored = await saveRaw(originals[i]);
      documents.push({ role: ROLES[i], url: originals[i].url, ...stored });
    }
    // All referenced raw objects have passed write-if-absent and byte readback.
    // An interrupted sequence may leave orphans; no authority index is updated.
    const bundle = {
      kind: "github_environment_approval_observation", version: 1,
      identity: review.identity, approver_id: review.approver_id, environment_id: review.environment_id,
      observed_at: observation.observed_at, review_observed_at: review.observed_at,
      request: { source_commit: request.source_commit, path: request.path, blob_sha: request.blob_sha, ...requestObject },
      documents,
    };
    const bytes = new TextEncoder().encode(JSON.stringify(canonical(bundle)));
    const fingerprint = await digest(bytes);
    this.#alive(observation);
    const archived = await this.#archive.put("authority/" + fingerprint.slice(7) + ".json", bytes,
      { sha256: fingerprint, size_bytes: bytes.length });
    this.#alive(observation);
    return {
      approval_evidence_ref: { id: "approval-observation:" + fingerprint, content_fingerprint: fingerprint },
      bundle: archived,
      request_source: { ...request, bytes: new Uint8Array(request.bytes) },
    };
  }

  async readForValidation(token) {
    // The expected reference comes only from this verifier's fresh internal
    // archive operation, never a caller-selected key or JSON "proof".
    const stored = await this.archive(token);
    const bundleBytes = await this.#archive.read(stored.bundle.key,
      { sha256: stored.bundle.sha256, size_bytes: stored.bundle.size_bytes });
    const bundle = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bundleBytes));
    const observation = { observed_at: bundle.observed_at, review: { identity: bundle.identity } };
    const descriptors = new Map();
    for (const item of [bundle.request, ...bundle.documents]) {
      const expected = { sha256: item.sha256, size_bytes: item.size_bytes };
      const previous = descriptors.get(item.key);
      if (previous && (previous.sha256 !== expected.sha256 || previous.size_bytes !== expected.size_bytes)) {
        throw new Error("review_archive_descriptor_conflict");
      }
      descriptors.set(item.key, expected);
    }
    const objects = {};
    for (const [key, expected] of descriptors) {
      this.#alive(observation);
      objects[key] = await this.#archive.read(key, expected);
    }
    this.#alive(observation);
    // Python consumes immutable bytes decoded by the future transport bridge,
    // and B2f is the sole validator of bundle roles and approval semantics.
    return { approval_evidence_ref: stored.approval_evidence_ref,
      approval_archive: { bundle_bytes: bundleBytes, objects } };
  }
}
