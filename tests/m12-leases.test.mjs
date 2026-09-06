import test from "node:test";
import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { LeaseStore } from "../services/publication/leases.mjs";

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
  return { storage, store, setTime: (value) => { now = value; },
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
