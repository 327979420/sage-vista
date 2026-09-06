import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { LeaseStore } from "../services/publication/leases.mjs";
import { AuthorizationStore } from "../services/publication/authorization_store.mjs";

const EPOCH = "11111111-1111-4111-8111-111111111111";
const OTHER_EPOCH = "22222222-2222-4222-8222-222222222222";
const NOW = Date.parse("2026-09-06T00:00:00Z");
const JOB = { repository_id: "repository-1", workflow_ref: "repo/workflow@refs/heads/main",
  workflow_commit: "b".repeat(40), run_id: "run-1", run_attempt: 1, environment: "production" };
const OTHER = { ...JOB, run_id: "run-2" };
const token = (handle) => ({ epoch: handle.epoch, fence: handle.lease.fence });

// Real local SQLite; the thin shim matches synchronous DO storage API shape.
// It does not emulate Cloudflare scheduling, output gates or remote durability.
function binding(path = ":memory:") {
  const db = new DatabaseSync(path);
  return {
    db,
    sql: { exec(query, ...args) {
      const statement = db.prepare(query);
      const rows = statement.all(...args);
      return { toArray: () => rows.map((row) => ({ ...row })) };
    } },
    transactionSync(callback) {
      db.exec("BEGIN IMMEDIATE");
      try {
        const result = callback();
        assert.ok(!(result instanceof Promise));
        db.exec("COMMIT");
        return result;
      } catch (error) {
        db.exec("ROLLBACK");
        throw error;
      }
    },
  };
}

function setup(t) {
  const storage = binding();
  t.after(() => storage.db.close());
  let now = NOW;
  const store = new LeaseStore(storage, { clock: () => now });
  store.initialize(EPOCH);
  return { storage, store, clock: () => now, setTime: (value) => { now = value; },
    log: () => storage.sql.exec("SELECT * FROM m12_lease_log ORDER BY sequence").toArray() };
}

test("opening does not initialize an epoch; explicit initialization is one-time", (t) => {
  const storage = binding();
  t.after(() => storage.db.close());
  const store = new LeaseStore(storage, { clock: () => NOW });
  assert.throws(() => store.acquire("publish/global", JOB, EPOCH), /not_initialized/);
  assert.equal(store.initialize(EPOCH), EPOCH);
  assert.equal(store.initialize(EPOCH), EPOCH);
  assert.throws(() => store.initialize(OTHER_EPOCH), /already_initialized/);
  assert.equal(storage.sql.exec("SELECT * FROM m12_lease_log").toArray().length, 1);
});

test("all five resources are independent; TTL is 300s and renew preserves fence", (t) => {
  const { store, setTime, log } = setup(t);
  for (const resource of ["daily/2026-09-06/config:1", "evaluation/task:1", "execution/task:1", "publish/global", "legacy-nightly"]) {
    const handle = store.acquire(resource, JOB, EPOCH);
    assert.deepEqual(handle, { epoch: EPOCH, lease: { resource, owner_job: JOB, fence: 1,
      expires_at: new Date(NOW + 300_000).toISOString() } });
  }
  setTime(NOW + 60_000);
  const renewed = store.renew("publish/global", JOB, { epoch: EPOCH, fence: 1 });
  assert.equal(renewed.lease.fence, 1);
  assert.equal(renewed.lease.expires_at, new Date(NOW + 360_000).toISOString());
  assert.equal(log().at(-1).operation, "renew");
});

test("acquire replay is stable, different owners are busy, Job field order is immaterial", (t) => {
  const { store, setTime, log } = setup(t);
  const handle = store.acquire("publish/global", JOB, EPOCH);
  setTime(NOW + 60_000);
  assert.deepEqual(store.acquire("publish/global", Object.fromEntries(Object.entries(JOB).reverse()), EPOCH), handle);
  assert.equal(log().length, 2);
  assert.throws(() => store.acquire("publish/global", OTHER, EPOCH), /busy/);
  for (const field of Object.keys(JOB)) {
    const wrong = { ...JOB, [field]: field === "run_attempt" ? 2 : JOB[field] + "x" };
    assert.throws(() => store.renew("publish/global", wrong, token(handle)), /not_owned/);
    assert.throws(() => store.release("publish/global", wrong, token(handle)), /not_owned/);
  }
});

