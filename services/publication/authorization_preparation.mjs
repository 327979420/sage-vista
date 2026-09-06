import { ImmutableArchive } from "./archive.mjs";
import { AuthorizationStore } from "./authorization_store.mjs";
import { ReviewedRequestArchive } from "./review_archive.mjs";
import { LeaseStore } from "./leases.mjs";

function base64(bytes) {
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 8192) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
  }
  return btoa(binary);
}

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

function validationInput(prepared) {
  return new TextEncoder().encode(JSON.stringify({ protocol: "m12-authorization-validation/1",
    approval_evidence_ref: prepared.approval_evidence_ref,
    approval_archive: { bundle_base64: base64(prepared.approval_archive.bundle_bytes),
      objects: Object.fromEntries(Object.entries(prepared.approval_archive.objects).map(([key, bytes]) => [key, base64(bytes)])) },
    validation_ticket: prepared.validation_ticket, history_base64: prepared.history_bytes.map(base64) }));
}

export class AuthorizationPreparation {
  #reviews;
  #store;
  #archive;
  #clock;
  #leases;

  constructor(identityPolicy, reviewPolicy, { storage, bucket, clock = Date.now, ...dependencies } = {}) {
    this.#reviews = new ReviewedRequestArchive(identityPolicy, reviewPolicy, { bucket, clock, ...dependencies });
    this.#store = new AuthorizationStore(storage, { clock });
    this.#archive = new ImmutableArchive(bucket);
    this.#clock = clock;
    this.#leases = new LeaseStore(storage, { clock });
  }

  async prepare(token, leaseToken) {
    // No supplied Job, history, ticket, request, Ref or claimed validation input.
    const readback = await this.#reviews.readForValidation(token);
    return this.#prepareReadback(readback, leaseToken);
  }

  async #prepareReadback(readback, leaseToken) {
    const bundle = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(readback.approval_archive.bundle_bytes));
    const alive = () => {
      const now = this.#clock();
      if (!Number.isSafeInteger(now) || now < Date.parse(bundle.observed_at) || now >= bundle.identity.expires_at * 1000) {
        throw new Error("authorization_preparation_identity_expired");
      }
    };
    alive();
    const ticket = this.#store.prepareValidation(bundle.identity.job, leaseToken, readback.approval_evidence_ref);
    const historyBytes = [];
    for (const item of ticket.history) {
      alive();
      historyBytes.push(await this.#archive.read(item.archive.key,
        { sha256: item.archive.sha256, size_bytes: item.archive.size_bytes }));
    }
    alive();
    const currentTicket = this.#store.readPreparedValidation(bundle.identity.job, leaseToken, ticket.ticket_id);
    alive();
    return { ...readback, validation_ticket: currentTicket, history_bytes: historyBytes };
  }

  async prepareValidationInput(token, leaseToken) {
    const prepared = await this.prepare(token, leaseToken);
    // Encode our own controlled result, never caller-selected evidence or history.
    // This encoding alone is not dispatch; use the recording wrapper below.
    return validationInput(prepared);
  }

  async dispatchValidationInput(token, leaseToken) {
    const raw = await this.prepareValidationInput(token, leaseToken);
    return this.#dispatchInput(raw, leaseToken);
  }

  async prepareJob(token, epoch) {
    // Authenticate environment approval and its original source before taking
    // a lease. epoch is server configuration, never a request-selected value.
    const readback = await this.#reviews.readForValidation(token);
    const bundle = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(readback.approval_archive.bundle_bytes));
    const now = this.#clock();
    if (!Number.isSafeInteger(now) || now < Date.parse(bundle.observed_at) || now >= bundle.identity.expires_at * 1000) {
      throw new Error("authorization_preparation_identity_expired");
    }
    const held = this.#leases.acquire("publish/global", bundle.identity.job, epoch);
    const leaseToken = { epoch, fence: held.lease.fence };
    const prepared = await this.#prepareReadback(readback, leaseToken);
    const result = await this.#dispatchInput(validationInput(prepared), leaseToken);
    return { ...result, lease_token: leaseToken };
  }

  async #dispatchInput(raw, leaseToken) {
    const wire = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(raw));
    const bundleBytes = Uint8Array.from(atob(wire.approval_archive.bundle_base64), (value) => value.charCodeAt(0));
    const bundle = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bundleBytes));
    const alive = () => {
      const now = this.#clock();
      if (!Number.isSafeInteger(now) || now < Date.parse(bundle.observed_at) || now >= bundle.identity.expires_at * 1000) {
        throw new Error("authorization_dispatch_identity_expired");
      }
    };
    const [inputHash, ticketHash] = await Promise.all([digest(raw),
      digest(new TextEncoder().encode(JSON.stringify(canonical(wire.validation_ticket))))]);
    alive();
    const inputArchive = await this.#archive.put("raw/" + inputHash.slice(7), raw,
      { sha256: inputHash, size_bytes: raw.length });
    alive();
    // The transaction rechecks the complete persistent ticket, head and lease
    // after all asynchronous writes/readbacks. No actual job dispatch is sent.
    const dispatch = this.#store.recordValidationDispatch(bundle.identity.job, leaseToken,
      { ticket: wire.validation_ticket, ticket_sha256: ticketHash, input_archive: inputArchive,
        source_commit: bundle.identity.code_commit, identity_issued_at: bundle.identity.issued_at,
        identity_expires_at: bundle.identity.expires_at });
    return { dispatch, input_bytes: raw };
  }
}
