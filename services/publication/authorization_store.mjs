import { LeaseStore } from "./leases.mjs";

const sameJob = (left, right) => Object.keys(left).sort().join() === Object.keys(right).sort().join() &&
  Object.keys(left).every((key) => left[key] === right[key]);

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

function returnBinding(identity, dispatch, artifacts) {
  const frozen = JSON.parse(JSON.stringify(artifacts));
  if (Object.keys(frozen).sort().join() !== "authorization_archive,authorization_ref,validation_receipt_archive") {
    throw new Error("authorization_return_record_invalid");
  }
  const ref = reference(frozen.authorization_ref, "publication-authorization:");
  const archived = location(frozen.authorization_archive), receipt = frozen.validation_receipt_archive;
  if (archived.key !== "authority/" + ref.content_fingerprint.slice(7) + ".json" ||
      !receipt || Object.keys(receipt).sort().join() !== "key,sha256,size_bytes" ||
      typeof receipt.sha256 !== "string" || !/^sha256:[a-f0-9]{64}$/.test(receipt.sha256) ||
      receipt.key !== "raw/" + receipt.sha256.slice(7) ||
      !Number.isSafeInteger(receipt.size_bytes) || receipt.size_bytes < 1) throw new Error("authorization_return_record_invalid");
  return { protocol: "m12-authorization-return/1", state: "archived_pending_registration",
      dispatch_id: dispatch.dispatch_id, ticket_id: dispatch.ticket_id, epoch: dispatch.epoch, fence: dispatch.fence,
      owner_job: dispatch.owner_job, actor_id: identity.actor_id, source_commit: dispatch.source_commit,
      input_archive: dispatch.input_archive, authorization_ref: ref, authorization_archive: archived,
      validation_receipt_archive: receipt };
}

export class AuthorizationStore {
  #storage;
  #leases;
  #clock;

