// Internal byte storage, not a business validator or authenticated RPC.
// Only the future fixed, original-contract-validated coordinator may call writes.
// Durable sequence numbers prove paired bytes, never trading-date completion.
import { ImmutableArchive } from './archive.mjs';
import { LeaseStore } from './leases.mjs';

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const sameBytes = (a, b) => a.length === b.length && a.every((value, i) => value === b[i]);
const TASK = /^execution-task:sha256:[a-f0-9]{64}$/;
const GENESIS = 'm12-execution-archive/1';
const MAX_BYTES = 32 * 1024 * 1024;
function descriptor(value) {
  if (!value || Object.keys(value).sort().join() !== 'key,sha256,size_bytes' ||
      !/^sha256:[a-f0-9]{64}$/.test(value.sha256) || value.key !== 'raw/' + value.sha256.slice(7) ||
      !Number.isSafeInteger(value.size_bytes) || value.size_bytes < 1 || value.size_bytes > MAX_BYTES) {
    throw new Error('execution_archive_descriptor_invalid');
  }
  return { key: value.key, sha256: value.sha256, size_bytes: value.size_bytes };
}
function task(value) {
  if (typeof value !== 'string' || !TASK.test(value)) throw new Error('execution_task_invalid');
  return value;
}

export class ExecutionTaskArchive {
  #storage; #archive; #leases;
  constructor(storage, bucket, { clock = Date.now } = {}) {
    this.#storage = storage;
    this.#archive = new ImmutableArchive(bucket);
    this.#leases = new LeaseStore(storage, { clock });
    storage.transactionSync(() => {
      this.#sql('CREATE TABLE IF NOT EXISTS m12_execution_catalog_head (singleton INTEGER PRIMARY KEY CHECK(singleton=1), marker TEXT NOT NULL, revision INTEGER NOT NULL)');
      this.#sql('CREATE TABLE IF NOT EXISTS m12_execution_catalog (position INTEGER PRIMARY KEY, task_id TEXT UNIQUE NOT NULL, record_json TEXT NOT NULL)');
      this.#sql('CREATE TABLE IF NOT EXISTS m12_execution_catalog_log (position INTEGER PRIMARY KEY, record_json TEXT NOT NULL)');
      this.#sql('CREATE TABLE IF NOT EXISTS m12_execution_heads (task_id TEXT PRIMARY KEY, revision INTEGER NOT NULL)');
      this.#sql('CREATE TABLE IF NOT EXISTS m12_execution_pairs (task_id TEXT NOT NULL, position INTEGER NOT NULL, step_id TEXT NOT NULL, record_json TEXT NOT NULL, PRIMARY KEY(task_id,position), UNIQUE(task_id,step_id))');
      this.#sql('CREATE TABLE IF NOT EXISTS m12_execution_pair_log (task_id TEXT NOT NULL, position INTEGER NOT NULL, record_json TEXT NOT NULL, PRIMARY KEY(task_id,position))');
    });
  }
  #sql(query, ...values) { return this.#storage.sql.exec(query, ...values).toArray(); }
  initializeEmpty() {
    return this.#storage.transactionSync(() => {
      for (const table of ['catalog_head', 'catalog', 'catalog_log', 'heads', 'pairs', 'pair_log']) {
        if (this.#sql('SELECT * FROM m12_execution_' + table + ' LIMIT 1').length) throw new Error('execution_not_empty');
      }
      this.#sql('INSERT INTO m12_execution_catalog_head VALUES (1, ?, 0)', GENESIS);
    });
  }
  #owned(identity, token, resource, callback, resolveDeadlineMs) {
    if (!identity || !Number.isSafeInteger(identity.issued_at) || !Number.isSafeInteger(identity.expires_at) ||
        !Number.isSafeInteger(identity.expires_at * 1000) || identity.issued_at >= identity.expires_at) {
      throw new Error('execution_trusted_identity_required');
    }
    return this.#leases.withOwnedLease(resource, identity.job, token, context => {
      if (context.now < identity.issued_at * 1000) throw new Error('execution_identity_not_yet_valid');
      return callback(context);
    }, { deadlineMs: identity.expires_at * 1000, resolveDeadlineMs });
  }
  #catalog() {
    const head = this.#sql('SELECT * FROM m12_execution_catalog_head WHERE singleton=1')[0];
    const rows = this.#sql('SELECT * FROM m12_execution_catalog ORDER BY position');
    const logs = this.#sql('SELECT * FROM m12_execution_catalog_log ORDER BY position');
    const heads = this.#sql('SELECT * FROM m12_execution_heads ORDER BY task_id');
    if (!head || head.marker !== GENESIS || !Number.isSafeInteger(head.revision) ||
        head.revision !== rows.length || logs.length !== rows.length || heads.length !== rows.length) {
      throw new Error('execution_catalog_recovery_required');
    }
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i], value = JSON.parse(row.record_json);
      if (row.position !== i + 1 || logs[i].position !== row.position || logs[i].record_json !== row.record_json ||
          value.task_id !== task(row.task_id) || value.position !== row.position ||
          !heads.some(item => item.task_id === row.task_id)) throw new Error('execution_catalog_corrupt');
      descriptor(value.root);
    }
    if (this.#sql('SELECT task_id FROM m12_execution_pairs WHERE task_id NOT IN (SELECT task_id FROM m12_execution_catalog) LIMIT 1').length ||
        this.#sql('SELECT task_id FROM m12_execution_pair_log WHERE task_id NOT IN (SELECT task_id FROM m12_execution_catalog) LIMIT 1').length) {
      throw new Error('execution_orphan_index');
    }
    return rows.map(row => JSON.parse(row.record_json));
  }
  #snapshot(taskId) {
    const root = this.#catalog().find(row => row.task_id === taskId);
    if (!root) throw new Error('execution_task_missing');
    const head = this.#sql('SELECT revision FROM m12_execution_heads WHERE task_id=?', taskId)[0];
    const rows = this.#sql('SELECT * FROM m12_execution_pairs WHERE task_id=? ORDER BY position', taskId);
    const logs = this.#sql('SELECT * FROM m12_execution_pair_log WHERE task_id=? ORDER BY position', taskId);
    if (!head || !Number.isSafeInteger(head.revision) || head.revision !== rows.length || rows.length !== logs.length) {
      throw new Error('execution_history_recovery_required');
    }
    let previous = null;
    const history = rows.map((row, i) => {
      const value = JSON.parse(row.record_json);
      if (row.position !== i + 1 || logs[i].position !== row.position || logs[i].record_json !== row.record_json ||
          value.task_id !== taskId || value.position !== row.position || value.step_id !== row.step_id ||
          value.previous_step_id !== previous) throw new Error('execution_history_corrupt');
      for (const item of [value.input, value.object, value.link]) descriptor(item);
      previous = value.step_id;
      return value;
    });
    return { root, revision: head.revision, history };
  }
  // Internal scheduling discovery only; no read capability or write permission
  // escapes. Claiming still requires the task lease and full readTask originals.
  registeredTasks() {
    return this.#storage.transactionSync(() => this.#catalog().map(row => this.#snapshot(row.task_id)));
  }
  listTasks(identity, token, dailyResource) {
    if (!dailyResource.startsWith('daily/')) throw new Error('execution_daily_lease_required');
    return this.#owned(identity, token, dailyResource, () => this.#catalog().map(row => this.#snapshot(row.task_id)));
  }
  #check(identity, token, resource, taskId, expected) {
    return this.#owned(identity, token, resource, () => {
      const current = this.#snapshot(taskId);
      if (expected && !same(expected, current)) throw new Error('execution_compare_failed');
      return current;
    });
  }
  async #save(bytes) {
    if (!(bytes instanceof Uint8Array) || bytes.length < 1 || bytes.length > MAX_BYTES) throw new Error('execution_bytes_invalid');
    const copy = new Uint8Array(bytes);
    const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', copy));
    const sha256 = 'sha256:' + Array.from(hash, v => v.toString(16).padStart(2, '0')).join('');
    return this.#archive.put('raw/' + sha256.slice(7), copy, { sha256, size_bytes: copy.length });
  }
  async #read(item) {
    const value = descriptor(item);
    return this.#archive.read(value.key, { sha256: value.sha256, size_bytes: value.size_bytes });
  }
  async register(identity, token, dailyResource, taskId, rootBytes) {
    identity = structuredClone(identity); token = structuredClone(token);
    task(taskId);
    if (!dailyResource.startsWith('daily/')) throw new Error('execution_daily_lease_required');
    const catalog = this.#owned(identity, token, dailyResource, () => this.#catalog());
    if (!(rootBytes instanceof Uint8Array) || rootBytes.length < 1 || rootBytes.length > MAX_BYTES) throw new Error('execution_bytes_invalid');
    const frozen = new Uint8Array(rootBytes);
    const old = catalog.find(row => row.task_id === taskId);
    if (old) {
      // Never heal an absent original, including after a lost successful reply.
      const original = await this.#read(old.root);
      if (!sameBytes(original, frozen)) throw new Error('execution_root_conflict');
      return this.#owned(identity, token, dailyResource, () => {
        if (!same(catalog, this.#catalog())) throw new Error('execution_compare_failed');
        return this.#snapshot(taskId);
      });
    }
    const root = await this.#save(frozen);
    return this.#owned(identity, token, dailyResource, ({ now, epoch, lease }) => {
      if (!same(catalog, this.#catalog())) throw new Error('execution_compare_failed');
      const position = catalog.length + 1;
      const record = JSON.stringify({ task_id: taskId, position, root,
        owner_job: lease.owner_job, epoch, fence: lease.fence, recorded_ms: now });
      this.#sql('INSERT INTO m12_execution_catalog VALUES (?, ?, ?)', position, taskId, record);
      this.#sql('INSERT INTO m12_execution_catalog_log VALUES (?, ?)', position, record);
      this.#sql('INSERT INTO m12_execution_heads VALUES (?, 0)', taskId);
      this.#sql('UPDATE m12_execution_catalog_head SET revision=? WHERE singleton=1', position);
      return this.#snapshot(taskId);
    });
  }
  withCurrentTask(identity, token, taskId, expected, callback, { resolveDeadlineMs } = {}) {
    if (typeof callback !== 'function' || callback.constructor.name === 'AsyncFunction') throw new Error('execution_callback_must_be_synchronous');
    const resource = 'execution/' + task(taskId);
    return this.#owned(identity, token, resource, context => {
      const current = this.#snapshot(taskId);
      if (!same(expected, current)) throw new Error('execution_compare_failed');
      const result = callback(context, current);
      if (result && typeof result.then === 'function') throw new Error('execution_callback_must_be_synchronous');
      return result;
    }, resolveDeadlineMs);
  }
  async readTask(identity, token, taskId) {
    identity = structuredClone(identity); token = structuredClone(token);
    const resource = 'execution/' + task(taskId);
    const current = this.#check(identity, token, resource, taskId);
    const objects = new Map();
    const refs = [current.root.root, ...current.history.flatMap(row => [row.input, row.object, row.link])];
    for (const item of refs) {
      const bytes = await this.#read(item);
      this.#check(identity, token, resource, taskId, current);
      objects.set(item.key, bytes);
    }
    return { current, objects }; // Full server-owned history; not SourceInventory.
  }
  async appendPair(identity, token, taskId, expected, stepId, inputBytes, objectBytes, linkBytes, onCommit = null, completionOriginals = []) {
    identity = structuredClone(identity); token = structuredClone(token);
    const resource = 'execution/' + task(taskId);
    if (onCommit !== null && (typeof onCommit !== 'function' || onCommit.constructor.name === 'AsyncFunction')) throw new Error('execution_callback_must_be_synchronous');
    if (typeof stepId !== 'string' || !/^sha256:[a-f0-9]{64}$/.test(stepId)) throw new Error('execution_step_invalid');
    const completionRefs = completionOriginals.map(item => descriptor(item));
    const frozenExpected = structuredClone(expected);
    const originals = [inputBytes, objectBytes, linkBytes].map(bytes => {
      if (!(bytes instanceof Uint8Array) || bytes.length < 1 || bytes.length > MAX_BYTES) throw new Error('execution_bytes_invalid');
      return new Uint8Array(bytes);
    });
    const { current, objects } = await this.readTask(identity, token, taskId);
    if (!same(frozenExpected, current)) throw new Error('execution_compare_failed');
    const old = current.history.find(row => row.step_id === stepId);
    if (old) {
      if (onCommit !== null) throw new Error('execution_pair_already_registered');
      [old.input, old.object, old.link].forEach((ref, i) => {
        if (!sameBytes(objects.get(ref.key), originals[i])) throw new Error('execution_step_conflict');
      });
      return this.#check(identity, token, resource, taskId, current);
    }
    const refs = [];
    for (const bytes of originals) {
      refs.push(await this.#save(bytes));
      this.#check(identity, token, resource, taskId, current);
    }
    // Verify all three original objects together after their last write.
    for (const ref of refs) {
      await this.#read(ref);
      this.#check(identity, token, resource, taskId, current);
    }
    // Recheck computation originals and all registered history after pair writes.
    // These are archive descriptors only; business validation stays in Python.
    for (const ref of completionRefs) {
      await this.#read(ref);
      this.#check(identity, token, resource, taskId, current);
    }
    const reread = await this.readTask(identity, token, taskId);
    if (!same(current, reread.current)) throw new Error('execution_compare_failed');
    return this.#owned(identity, token, resource, ({ now, epoch, lease }) => {
      if (!same(current, this.#snapshot(taskId))) throw new Error('execution_compare_failed');
      const position = current.revision + 1;
      const record = JSON.stringify({ task_id: taskId, position, step_id: stepId,
        previous_step_id: current.history.at(-1)?.step_id ?? null,
        input: refs[0], object: refs[1], link: refs[2], owner_job: lease.owner_job,
        epoch, fence: lease.fence, recorded_ms: now });
      this.#sql('INSERT INTO m12_execution_pairs VALUES (?, ?, ?, ?)', taskId, position, stepId, record);
      this.#sql('INSERT INTO m12_execution_pair_log VALUES (?, ?, ?)', taskId, position, record);
      this.#sql('UPDATE m12_execution_heads SET revision=? WHERE task_id=?', position, taskId);
      const completed = this.#snapshot(taskId);
      if (onCommit !== null) {
        const result = onCommit(completed, { now, epoch, lease });
        if (result && typeof result.then === 'function') throw new Error('execution_callback_must_be_synchronous');
      }
      return completed;
    });
  }
}
