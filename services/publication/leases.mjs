// Internal synchronous DO storage component, not an authenticated RPC endpoint.
// ownerJob must come from the future trusted adapter after Python Job validation.
const TTL_MS = 300_000;
const SEGMENT = "[A-Za-z0-9_:.-]+";
const RESOURCE = new RegExp(`^(?:publish/global|legacy-nightly|(?:evaluation|execution)/${SEGMENT}|daily/\\d{4}-\\d{2}-\\d{2}/${SEGMENT})$`);

function resourceKey(resource) {
  if (typeof resource !== "string" || !RESOURCE.test(resource) || /[\r\n]/.test(resource)) {
    throw new Error("lease_resource_invalid");
  }
  if (resource.startsWith("daily/")) {
    const date = resource.split("/")[1];
    const parsed = new Date(date + "T00:00:00Z");
    if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== date) {
      throw new Error("lease_resource_date_invalid");
    }
  }
  return resource;
}

// Lossless encoding of already validated Job primitive fields, not Job validation.
function jobBytes(job) {
  if (!job || Object.getPrototypeOf(job) !== Object.prototype || !Object.keys(job).length) {
    throw new Error("lease_trusted_job_required");
  }
  const entries = Object.keys(job).sort().map((key) => {
    const value = job[key];
    if (typeof value !== "string" && !(typeof value === "number" && Number.isSafeInteger(value))) {
      throw new Error("lease_job_encoding_invalid");
    }
    return [key, value];
  });
  return JSON.stringify(Object.fromEntries(entries));
}

export class LeaseStore {
  #storage;
  #clock;

