// Opt-in server route adapter. No Worker wiring, policy factory or deployment.
import { GitHubIdentityVerifier } from './identity.mjs';
import { MembershipArchiveSession } from './membership_archive.mjs';
import { MembershipUseFactory } from './membership_use.mjs';
import { body, base64, response } from './job_wire.mjs';

const PROTOCOL = 'm12-membership-archive/1';
const WIRE_LIMIT = 48 * 1024 * 1024;
const RAW_LIMIT = 32 * 1024 * 1024 + 1;
const expected = value => ({ sha256: value.sha256, size_bytes: value.size_bytes });

function descriptor(value) {
  if (typeof value.key !== 'string' || !/^raw\/[a-f0-9]{64}$/.test(value.key) ||
      value.sha256 !== 'sha256:' + value.key.slice(4) || !Number.isSafeInteger(value.size_bytes) ||
      value.size_bytes < 0 || value.size_bytes > RAW_LIMIT) throw new Error('invalid');
  return { key: value.key, ...expected(value) };
}

async function describe(bytes) {
  const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  const hex = Array.from(hash, v => v.toString(16).padStart(2, '0')).join('');
  return { key: 'raw/' + hex, sha256: 'sha256:' + hex, size_bytes: bytes.length };
}

export class MembershipArchiveApi {
  #enabled;
  #identity;
  #session;

  constructor(identityPolicy, { enabled = false, sessionPolicy = null, acquisitionPolicy = null, preparationPolicy, ...dependencies } = {}) {
    if (typeof enabled !== 'boolean') throw new Error('membership_api_configuration_invalid');
    this.#enabled = enabled;
    if (!enabled) return;
    if ((sessionPolicy === null) === (acquisitionPolicy === null)) throw new Error('membership_api_policy_required');
    this.#identity = new GitHubIdentityVerifier(identityPolicy, dependencies);
    this.#session = acquisitionPolicy === null
      ? new MembershipArchiveSession(identityPolicy, { sessionPolicy, ...dependencies })
      : new MembershipUseFactory(identityPolicy, { acquisitionPolicy, preparationPolicy, ...dependencies });
  }

  async fetch(request) {
    const error = (status, reason) => response({ protocol: PROTOCOL, error: reason }, status);
    if (!this.#enabled) return error(503, 'membership_archive_disabled');
    const url = new URL(request.url), prefix = '/v1/membership/';
    const operation = url.pathname.slice(prefix.length);
    if (!url.pathname.startsWith(prefix) || url.search || url.hash || !['permit', 'put', 'read'].includes(operation)) {
      return error(404, 'route_unavailable');
    }
    if (request.method !== 'POST') return error(405, 'method_not_allowed');
    const authorization = request.headers.get('Authorization') ?? '';
    if (!authorization.startsWith('Bearer ') || authorization.length > 65543) return error(401, 'unauthorized');
    const token = authorization.slice(7);
    try { await this.#identity.verify(token); } // Before any potentially large request body.
    catch { return error(401, 'unauthorized'); }
    let value, raw;
    try {
      value = await body(request, operation === 'put' ? WIRE_LIMIT : 2048);
      const fields = operation === 'permit' ? 'as_of,protocol,request_url' :
        operation === 'put' ? 'bytes_base64,key,protocol,sha256,size_bytes' : 'key,protocol,sha256,size_bytes';
      if (Object.keys(value).sort().join() !== fields || value.protocol !== PROTOCOL) throw new Error('invalid');
      if (operation === 'permit') {
        if (typeof value.as_of !== 'string' || typeof value.request_url !== 'string') throw new Error('invalid');
      } else {
        descriptor(value);
        if (operation === 'put') {
          if (typeof value.bytes_base64 !== 'string' || value.bytes_base64.length > 4 * Math.ceil(RAW_LIMIT / 3)) throw new Error('invalid');
          const binary = atob(value.bytes_base64);
          if (btoa(binary) !== value.bytes_base64 || binary.length !== value.size_bytes) throw new Error('invalid');
          raw = Uint8Array.from(binary, c => c.charCodeAt(0));
        }
      }
    } catch { return error(400, 'request_invalid'); }
    try {
      let entry, payload;
      if (operation === 'permit') {
        const bytes = await this.#session.acquisitionEvidence(token, value.as_of, value.request_url);
        entry = await describe(bytes);
        payload = { protocol: PROTOCOL, as_of: value.as_of, request_url: value.request_url,
          ...entry, bytes_base64: base64(bytes) };
      } else if (operation === 'put') {
        entry = await this.#session.put(token, value.key, raw, expected(value));
        payload = { protocol: PROTOCOL, ...entry };
      } else {
        const bytes = await this.#session.read(token, value.key, expected(value));
        entry = descriptor(value);
        payload = { protocol: PROTOCOL, ...entry, bytes_base64: base64(bytes) };
      }
      const result = response(payload);
      // Encoding can take time. Do not release already-encoded bytes under a
      // stale token, fence, or lost ownership; no authority is added here.
      await this.#session.verifyAccess(token, entry.key, expected(entry));
      return result;
    } catch { return error(409, 'membership_archive_not_ready'); }
  }
}
