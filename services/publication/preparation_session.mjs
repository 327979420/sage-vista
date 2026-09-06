// Internal server session only; a pinned runner's result is necessary evidence,
// not a supplier license. No route, automatic dispatch or production policy.
import { PreparationEvidenceReadback } from './preparation_readback.mjs';
import { GitHubIdentityVerifier } from './identity.mjs';
import { AuthorizationStore } from './authorization_store.mjs';
import { ImmutableArchive } from './archive.mjs';

const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ?
  Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const encode = value => JSON.stringify(canonical(value));
const same = (a, b) => encode(a) === encode(b);
const exact = (value, fields) => {
  if (!value || Array.isArray(value) || typeof value !== 'object' || Object.keys(value).sort().join() !== fields.sort().join()) {
    throw new Error('preparation_session_fields_invalid');
  }
};
const sha = async bytes => 'sha256:' + Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
  v => v.toString(16).padStart(2, '0')).join('');
const newYorkDay = milliseconds => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).format(milliseconds);
const parse = bytes => JSON.parse(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes));
const handleCopy = handle => {
  exact(handle, ['epoch', 'fence']);
  return { ...handle };
};

export class PreparationValidationSession {
  #policy;
  #binding;
  #readback;
  #verifier;
  #store;
  #archive;
  #storage;
  #clock;
  #resource;

  constructor(identityPolicy, { preparationPolicy = null, storage, bucket, clock = Date.now, fetchKeys } = {}) {
    if (preparationPolicy === null) return;
    this.#readback = new PreparationEvidenceReadback(identityPolicy, { preparationPolicy, storage, bucket, clock, fetchKeys });
    this.#verifier = new GitHubIdentityVerifier(identityPolicy, { clock, fetchKeys });
    this.#store = new AuthorizationStore(storage, { clock });
    this.#archive = new ImmutableArchive(bucket);
    this.#storage = storage;
    this.#clock = clock;
    this.#policy = structuredClone(preparationPolicy);
    this.#binding = encode({ identity: identityPolicy, preparation: preparationPolicy });
    this.#resource = `daily/${this.#policy.as_of}/${this.#policy.config_ref.id}`;
    storage.transactionSync(() => {
      for (const table of ['m12_preparation_inputs', 'm12_preparation_input_log', 'm12_preparation_returns', 'm12_preparation_return_log']) {
        this.#exec(`CREATE TABLE IF NOT EXISTS ${table} (key TEXT PRIMARY KEY, record_json TEXT NOT NULL)`);
      }
    });
  }