test("exact expiry rejects old renew/release; takeover advances fence", (t) => {
  const { store, setTime } = setup(t);
  const old = store.acquire("publish/global", JOB, EPOCH);
  setTime(NOW + 300_000);
  assert.throws(() => store.renew("publish/global", JOB, token(old)), /stale/);
  assert.throws(() => store.release("publish/global", JOB, token(old)), /stale/);
  const next = store.acquire("publish/global", OTHER, EPOCH);
  assert.equal(next.lease.fence, 2);
  assert.throws(() => store.renew("publish/global", JOB, token(old)), /stale/);
  assert.throws(() => store.release("publish/global", OTHER, token(old)), /stale/);
});

test("release retains fence and same-owner reacquire invalidates previous token", (t) => {
  const { store, log } = setup(t);
  const old = store.acquire("legacy-nightly", JOB, EPOCH);
  assert.deepEqual(store.release("legacy-nightly", JOB, token(old)), { released: true });
  assert.throws(() => store.release("legacy-nightly", JOB, token(old)), /stale/);
  const next = store.acquire("legacy-nightly", JOB, EPOCH);
  assert.equal(next.lease.fence, 2);
  assert.throws(() => store.renew("legacy-nightly", JOB, token(old)), /stale/);
  const released = JSON.parse(log().find((r) => r.operation === "release").after_json);
  assert.equal(released.owner_json, null);
  assert.equal(released.fence, 1);
});

test("epoch mismatch rejects acquisition, renewal and release without logging", (t) => {
  const { store, log } = setup(t);
  const handle = store.acquire("publish/global", JOB, EPOCH);
  const wrong = { ...token(handle), epoch: OTHER_EPOCH };
  assert.throws(() => store.acquire("publish/global", JOB, OTHER_EPOCH), /epoch_mismatch/);
  assert.throws(() => store.renew("publish/global", JOB, wrong), /epoch_mismatch/);
  assert.throws(() => store.release("publish/global", JOB, wrong), /epoch_mismatch/);
  assert.equal(log().length, 2);
});

