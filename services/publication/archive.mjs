// Byte transport only. Contract validation and authoritative registration belong
// to the authenticated coordinator; possession of this adapter grants neither.
const DIGEST = "[a-f0-9]{64}";
const KEY = new RegExp(`^(?:(?:raw|indexes)/${DIGEST}|facts/[A-Za-z][A-Za-z0-9]*/${DIGEST}|(?:manifests|receipts|authority)/${DIGEST}\\.json|releases/${DIGEST}/[a-z][a-z0-9-]*\\.json)$`);

function descriptor(key, expected) {
  if (typeof key !== "string" || !KEY.test(key)) throw new Error("archive_key_invalid");
  if (!expected || Object.keys(expected).sort().join() !== "sha256,size_bytes" ||
      typeof expected.sha256 !== "string" ||
      !/^sha256:[a-f0-9]{64}$/.test(expected.sha256) ||
      !Number.isSafeInteger(expected.size_bytes) || expected.size_bytes < 0) {
    throw new Error("archive_descriptor_invalid");
  }
  const result = { sha256: expected.sha256, size_bytes: expected.size_bytes };
  if (/^(raw|indexes)\//.test(key) && key.split("/")[1] !== result.sha256.slice(7)) {
    throw new Error("archive_content_key_mismatch");
  }
  return result;
}

async function verify(bytes, expected) {
  if (bytes.byteLength !== expected.size_bytes) throw new Error("archive_size_mismatch");
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  const hash = "sha256:" + Array.from(digest, (b) => b.toString(16).padStart(2, "0")).join("");
  if (hash !== expected.sha256) throw new Error("archive_hash_mismatch");
}

export class ImmutableArchive {
  #bucket;

  constructor(bucket) {
    if (!bucket || typeof bucket.put !== "function" || typeof bucket.get !== "function") {
      throw new Error("archive_binding_required");
    }
    this.#bucket = bucket;
  }

  async read(key, expected) {
    const frozen = descriptor(key, expected);
    const object = await this.#bucket.get(key);
    if (object === null) throw new Error("archive_object_missing");
    const bytes = new Uint8Array(await object.arrayBuffer());
    await verify(bytes, frozen);
    return bytes;
  }

  async put(key, input, expected) {
    const frozen = descriptor(key, expected);
    if (!(input instanceof Uint8Array)) throw new Error("archive_bytes_required");
    // Copy before the first await: caller mutation cannot change the write.
    const bytes = new Uint8Array(input);
    await verify(bytes, frozen);
    // The R2 condition is atomic, unlike a head/get followed by an ordinary put.
    // A thrown/uncertain write is not acknowledged; retry uses the same key/bytes.
    await this.#bucket.put(key, bytes, { onlyIf: new Headers({ "If-None-Match": "*" }) });
    // Both a new write and a precondition miss require an actual byte readback.
    const stored = await this.read(key, frozen);
    if (stored.some((byte, i) => byte !== bytes[i])) throw new Error("archive_bytes_mismatch");
    return { key, ...frozen };
  }
}
