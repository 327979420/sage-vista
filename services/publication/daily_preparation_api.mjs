// Internal coordinator router, disabled unless a reviewed server config opts in.
import { GitHubIdentityVerifier } from './identity.mjs';
import { LeaseStore } from './leases.mjs';
import { PreparationValidationSession } from './preparation_session.mjs';
import { MembershipArchiveApi } from './membership_api.mjs';
import { MembershipRegistrationSession } from './membership_session.mjs';
import { body, base64, response } from './job_wire.mjs';

const PROTOCOL = 'm12-daily-preparation/1';
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ?
  Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const same = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));

const REGISTRATION = 'm12-membership-registration/1';
function resultBytes(value) {
  if (typeof value.result_base64 !== 'string' || value.result_base64.length > 4 * Math.ceil(65536 / 3)) throw new Error('size');
  const binary = atob(value.result_base64);
  if (!binary.length || binary.length > 65536 || btoa(binary) !== value.result_base64) throw new Error('encoding');
  return Uint8Array.from(binary, c => c.charCodeAt(0));
}

export class DailyPreparationApi {
  #enabled;
  #identity;
  #sessions;
  #leases;
  #policy;
  #epoch;
  #license;
  #identityPolicy;
  #dependencies;

  constructor(identityPolicy, { enabled = false, preparationPolicy, leaseEpoch, licensePolicy = null, ...dependencies } = {}) {
    if (typeof enabled !== 'boolean') throw new Error('daily_preparation_configuration_invalid');
    this.#enabled = enabled;
    if (!enabled) return;
    if (!preparationPolicy || typeof leaseEpoch !== 'string' || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(leaseEpoch)) throw new Error('daily_preparation_configuration_invalid');
    if (licensePolicy !== null && Object.keys(licensePolicy).sort().join() !== 'license_archive,license_valid_from,license_valid_until,purpose') throw new Error('daily_license_configuration_invalid');
    this.#policy = structuredClone(preparationPolicy);
    this.#epoch = leaseEpoch;
    this.#license = structuredClone(licensePolicy);
    this.#identityPolicy = structuredClone(identityPolicy);
    this.#dependencies = { ...dependencies };
    this.#identity = new GitHubIdentityVerifier(identityPolicy, dependencies);
    this.#sessions = new PreparationValidationSession(identityPolicy, { preparationPolicy, ...dependencies });
    this.#leases = new LeaseStore(dependencies.storage, { clock: dependencies.clock });
  }