test("file-backed reopen preserves epoch, expiry, fences and log", (t) => {
  const dir = mkdtempSync(join(tmpdir(), "sage-m12-leases-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const path = join(dir, "coordinator.sqlite");
  const first = binding(path);
  const a = new LeaseStore(first, { clock: () => NOW });
  a.initialize(EPOCH);
  const old = a.acquire("publish/global", JOB, EPOCH);
  first.db.close();
  const second = binding(path);
  t.after(() => second.db.close());
  const b = new LeaseStore(second, { clock: () => NOW + 300_000 });
  assert.equal(b.acquire("publish/global", OTHER, EPOCH).lease.fence, 2);
  assert.throws(() => b.renew("publish/global", JOB, token(old)), /stale/);
  assert.equal(second.sql.exec("SELECT * FROM m12_lease_log").toArray().length, 3);
});

test("journal failure rolls back lease update and server-clock watermark", (t) => {
  const { storage, store, setTime, log } = setup(t);
  const before = store.acquire("publish/global", JOB, EPOCH);
  storage.db.exec(`CREATE TRIGGER fail_log BEFORE INSERT ON m12_lease_log
    BEGIN SELECT RAISE(ABORT, 'journal_unavailable'); END`);
  setTime(NOW + 60_000);
  assert.throws(() => store.renew("publish/global", JOB, token(before)), /journal_unavailable/);
  assert.throws(() => store.release("publish/global", JOB, token(before)), /journal_unavailable/);
  assert.throws(() => store.acquire("legacy-nightly", JOB, EPOCH), /journal_unavailable/);
  assert.equal(log().length, 2);
  storage.db.exec("DROP TRIGGER fail_log");
  setTime(NOW);
  assert.deepEqual(store.acquire("publish/global", JOB, EPOCH), before);
  assert.equal(store.acquire("legacy-nightly", JOB, EPOCH).lease.fence, 1);
});

test("invalid resources, token types and clock fail closed", (t) => {
  const { store, setTime } = setup(t);
  for (const resource of ["daily/2026-02-30/c", "execution/", "publish/other", "legacy-nightly\n", "execution/x/../y", "current"]) {
    assert.throws(() => store.acquire(resource, JOB, EPOCH), /resource/);
  }
  for (const fence of [true, 0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => store.renew("publish/global", JOB, { epoch: EPOCH, fence }), /token_invalid/);
  }
  for (const time of [NOW - 1, NaN, Infinity, 1.2, Number.MAX_SAFE_INTEGER]) {
    setTime(time);
    assert.throws(() => store.acquire("publish/global", JOB, EPOCH), /clock_invalid/);
  }
});

test("missing epoch with surviving state requires recovery, never resets fence", (t) => {
  const { storage, store } = setup(t);
  store.acquire("publish/global", JOB, EPOCH);
  storage.db.exec("DELETE FROM m12_lease_epoch");
  const reopened = new LeaseStore(storage, { clock: () => NOW });
  assert.throws(() => reopened.acquire("publish/global", JOB, EPOCH), /not_initialized/);
  assert.throws(() => reopened.initialize(OTHER_EPOCH), /recovery_required/);
});

test("fence overflow fails without replacing the previous row", (t) => {
  const { storage, store } = setup(t);
  storage.sql.exec("INSERT INTO m12_leases VALUES (?, NULL, ?, 0)", "publish/global", Number.MAX_SAFE_INTEGER);
  assert.throws(() => store.acquire("publish/global", JOB, EPOCH), /fence_exhausted/);
  assert.equal(storage.sql.exec("SELECT fence FROM m12_leases").toArray()[0].fence, Number.MAX_SAFE_INTEGER);
});

test("two store instances serialize contenders against the same SQLite state", (t) => {
  const { storage, store, log } = setup(t);
  const other = new LeaseStore(storage, { clock: () => NOW });
  const winner = store.acquire("execution/task:1", JOB, EPOCH);
  for (let i = 0; i < 20; i++) {
    assert.throws(() => other.acquire("execution/task:1", { ...OTHER, run_id: `loser-${i}` }, EPOCH), /busy/);
  }
  winner.lease.owner_job.run_id = "caller-mutation";
  assert.deepEqual(other.acquire("execution/task:1", JOB, EPOCH).lease.owner_job, JOB);
  assert.equal(log().length, 2);
});

const APPROVAL = { id: "approval-observation:sha256:" + "f".repeat(64), content_fingerprint: "sha256:" + "f".repeat(64) };
const authRef = (digit) => ({ id: "publication-authorization:sha256:" + digit.repeat(64), content_fingerprint: "sha256:" + digit.repeat(64) });

function authorizations(t) {
  const f = setup(t);
  const authorization = new AuthorizationStore(f.storage, { clock: f.clock });
  const handle = f.store.acquire("publish/global", JOB, EPOCH);
  return { ...f, authorization, handle,
    tickets: () => f.storage.sql.exec("SELECT * FROM m12_authorization_tickets").toArray(),
    authLog: () => f.storage.sql.exec("SELECT * FROM m12_authorization_log").toArray() };
}

// Only synthetic index metadata; B3a does not register real authorization bodies.
function seedHistory(storage) {
  const refs = [authRef("a"), authRef("b")];
  storage.transactionSync(() => {
    refs.forEach((ref, i) => storage.sql.exec("INSERT INTO m12_authorization_index VALUES (?, ?, ?, ?)",
      i + 1, JSON.stringify(ref), JSON.stringify({ key: `authority/${String(i + 1).repeat(64)}.json`,
        sha256: "sha256:" + String(i + 1).repeat(64), size_bytes: 100 + i }),
      i === 0 ? null : JSON.stringify(refs[i - 1])));
    storage.sql.exec("UPDATE m12_authorization_head SET revision = 2, head_json = ?", JSON.stringify(refs[1]));
    // Full trusted synthetic prefix, not a boolean exemption for missing records.
    storage.sql.exec("UPDATE m12_authorization_import_baseline SET history_json=? WHERE singleton=1",
      JSON.stringify(refs.map((ref, i) => ({ reference: ref, archive: { key: `authority/${String(i + 1).repeat(64)}.json`,
        sha256: "sha256:" + String(i + 1).repeat(64), size_bytes: 100 + i }, previous_ref: i ? refs[i - 1] : null }))));
  });
  return refs;
}

test("lease-owned transaction rejects async closures and rolls back synchronous errors", (t) => {
  const { storage, store } = setup(t);
  const handle = store.acquire("publish/global", JOB, EPOCH);
  storage.db.exec("CREATE TABLE test_mutation (value INTEGER)");
  let invoked = false;
  assert.throws(() => store.withOwnedLease("publish/global", JOB, token(handle), async () => { invoked = true; }), /synchronous/);
  assert.equal(invoked, false);
  for (const callback of [() => { storage.db.exec("INSERT INTO test_mutation VALUES (1)"); throw new Error("abort"); },
    () => { storage.db.exec("INSERT INTO test_mutation VALUES (1)"); return Promise.resolve(); }]) {
    assert.throws(() => store.withOwnedLease("publish/global", JOB, token(handle), callback));
    assert.equal(storage.sql.exec("SELECT * FROM test_mutation").toArray().length, 0);
  }
});

test("empty history produces one durable ticket bound to current lease and original evidence", (t) => {
  const f = authorizations(t);
  const ticket = f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL);
  assert.deepEqual(ticket.history, []);
  assert.equal(ticket.expected_revision, 0);
  assert.equal(ticket.expected_head_ref, null);
  assert.equal(ticket.epoch, EPOCH);
  assert.equal(ticket.fence, f.handle.lease.fence);
  assert.equal(ticket.resource, "publish/global");
  assert.deepEqual(ticket.owner_job, JOB);
  assert.equal(ticket.expires_at, f.handle.lease.expires_at);
  assert.deepEqual(ticket.approval_evidence_ref, APPROVAL);
  assert.equal(f.tickets().length, 1);
  assert.equal(f.authLog()[0].record_json, JSON.stringify(ticket));
  assert.equal(f.storage.sql.exec("SELECT * FROM m12_authorization_index").toArray().length, 0);
});

test("complete ordered index and head are frozen; replay does not extend ticket time", (t) => {
  const f = authorizations(t);
  const refs = seedHistory(f.storage);
  const first = f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL);
  assert.deepEqual(first.history.map((item) => item.reference), refs);
  assert.equal(first.expected_revision, 2);
  assert.deepEqual(first.expected_head_ref, refs[1]);
  f.setTime(NOW + 60_000);
  const repeated = f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL);
  assert.deepEqual(repeated, first);
  assert.equal(f.tickets().length, 1);
  assert.equal(f.authLog().length, 1);
  repeated.history.pop(); repeated.owner_job.run_id = "attacker";
  assert.deepEqual(f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL), first);
});

