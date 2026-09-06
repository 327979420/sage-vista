// Internal authenticated session. No HTTP route or production policy installed.
// Python owns source/identity business validation; this binds its fixed result.
import { MembershipRegistrationReadback } from './membership_readback.mjs';
import { MembershipObservationIndex } from './membership_index.mjs';
import { AuthorizationStore } from './authorization_store.mjs';
import { ImmutableArchive } from './archive.mjs';
import { GitHubIdentityVerifier } from './identity.mjs';

const canonical = v => Array.isArray(v) ? v.map(canonical) : v && typeof v === 'object' ?
  Object.fromEntries(Object.keys(v).sort().map(k => [k, canonical(v[k])])) : v;
const encode = v => JSON.stringify(canonical(v));
const same = (a, b) => encode(a) === encode(b);
const parse = b => JSON.parse(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(b));
const preparation = input => parse(Uint8Array.from(atob(input.preparation_base64), c => c.charCodeAt(0)));
const hash = async b => 'sha256:' + Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', b)),
  v => v.toString(16).padStart(2, '0')).join('');
const exact = (v, keys) => {
  if (!v || Array.isArray(v) || typeof v !== 'object' || Object.keys(v).sort().join() !== keys.split(',').sort().join()) {
    throw new Error('membership_session_fields_invalid');
  }
};