  async fetch(request) {
    const fail = (status, error) => response({ protocol: PROTOCOL, error }, status);
    if (!this.#enabled) return fail(503, 'daily_preparation_disabled');
    const url = new URL(request.url);
    const member = ['/v1/membership/permit', '/v1/membership/put', '/v1/membership/read'].includes(url.pathname);
    const registration = ['/v1/membership/registration/prepare', '/v1/membership/registration/return'].includes(url.pathname);
    if ((!member && !registration && !['/v1/preparation/prepare', '/v1/preparation/return'].includes(url.pathname)) || url.search || url.hash) return fail(404, 'route_unavailable');
    if (request.method !== 'POST') return fail(405, 'method_not_allowed');
    const auth = request.headers.get('Authorization') ?? '';
    if (!auth.startsWith('Bearer ') || auth.length > 65543) return fail(401, 'unauthorized');
    const token = auth.slice(7);
    let identity;
    try { identity = await this.#identity.verify(token); }
    catch { return fail(401, 'unauthorized'); }
    if (identity.actor_id !== this.#policy.actor_id) return fail(401, 'unauthorized');
    if (registration) return this.#registration(request, token);
    if (member) {
      try {
        if (this.#license === null) throw new Error('license not configured');
        const chosen = await this.#sessions.selectedForUse(token);
        const api = new MembershipArchiveApi(this.#identityPolicy, { ...this.#dependencies, enabled: true,
          preparationPolicy: this.#policy, acquisitionPolicy: { ...this.#license, ...chosen } });
        const result = await api.fetch(request);
        if (!same(chosen, await this.#sessions.selectedForUse(token))) throw new Error('selection changed');
        return result;
      } catch { return fail(409, 'daily_preparation_not_ready'); }
    }
    let value, raw;
    const preparing = url.pathname.endsWith('/prepare');
    try {
      value = await body(request, preparing ? 256 : 131072);
      if (value.protocol !== PROTOCOL || Object.keys(value).sort().join() !== (preparing ? 'protocol' : 'input_sha256,lease_token,protocol,result_base64')) throw new Error('fields');
      if (!preparing) raw = resultBytes(value);
    } catch { return fail(400, 'request_invalid'); }
    try {
      if (preparing) {
        const resource = `daily/${this.#policy.as_of}/${this.#policy.config_ref.id}`;
        const lease = this.#dependencies.storage.transactionSync(() => {
          const live = () => {
            const now = (this.#dependencies.clock ?? Date.now)();
            if (!Number.isSafeInteger(now) || now < identity.issued_at * 1000 || now >= identity.expires_at * 1000) throw new Error('identity expired');
          };
          live();
          const held = this.#leases.acquire(resource, identity.job, this.#epoch);
          const handle = { epoch: this.#epoch, fence: held.lease.fence };
          this.#leases.renew(resource, identity.job, handle);
          live();
          return handle;
        });
        const prepared = await this.#sessions.prepare(token, lease);
        const result = response({ protocol: PROTOCOL, lease_token: lease,
          input_sha256: prepared.input_archive.sha256, input_size_bytes: prepared.input_archive.size_bytes,
          input_base64: base64(prepared.input_bytes) });
        // Check the original persisted input after encoding, never recapture
        // another observation with a new checked_at timestamp.
        const current = await this.#sessions.verifyPrepared(token, lease, prepared.input_archive.sha256);
        if (!same(current, prepared.input_archive)) throw new Error('input changed');
        return result;
      }
      const accepted = await this.#sessions.accept(token, value.lease_token, value.input_sha256, raw);
      const selected = await this.#sessions.selectForUse(token, value.lease_token, accepted.input_sha256, accepted.output_archive.sha256);
      const result = response({ protocol: PROTOCOL, ...accepted });
      if (!same(selected, await this.#sessions.selectedForUse(token))) throw new Error('selection changed');
      return result;
    } catch { return fail(409, 'daily_preparation_not_ready'); }
  }

  async #registration(request, token) {
    const fail = (status, error) => response({ protocol: REGISTRATION, error }, status);
    const preparing = new URL(request.url).pathname.endsWith('/prepare');
    let value, raw;
    try {
      value = await body(request, preparing ? 1024 : 131072);
      if (value.protocol !== REGISTRATION || Object.keys(value).sort().join() !==
          (preparing ? 'candidate_archive,protocol' : 'input_sha256,protocol,result_base64')) throw new Error('fields');
      if (!preparing) raw = resultBytes(value);
    } catch { return fail(400, 'request_invalid'); }
    try {
      const session = new MembershipRegistrationSession(this.#identityPolicy, { ...this.#dependencies,
        preparationPolicy: this.#policy, licensePolicy: this.#license });
      if (preparing) {
        const sent = await session.prepare(token, value.candidate_archive);
        const result = response({ protocol: REGISTRATION, input_sha256: sent.input_archive.sha256,
          input_size_bytes: sent.input_archive.size_bytes, input_base64: base64(sent.input_bytes) });
        if (!same(sent.input_archive, await session.verifyPrepared(token, sent.input_archive.sha256))) throw new Error('input changed');
        return result;
      }
      const accepted = await session.accept(token, value.input_sha256, raw);
      const result = response({ protocol: REGISTRATION, input_sha256: accepted.input_sha256,
        output_archive: accepted.output_archive, current_index: accepted.current_index });
      if (!same(accepted, await session.verifyRegistered(token, value.input_sha256, raw, accepted))) throw new Error('return changed');
      return result;
    } catch { return fail(409, 'membership_registration_not_ready'); }
  }

}