test("stale fence, different epoch/owner and exact expiry cannot prepare tickets", (t) => {
  const f = authorizations(t);
  assert.throws(() => f.authorization.prepareValidation(OTHER, token(f.handle), APPROVAL), /not_owned/);
  assert.throws(() => f.authorization.prepareValidation(JOB, { epoch: OTHER_EPOCH, fence: 1 }, APPROVAL), /epoch_mismatch/);
  assert.throws(() => f.authorization.prepareValidation(JOB, { epoch: EPOCH, fence: 2 }, APPROVAL), /stale/);
  f.setTime(NOW + 300_000);
  assert.throws(() => f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL), /stale/);
  assert.equal(f.tickets().length, 0);
});

test("history gap, wrong predecessor/head or malformed archive location fail closed", (t) => {
  const f = authorizations(t);
  const refs = seedHistory(f.storage);
  for (const sql of ["DELETE FROM m12_authorization_index WHERE position = 1",
    "UPDATE m12_authorization_index SET previous_ref_json = NULL WHERE position = 2",
    "UPDATE m12_authorization_index SET position = 3 WHERE position = 2",
    "UPDATE m12_authorization_index SET archive_json = '{}' WHERE position = 1"]) {
    f.storage.db.exec("BEGIN");
    f.storage.db.exec(sql);
    // Avoid nested transaction in the shim: persist the malformed state, then
    // restore it explicitly for the next isolated counterexample.
    f.storage.db.exec("COMMIT");
    assert.throws(() => f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL));
    f.storage.db.exec("DELETE FROM m12_authorization_index");
    seedHistory(f.storage);
  }
  f.storage.sql.exec("UPDATE m12_authorization_head SET head_json = ?", JSON.stringify(refs[0]));
  assert.throws(() => f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL), /head_mismatch/);
  assert.equal(f.tickets().length, 0);
});

