import { ImmutableArchive } from "./archive.mjs";
import { AuthorizationStore } from "./authorization_store.mjs";
import { AuthorizationValidationReturn } from "./authorization_return.mjs";

async function digest(bytes) {
  const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return "sha256:" + Array.from(hash, (value) => value.toString(16).padStart(2, "0")).join("");
}

export class AuthorizationValidationArchive {
  #returns;
  #archive;
  #store;

  constructor(identityPolicy, { storage, bucket, clock = Date.now, fetchKeys } = {}) {
    this.#returns = new AuthorizationValidationReturn(identityPolicy, { storage, bucket, clock, fetchKeys });
    this.#archive = new ImmutableArchive(bucket);
    this.#store = new AuthorizationStore(storage, { clock });
  }

  async archive(token, leaseToken, dispatchId, resultBytes) {
    // Always verify internally; no supplied verified object, Ref or location.
    const verified = await this.#returns.verify(token, leaseToken, dispatchId, resultBytes);
    const snapshot = { dispatch: verified.dispatch, validation_ticket: verified.validation_ticket };
    const current = () => {
      const value = this.#store.readValidationDispatch(verified.identity, leaseToken, dispatchId);
      if (JSON.stringify(value) !== JSON.stringify(snapshot)) throw new Error("authorization_archive_dispatch_changed");
      return value;
    };
    const receipt = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(verified.receipt_bytes));
    const authorizationLocation = receipt.authorization_archive;
    const receiptHash = await digest(verified.receipt_bytes);
    current();
    const authorizationArchive = await this.#archive.put(authorizationLocation.key, verified.authorization_bytes,
      { sha256: authorizationLocation.sha256, size_bytes: authorizationLocation.size_bytes });
    current();
    // This internal validation artifact has no PublicationReceipt business ID.
    // Keep its exact bytes in raw/, not the business lifecycle receipts namespace.
    const receiptArchive = await this.#archive.put("raw/" + receiptHash.slice(7), verified.receipt_bytes,
      { sha256: receiptHash, size_bytes: verified.receipt_bytes.length });
    current();
    const authorizationBytes = await this.#archive.read(authorizationArchive.key,
      { sha256: authorizationArchive.sha256, size_bytes: authorizationArchive.size_bytes });
    current();
    const receiptBytes = await this.#archive.read(receiptArchive.key,
      { sha256: receiptArchive.sha256, size_bytes: receiptArchive.size_bytes });
    const final = current();
    // Still unregistered objects. Final permission/config checks and atomic
    // ticket consumption/index append must happen after this entire operation.
    return { ...verified, ...final, authorization_bytes: authorizationBytes, receipt_bytes: receiptBytes,
      authorization_archive: authorizationArchive, validation_receipt_archive: receiptArchive };
  }
}
