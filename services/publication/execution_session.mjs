// Internal fixed-computation binding, not an RPC, identity verifier or data license.
// Identities must come from the existing trusted boundary; returning worker must
// be the pinned execution runtime. Callers cannot supply a source inventory graph.
import { ImmutableArchive } from './archive.mjs';
import { ExecutionTaskArchive } from './execution_archive.mjs';

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
  return value;
}
const bytes = value => new TextEncoder().encode(JSON.stringify(canonical(value)));
const same = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
async function sha(value) {
  return 'sha256:' + Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', value)), v => v.toString(16).padStart(2, '0')).join('');
}
function b64(value) {
  let text = '';
  for (let i = 0; i < value.length; i += 8192) text += String.fromCharCode(...value.subarray(i, i + 8192));
  return btoa(text);
}
function unb64(value) {
  if (typeof value !== 'string') throw new Error('execution_result_encoding_invalid');
  const raw = Uint8Array.from(atob(value), v => v.charCodeAt(0));
  if (b64(raw) !== value) throw new Error('execution_result_encoding_invalid');
  return raw;
}
function actor(identity) {
  return { job: identity.job, code_commit: identity.code_commit, actor_id: identity.actor_id, subject: identity.subject };
}

export class ExecutionComputationSession {
  #storage; #tasks; #archive;
  constructor(storage, bucket, options = {}) {
    this.#storage = storage;
    this.#tasks = new ExecutionTaskArchive(storage, bucket, options);
    this.#archive = new ImmutableArchive(bucket);
    storage.transactionSync(() => {
      this.#sql('CREATE TABLE IF NOT EXISTS m12_execution_validation_head (singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL)');
      this.#sql('CREATE TABLE IF NOT EXISTS m12_execution_validation_inputs (position INTEGER PRIMARY KEY, input_sha TEXT UNIQUE NOT NULL, record_json TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0)');
      this.#sql('CREATE TABLE IF NOT EXISTS m12_execution_validation_input_log (position INTEGER PRIMARY KEY, record_json TEXT NOT NULL)');
      this.#sql('CREATE TABLE IF NOT EXISTS m12_execution_validation_results (input_sha TEXT PRIMARY KEY, record_json TEXT NOT NULL)');
      this.#sql('CREATE TABLE IF NOT EXISTS m12_execution_validation_result_log (input_sha TEXT PRIMARY KEY, record_json TEXT NOT NULL)');
    });
  }
  #sql(query, ...args) { return this.#storage.sql.exec(query, ...args).toArray(); }
  initializeEmpty() {
    this.#storage.transactionSync(() => {
      for (const name of ['head', 'inputs', 'input_log', 'results', 'result_log']) {
        if (this.#sql('SELECT * FROM m12_execution_validation_' + name + ' LIMIT 1').length) throw new Error('execution_validation_not_empty');
      }
      this.#sql('INSERT INTO m12_execution_validation_head VALUES (1,0)');
    });
  }
  #catalog() {
    const head = this.#sql('SELECT revision FROM m12_execution_validation_head WHERE singleton=1')[0];
    const rows = this.#sql('SELECT * FROM m12_execution_validation_inputs ORDER BY position');
    const logs = this.#sql('SELECT * FROM m12_execution_validation_input_log ORDER BY position');
    const results = this.#sql('SELECT * FROM m12_execution_validation_results ORDER BY input_sha');
    const resultLogs = this.#sql('SELECT * FROM m12_execution_validation_result_log ORDER BY input_sha');
    if (!head || head.revision !== rows.length || rows.length !== logs.length ||
        results.length !== rows.filter(row => row.completed === 1).length || !same(results, resultLogs)) throw new Error('execution_validation_recovery_required');
    return rows.map((row, index) => {
      const record = JSON.parse(row.record_json);
      if (row.position !== index + 1 || logs[index].position !== row.position || logs[index].record_json !== row.record_json ||
          record.input.sha256 !== row.input_sha || ![0, 1].includes(row.completed)) throw new Error('execution_validation_history_invalid');
      const result = results.find(item => item.input_sha === row.input_sha);
      if (Boolean(result) !== Boolean(row.completed)) throw new Error('execution_validation_result_missing');
      return { ...record, result: result ? JSON.parse(result.record_json) : null };
    });
  }
  async #read(ref) { return this.#archive.read(ref.key, { sha256: ref.sha256, size_bytes: ref.size_bytes }); }
  async #save(raw) {
    const digest = await sha(raw);
    return this.#archive.put('raw/' + digest.slice(7), raw, { sha256: digest, size_bytes: raw.length });
  }
  async prepare(identity, token, taskId, requestBytes) {
    identity = structuredClone(identity); token = structuredClone(token);
    if (!(requestBytes instanceof Uint8Array)) throw new Error('execution_request_bytes_required');
    const request = new Uint8Array(requestBytes);
    const { current, objects } = await this.#tasks.readTask(identity, token, taskId);
    const raw = bytes({ protocol: 'm12-execution-validation/1', identity, snapshot: current,
      objects: Object.fromEntries([...objects].map(([key, value]) => [key, b64(value)])), request_bytes: b64(request) });
    if (raw.length > 32 * 1024 * 1024) throw new Error('execution_input_too_large');
    const digest = await sha(raw);
    const catalog = this.#tasks.withCurrentTask(identity, token, taskId, current, () => this.#catalog());
    const existing = catalog.find(row => row.input.sha256 === digest);
    const input = existing ? existing.input : await this.#save(raw);
    if (existing) await this.#read(input); // Missing registered input never heals.
    this.#tasks.withCurrentTask(identity, token, taskId, current, ({ now }) => {
      if (!same(catalog, this.#catalog())) throw new Error('execution_validation_compare_failed');
      if (existing) return;
      const position = catalog.length + 1;
      const record = JSON.stringify({ input, task_id: taskId, snapshot: current, identity, recorded_ms: now });
      this.#sql('INSERT INTO m12_execution_validation_inputs (position,input_sha,record_json) VALUES (?,?,?)', position, digest, record);
      this.#sql('INSERT INTO m12_execution_validation_input_log VALUES (?,?)', position, record);
      this.#sql('UPDATE m12_execution_validation_head SET revision=? WHERE singleton=1', position);
    });
    return { input, input_bytes: new Uint8Array(raw) };
  }
  async accept(identity, token, inputSha, outputBytes) {
    identity = structuredClone(identity); token = structuredClone(token);
    if (!(outputBytes instanceof Uint8Array) || !outputBytes.length || outputBytes.length > 2 * 1024 * 1024) throw new Error('execution_output_size_invalid');
    const raw = new Uint8Array(outputBytes);
    const pending = this.#catalog().find(row => row.input.sha256 === inputSha);
    if (!pending || !same(actor(identity), actor(pending.identity))) throw new Error('execution_validation_actor_mismatch');
    identity.expires_at = Math.min(identity.expires_at, pending.identity.expires_at);
    this.#tasks.withCurrentTask(identity, token, pending.task_id, pending.result?.snapshot ?? pending.snapshot, () => {
      if (!same(pending, this.#catalog().find(row => row.input.sha256 === inputSha))) throw new Error('execution_validation_compare_failed');
    });
    await this.#read(pending.input);
    const result = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw));
    if (Object.keys(result).sort().join() !== 'completed_ms,input_sha256,input_size_bytes,inventory_bytes,next_pair,protocol,snapshot_sha256,started_ms,task_id' ||
        result.protocol !== 'm12-execution-validation/1' || result.input_sha256 !== inputSha || result.input_size_bytes !== pending.input.size_bytes ||
        result.task_id !== pending.task_id || result.snapshot_sha256 !== await sha(bytes(pending.snapshot)) ||
        !Number.isSafeInteger(result.started_ms) || !Number.isSafeInteger(result.completed_ms) ||
        result.started_ms < pending.recorded_ms || result.completed_ms < result.started_ms ||
        result.completed_ms >= pending.identity.expires_at * 1000 || result.completed_ms - result.started_ms >= 30000) throw new Error('execution_validation_output_binding_invalid');
    const inventory = unb64(result.inventory_bytes);
    if (!inventory.length) throw new Error('execution_inventory_output_empty');
    if (pending.result) {
      const stored = await this.#read(pending.result.output);
      if (stored.length !== raw.length || stored.some((value, i) => value !== raw[i])) throw new Error('execution_validation_output_conflict');
      const { current } = await this.#tasks.readTask(identity, token, pending.task_id);
      if (!same(current, pending.result.snapshot)) throw new Error('execution_validation_compare_failed');
      return this.#tasks.withCurrentTask(identity, token, pending.task_id, pending.result.snapshot, context => {
        if (result.completed_ms > context.now) throw new Error('execution_result_completed_in_future');
        if (!same(pending, this.#catalog().find(row => row.input.sha256 === inputSha))) throw new Error('execution_validation_compare_failed');
        return pending.result;
      });
    }
    const { current } = await this.#tasks.readTask(identity, token, pending.task_id);
    if (!same(current, pending.snapshot)) throw new Error('execution_validation_compare_failed');
    const output = await this.#save(raw);
    await this.#read(pending.input);
    await this.#read(output);
    const finish = (snapshot, context) => {
      if (result.completed_ms > context.now) throw new Error('execution_result_completed_in_future');
      if (!same(pending, this.#catalog().find(row => row.input.sha256 === inputSha))) throw new Error('execution_validation_compare_failed');
      const record = JSON.stringify({ input: pending.input, output, source_snapshot: pending.snapshot, snapshot });
      this.#sql('INSERT INTO m12_execution_validation_results VALUES (?,?)', inputSha, record);
      this.#sql('INSERT INTO m12_execution_validation_result_log VALUES (?,?)', inputSha, record);
      this.#sql('UPDATE m12_execution_validation_inputs SET completed=1 WHERE input_sha=?', inputSha);
    };
    if (result.next_pair === null) {
      const reread = await this.#tasks.readTask(identity, token, pending.task_id);
      if (!same(reread.current, current)) throw new Error('execution_validation_compare_failed');
      this.#tasks.withCurrentTask(identity, token, pending.task_id, current, (context, snapshot) => finish(snapshot, context));
    } else {
      const pair = result.next_pair;
      if (Object.keys(pair).sort().join() !== 'input_bytes,link_bytes,object_bytes,step_id') throw new Error('execution_result_pair_invalid');
      await this.#tasks.appendPair(identity, token, pending.task_id, current, pair.step_id,
        unb64(pair.input_bytes), unb64(pair.object_bytes), unb64(pair.link_bytes), finish, [pending.input, output]);
    }
    const completed = this.#catalog().find(row => row.input.sha256 === inputSha)?.result;
    if (!completed) throw new Error('execution_validation_result_missing');
    return this.#tasks.withCurrentTask(identity, token, pending.task_id, completed.snapshot, () => completed);
  }
}
