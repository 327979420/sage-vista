// Server half of the private byte bridge, no HTTP route or runtime factory.
// sessionPolicy is a trusted server capability, NOT a caller-provided permit.
// The future factory must establish actual acquisition rights from source
// evidence. This adapter authenticates/binds their use, not their semantics.
import { GitHubIdentityVerifier } from './identity.mjs';
import { ImmutableArchive } from './archive.mjs';
import { LeaseStore } from './leases.mjs';

const SOURCE = 'https://eodhd.com/api/exchange-symbol-list/US?delisted=0&fmt=json';
const MAX_BYTES = 32 * 1024 * 1024 + 1; // Preserve the collector's over-limit sentinel.
const UUID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ?
  Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const encode = value => JSON.stringify(canonical(value));

function descriptor(key, expected) {
  if (typeof key !== 'string' || !/^raw\/[a-f0-9]{64}$/.test(key) || !expected ||
      Object.keys(expected).sort().join() !== 'sha256,size_bytes' ||
      expected.sha256 !== 'sha256:' + key.slice(4) || !Number.isSafeInteger(expected.size_bytes) ||
      expected.size_bytes < 0 || expected.size_bytes > MAX_BYTES) throw new Error('membership_archive_descriptor_invalid');
  return { sha256: expected.sha256, size_bytes: expected.size_bytes };
}

export class MembershipArchiveSession {
  #policy;
  #binding;
  #verifier;
  #archive;
  #leases;
  #storage;
  #resource;