  constructor(storage, { clock = Date.now } = {}) {
    this.#storage = storage;
    this.#clock = clock;
    this.#leases = new LeaseStore(storage, { clock });
    storage.transactionSync(() => {
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_authorization_head (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1), revision INTEGER NOT NULL, head_json TEXT)`);
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_authorization_index (
        position INTEGER PRIMARY KEY CHECK(position > 0), reference_json TEXT NOT NULL UNIQUE,
        archive_json TEXT NOT NULL, previous_ref_json TEXT)`);
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_authorization_tickets (
        ticket_id TEXT PRIMARY KEY, preparation_key TEXT NOT NULL UNIQUE, ticket_json TEXT NOT NULL)`);
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_authorization_dispatches (
        ticket_id TEXT PRIMARY KEY, dispatch_id TEXT NOT NULL UNIQUE, dispatch_json TEXT NOT NULL)`);
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_authorization_returns (
        dispatch_id TEXT NOT NULL, receipt_key TEXT NOT NULL, ticket_id TEXT NOT NULL,
        record_json TEXT NOT NULL, PRIMARY KEY(dispatch_id,receipt_key))`);
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_authorization_log (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT, operation TEXT NOT NULL, ticket_id TEXT NOT NULL,
        record_json TEXT NOT NULL, occurred_ms INTEGER NOT NULL)`);
      // Do not silently restore a lost head over surviving history/tickets/logs.
      if (!this.#exec("SELECT singleton FROM m12_authorization_head").length &&
          !this.#exec("SELECT position FROM m12_authorization_index LIMIT 1").length &&
          !this.#exec("SELECT ticket_id FROM m12_authorization_tickets LIMIT 1").length &&
          !this.#exec("SELECT ticket_id FROM m12_authorization_dispatches LIMIT 1").length &&
          !this.#exec("SELECT ticket_id FROM m12_authorization_returns LIMIT 1").length &&
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
    // Called only by the internal authenticated coordinator after controlled B2g
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
    return this.#leases.withOwnedLease("publish/global", ownerJob, token, (context) => this.#ticket(ticketId, context));
  }

  #ticketRecord(ticketId) {
    if (typeof ticketId !== "string" || !/^[a-f0-9-]{36}$/.test(ticketId)) throw new Error("authorization_ticket_invalid");
    const rows = this.#exec("SELECT ticket_json FROM m12_authorization_tickets WHERE ticket_id = ?", ticketId);
    if (rows.length !== 1) throw new Error("authorization_ticket_missing");
    const record = rows[0].ticket_json;
    const ticket = JSON.parse(record);
    const logs = this.#exec("SELECT record_json FROM m12_authorization_log WHERE operation = 'prepare_validation' AND ticket_id = ?", ticketId);
    if (logs.length !== 1 || logs[0].record_json !== record) throw new Error("authorization_ticket_recovery_required");
    return ticket;
  }

  #ticket(ticketId, { epoch, lease, now }) {
    const ticket = this.#ticketRecord(ticketId);
    const prepared = Date.parse(ticket.prepared_at), expiry = Date.parse(ticket.expires_at);
    if (ticket.ticket_id !== ticketId || ticket.resource !== "publish/global" || ticket.epoch !== epoch ||
        ticket.fence !== lease.fence || JSON.stringify(ticket.owner_job) !== JSON.stringify(lease.owner_job) ||
        !Number.isFinite(prepared) || !Number.isFinite(expiry) || prepared > now || expiry <= now ||
        expiry > Date.parse(lease.expires_at)) throw new Error("authorization_ticket_stale");
    const current = this.#history();
    if (ticket.expected_revision !== current.revision || JSON.stringify(ticket.expected_head_ref) !== JSON.stringify(current.head) ||
        JSON.stringify(ticket.history) !== JSON.stringify(current.history)) throw new Error("authorization_ticket_history_changed");
    return ticket;
  }

  recordValidationDispatch(ownerJob, token, preparation) {
    // Only the internal coordinator may supply these read-verified descriptors.
    // This SQL layer cannot authenticate an arbitrary caller's hash or identity.
    if (!preparation || Object.keys(preparation).sort().join() !==
        "identity_expires_at,identity_issued_at,input_archive,source_commit,ticket,ticket_sha256") {
      throw new Error("authorization_dispatch_input_invalid");
    }
    const frozen = JSON.parse(JSON.stringify(preparation));
    const input = frozen.input_archive;
    if (!input || Object.keys(input).sort().join() !== "key,sha256,size_bytes" ||
        typeof input.sha256 !== "string" || !/^sha256:[a-f0-9]{64}$/.test(input.sha256) ||
        input.key !== "raw/" + input.sha256.slice(7) || !Number.isSafeInteger(input.size_bytes) || input.size_bytes < 1 ||
        typeof frozen.ticket_sha256 !== "string" || !/^sha256:[a-f0-9]{64}$/.test(frozen.ticket_sha256) ||
        typeof frozen.source_commit !== "string" || !/^[a-f0-9]{40}$/.test(frozen.source_commit) ||
        !Number.isSafeInteger(frozen.identity_issued_at) || !Number.isSafeInteger(frozen.identity_expires_at) ||
        frozen.identity_issued_at < 0 || frozen.identity_expires_at <= frozen.identity_issued_at ||
        !Number.isSafeInteger(frozen.identity_expires_at * 1000)) throw new Error("authorization_dispatch_input_invalid");
    const expires = Math.min(Date.parse(frozen.ticket?.expires_at), frozen.identity_expires_at * 1000);
    return this.#leases.withOwnedLease("publish/global", ownerJob, token, (context) => {
      const ticket = this.#ticket(frozen.ticket?.ticket_id, context);
      if (JSON.stringify(frozen.ticket) !== JSON.stringify(ticket)) throw new Error("authorization_dispatch_ticket_mismatch");
      if (context.now < frozen.identity_issued_at * 1000) throw new Error("authorization_dispatch_identity_not_yet_valid");
      const binding = { protocol: "m12-authorization-validation/1", ticket_id: ticket.ticket_id,
        ticket_sha256: frozen.ticket_sha256, input_archive: input, owner_job: ticket.owner_job,
        epoch: ticket.epoch, fence: ticket.fence, approval_evidence_ref: ticket.approval_evidence_ref,
        source_commit: frozen.source_commit, identity_issued_at: frozen.identity_issued_at,
        identity_expires_at: frozen.identity_expires_at, expires_at: new Date(expires).toISOString() };
      const rows = this.#exec("SELECT dispatch_id,dispatch_json FROM m12_authorization_dispatches WHERE ticket_id = ?", ticket.ticket_id);
      const logs = this.#exec("SELECT record_json FROM m12_authorization_log WHERE operation = 'dispatch_validation' AND ticket_id = ?", ticket.ticket_id);
      if (rows.length) {
        const prior = JSON.parse(rows[0].dispatch_json);
        if (logs.length !== 1 || logs[0].record_json !== rows[0].dispatch_json || rows[0].dispatch_id !== prior.dispatch_id) {
          throw new Error("authorization_dispatch_recovery_required");
        }
        const { dispatch_id, dispatched_at, ...priorBinding } = prior;
        if (JSON.stringify(priorBinding) !== JSON.stringify(binding)) throw new Error("authorization_dispatch_conflict");
        if (typeof dispatch_id !== "string" || !/^[a-f0-9-]{36}$/.test(dispatch_id) ||
            !Number.isFinite(Date.parse(dispatched_at)) || Date.parse(dispatched_at) < Date.parse(ticket.prepared_at) ||
            Date.parse(dispatched_at) > context.now) throw new Error("authorization_dispatch_recovery_required");
        return prior;
      }
      if (logs.length) throw new Error("authorization_dispatch_recovery_required");
      const dispatch = { ...binding, dispatch_id: crypto.randomUUID(), dispatched_at: new Date(context.now).toISOString() };
      const record = JSON.stringify(dispatch);
      this.#exec("INSERT INTO m12_authorization_dispatches VALUES (?, ?, ?)", ticket.ticket_id, dispatch.dispatch_id, record);
      this.#exec(`INSERT INTO m12_authorization_log (operation,ticket_id,record_json,occurred_ms)
        VALUES ('dispatch_validation', ?, ?, ?)`, ticket.ticket_id, record, context.now);
      return JSON.parse(record);
    }, { deadlineMs: expires });
  }

  #dispatch(dispatchId) {
    if (typeof dispatchId !== "string" || !/^[a-f0-9-]{36}$/.test(dispatchId)) throw new Error("authorization_dispatch_id_invalid");
    const row = this.#exec("SELECT * FROM m12_authorization_dispatches WHERE dispatch_id = ?", dispatchId)[0];
    if (!row) throw new Error("authorization_dispatch_missing");
    const dispatch = JSON.parse(row.dispatch_json);
    const logs = this.#exec("SELECT record_json FROM m12_authorization_log WHERE operation = 'dispatch_validation' AND ticket_id = ?", row.ticket_id);
    if (logs.length !== 1 || logs[0].record_json !== row.dispatch_json || dispatch.dispatch_id !== dispatchId ||
        dispatch.ticket_id !== row.ticket_id || Object.keys(dispatch).sort().join() !==
        "approval_evidence_ref,dispatch_id,dispatched_at,epoch,expires_at,fence,identity_expires_at,identity_issued_at,input_archive,owner_job,protocol,source_commit,ticket_id,ticket_sha256") {
      throw new Error("authorization_dispatch_recovery_required");
    }
    return dispatch;
  }

  readValidationDispatch(identity, token, dispatchId) {
    // Identity must come from the internal OIDC verifier, not an RPC JSON claim.
    const initial = this.#dispatch(dispatchId);
    const deadline = Math.min(Date.parse(initial.expires_at), identity.expires_at * 1000);
    return this.#leases.withOwnedLease("publish/global", identity.job, token, (context) => {
      const dispatch = this.#dispatch(dispatchId);
      if (JSON.stringify(initial) !== JSON.stringify(dispatch)) throw new Error("authorization_dispatch_changed");
      const ticket = this.#ticket(dispatch.ticket_id, context);
      if (dispatch.protocol !== "m12-authorization-validation/1" || dispatch.epoch !== ticket.epoch || dispatch.fence !== ticket.fence ||
          JSON.stringify(dispatch.owner_job) !== JSON.stringify(ticket.owner_job) ||
          JSON.stringify(dispatch.approval_evidence_ref) !== JSON.stringify(ticket.approval_evidence_ref) ||
          dispatch.source_commit !== identity.code_commit || context.now < identity.issued_at * 1000 ||
          !Number.isSafeInteger(dispatch.identity_issued_at) || !Number.isSafeInteger(dispatch.identity_expires_at) ||
          dispatch.identity_issued_at < 0 || dispatch.identity_expires_at <= dispatch.identity_issued_at ||
          !Number.isSafeInteger(dispatch.identity_expires_at * 1000)) throw new Error("authorization_dispatch_identity_mismatch");
      const expires = Math.min(Date.parse(ticket.expires_at), dispatch.identity_expires_at * 1000);
      const dispatched = Date.parse(dispatch.dispatched_at);
      if (dispatch.expires_at !== new Date(expires).toISOString() || !Number.isFinite(dispatched) ||
          dispatched < Date.parse(ticket.prepared_at) || dispatched < dispatch.identity_issued_at * 1000 ||
          dispatched >= expires || dispatched > context.now) throw new Error("authorization_dispatch_recovery_required");
      return { dispatch, validation_ticket: ticket };
    }, { deadlineMs: deadline });
  }

  #returnRows(dispatch) {
    const allRows = this.#exec("SELECT * FROM m12_authorization_returns WHERE ticket_id=?", dispatch.ticket_id);
    const logs = this.#exec(`SELECT record_json,occurred_ms FROM m12_authorization_log
      WHERE operation='archive_validation' AND ticket_id=?`, dispatch.ticket_id);
    if (allRows.length !== logs.length) throw new Error("authorization_return_record_recovery_required");
    for (const row of allRows) {
      const prior = JSON.parse(row.record_json);
      if (row.dispatch_id !== dispatch.dispatch_id || prior.dispatch_id !== dispatch.dispatch_id || prior.ticket_id !== dispatch.ticket_id ||
          row.receipt_key !== prior.validation_receipt_archive?.key ||
          logs.filter((log) => log.record_json === row.record_json).length !== 1) {
        throw new Error("authorization_return_record_recovery_required");
      }
    }
    return { allRows, logs };
  }

  readArchivedValidation(identity, epoch, dispatchId, receiptKey) {
    // Historical lookup only: identity is freshly verified by the internal
    // recovery adapter; epoch is server configuration, never a lease revival.
    if (typeof epoch !== "string" || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(epoch) ||
        typeof receiptKey !== "string" || !/^raw\/[a-f0-9]{64}$/.test(receiptKey)) throw new Error("authorization_recovery_request_invalid");
    return this.#storage.transactionSync(() => {
      const state = this.#exec("SELECT epoch,last_now FROM m12_lease_epoch WHERE singleton=1")[0];
      const checkTime = (previous) => {
        const now = this.#clock();
        if (!state || state.epoch !== epoch || !Number.isSafeInteger(now) || !Number.isSafeInteger(previous) || now < previous ||
            now < identity.issued_at * 1000 || now >= identity.expires_at * 1000) throw new Error("authorization_recovery_identity_or_epoch_invalid");
        return now;
      };
      const now = checkTime(state?.last_now);
      const history = this.#history(); // Fail closed on lost/corrupt authority state.
      const dispatch = this.#dispatch(dispatchId), ticket = this.#ticketRecord(dispatch.ticket_id);
      const prepared = Date.parse(ticket.prepared_at), expiry = Date.parse(ticket.expires_at);
      const dispatched = Date.parse(dispatch.dispatched_at);
      if (dispatch.protocol !== "m12-authorization-validation/1" || dispatch.epoch !== epoch || ticket.epoch !== epoch ||
          ticket.ticket_id !== dispatch.ticket_id || ticket.resource !== "publish/global" || ticket.fence !== dispatch.fence ||
          !Number.isSafeInteger(dispatch.fence) || dispatch.fence < 1 || dispatch.source_commit !== identity.code_commit ||
          !sameJob(dispatch.owner_job, identity.job) || !sameJob(ticket.owner_job, identity.job) ||
          JSON.stringify(ticket.approval_evidence_ref) !== JSON.stringify(dispatch.approval_evidence_ref) ||
          !Number.isSafeInteger(dispatch.identity_issued_at) || !Number.isSafeInteger(dispatch.identity_expires_at) ||
          dispatch.identity_issued_at < 0 || dispatch.identity_expires_at <= dispatch.identity_issued_at ||
          !Number.isFinite(prepared) || !Number.isFinite(expiry) || !Number.isFinite(dispatched) || prepared > dispatched ||
          dispatched < dispatch.identity_issued_at * 1000 || dispatched >= Math.min(expiry, dispatch.identity_expires_at * 1000) ||
          dispatch.expires_at !== new Date(Math.min(expiry, dispatch.identity_expires_at * 1000)).toISOString()) {
        throw new Error("authorization_recovery_dispatch_invalid");
      }
      const { allRows, logs } = this.#returnRows(dispatch);
      const row = allRows.find((value) => value.receipt_key === receiptKey);
      if (!row) throw new Error("authorization_recovery_record_unavailable"); // Never infer not received.
      const record = JSON.parse(row.record_json), { recorded_at, ...binding } = record;
      const expected = returnBinding(identity, dispatch, { authorization_ref: record.authorization_ref,
        authorization_archive: record.authorization_archive, validation_receipt_archive: record.validation_receipt_archive });
      const recorded = Date.parse(recorded_at);
      if (JSON.stringify(binding) !== JSON.stringify(expected) || !Number.isFinite(recorded) ||
          new Date(recorded).toISOString() !== recorded_at || recorded < dispatched || recorded >= Date.parse(dispatch.expires_at) ||
          recorded > now || logs.find((log) => log.record_json === row.record_json)?.occurred_ms !== recorded) {
        throw new Error("authorization_recovery_record_invalid");
      }
      const completed = checkTime(now);
      this.#exec("UPDATE m12_lease_epoch SET last_now=? WHERE singleton=1", completed);
      return { dispatch, validation_ticket: ticket, return_record: record, current_history: history };
    });
  }

  recordValidationArchive(identity, token, dispatchId, snapshot, artifacts) {
    // Internal B3f readback only. This method does not authenticate arbitrary
    // descriptors or prove R2 writes; it is never exposed directly over RPC.
    const expected = JSON.stringify(snapshot);
    return this.#storage.transactionSync(() => {
      const current = () => {
        const value = this.readValidationDispatch(identity, token, dispatchId);
        if (JSON.stringify(value) !== expected) throw new Error("authorization_return_record_changed");
        return value.dispatch;
      };
      const dispatch = current();
      const binding = returnBinding(identity, dispatch, artifacts);
      const receipt = binding.validation_receipt_archive;
      const { allRows, logs } = this.#returnRows(dispatch);
      const rows = allRows.filter((row) => row.receipt_key === receipt.key);
      const matchingLogs = rows.length ? logs.filter((log) => log.record_json === rows[0].record_json) : [];
      const now = this.#clock();
      const lastNow = this.#exec("SELECT last_now FROM m12_lease_epoch WHERE singleton=1")[0]?.last_now;
      if (!Number.isSafeInteger(now) || !Number.isSafeInteger(lastNow) || now < lastNow || now < Date.parse(dispatch.dispatched_at) ||
          now >= Math.min(Date.parse(dispatch.expires_at), identity.expires_at * 1000)) throw new Error("authorization_return_record_expired");
      let record;
      if (rows.length) {
        if (rows.length !== 1 || matchingLogs.length !== 1 ||
            rows[0].ticket_id !== dispatch.ticket_id) throw new Error("authorization_return_record_recovery_required");
        record = JSON.parse(rows[0].record_json);
        const { recorded_at, ...prior } = record;
        const recorded = Date.parse(recorded_at);
        if (JSON.stringify(prior) !== JSON.stringify(binding) || !Number.isFinite(recorded) ||
            new Date(recorded).toISOString() !== recorded_at || recorded < Date.parse(dispatch.dispatched_at) ||
            recorded > now || recorded >= Date.parse(dispatch.expires_at) || matchingLogs[0].occurred_ms !== recorded) {
          throw new Error("authorization_return_record_conflict");
        }
      } else {
        record = { ...binding, recorded_at: new Date(now).toISOString() };
        const raw = JSON.stringify(record);
        this.#exec("INSERT INTO m12_authorization_returns VALUES (?, ?, ?, ?)", dispatchId, receipt.key, dispatch.ticket_id, raw);
        this.#exec(`INSERT INTO m12_authorization_log (operation,ticket_id,record_json,occurred_ms)
          VALUES ('archive_validation', ?, ?, ?)`, dispatch.ticket_id, raw, now);
      }
      current(); // Last synchronous identity/lease/ticket/history check before commit.
      return record;
    });
  }
}