test("ticket-log failure rolls back ticket insertion and lease clock watermark", (t) => {
  const f = authorizations(t);
  f.storage.db.exec(`CREATE TRIGGER fail_ticket_log BEFORE INSERT ON m12_authorization_log
    BEGIN SELECT RAISE(ABORT, 'ticket_log_unavailable'); END`);
  f.setTime(NOW + 60_000);
  assert.throws(() => f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL), /ticket_log_unavailable/);
  assert.equal(f.tickets().length, 0);
  f.storage.db.exec("DROP TRIGGER fail_ticket_log");
  f.setTime(NOW);
  assert.equal(f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL).prepared_at, new Date(NOW).toISOString());
});

test("lease expiry inside the ticket transaction rolls back both ticket and log", (t) => {
  const f = authorizations(t);
  const original = f.storage.sql.exec;
  f.storage.sql.exec = (query, ...args) => {
    const result = original(query, ...args);
    if (query.includes("INSERT INTO m12_authorization_log")) f.setTime(NOW + 300_000);
    return result;
  };
  assert.throws(() => f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL), /expired_before_commit/);
  assert.equal(f.tickets().length, 0);
  assert.equal(f.authLog().length, 0);
});

test("renewed lease or changed head creates a new snapshot without rewriting old ticket", (t) => {
  const f = authorizations(t);
  const first = f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL);
  f.setTime(NOW + 60_000);
  f.store.renew("publish/global", JOB, token(f.handle));
  const renewed = f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL);
  assert.notEqual(renewed.ticket_id, first.ticket_id);
  assert.notEqual(renewed.expires_at, first.expires_at);
  seedHistory(f.storage);
  const changed = f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL);
  assert.notEqual(changed.ticket_id, renewed.ticket_id);
  assert.equal(changed.expected_revision, 2);
  assert.deepEqual(JSON.parse(f.tickets()[0].ticket_json), first);
});

test("ticket persists across file database reopen and replay retains exact identity", (t) => {
  const dir = mkdtempSync(join(tmpdir(), "sage-m12-auth-ticket-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const file = join(dir, "state.sqlite");
  const first = binding(file);
  const lease = new LeaseStore(first, { clock: () => NOW });
  lease.initialize(EPOCH);
  const handle = lease.acquire("publish/global", JOB, EPOCH);
  const a = new AuthorizationStore(first, { clock: () => NOW });
  const prepared = a.prepareValidation(JOB, token(handle), APPROVAL);
  first.db.close();
  const second = binding(file);
  t.after(() => second.db.close());
  const b = new AuthorizationStore(second, { clock: () => NOW + 60_000 });
  assert.deepEqual(b.prepareValidation(JOB, token(handle), APPROVAL), prepared);
});

test("lost head or ticket log requires recovery instead of silently empty bootstrap", (t) => {
  const f = authorizations(t);
  f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL);
  f.storage.db.exec("DELETE FROM m12_authorization_log");
  assert.throws(() => f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL), /recovery_required/);
  f.storage.db.exec("DELETE FROM m12_authorization_head");
  const reopened = new AuthorizationStore(f.storage, { clock: f.clock });
  assert.throws(() => reopened.prepareValidation(JOB, token(f.handle), APPROVAL), /recovery_required/);
});

