import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { ImmutableArchive } from "../services/publication/archive.mjs";

const bytes = (text) => new TextEncoder().encode(text);
const describe = (value) => ({
  sha256: "sha256:" + createHash("sha256").update(value).digest("hex"),
  size_bytes: value.length,
});
const key = `facts/SourceInventory/${"a".repeat(64)}`;

// Deterministic R2 binding double, not a deployed bucket or lock-policy test.
class Bucket {
  objects = new Map();
  puts = 0;
  gets = 0;
  async put(key, value, options) {
    assert.equal(options.onlyIf.get("If-None-Match"), "*");
    this.puts++;
    if (this.objects.has(key)) return null;
    this.objects.set(key, new Uint8Array(value));
    return { key };
  }
  async get(key) {
    this.gets++;
    const value = this.objects.get(key);
    return value === undefined ? null : { arrayBuffer: async () => new Uint8Array(value).buffer };
  }
}

test("all seven archive namespaces preserve UTF-8 original bytes and replay", async () => {
  const bucket = new Bucket();
  const archive = new ImmutableArchive(bucket);
  const value = bytes('{"证据": 1}\n');
  const expected = describe(value);
  const digest = expected.sha256.slice(7);
  const keys = [`raw/${digest}`, `indexes/${digest}`, key,
    `manifests/${digest}.json`, `receipts/${digest}.json`,
    `authority/${digest}.json`, `releases/${digest}/notification-plan.json`];
  for (const path of keys) {
    assert.deepEqual(await archive.put(path, value, expected), { key: path, ...expected });
    assert.deepEqual(await archive.put(path, value, expected), { key: path, ...expected });
    assert.deepEqual(await archive.read(path, expected), value);
  }
  assert.equal(bucket.objects.size, 7);
  assert.equal(bucket.gets, 21);
});

test("concurrent same bytes converge; competing different bytes cannot overwrite", async () => {
  const bucket = new Bucket();
  const a = new ImmutableArchive(bucket);
  const b = new ImmutableArchive(bucket);
  const value = bytes("a");
  const results = await Promise.all(Array.from({ length: 20 }, () => a.put(key, value, describe(value))));
  assert.ok(results.every((r) => r.sha256 === describe(value).sha256));
  const conflict = bytes("b");
  await assert.rejects(b.put(key, conflict, describe(conflict)), /hash_mismatch/);
  assert.deepEqual(bucket.objects.get(key), value);
  const fresh = new Bucket();
  const competing = new ImmutableArchive(fresh);
  const race = await Promise.allSettled([value, conflict].map((v) => competing.put(key, v, describe(v))));
  assert.equal(race.filter((r) => r.status === "fulfilled").length, 1);
  assert.equal(fresh.objects.size, 1);
});

test("key traversal, temporary keys and wrong content addresses fail before I/O", async () => {
  const bucket = new Bucket();
  const archive = new ImmutableArchive(bucket);
  const value = bytes("x");
  for (const path of ["current", "staging/job/file", `${key}/../x`,
    `releases/${"a".repeat(64)}/../secret.json`, `raw/${"a".repeat(64)}`,
    `indexes/${"a".repeat(64)}`, key + "\n"]) {
    await assert.rejects(archive.put(path, value, describe(value)));
  }
  assert.equal(bucket.puts + bucket.gets, 0);
});

test("invalid descriptors and non-byte input fail before I/O", async () => {
  const bucket = new Bucket();
  const archive = new ImmutableArchive(bucket);
  const value = bytes("x");
  for (const expected of [null, {}, { ...describe(value), size_bytes: true },
    { ...describe(value), size_bytes: -1 }, { ...describe(value), extra: 1 },
    { ...describe(value), sha256: "x" }, { ...describe(value), size_bytes: 2 }, describe(bytes("y"))]) {
    await assert.rejects(archive.put(key, value, expected));
  }
  await assert.rejects(archive.put(key, "x", describe(value)), /bytes_required/);
  assert.equal(bucket.puts + bucket.gets, 0);
});

test("caller mutation while hashing cannot change submitted bytes or descriptor", async () => {
  const bucket = new Bucket();
  const archive = new ImmutableArchive(bucket);
  const value = bytes("abc");
  const expected = describe(value);
  const original = { ...expected };
  const pending = archive.put(key, value, expected);
  value.fill(0);
  expected.sha256 = describe(value).sha256;
  assert.deepEqual(await pending, { key, ...original });
  assert.deepEqual(bucket.objects.get(key), bytes("abc"));
});

test("missing and corrupted readback never acknowledge success", async () => {
  for (const corrupt of [null, bytes("bad"), bytes("longer")]) {
    const bucket = new Bucket();
    bucket.get = async () => corrupt === null ? null : { arrayBuffer: async () => corrupt.buffer };
    await assert.rejects(new ImmutableArchive(bucket).put(key, bytes("abc"), describe(bytes("abc"))));
  }
  await assert.rejects(new ImmutableArchive(new Bucket()).read(key, describe(bytes("abc"))), /missing/);
});

test("lost write response can safely retry without erasing the first object", async () => {
  const bucket = new Bucket();
  const normalPut = bucket.put.bind(bucket);
  let fail = true;
  bucket.put = async (...args) => {
    const result = await normalPut(...args);
    if (fail) { fail = false; throw new Error("response_lost"); }
    return result;
  };
  const archive = new ImmutableArchive(bucket);
  const value = bytes("original\n");
  await assert.rejects(archive.put(key, value, describe(value)), /response_lost/);
  assert.equal(bucket.gets, 0);
  await archive.put(key, value, describe(value));
  assert.deepEqual(bucket.objects.get(key), value);
});

test("read failure propagates, and retry verifies existing object", async () => {
  const bucket = new Bucket();
  const normalGet = bucket.get.bind(bucket);
  bucket.get = async () => { throw new Error("read_unavailable"); };
  const archive = new ImmutableArchive(bucket);
  const value = bytes("original");
  await assert.rejects(archive.put(key, value, describe(value)), /read_unavailable/);
  bucket.get = normalGet;
  await archive.put(key, value, describe(value));
  const returned = await archive.read(key, describe(value));
  returned.fill(0);
  assert.deepEqual(await archive.read(key, describe(value)), value);
});

test("binding is explicit and adapter exposes no delete or overwrite operation", () => {
  assert.throws(() => new ImmutableArchive(), /binding_required/);
  assert.deepEqual(Object.getOwnPropertyNames(ImmutableArchive.prototype).sort(), ["constructor", "put", "read"]);
});