  constructor(identityPolicy, { sessionPolicy = null, ...dependencies } = {}) {
    if (sessionPolicy === null) return; // No SQL/network when disabled.
    const p = JSON.parse(JSON.stringify(sessionPolicy));
    if (Object.keys(p).sort().join() !== 'acquisition_evidence,actor_id,as_of,config_id,expires_at,job,lease_token' ||
        typeof p.as_of !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(p.as_of) ||
        !Number.isFinite(Date.parse(p.as_of + 'T00:00:00Z')) || new Date(p.as_of).toISOString().slice(0, 10) !== p.as_of ||
        typeof p.actor_id !== 'string' || !/^[1-9][0-9]*$/.test(p.actor_id) ||
        typeof p.config_id !== 'string' || !/^[A-Za-z0-9_:.-]+$/.test(p.config_id) ||
        !Number.isSafeInteger(p.expires_at) || p.expires_at < 1 ||
        !p.job || Object.keys(p.job).sort().join() !== 'environment,repository_id,run_attempt,run_id,workflow_commit,workflow_ref' ||
        !p.lease_token || Object.keys(p.lease_token).sort().join() !== 'epoch,fence' ||
        typeof p.lease_token.epoch !== 'string' || !UUID.test(p.lease_token.epoch) ||
        !Number.isSafeInteger(p.lease_token.fence) || p.lease_token.fence < 1 ||
        !p.acquisition_evidence || Object.keys(p.acquisition_evidence).sort().join() !== 'key,sha256,size_bytes') {
      throw new Error('membership_archive_policy_invalid');
    }
    const { key, ...expected } = p.acquisition_evidence;
    descriptor(key, expected);
    if (expected.size_bytes < 1 || expected.size_bytes > 1024 * 1024) throw new Error('membership_archive_policy_invalid');
    this.#verifier = new GitHubIdentityVerifier(identityPolicy, dependencies);
    this.#archive = new ImmutableArchive(dependencies.bucket);
    this.#leases = new LeaseStore(dependencies.storage, { clock: dependencies.clock });
    this.#storage = dependencies.storage;
    this.#policy = p; // Deep copied and never exposed.
    this.#binding = encode({ identity: identityPolicy, session: p });
    this.#resource = `daily/${p.as_of}/${p.config_id}`;
    this.#storage.transactionSync(() => {
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_membership_raw_access (
        binding TEXT NOT NULL, key TEXT NOT NULL, descriptor_json TEXT NOT NULL,
        PRIMARY KEY (binding, key))`);
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_membership_raw_log (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT, binding TEXT NOT NULL, key TEXT NOT NULL,
        descriptor_json TEXT NOT NULL, occurred_ms INTEGER NOT NULL, UNIQUE(binding, key))`);
    });
  }

  #exec(sql, ...args) { return this.#storage.sql.exec(sql, ...args).toArray(); }

  #guard(identity, action = () => undefined) {
    return this.#leases.withOwnedLease(this.#resource, identity.job, this.#policy.lease_token, ({ now }) => {
      if (now < identity.issued_at * 1000 || encode(identity.job) !== encode(this.#policy.job) ||
          identity.actor_id !== this.#policy.actor_id) throw new Error('membership_archive_session_stale');
      return action({ now });
    }, { deadlineMs: Math.min(identity.expires_at * 1000, this.#policy.expires_at) });
  }

  async #identity(token) {
    if (!this.#policy) throw new Error('membership_archive_disabled');
    const identity = await this.#verifier.verify(token);
    this.#guard(identity);
    return identity;
  }

  async #evidence(identity) {
    const { key, ...expected } = this.#policy.acquisition_evidence;
    const bytes = await this.#archive.read(key, expected);
    this.#guard(identity);
    return bytes;
  }

  #owned(key, expected, required, now) {
    const rows = this.#exec('SELECT descriptor_json FROM m12_membership_raw_access WHERE binding=? AND key=?', this.#binding, key);
    const logs = this.#exec('SELECT descriptor_json,occurred_ms FROM m12_membership_raw_log WHERE binding=? AND key=?', this.#binding, key);
    if (!rows.length && !logs.length) {
      if (required) throw new Error('membership_archive_read_not_owned');
      return false;
    }
    if (rows.length !== 1 || logs.length !== 1 || rows[0].descriptor_json !== encode(expected) ||
        logs[0].descriptor_json !== rows[0].descriptor_json || !Number.isSafeInteger(logs[0].occurred_ms) ||
        logs[0].occurred_ms < 0 || logs[0].occurred_ms > now) throw new Error('membership_archive_access_conflict');
    return true;
  }

  async acquisitionEvidence(token, asOf, requestUrl) {
    const identity = await this.#identity(token);
    if (asOf !== this.#policy.as_of || requestUrl !== SOURCE) throw new Error('membership_acquisition_target_mismatch');
    return this.#evidence(identity); // Actual fixed bytes, not a permission boolean.
  }

  async put(token, key, input, expected) {
    if (!this.#policy) throw new Error('membership_archive_disabled');
    const frozen = descriptor(key, expected);
    if (!(input instanceof Uint8Array) || input.length !== frozen.size_bytes) throw new Error('membership_archive_bytes_invalid');
    const bytes = new Uint8Array(input); // Before await/identity fetch.
    const identity = await this.#identity(token);
    await this.#evidence(identity); // Fixed source must remain readable on every use.
    const result = await this.#archive.put(key, bytes, frozen);
    // Only after actual write/readback: register private read ownership under
    // the current fence. Lost responses can leave immutable unowned orphans.
    this.#guard(identity, ({ now }) => {
      if (!this.#owned(key, frozen, false, now)) {
        const encoded = encode(frozen);
        this.#exec('INSERT INTO m12_membership_raw_access VALUES (?, ?, ?)', this.#binding, key, encoded);
        this.#exec('INSERT INTO m12_membership_raw_log (binding,key,descriptor_json,occurred_ms) VALUES (?, ?, ?, ?)',
          this.#binding, key, encoded, now);
      }
    });
    return result;
  }

  #allowed(key, frozen, now) {
    if (encode({ key, ...frozen }) === encode(this.#policy.acquisition_evidence)) return;
    this.#owned(key, frozen, true, now);
  }

  async verifyAccess(token, key, expected) {
    const frozen = descriptor(key, expected);
    const identity = await this.#identity(token);
    this.#guard(identity, ({ now }) => this.#allowed(key, frozen, now));
  }

  async read(token, key, expected) {
    const frozen = descriptor(key, expected);
    const identity = await this.#identity(token);
    const allowed = ({ now }) => this.#allowed(key, frozen, now);
    this.#guard(identity, allowed);
    await this.#evidence(identity);
    const bytes = await this.#archive.read(key, frozen);
    this.#guard(identity, allowed);
    return bytes;
  }
}