test("wrong reference type is rejected and only internal authorization methods are exposed", (t) => {
  const f = authorizations(t);
  assert.throws(() => f.authorization.prepareValidation(JOB, token(f.handle), authRef("a")), /reference_invalid/);
  assert.deepEqual(Object.getOwnPropertyNames(AuthorizationStore.prototype).sort(), ["constructor", "prepareValidation", "readArchivedValidation", "readCurrentForPreparation", "readPreparedValidation", "readValidationDispatch", "recordValidationArchive", "recordValidationDispatch", "registerValidatedAuthorization"]);
});

// Synthetic transport descriptors only; real byte hashing/readback is covered
// by the internal preparation integration tests, not this SQL component.
function dispatchPreparation(ticket) {
  return { ticket, ticket_sha256: "sha256:" + "2".repeat(64),
    input_archive: { key: "raw/" + "1".repeat(64), sha256: "sha256:" + "1".repeat(64), size_bytes: 100 },
    source_commit: "3".repeat(40), identity_issued_at: NOW / 1000 - 30, identity_expires_at: NOW / 1000 + 120 };
}

function dispatchSetup(t) {
  const f = authorizations(t);
  const ticket = f.authorization.prepareValidation(JOB, token(f.handle), APPROVAL);
  return { ...f, input: dispatchPreparation(ticket),
    dispatches: () => f.storage.sql.exec("SELECT * FROM m12_authorization_dispatches").toArray() };
}

test("dispatch persists exact binding once, preserves replay time and rejects same-ticket substitutions", (t) => {
  const f = dispatchSetup(t);
  const first = f.authorization.recordValidationDispatch(JOB, token(f.handle), f.input);
  assert.equal(first.ticket_id, f.input.ticket.ticket_id);
  assert.deepEqual(first.input_archive, f.input.input_archive);
  assert.equal(first.expires_at, new Date(NOW + 120_000).toISOString());
  f.setTime(NOW + 60_000);
  assert.deepEqual(f.authorization.recordValidationDispatch(JOB, token(f.handle), f.input), first);
  const changed = structuredClone(first); changed.input_archive.size_bytes++;
  assert.notDeepEqual(f.authorization.recordValidationDispatch(JOB, token(f.handle), f.input), changed);
  for (const patch of [(v) => { v.input_archive.size_bytes++; }, (v) => { v.ticket_sha256 = "sha256:" + "a".repeat(64); },
    (v) => { v.source_commit = "b".repeat(40); }, (v) => { v.identity_expires_at++; },
    (v) => { v.ticket.expected_revision++; }]) {
    const input = structuredClone(f.input); patch(input);
    assert.throws(() => f.authorization.recordValidationDispatch(JOB, token(f.handle), input), /conflict|ticket_mismatch/);
  }
  assert.equal(f.dispatches().length, 1);
  assert.equal(f.authLog().filter((row) => row.operation === "dispatch_validation").length, 1);
});

test("dispatch refuses invalid descriptor, stale lease, expired identity and changed head before any append", (t) => {
  for (const change of [(f) => { f.input.input_archive.key = "raw/" + "9".repeat(64); },
    (f) => { f.input.input_archive.size_bytes = true; }, (f) => { f.input.identity_expires_at = true; },
    (f) => { f.input.extra = true; }, (f) => { f.setTime(NOW + 120_000); },
    (f) => { f.store.release("publish/global", JOB, token(f.handle)); f.store.acquire("publish/global", OTHER, EPOCH); },
    (f) => { seedHistory(f.storage); }]) {
    const f = dispatchSetup(t); change(f);
    assert.throws(() => f.authorization.recordValidationDispatch(JOB, token(f.handle), f.input));
    assert.equal(f.dispatches().length, 0);
    assert.equal(f.authLog().filter((row) => row.operation === "dispatch_validation").length, 0);
  }
});