export class MembershipRegistrationSession {
  #readback; #index; #auth; #archive; #storage; #clock; #binding; #resource; #license; #verifier;
  constructor(identityPolicy, { licensePolicy = null, ...options } = {}) {
    if (licensePolicy === null) return;
    this.#readback = new MembershipRegistrationReadback(identityPolicy, { ...options, licensePolicy });
    this.#storage = options.storage;
    this.#clock = options.clock ?? Date.now;
    this.#license = structuredClone(licensePolicy);
    this.#binding = encode({ identityPolicy, preparationPolicy: options.preparationPolicy, licensePolicy });
    this.#index = new MembershipObservationIndex(options.storage, options);
    this.#auth = new AuthorizationStore(options.storage, options);
    this.#archive = new ImmutableArchive(options.bucket);
    this.#verifier = new GitHubIdentityVerifier(identityPolicy, options);
    this.#resource = `daily/${options.preparationPolicy.as_of}/${options.preparationPolicy.config_ref.id}`;
    options.storage.transactionSync(() => {
      for (const name of ['inputs', 'input_log', 'returns', 'return_log']) {
        this.#exec(`CREATE TABLE IF NOT EXISTS m12_membership_${name} (key TEXT PRIMARY KEY, record_json TEXT NOT NULL)`);
      }
    });
  }
  #exec(sql, ...args) { return this.#storage.sql.exec(sql, ...args).toArray(); }
  #enabled() { if (!this.#readback) throw new Error('membership_session_disabled'); }
  #time() {
    const now = this.#clock();
    if (!Number.isSafeInteger(now) || now < 0) throw new Error('membership_session_clock_invalid');
    return now;
  }
  #pair(kind, key, optional = false) {
    const row = this.#exec(`SELECT record_json FROM m12_membership_${kind}s WHERE key=?`, key);
    const log = this.#exec(`SELECT record_json FROM m12_membership_${kind}_log WHERE key=?`, key);
    if (optional && !row.length && !log.length) return null;
    if (row.length !== 1 || log.length !== 1 || row[0].record_json !== log[0].record_json) {
      throw new Error('membership_session_recovery_required');
    }
    return JSON.parse(row[0].record_json);
  }
  #save(kind, key, record) {
    const old = this.#pair(kind, key, true);
    if (old) {
      if (!same(old, record)) throw new Error('membership_session_record_conflict');
    } else {
      this.#exec(`INSERT INTO m12_membership_${kind}s VALUES (?,?)`, key, encode(record));
      this.#exec(`INSERT INTO m12_membership_${kind}_log VALUES (?,?)`, key, encode(record));
    }
  }
  #guard(record, identity, expected) {
    if (record.binding !== this.#binding || !same(identity.job, record.identity.job) ||
        identity.actor_id !== record.identity.actor_id || identity.code_commit !== record.identity.code_commit) {
      throw new Error('membership_session_origin_mismatch');
    }
    const handle = record.selection.lease_token;
    for (const who of [identity, record.identity]) {
      if (!same(this.#auth.readCurrentForPreparation(who, handle, this.#resource), record.current_history)) {
        throw new Error('membership_session_authorization_changed');
      }
    }
    if (!same(this.#index.readCurrent(record.identity, handle, this.#resource), expected)) {
      throw new Error('membership_session_index_changed');
    }
    const now = this.#time();
    if (now < record.recorded_ms || now >= Math.min(identity.expires_at, record.identity.expires_at) * 1000 ||
        now < this.#license.license_valid_from || now >= this.#license.license_valid_until) {
      throw new Error('membership_session_window_changed');
    }
  }
  async #fresh(token, record, input, expected) {
    const captured = await this.#readback.captureForRegistration(token, input.candidate_archive);
    const current = parse(captured.input_bytes);
    if (!same(captured.selection, record.selection) || !same(current.expected_index, expected) ||
        !same(current.candidate_archive, input.candidate_archive) ||
        !same(current.acquisition_archive, input.acquisition_archive) ||
        !same(current.observations_base64, input.observations_base64)) {
      throw new Error('membership_session_source_changed');
    }
    this.#guard(record, current.identity, expected);
    return current.identity;
  }
  async #read(descriptor) {
    const { key, sha256, size_bytes } = descriptor;
    return this.#archive.read(key, { sha256, size_bytes });
  }
  async prepare(token, candidateArchive) {
    this.#enabled();
    const captured = await this.#readback.captureForRegistration(token, candidateArchive);
    const raw = captured.input_bytes, input = parse(raw), fingerprint = await hash(raw);
    const record = { binding: this.#binding, identity: input.identity, selection: captured.selection,
      current_history: preparation(input).evidence.current_history, input_archive: null, recorded_ms: this.#time() };
    this.#guard(record, input.identity, input.expected_index);
    record.input_archive = await this.#archive.put('raw/' + fingerprint.slice(7), raw, { sha256: fingerprint, size_bytes: raw.length });
    await this.#read(record.input_archive);
    const identity = await this.#fresh(token, record, input, input.expected_index);
    return this.#storage.transactionSync(() => {
      const old = this.#pair('input', fingerprint, true);
      if (old) record.recorded_ms = old.recorded_ms;
      this.#guard(record, identity, input.expected_index);
      this.#save('input', fingerprint, record);
      this.#guard(record, identity, input.expected_index);
      return { input_archive: structuredClone(record.input_archive), input_bytes: raw };
    });
  }
  #result(record, input, raw, bytes) {
    const result = parse(bytes), p = result.preparation, m = result.membership_registration;
    exact(result, 'protocol,input_sha256,input_size_bytes,started_ms,completed_ms,preparation,membership_registration');
    exact(p, 'authorization_ref,config_ref,config_archive,code_commit,as_of,checked_at,history_revision');
    exact(m, 'as_of,expected_index,candidate_archive,member_count,members_fingerprint');
    const prepared = preparation(input).evidence;
    if (encode(result) + '\n' !== new TextDecoder().decode(bytes) || result.protocol !== input.protocol ||
        result.input_sha256 !== record.input_archive.sha256 || result.input_size_bytes !== raw.length ||
        !Number.isSafeInteger(result.started_ms) || !Number.isSafeInteger(result.completed_ms) ||
        result.started_ms < record.recorded_ms || result.started_ms < Date.parse(prepared.checked_at) ||
        result.completed_ms < result.started_ms || result.completed_ms > this.#time() ||
        result.completed_ms >= record.identity.expires_at * 1000 ||
        !same(p.authorization_ref, record.current_history.head) || p.history_revision !== record.current_history.revision ||
        !same(p.config_ref, prepared.config_ref) || !same(p.config_archive, prepared.config_archive) ||
        p.code_commit !== record.identity.code_commit || p.as_of !== prepared.as_of ||
        p.checked_at !== new Date(result.completed_ms).toISOString().replace(/\.\d{3}Z$/, 'Z') ||
        m.as_of !== prepared.as_of || !same(m.expected_index, input.expected_index) ||
        !same(m.candidate_archive, input.candidate_archive) || !Number.isSafeInteger(m.member_count) || m.member_count < 0 ||
        typeof m.members_fingerprint !== 'string' || !/^sha256:[a-f0-9]{64}$/.test(m.members_fingerprint)) {
      throw new Error('membership_session_result_binding_invalid');
    }
    return result;
  }
  async accept(token, inputHash, resultBytes) {
    this.#enabled();
    if (!(resultBytes instanceof Uint8Array) || !resultBytes.length || resultBytes.length > 65536) {
      throw new Error('membership_session_result_invalid');
    }
    const frozen = new Uint8Array(resultBytes);
    const verifiedIdentity = await this.#verifier.verify(token);
    const record = this.#pair('input', inputHash);
    if (record.input_archive.sha256 !== inputHash || record.binding !== this.#binding) throw new Error('membership_session_input_mismatch');
    this.#guard(record, verifiedIdentity, this.#index.readCurrent(record.identity, record.selection.lease_token, this.#resource));
    // Actual stored input is necessary even on an acknowledged-success retry.
    const raw = await this.#read(record.input_archive), input = parse(raw);
    if (!same(input.identity, record.identity) || !same(preparation(input).evidence.current_history, record.current_history)) {
      throw new Error('membership_session_input_mismatch');
    }
    const prior = this.#pair('return', inputHash, true);
    const expected = prior ? prior.current_index : input.expected_index;
    await this.#fresh(token, record, input, expected);
    const result = this.#result(record, input, raw, frozen), fingerprint = await hash(frozen);
    let output;
    if (prior) {
      if (prior.output_archive.sha256 !== fingerprint || prior.input_sha256 !== inputHash || prior.binding !== this.#binding) {
        throw new Error('membership_session_return_conflict');
      }
      output = prior.output_archive;
    } else {
      output = await this.#archive.put('raw/' + fingerprint.slice(7), frozen, { sha256: fingerprint, size_bytes: frozen.length });
    }
    // Re-read the output itself, not just the caller's body or put response.
    const actual = await this.#read(output);
    this.#result(record, input, raw, actual);
    await this.#read(record.input_archive);
    const identity = await this.#fresh(token, record, input, expected);
    return this.#storage.transactionSync(() => {
      if (!same(record, this.#pair('input', inputHash)) || !same(prior, this.#pair('return', inputHash, true))) {
        throw new Error('membership_session_records_changed');
      }
      this.#guard(record, identity, expected);
      if (prior) return structuredClone(prior);
      const current = this.#index.append(record.identity, record.selection.lease_token, this.#resource, {
        as_of: result.membership_registration.as_of, expected_index: input.expected_index, observation_archive: input.candidate_archive });
      const receipt = { binding: this.#binding, input_sha256: inputHash, output_archive: output,
        current_index: current, registered_ms: this.#time() };
      this.#save('return', inputHash, receipt);
      this.#guard(record, identity, current);
      return structuredClone(receipt);
    });
  }
}