  #exec(sql, ...args) { return this.#storage.sql.exec(sql, ...args).toArray(); }
  #enabled() { if (!this.#policy) throw new Error('preparation_session_disabled'); }
  #pair(table, log, key) {
    const rows = this.#exec(`SELECT record_json FROM ${table} WHERE key=?`, key);
    const logs = this.#exec(`SELECT record_json FROM ${log} WHERE key=?`, key);
    if (rows.length !== 1 || logs.length !== 1 || rows[0].record_json !== logs[0].record_json) {
      throw new Error('preparation_session_record_missing_or_corrupt');
    }
    return JSON.parse(rows[0].record_json);
  }
  #save(table, log, key, record) {
    const count = this.#exec(`SELECT key FROM ${table} WHERE key=?`, key).length + this.#exec(`SELECT key FROM ${log} WHERE key=?`, key).length;
    if (count) {
      const prior = this.#pair(table, log, key);
      if (!same(prior, record)) throw new Error('preparation_session_record_conflict');
      return prior;
    }
    this.#exec(`INSERT INTO ${table} VALUES (?,?)`, key, encode(record));
    this.#exec(`INSERT INTO ${log} VALUES (?,?)`, key, encode(record));
    return record;
  }
  #current(identity, handle, record) {
    if (record.binding !== this.#binding || !same(record.lease_token, handle) ||
        !same(record.identity.job, identity.job) || record.identity.actor_id !== identity.actor_id ||
        record.identity.code_commit !== identity.code_commit) throw new Error('preparation_session_origin_mismatch');
    const current = this.#store.readCurrentForPreparation(identity, handle, this.#resource);
    // Neither a renewed JWT nor a new lease revives the original input window.
    const original = this.#store.readCurrentForPreparation(record.identity, handle, this.#resource);
    if (!same(current, record.current_history) || !same(original, current)) throw new Error('preparation_session_history_changed');
    const now = this.#time();
    if (now >= Math.min(identity.expires_at, record.identity.expires_at) * 1000 ||
        newYorkDay(record.recorded_ms) !== newYorkDay(now)) throw new Error('preparation_session_window_changed');
  }
  #load(identity, handle, inputHash) {
    const record = this.#pair('m12_preparation_inputs', 'm12_preparation_input_log', inputHash);
    if (record.input_archive.sha256 !== inputHash) throw new Error('preparation_session_input_mismatch');
    this.#current(identity, handle, record);
    return record;
  }
  #time() {
    const now = this.#clock();
    if (!Number.isSafeInteger(now) || now < 0) throw new Error('preparation_session_clock_invalid');
    return now;
  }

  async prepare(token, leaseToken) {
    this.#enabled();
    const handle = handleCopy(leaseToken);
    const raw = await this.#readback.readValidationInput(token, handle);
    const input = parse(raw);
    const record = { binding: this.#binding, identity: input.identity, lease_token: handle,
      current_history: input.evidence.current_history, input_archive: null, recorded_ms: this.#time() };
    const fingerprint = await sha(raw);
    this.#current(input.identity, handle, record);
    record.input_archive = await this.#archive.put('raw/' + fingerprint.slice(7), raw, { sha256: fingerprint, size_bytes: raw.length });
    this.#current(input.identity, handle, record);
    return this.#storage.transactionSync(() => {
      this.#current(input.identity, handle, record);
      const existing = this.#exec('SELECT key FROM m12_preparation_inputs WHERE key=?', fingerprint).length;
      if (existing) record.recorded_ms = this.#pair('m12_preparation_inputs', 'm12_preparation_input_log', fingerprint).recorded_ms;
      else record.recorded_ms = this.#time();
      this.#save('m12_preparation_inputs', 'm12_preparation_input_log', fingerprint, record);
      this.#current(input.identity, handle, record);
      return { input_archive: { ...record.input_archive }, input_bytes: raw };
    });
  }

  async #verify(identity, handle, inputHash, frozen) {
    const record = this.#load(identity, handle, inputHash);
    const { key, sha256, size_bytes } = record.input_archive;
    const raw = await this.#archive.read(key, { sha256, size_bytes });
    if (!same(this.#load(identity, handle, inputHash), record)) throw new Error('preparation_session_input_changed');
    const input = parse(raw);
    if (input.protocol !== 'm12-preparation-validation/1' || !same(input.identity, record.identity) ||
        !same(input.evidence.current_history, record.current_history) ||
        !same(input.evidence.config_ref, this.#policy.config_ref) || !same(input.evidence.config_archive, this.#policy.config_archive) ||
        input.evidence.as_of !== this.#policy.as_of || input.evidence.code_commit !== identity.code_commit) {
      throw new Error('preparation_session_input_mismatch');
    }
    const result = parse(frozen);
    if (encode(result) + '\n' !== new TextDecoder().decode(frozen)) throw new Error('preparation_session_result_encoding_invalid');
    exact(result, ['protocol', 'input_sha256', 'input_size_bytes', 'started_ms', 'completed_ms', 'preparation']);
    const p = result.preparation;
    const now = this.#time();
    exact(p, ['authorization_ref', 'config_ref', 'config_archive', 'code_commit', 'as_of', 'checked_at', 'history_revision']);
    if (result.protocol !== input.protocol || result.input_sha256 !== inputHash || result.input_size_bytes !== raw.length ||
        !Number.isSafeInteger(result.started_ms) || !Number.isSafeInteger(result.completed_ms) ||
        result.started_ms < record.recorded_ms || result.started_ms < Date.parse(input.evidence.checked_at) ||
        result.completed_ms < result.started_ms || result.completed_ms > now ||
        newYorkDay(result.completed_ms) !== newYorkDay(now) ||
        result.completed_ms >= record.identity.expires_at * 1000 ||
        !same(p.authorization_ref, record.current_history.head) || p.history_revision !== record.current_history.revision ||
        !same(p.config_ref, this.#policy.config_ref) || !same(p.config_archive, this.#policy.config_archive) ||
        p.code_commit !== identity.code_commit || p.as_of !== this.#policy.as_of ||
        p.checked_at !== new Date(result.completed_ms).toISOString().replace(/\.\d{3}Z$/, 'Z')) {
      throw new Error('preparation_session_result_binding_invalid');
    }
    this.#current(identity, handle, record);
    return { record, result };
  }

  async accept(token, leaseToken, inputHash, resultBytes) {
    this.#enabled();
    const handle = handleCopy(leaseToken);
    if (!(resultBytes instanceof Uint8Array) || !resultBytes.length || resultBytes.length > 65536) throw new Error('preparation_session_result_invalid');
    const frozen = new Uint8Array(resultBytes);
    const identity = await this.#verifier.verify(token);
    const verified = await this.#verify(identity, handle, inputHash, frozen);
    const fingerprint = await sha(frozen);
    this.#current(identity, handle, verified.record);
    const output = await this.#archive.put('raw/' + fingerprint.slice(7), frozen, { sha256: fingerprint, size_bytes: frozen.length });
    return this.#storage.transactionSync(() => {
      if (!same(this.#load(identity, handle, inputHash), verified.record)) throw new Error('preparation_session_input_changed');
      const result = { input_sha256: inputHash, output_archive: output, binding: this.#binding };
      this.#save('m12_preparation_returns', 'm12_preparation_return_log', inputHash + '/' + fingerprint, result);
      this.#current(identity, handle, verified.record);
      return { input_sha256: inputHash, output_archive: { ...output } };
    });
  }

  async readForUse(token, leaseToken, inputHash, outputHash) {
    this.#enabled();
    const handle = handleCopy(leaseToken);
    const identity = await this.#verifier.verify(token);
    this.#load(identity, handle, inputHash);
    const key = inputHash + '/' + outputHash;
    const record = this.#pair('m12_preparation_returns', 'm12_preparation_return_log', key);
    if (record.binding !== this.#binding || record.input_sha256 !== inputHash || record.output_archive.sha256 !== outputHash) throw new Error('preparation_session_return_mismatch');
    const { key: location, sha256, size_bytes } = record.output_archive;
    const bytes = await this.#archive.read(location, { sha256, size_bytes });
    // Re-read ALL current authorization/config originals, not just archived
    // copies embedded in yesterday's validation input. No cached use permit.
    const fresh = await this.#readback.read(token, handle);
    this.#load(fresh.identity, handle, inputHash);
    const verified = await this.#verify(identity, handle, inputHash, bytes);
    if (!same(record, this.#pair('m12_preparation_returns', 'm12_preparation_return_log', key))) throw new Error('preparation_session_return_changed');
    this.#current(identity, handle, verified.record);
    return { identity, preparation: verified.result.preparation, input_sha256: inputHash, output_archive: { ...record.output_archive } };
  }
}