  constructor(storage, { clock = Date.now } = {}) {
    if (!storage?.sql?.exec || typeof storage.transactionSync !== "function" || typeof clock !== "function") {
      throw new Error("lease_sqlite_binding_required");
    }
    this.#storage = storage;
    this.#clock = clock;
    storage.transactionSync(() => {
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_lease_epoch (
        singleton INTEGER PRIMARY KEY CHECK(singleton = 1), epoch TEXT NOT NULL, last_now INTEGER NOT NULL)`);
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_leases (
        resource TEXT PRIMARY KEY, owner_json TEXT, fence INTEGER NOT NULL CHECK(fence > 0),
        expires_ms INTEGER NOT NULL)`);
      this.#exec(`CREATE TABLE IF NOT EXISTS m12_lease_log (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT, epoch TEXT NOT NULL, operation TEXT NOT NULL,
        resource TEXT, before_json TEXT, after_json TEXT, occurred_ms INTEGER NOT NULL)`);
    });
  }

  #exec(sql, ...args) { return this.#storage.sql.exec(sql, ...args).toArray(); }

  #now(previous = 0) {
    const now = this.#clock();
    if (!Number.isSafeInteger(now) || now < previous || now < 0 ||
        !Number.isFinite(new Date(now + TTL_MS).getTime())) throw new Error("lease_clock_invalid");
    return now;
  }

  // Explicit control-plane initialization only; opening a store never activates it.
  // Restoration/epoch rotation requires a later approved recovery adapter.
  initialize(epoch) {
    if (typeof epoch !== "string" || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(epoch)) {
      throw new Error("lease_epoch_invalid");
    }
    return this.#storage.transactionSync(() => {
      const old = this.#exec("SELECT * FROM m12_lease_epoch")[0];
      if (old) {
        if (old.epoch !== epoch) throw new Error("lease_epoch_already_initialized");
        return epoch;
      }
      if (this.#exec("SELECT resource FROM m12_leases LIMIT 1").length ||
          this.#exec("SELECT sequence FROM m12_lease_log LIMIT 1").length) {
        throw new Error("lease_recovery_required");
      }
      const now = this.#now();
      this.#exec("INSERT INTO m12_lease_epoch VALUES (1, ?, ?)", epoch, now);
      this.#log(epoch, "initialize", null, null, { epoch }, now);
      return epoch;
    });
  }

  #log(epoch, operation, resource, before, after, now) {
    this.#exec(`INSERT INTO m12_lease_log (epoch, operation, resource, before_json, after_json, occurred_ms)
      VALUES (?, ?, ?, ?, ?, ?)`, epoch, operation, resource,
    before === null ? null : JSON.stringify(before), after === null ? null : JSON.stringify(after), now);
  }

  #handle(epoch, row) {
    return { epoch, lease: { resource: row.resource, owner_job: JSON.parse(row.owner_json),
      fence: row.fence, expires_at: new Date(row.expires_ms).toISOString() } };
  }

  #transaction(resource, epoch, callback) {
    resourceKey(resource);
    return this.#storage.transactionSync(() => {
      const state = this.#exec("SELECT * FROM m12_lease_epoch WHERE singleton = 1")[0];
      if (!state) throw new Error("lease_not_initialized");
      if (state.epoch !== epoch) throw new Error("lease_epoch_mismatch");
      const now = this.#now(state.last_now);
      const row = this.#exec("SELECT * FROM m12_leases WHERE resource = ?", resource)[0] ?? null;
      const result = callback(row, now);
      this.#exec("UPDATE m12_lease_epoch SET last_now = ? WHERE singleton = 1", now);
      return result;
    });
  }

  acquire(resource, ownerJob, epoch) {
    const owner = jobBytes(ownerJob);
    return this.#transaction(resource, epoch, (before, now) => {
      if (before?.owner_json !== null && before?.expires_ms > now) {
        if (before.owner_json !== owner) throw new Error("lease_busy");
        return this.#handle(epoch, before); // Lost-response replay does not extend TTL.
      }
      const fence = (before?.fence ?? 0) + 1;
      if (!Number.isSafeInteger(fence)) throw new Error("lease_fence_exhausted");
      const after = { resource, owner_json: owner, fence, expires_ms: now + TTL_MS };
      this.#exec(`INSERT INTO m12_leases VALUES (?, ?, ?, ?)
        ON CONFLICT(resource) DO UPDATE SET owner_json=excluded.owner_json,
        fence=excluded.fence, expires_ms=excluded.expires_ms`, resource, owner, fence, after.expires_ms);
      this.#log(epoch, "acquire", resource, before, after, now);
      return this.#handle(epoch, after);
    });
  }

  #ownerTransaction(resource, ownerJob, token, callback) {
    const owner = jobBytes(ownerJob);
    if (!token || !Number.isSafeInteger(token.fence) || token.fence < 1 || typeof token.epoch !== "string" ||
        Object.keys(token).sort().join() !== "epoch,fence") throw new Error("lease_token_invalid");
    return this.#transaction(resource, token.epoch, (before, now) => {
      if (!before || before.owner_json !== owner || before.fence !== token.fence || before.expires_ms <= now) {
        throw new Error("lease_stale_or_not_owned");
      }
      return callback(before, now);
    });
  }

  #owned(resource, ownerJob, token, operation) {
    return this.#ownerTransaction(resource, ownerJob, token, (before, now) => {
      const owner = before.owner_json;
      const after = { ...before, owner_json: operation === "release" ? null : owner,
        expires_ms: operation === "release" ? 0 : now + TTL_MS };
      this.#exec("UPDATE m12_leases SET owner_json = ?, expires_ms = ? WHERE resource = ?",
        after.owner_json, after.expires_ms, resource);
      this.#log(token.epoch, operation, resource, before, after, now);
      return operation === "release" ? { released: true } : this.#handle(token.epoch, after);
    });
  }

  renew(resource, ownerJob, token) { return this.#owned(resource, ownerJob, token, "renew"); }
  release(resource, ownerJob, token) { return this.#owned(resource, ownerJob, token, "release"); }

  withOwnedLease(resource, ownerJob, token, callback, { deadlineMs, resolveDeadlineMs } = {}) {
    // Internal synchronous SQL closures only. Never expose callback code over RPC
    // or perform network/async work here; no lease check result escapes for reuse.
    if (typeof callback !== "function" || callback.constructor.name === "AsyncFunction") {
      throw new Error("lease_callback_must_be_synchronous");
    }
    if (deadlineMs !== undefined && (!Number.isSafeInteger(deadlineMs) || deadlineMs < 0)) {
      throw new Error("lease_operation_deadline_invalid");
    }
    if (resolveDeadlineMs !== undefined && (typeof resolveDeadlineMs !== "function" || resolveDeadlineMs.constructor.name === "AsyncFunction")) {
      throw new Error("lease_deadline_resolver_must_be_synchronous");
    }
    return this.#ownerTransaction(resource, ownerJob, token, (row, now) => {
      // Resolve from current persisted state inside this same transaction.
      // Capture once; both entry and final clock enforce the stricter deadline.
      let effectiveDeadline = deadlineMs;
      if (resolveDeadlineMs !== undefined) {
        const resolved = resolveDeadlineMs();
        if (!Number.isSafeInteger(resolved) || resolved < 0) throw new Error("lease_operation_deadline_invalid");
        effectiveDeadline = Math.min(deadlineMs ?? resolved, resolved);
      }
      if (effectiveDeadline !== undefined && now >= effectiveDeadline) throw new Error("lease_operation_deadline_expired");
      const result = callback({ ...this.#handle(token.epoch, row), now });
      if (result && typeof result.then === "function") throw new Error("lease_callback_must_be_synchronous");
      const completed = this.#now(now);
      if (completed >= row.expires_ms) throw new Error("lease_expired_before_commit");
      if (effectiveDeadline !== undefined && completed >= effectiveDeadline) throw new Error("lease_operation_deadline_expired");
      return result;
    });
  }
}
