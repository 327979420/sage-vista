import { ImmutableArchive } from "./archive.mjs";
import { AuthorizationStore } from "./authorization_store.mjs";
import { GitHubIdentityVerifier } from "./identity.mjs";

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}
const encoding = (value) => JSON.stringify(canonical(value));
const same = (left, right) => encoding(left) === encoding(right);
const utf8 = (bytes) => new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);

function exact(value, fields) {
  if (!value || Array.isArray(value) || typeof value !== "object" || Object.keys(value).sort().join() !== fields.sort().join()) {
    throw new Error("authorization_return_fields_invalid");
  }
}

function encodedObject(bytes, newline = "") {
  const text = utf8(bytes);
  const value = JSON.parse(text);
  if (!value || Array.isArray(value) || typeof value !== "object" || encoding(value) + newline !== text) {
    throw new Error("authorization_return_encoding_invalid");
  }
  return value;
}

function unbase64(value) {
  if (typeof value !== "string") throw new Error("authorization_return_base64_invalid");
  const binary = atob(value);
  if (btoa(binary) !== value) throw new Error("authorization_return_base64_invalid");
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

async function digest(bytes) {
  const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return "sha256:" + Array.from(hash, (value) => value.toString(16).padStart(2, "0")).join("");
}

export class AuthorizationValidationReturn {
  #verifier;
  #store;
  #archive;
  #clock;
  #recoveryEpoch;

  constructor(identityPolicy, { storage, bucket, clock = Date.now, fetchKeys, recoveryEpoch } = {}) {
    if (recoveryEpoch !== undefined && (typeof recoveryEpoch !== "string" ||
        !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(recoveryEpoch))) throw new Error("authorization_recovery_epoch_invalid");
    this.#recoveryEpoch = recoveryEpoch;
    this.#verifier = new GitHubIdentityVerifier(identityPolicy, { clock, fetchKeys });
    this.#store = new AuthorizationStore(storage, { clock });
    this.#archive = new ImmutableArchive(bucket);
    this.#clock = clock;
  }

  async #readInput(identity, snapshot) {
    const { dispatch, validation_ticket: ticket } = snapshot;
    const inputBytes = await this.#archive.read(dispatch.input_archive.key,
      { sha256: dispatch.input_archive.sha256, size_bytes: dispatch.input_archive.size_bytes });
    const input = JSON.parse(utf8(inputBytes)); // Own read-verified B3d input, not caller JSON.
    if (dispatch.input_archive.key !== "raw/" + dispatch.input_archive.sha256.slice(7) ||
        input.protocol !== dispatch.protocol || !same(input.validation_ticket, ticket) ||
        !same(input.approval_evidence_ref, dispatch.approval_evidence_ref)) throw new Error("authorization_return_input_mismatch");
    const original = JSON.parse(utf8(unbase64(input.approval_archive.bundle_base64))).identity;
    if (original.actor_id !== identity.actor_id || original.code_commit !== identity.code_commit ||
        !same(original.job, dispatch.owner_job) || original.issued_at !== dispatch.identity_issued_at ||
        original.expires_at !== dispatch.identity_expires_at) throw new Error("authorization_return_origin_mismatch");

    return inputBytes;
  }

  async verifyDispatch(token, leaseToken, dispatchId) {
    const identity = await this.#verifier.verify(token);
    const snapshot = this.#store.readValidationDispatch(identity, leaseToken, dispatchId);
    const inputBytes = await this.#readInput(identity, snapshot);

    const current = this.#store.readValidationDispatch(identity, leaseToken, dispatchId);
    if (!same(current, snapshot)) throw new Error("authorization_return_dispatch_changed");
    return { identity, ...current, input_bytes: inputBytes };
  }

  async #verifyOutput(prepared, frozen) {
    const output = encodedObject(frozen, "\n");
    exact(output, ["authorization_base64", "receipt_base64"]);
    const receiptBytes = unbase64(output.receipt_base64), authorizationBytes = unbase64(output.authorization_base64);
    return this.#verifyArtifacts(prepared, receiptBytes, authorizationBytes);
  }

  async #verifyArtifacts(prepared, receiptBytes, authorizationBytes) {
    const { dispatch, validation_ticket: ticket } = prepared;
    const receipt = encodedObject(receiptBytes), authorization = encodedObject(authorizationBytes);
    exact(receipt, ["protocol", "verdict", "validated_at", "input_sha256", "input_size_bytes", "ticket_id", "ticket_sha256",
      "approval_evidence_ref", "authorization_ref", "authorization_archive"]);
    const [ticketHash, outputHash] = await Promise.all([
      digest(new TextEncoder().encode(encoding(ticket))), digest(authorizationBytes) ]);
    if (receipt.protocol !== dispatch.protocol || receipt.verdict !== "valid" || receipt.ticket_id !== dispatch.ticket_id ||
        receipt.ticket_sha256 !== dispatch.ticket_sha256 || ticketHash !== dispatch.ticket_sha256 ||
        receipt.input_sha256 !== dispatch.input_archive.sha256 || receipt.input_size_bytes !== dispatch.input_archive.size_bytes ||
        !same(receipt.approval_evidence_ref, dispatch.approval_evidence_ref)) throw new Error("authorization_return_receipt_mismatch");
    exact(receipt.authorization_ref, ["id", "content_fingerprint"]);
    exact(receipt.authorization_archive, ["key", "sha256", "size_bytes"]);
    const ref = receipt.authorization_ref, location = receipt.authorization_archive;
    if (typeof ref.content_fingerprint !== "string" || !/^sha256:[a-f0-9]{64}$/.test(ref.content_fingerprint) ||
        ref.id !== "publication-authorization:" + ref.content_fingerprint ||
        authorization.authorization_id !== ref.id || authorization.content_fingerprint !== ref.content_fingerprint ||
        !same(authorization.job, dispatch.owner_job) || !same(authorization.approval_evidence_ref, dispatch.approval_evidence_ref) ||
        !same(authorization.prior_authorization_ref, ticket.expected_head_ref) ||
        location.key !== "authority/" + ref.content_fingerprint.slice(7) + ".json" ||
        location.sha256 !== outputHash || location.size_bytes !== authorizationBytes.length) {
      throw new Error("authorization_return_output_mismatch");
    }
    const now = this.#clock(), validated = Date.parse(receipt.validated_at);
    if (!Number.isSafeInteger(now) || !Number.isFinite(validated) || new Date(validated).toISOString() !== receipt.validated_at ||
        validated < Date.parse(dispatch.dispatched_at) || validated >= Date.parse(dispatch.expires_at) || validated > now) {
      throw new Error("authorization_return_time_invalid");
    }
    return { receipt_bytes: receiptBytes, authorization_bytes: authorizationBytes };
  }

  async recover(token, dispatchId, receiptKey) {
    if (this.#recoveryEpoch === undefined) throw new Error("authorization_recovery_not_configured");
    const identity = await this.#verifier.verify(token);
    const snapshot = this.#store.readArchivedValidation(identity, this.#recoveryEpoch, dispatchId, receiptKey);
    const current = () => {
      const value = this.#store.readArchivedValidation(identity, this.#recoveryEpoch, dispatchId, receiptKey);
      if (!same(value, snapshot)) throw new Error("authorization_recovery_state_changed");
    };
    const inputBytes = await this.#readInput(identity, snapshot);
    current();
    const record = snapshot.return_record;
    const read = (location) => this.#archive.read(location.key, { sha256: location.sha256, size_bytes: location.size_bytes });
    const authorizationBytes = await read(record.authorization_archive);
    current();
    const receiptBytes = await read(record.validation_receipt_archive);
    current();
    const prepared = { identity, ...snapshot, input_bytes: inputBytes };
    const checked = await this.#verifyArtifacts(prepared, receiptBytes, authorizationBytes);
    const receipt = encodedObject(checked.receipt_bytes);
    if (!same(receipt.authorization_ref, record.authorization_ref) || !same(receipt.authorization_archive, record.authorization_archive) ||
        Date.parse(receipt.validated_at) > Date.parse(record.recorded_at)) throw new Error("authorization_recovery_artifacts_changed");
    current();
    // Historical readback only. No lease acquisition, validation rerun, artifact
    // write, ticket consumption or permission decision; clock bookkeeping only.
    return { ...prepared, ...checked };
  }

  async verify(token, leaseToken, dispatchId, resultBytes) {
    if (!(resultBytes instanceof Uint8Array)) throw new Error("authorization_return_bytes_required");
    const frozen = new Uint8Array(resultBytes);
    const prepared = await this.verifyDispatch(token, leaseToken, dispatchId);
    const { identity, dispatch, validation_ticket: ticket, input_bytes: inputBytes } = prepared;
    const snapshot = { dispatch, validation_ticket: ticket };

    const checked = await this.#verifyOutput(prepared, frozen);
    // No business reimplementation here: the pinned workflow must actually run
    // B3c on our exact dispatched bytes. OIDC alone is not execution attestation.
    const current = this.#store.readValidationDispatch(identity, leaseToken, dispatchId);
    if (!same(current, snapshot)) throw new Error("authorization_return_dispatch_changed");
    return { identity, ...current, input_bytes: inputBytes, ...checked };
  }
}