test("dispatch log failure rolls back input binding and leaves the prepared ticket retryable", (t) => {
  const f = dispatchSetup(t);
  f.storage.db.exec(`CREATE TRIGGER fail_dispatch BEFORE INSERT ON m12_authorization_log
    WHEN NEW.operation = 'dispatch_validation' BEGIN SELECT RAISE(ABORT, 'dispatch log failure'); END`);
  assert.throws(() => f.authorization.recordValidationDispatch(JOB, token(f.handle), f.input), /dispatch log failure/);
  assert.equal(f.dispatches().length, 0);
  assert.equal(f.tickets().length, 1);
  f.storage.db.exec("DROP TRIGGER fail_dispatch");
  f.authorization.recordValidationDispatch(JOB, token(f.handle), f.input);
  assert.equal(f.dispatches().length, 1);
});

test("identity or original ticket expiration inside dispatch transaction rolls back even after lease renewal", (t) => {
  for (const ticketDeadline of [false, true]) {
    const f = dispatchSetup(t);
    const deadline = NOW + (ticketDeadline ? 300_000 : 120_000);
    if (ticketDeadline) {
      f.input.identity_expires_at = NOW / 1000 + 600;
      f.setTime(NOW + 60_000);
      f.store.renew("publish/global", JOB, token(f.handle));
    }
    const original = f.storage.sql.exec;
    f.storage.sql.exec = (query, ...args) => {
      const result = original(query, ...args);
      if (query.includes("VALUES ('dispatch_validation'")) f.setTime(deadline);
      return result;
    };
    assert.throws(() => f.authorization.recordValidationDispatch(JOB, token(f.handle), f.input), /deadline_expired/);
    assert.equal(f.dispatches().length, 0);
    assert.equal(f.authLog().filter((row) => row.operation === "dispatch_validation").length, 0);
    assert.equal(f.tickets().length, 1);
  }
});

test("dispatch binding and original response survive file database reopen", (t) => {
  const directory = mkdtempSync(join(tmpdir(), "m12-dispatch-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const path = join(directory, "coordinator.sqlite");
  const first = binding(path);
  const lease = new LeaseStore(first, { clock: () => NOW });
  lease.initialize(EPOCH);
  const held = lease.acquire("publish/global", JOB, EPOCH);
  const a = new AuthorizationStore(first, { clock: () => NOW });
  const input = dispatchPreparation(a.prepareValidation(JOB, token(held), APPROVAL));
  const saved = a.recordValidationDispatch(JOB, token(held), input);
  first.db.close();
  const second = binding(path); t.after(() => second.db.close());
  const b = new AuthorizationStore(second, { clock: () => NOW + 1000 });
  assert.deepEqual(b.recordValidationDispatch(JOB, token(held), input), saved);
  const identity = { job: JOB, code_commit: input.source_commit, issued_at: input.identity_issued_at, expires_at: input.identity_expires_at };
  assert.deepEqual(b.readValidationDispatch(identity, token(held), saved.dispatch_id), { dispatch: saved, validation_ticket: input.ticket });
  assert.equal(second.sql.exec("SELECT * FROM m12_authorization_dispatches").toArray().length, 1);
});

test("partial dispatch/log/head loss requires recovery instead of reconstructing success", (t) => {
  for (const table of ["m12_authorization_dispatches", "m12_authorization_log"]) {
    const f = dispatchSetup(t);
    f.authorization.recordValidationDispatch(JOB, token(f.handle), f.input);
    f.storage.db.exec(table.endsWith("_log") ? "DELETE FROM m12_authorization_log WHERE operation='dispatch_validation'" :
      "DELETE FROM m12_authorization_dispatches");
    assert.throws(() => f.authorization.recordValidationDispatch(JOB, token(f.handle), f.input), /recovery_required/);
  }
  const f = dispatchSetup(t);
  f.authorization.recordValidationDispatch(JOB, token(f.handle), f.input);
  f.storage.db.exec("DELETE FROM m12_authorization_head; DELETE FROM m12_authorization_log; DELETE FROM m12_authorization_tickets");
  const reopened = new AuthorizationStore(f.storage, { clock: f.clock });
  assert.throws(() => reopened.prepareValidation(JOB, token(f.handle), APPROVAL), /recovery_required/);
  assert.equal(f.storage.sql.exec("SELECT * FROM m12_authorization_head").toArray().length, 0);
});
