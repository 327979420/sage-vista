import { GitHubIdentityVerifier } from "./identity.mjs";
import { AuthorizationPreparation } from "./authorization_preparation.mjs";
import { AuthorizationValidationArchive } from "./authorization_validation_archive.mjs";
import { AuthorizationStore } from "./authorization_store.mjs";

const PROTOCOL = "m12-authorization-job/1";
const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const RETURN_LIMIT = 4 * 1024 * 1024;

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

function base64(bytes) {
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
  return btoa(binary);
}

function response(value, status = 200) {
  return new Response(JSON.stringify(canonical(value)), { status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
}

async function body(request, limit) {
  if (request.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase() !== "application/json" ||
      ![null, "identity"].includes(request.headers.get("Content-Encoding"))) throw new Error("invalid");
  const length = request.headers.get("Content-Length");
  if (length !== null && (!/^[0-9]+$/.test(length) || Number(length) > limit)) throw new Error("invalid");
  if (!request.body) throw new Error("invalid");
  const reader = request.body.getReader();
  let timer;
  try {
    const read = async () => {
      const chunks = [];
      let size = 0;
      while (true) {
        const item = await reader.read();
        if (item.done) break;
        size += item.value.length;
        if (size > limit) throw new Error("invalid");
        chunks.push(item.value);
      }
      if (!size || (length !== null && size !== Number(length))) throw new Error("invalid");
      const bytes = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
      const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
      const value = JSON.parse(text);
      if (!value || Array.isArray(value) || typeof value !== "object" || JSON.stringify(canonical(value)) !== text) throw new Error("invalid");
      return value;
    };
    return await Promise.race([read(), new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error("invalid")), 5000);
    })]);
  } finally {
    clearTimeout(timer);
    void reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export class AuthorizationJobApi {
  #enabled;
  #epoch;
  #verifier;
  #preparation;
  #archive;
  #store;

  constructor(identityPolicy, reviewPolicy, { enabled = false, leaseEpoch, ...dependencies } = {}) {
    if (typeof enabled !== "boolean") throw new Error("authorization_api_configuration_invalid");
    this.#enabled = enabled;
    if (!enabled) return; // No storage initialization or network in disabled mode.
    if (typeof leaseEpoch !== "string" || !UUID.test(leaseEpoch)) throw new Error("authorization_api_epoch_required");
    this.#epoch = leaseEpoch;
    this.#verifier = new GitHubIdentityVerifier(identityPolicy, dependencies);
    this.#preparation = new AuthorizationPreparation(identityPolicy, reviewPolicy, dependencies);
    this.#archive = new AuthorizationValidationArchive(identityPolicy, dependencies);
    this.#store = new AuthorizationStore(dependencies.storage, { clock: dependencies.clock });
  }

  async fetch(request) {
    const error = (status, code) => response({ protocol: PROTOCOL, error: code }, status);
    if (!this.#enabled) return error(503, "authorization_jobs_disabled");
    const url = new URL(request.url);
    if (url.search || url.hash || !["/v1/authorization/prepare", "/v1/authorization/return"].includes(url.pathname)) return error(404, "route_unavailable");
    if (request.method !== "POST") return error(405, "method_not_allowed");
    const authorization = request.headers.get("Authorization") ?? "";
    if (!authorization.startsWith("Bearer ") || authorization.length > 65543) return error(401, "unauthorized");
    const token = authorization.slice(7);
    let identity;
    try { identity = await this.#verifier.verify(token); }
    catch { return error(401, "unauthorized"); }
    let value;
    try {
      value = await body(request, url.pathname.endsWith("/prepare") ? 2 : RETURN_LIMIT);
      if (url.pathname.endsWith("/prepare")) {
        if (Object.keys(value).length) throw new Error("invalid");
      } else {
        if (Object.keys(value).sort().join() !== "dispatch_id,lease_token,protocol,result_base64" || value.protocol !== PROTOCOL ||
            typeof value.dispatch_id !== "string" || !UUID.test(value.dispatch_id) ||
            !value.lease_token || Object.keys(value.lease_token).sort().join() !== "epoch,fence" ||
            typeof value.lease_token.epoch !== "string" || !UUID.test(value.lease_token.epoch) ||
            !Number.isSafeInteger(value.lease_token.fence) || value.lease_token.fence < 1 || typeof value.result_base64 !== "string") {
          throw new Error("invalid");
        }
        const raw = atob(value.result_base64);
        if (btoa(raw) !== value.result_base64) throw new Error("invalid");
        value.result_bytes = Uint8Array.from(raw, (char) => char.charCodeAt(0));
      }
    } catch { return error(400, "request_invalid"); }
    try {
      if (url.pathname.endsWith("/prepare")) {
        const prepared = await this.#preparation.prepareJob(token, this.#epoch);
        // Check before allocating the base64-expanded response.
        if (4 * Math.ceil(prepared.input_bytes.length / 3) + 2048 > 32 * 1024 * 1024) return error(409, "job_not_ready");
        const result = response({ protocol: PROTOCOL, dispatch_id: prepared.dispatch.dispatch_id, lease_token: prepared.lease_token,
          input_sha256: prepared.dispatch.input_archive.sha256, input_size_bytes: prepared.input_bytes.length,
          input_base64: base64(prepared.input_bytes) });
        this.#store.readValidationDispatch(identity, prepared.lease_token, prepared.dispatch.dispatch_id);
        return result;
      }
      const archived = await this.#archive.archive(token, value.lease_token, value.dispatch_id, value.result_bytes);
      const result = response({ protocol: PROTOCOL, dispatch_id: value.dispatch_id, state: "archived_pending_registration",
        authorization_archive: archived.authorization_archive, validation_receipt_archive: archived.validation_receipt_archive });
      this.#store.readValidationDispatch(archived.identity, value.lease_token, value.dispatch_id);
      return result;
    } catch { return error(409, "job_not_ready"); }
  }
}
