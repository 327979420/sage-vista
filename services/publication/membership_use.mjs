// Trusted server factory for the fixed PRIVATE membership acquisition purpose.
// licensePolicy is installed only from the reviewed launch card, never a request
// or a claim parsed from the provider. No real license policy ships in this repo.
import { PreparationValidationSession } from './preparation_session.mjs';
import { MembershipArchiveSession } from './membership_archive.mjs';
import { ImmutableArchive } from './archive.mjs';

export class MembershipUseFactory {
  #policy;
  #preparation;
  #identityPolicy;
  #options;
  #checks;
  #archive;
  #raw;
  #clock;

  constructor(identityPolicy, { acquisitionPolicy = null, preparationPolicy, clock = Date.now, ...dependencies } = {}) {
    if (acquisitionPolicy === null) return;
    const p = structuredClone(acquisitionPolicy);
    if (!preparationPolicy || !p || Object.keys(p).sort().join() !== 'input_sha256,lease_token,license_archive,license_valid_from,license_valid_until,output_sha256,purpose' ||
        p.purpose !== 'eodhd_us_membership_private_acquisition' ||
        ![p.input_sha256, p.output_sha256].every(v => typeof v === 'string' && /^sha256:[a-f0-9]{64}$/.test(v)) ||
        !p.lease_token || Object.keys(p.lease_token).sort().join() !== 'epoch,fence' ||
        typeof p.lease_token.epoch !== 'string' || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(p.lease_token.epoch) ||
        !Number.isSafeInteger(p.lease_token.fence) || p.lease_token.fence < 1 ||
        !Number.isSafeInteger(p.license_valid_from) || !Number.isSafeInteger(p.license_valid_until) ||
        p.license_valid_from < 0 || p.license_valid_until <= p.license_valid_from ||
        !p.license_archive || Object.keys(p.license_archive).sort().join() !== 'key,sha256,size_bytes' ||
        typeof p.license_archive.key !== 'string' || !/^raw\/[a-f0-9]{64}$/.test(p.license_archive.key) ||
        p.license_archive.sha256 !== 'sha256:' + p.license_archive.key.slice(4) ||
        !Number.isSafeInteger(p.license_archive.size_bytes) || p.license_archive.size_bytes < 1 || p.license_archive.size_bytes > 1024 * 1024) {
      throw new Error('membership_use_policy_invalid');
    }
    this.#checks = new PreparationValidationSession(identityPolicy, { preparationPolicy, clock, ...dependencies });
    this.#archive = new ImmutableArchive(dependencies.bucket);
    this.#policy = p;
    this.#preparation = structuredClone(preparationPolicy);
    this.#identityPolicy = structuredClone(identityPolicy);
    this.#options = { clock, ...dependencies };
    this.#clock = clock;
  }

  #window() {
    if (!this.#policy) throw new Error('membership_use_disabled');
    const now = this.#clock();
    if (!Number.isSafeInteger(now) || now < this.#policy.license_valid_from || now >= this.#policy.license_valid_until) {
      throw new Error('membership_license_window_invalid');
    }
  }

  async #ready(token) {
    this.#window();
    const p = this.#policy;
    const currentCheck = () => this.#checks.readForUse(token, p.lease_token, p.input_sha256, p.output_sha256);
    await currentCheck();
    const { key, sha256, size_bytes } = p.license_archive;
    await this.#archive.read(key, { sha256, size_bytes });
    const checked = await currentCheck(); // A revoke during license I/O must not succeed.
    this.#window();
    if (!this.#raw) {
      this.#raw = new MembershipArchiveSession(this.#identityPolicy, { ...this.#options, sessionPolicy: {
        acquisition_evidence: p.license_archive, actor_id: checked.identity.actor_id,
        as_of: this.#preparation.as_of, config_id: this.#preparation.config_ref.id,
        expires_at: p.license_valid_until, job: checked.identity.job, lease_token: p.lease_token } });
    }
  }

  async #operate(token, method, args) {
    await this.#ready(token);
    const result = await this.#raw[method](token, ...args);
    await this.#ready(token);
    return result;
  }

  acquisitionEvidence(token, asOf, requestUrl) {
    return this.#operate(token, 'acquisitionEvidence', [asOf, requestUrl]);
  }
  put(token, key, bytes, expected) {
    if (!(bytes instanceof Uint8Array)) return Promise.reject(new Error('membership_use_bytes_invalid'));
    return this.#operate(token, 'put', [key, new Uint8Array(bytes), { ...expected }]);
  }
  read(token, key, expected) { return this.#operate(token, 'read', [key, { ...expected }]); }
  verifyAccess(token, key, expected) { return this.#operate(token, 'verifyAccess', [key, { ...expected }]); }
}
