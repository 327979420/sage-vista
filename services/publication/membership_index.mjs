// Internal storage component only, not an authenticated RPC or source validator.
// The fixed coordinator must verify successful original acquisition bytes and
// its bound Python result before invoking append. No live adapter is installed.
import { LeaseStore } from './leases.mjs';

const GENESIS = 'm12-membership-index/1';
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function archive(value) {
  if (!value || Object.keys(value).sort().join() !== 'key,sha256,size_bytes' ||
      typeof value.sha256 !== 'string' || !/^sha256:[a-f0-9]{64}$/.test(value.sha256) ||
      value.key !== 'raw/' + value.sha256.slice(7) || !Number.isSafeInteger(value.size_bytes) ||
      value.size_bytes < 1 || value.size_bytes > 16384) throw new Error('membership_index_archive_invalid');
  return { key: value.key, sha256: value.sha256, size_bytes: value.size_bytes };
}

function day(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('membership_index_date_invalid');
  const time = new Date(value + 'T00:00:00Z');
  if (!Number.isFinite(time.getTime()) || time.toISOString().slice(0, 10) !== value) throw new Error('membership_index_date_invalid');
  return value;
}

function index(value) {
  if (!value || Object.keys(value).sort().join() !== 'head,history,revision' ||
      !Number.isSafeInteger(value.revision) || value.revision < 0 || !Array.isArray(value.history) ||
      value.history.length !== value.revision) throw new Error('membership_index_expected_invalid');
  return { revision: value.revision, head: value.head === null ? null : archive(value.head),
    history: value.history.map(archive) };
}

export class MembershipObservationIndex {
  #storage;
  #leases;

  constructor(storage, { clock = Date.now } = {}) {
    this.#storage = storage;
    this.#leases = new LeaseStore(storage, { clock });
    storage.transactionSync(() => {
      this.#exec('CREATE TABLE IF NOT EXISTS m12_membership_head (singleton INTEGER PRIMARY KEY CHECK(singleton=1), revision INTEGER NOT NULL, head_json TEXT)');
      this.#exec('CREATE TABLE IF NOT EXISTS m12_membership_index (position INTEGER PRIMARY KEY, as_of TEXT NOT NULL UNIQUE, archive_key TEXT NOT NULL UNIQUE, record_json TEXT NOT NULL)');
      this.#exec('CREATE TABLE IF NOT EXISTS m12_membership_index_log (position INTEGER PRIMARY KEY, record_json TEXT NOT NULL)');
      this.#exec('CREATE TABLE IF NOT EXISTS m12_membership_genesis (singleton INTEGER PRIMARY KEY CHECK(singleton=1), marker TEXT NOT NULL)');
    });
  }

  #exec(sql, ...args) { return this.#storage.sql.exec(sql, ...args).toArray(); }

  initializeEmpty() {
    // Trusted migration/setup operation, never an RPC or automatic recovery.
    return this.#storage.transactionSync(() => {
      if (['head', 'index', 'index_log', 'genesis'].some(name =>
        this.#exec('SELECT * FROM m12_membership_' + name + ' LIMIT 1').length)) {
        throw new Error('membership_index_not_empty');
      }
      this.#exec('INSERT INTO m12_membership_genesis VALUES (1, ?)', GENESIS);
      this.#exec('INSERT INTO m12_membership_head VALUES (1, 0, NULL)');
    });
  }

  #snapshot() {
    const genesis = this.#exec('SELECT * FROM m12_membership_genesis WHERE singleton=1');
    const head = this.#exec('SELECT * FROM m12_membership_head WHERE singleton=1')[0];
    const rows = this.#exec('SELECT * FROM m12_membership_index ORDER BY position');
    const logs = this.#exec('SELECT * FROM m12_membership_index_log ORDER BY position');
    if (genesis.length !== 1 || genesis[0].marker !== GENESIS || !head ||
        !Number.isSafeInteger(head.revision) || head.revision < 0 ||
        rows.length !== head.revision || logs.length !== rows.length) throw new Error('membership_index_recovery_required');
    const history = [];
    let lastDay = null, previous = null;
    const keys = new Set();
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i], record = JSON.parse(row.record_json), current = archive(record.observation_archive);
      if (row.position !== i + 1 || logs[i].position !== row.position || logs[i].record_json !== row.record_json ||
          Object.keys(record).sort().join() !== 'as_of,epoch,fence,observation_archive,owner_job,position,previous_archive,recorded_ms,resource' ||
          record.position !== row.position || record.as_of !== row.as_of || current.key !== row.archive_key ||
          !same(record.previous_archive, previous) || keys.has(current.key) ||
          (lastDay !== null && day(record.as_of) <= lastDay) ||
          !record.resource.startsWith('daily/' + day(record.as_of) + '/')) throw new Error('membership_index_history_invalid');
      history.push(current); keys.add(current.key); previous = current; lastDay = record.as_of;
    }
    const currentHead = head.head_json === null ? null : archive(JSON.parse(head.head_json));
    if (!same(currentHead, previous)) throw new Error('membership_index_head_mismatch');
    return { current: { revision: head.revision, head: currentHead, history }, lastDay };
  }

  #owned(identity, token, resource, callback) {
    if (typeof resource !== 'string' || !resource.startsWith('daily/') || !identity ||
        !Number.isSafeInteger(identity.issued_at) || !Number.isSafeInteger(identity.expires_at) ||
        !Number.isSafeInteger(identity.expires_at * 1000) || identity.issued_at >= identity.expires_at) {
      throw new Error('membership_index_trusted_identity_required');
    }
    return this.#leases.withOwnedLease(resource, identity.job, token, context => {
      if (context.now < identity.issued_at * 1000) throw new Error('membership_index_identity_not_yet_valid');
      return callback(context);
    }, { deadlineMs: identity.expires_at * 1000 });
  }

  readCurrent(identity, token, resource) {
    return this.#owned(identity, token, resource, () => this.#snapshot().current);
  }

  append(identity, token, resource, input) {
    if (!input || Object.keys(input).sort().join() !== 'as_of,expected_index,observation_archive') throw new Error('membership_index_append_invalid');
    const expected = index(input.expected_index), targetDay = day(input.as_of), target = archive(input.observation_archive);
    if (typeof resource !== 'string' || !resource.startsWith('daily/' + targetDay + '/')) throw new Error('membership_index_wrong_daily_target');
    return this.#owned(identity, token, resource, ({ now, epoch, lease }) => {
      const { current, lastDay } = this.#snapshot();
      if (!same(expected, current)) throw new Error('membership_index_compare_failed');
      if (lastDay === targetDay && same(current.head, target)) return current;
      if (lastDay !== null && targetDay <= lastDay) throw new Error('membership_index_date_conflict');
      if (current.history.some(item => item.key === target.key)) throw new Error('membership_index_duplicate_observation');
      const position = current.revision + 1;
      if (!Number.isSafeInteger(position)) throw new Error('membership_index_revision_exhausted');
      const record = JSON.stringify({ position, as_of: targetDay, observation_archive: target,
        previous_archive: current.head, owner_job: lease.owner_job, epoch, fence: lease.fence,
        resource, recorded_ms: now });
      this.#exec('INSERT INTO m12_membership_index VALUES (?, ?, ?, ?)', position, targetDay, target.key, record);
      this.#exec('INSERT INTO m12_membership_index_log VALUES (?, ?)', position, record);
      this.#exec('UPDATE m12_membership_head SET revision=?, head_json=? WHERE singleton=1', position, JSON.stringify(target));
      return this.#snapshot().current;
    });
  }
}
