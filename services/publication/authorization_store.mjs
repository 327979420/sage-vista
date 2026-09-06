import { LeaseStore } from "./leases.mjs";

function reference(value, prefix) {
  if (!value || Object.keys(value).sort().join() !== "content_fingerprint,id" ||
      typeof value.content_fingerprint !== "string" || !/^sha256:[a-f0-9]{64}$/.test(value.content_fingerprint) ||
      value.id !== prefix + value.content_fingerprint) throw new Error("authorization_reference_invalid");
  return { id: value.id, content_fingerprint: value.content_fingerprint };
}

function location(value) {
  if (!value || Object.keys(value).sort().join() !== "key,sha256,size_bytes" ||
      typeof value.key !== "string" || !/^authority\/[a-f0-9]{64}\.json$/.test(value.key) ||
      typeof value.sha256 !== "string" || !/^sha256:[a-f0-9]{64}$/.test(value.sha256) ||
      !Number.isSafeInteger(value.size_bytes) || value.size_bytes < 1) throw new Error("authorization_location_invalid");
  return { key: value.key, sha256: value.sha256, size_bytes: value.size_bytes };
}

export class AuthorizationStore {
  #storage;
  #leases;

  constructor(storage, { clock = Date.now } = {}) {
    this.#storage = storage;
    this.#leases = new LeaseStore(storage, { clock });
    storage.transactionSync(() => {
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_authorization_head (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1), revision INTEGER NOT NULL, head_json TEXT)`);
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_authorization_index (
        position INTEGER PRIMARY KEY CHECK(position > 0), reference_json TEXT NOT NULL UNIQUE,
        archive_json TEXT NOT NULL, previous_ref_json TEXT)`);
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_authorization_tickets (
        ticket_id TEXT PRIMARY KEY, preparation_key TEXT NOT NULL UNIQUE, ticket_json TEXT NOT NULL)`);
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_authorization_log (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT, operation TEXT NOT NULL, ticket_id TEXT NOT NULL,
        record_json TEXT NOT NULL, occurred_ms INTEGER NOT NULL)`);
      // Do not silently restore a lost head over surviving history/tickets/logs.
      if (!this.#exec("SELECT singleton FROM m12_authorization_head").length &&
          !this.#exec("SELECT position FROM m12_authorization_index LIMIT 1").length &&
          !this.#exec("SELECT ticket_id FROM m12_authorization_tickets LIMIT 1").length &&
          !this.#exec("SELECT sequence FROM m12_authorization_log LIMIT 1").length) {
        this.#exec("INSERT INTO m12_authorization_head VALUES (1, 0, NULL)");
      }
    });
  }

  #exec(query, ...args) { return this.#storage.sql.exec(query, ...args).toArray(); }

  #history() {
    const state = this.#exec("SELECT * FROM m12_authorization_head WHERE singleton = 1")[0];
    if (!state || !Number.isSafeInteger(state.revision) || state.revision < 0) throw new Error("authorization_recovery_required");
    const rows = this.#exec("SELECT * FROM m12_authorization_index ORDER BY position");
    if (rows.length !== state.revision) throw new Error("authorization_history_incomplete");
    const history = [];
    const seen = new Set();
    let previous = null;
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      const ref = reference(JSON.parse(row.reference_json), "publication-authorization:");
      const prior = row.previous_ref_json === null ? null : reference(JSON.parse(row.previous_ref_json), "publication-authorization:");
      if (row.position !== i + 1 || seen.has(ref.id) || JSON.stringify(prior) !== JSON.stringify(previous)) {
        throw new Error("authorization_history_not_linear");
      }
      history.push({ reference: ref, archive: location(JSON.parse(row.archive_json)), previous_ref: prior });
      seen.add(ref.id);
      previous = ref;
    }
    const head = state.head_json === null ? null : reference(JSON.parse(state.head_json), "publication-authorization:");
    if (JSON.stringify(head) !== JSON.stringify(previous)) throw new Error("authorization_head_mismatch");
    return { revision: state.revision, head, history };
  }

  prepareValidation(ownerJob, token, approvalEvidenceRef) {
    const evidenceRef = reference(approvalEvidenceRef, "approval-observation:");
    // Called only by the future authenticated coordinator after controlled B2g
    // reads. Creating a ticket neither authenticates this Ref nor grants rights.
    return this.#leases.withOwnedLease("publish/global", ownerJob, token, ({ epoch, lease, now }) => {
      const snapshot = this.#history();
      const preparationKey = JSON.stringify([epoch, lease.owner_job, lease.fence, lease.expires_at,
        snapshot.revision, snapshot.head, evidenceRef]);
      const prior = this.#exec("SELECT ticket_json FROM m12_authorization_tickets WHERE preparation_key = ?", preparationKey)[0];
      if (prior) {
        const ticket = JSON.parse(prior.ticket_json);
        const logs = this.#exec("SELECT record_json FROM m12_authorization_log WHERE operation = 'prepare_validation' AND ticket_id = ?", ticket.ticket_id);
        if (logs.length !== 1 || logs[0].record_json !== prior.ticket_json) throw new Error("authorization_ticket_recovery_required");
        return ticket;
      }
      const ticket = { ticket_id: crypto.randomUUID(), resource: "publish/global", owner_job: lease.owner_job,
        epoch, fence: lease.fence, prepared_at: new Date(now).toISOString(), expires_at: lease.expires_at,
        approval_evidence_ref: evidenceRef, expected_revision: snapshot.revision,
        expected_head_ref: snapshot.head, history: snapshot.history };
      const record = JSON.stringify(ticket);
      this.#exec("INSERT INTO m12_authorization_tickets VALUES (?, ?, ?)", ticket.ticket_id, preparationKey, record);
      this.#exec(`INSERT INTO m12_authorization_log (operation,ticket_id,record_json,occurred_ms)
        VALUES ('prepare_validation', ?, ?, ?)`, ticket.ticket_id, record, now);
      return JSON.parse(record);
    });
  }

  readPreparedValidation(ownerJob, token, ticketId) {
    if (typeof ticketId !== "string" || !/^[a-f0-9-]{36}$/.test(ticketId)) throw new Error("authorization_ticket_invalid");
    return this.#leases.withOwnedLease("publish/global", ownerJob, token, ({ epoch, lease, now }) => {
      const rows = this.#exec("SELECT ticket_json FROM m12_authorization_tickets WHERE ticket_id = ?", ticketId);
      if (rows.length !== 1) throw new Error("authorization_ticket_missing");
      const record = rows[0].ticket_json;
      const ticket = JSON.parse(record);
      const logs = this.#exec("SELECT record_json FROM m12_authorization_log WHERE operation = 'prepare_validation' AND ticket_id = ?", ticketId);
      if (logs.length !== 1 || logs[0].record_json !== record) throw new Error("authorization_ticket_recovery_required");
      const prepared = Date.parse(ticket.prepared_at), expiry = Date.parse(ticket.expires_at);
      if (ticket.ticket_id !== ticketId || ticket.resource !== "publish/global" || ticket.epoch !== epoch ||
          ticket.fence !== lease.fence || JSON.stringify(ticket.owner_job) !== JSON.stringify(lease.owner_job) ||
          !Number.isFinite(prepared) || !Number.isFinite(expiry) || prepared > now || expiry <= now ||
          expiry > Date.parse(lease.expires_at)) throw new Error("authorization_ticket_stale");
      const current = this.#history();
      if (ticket.expected_revision !== current.revision || JSON.stringify(ticket.expected_head_ref) !== JSON.stringify(current.head) ||
          JSON.stringify(ticket.history) !== JSON.stringify(current.history)) throw new Error("authorization_ticket_history_changed");
      return ticket;
    });
  }
}
