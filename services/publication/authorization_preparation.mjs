import { ImmutableArchive } from "./archive.mjs";
import { AuthorizationStore } from "./authorization_store.mjs";
import { ReviewedRequestArchive } from "./review_archive.mjs";

export class AuthorizationPreparation {
  #reviews;
  #store;
  #archive;
  #clock;

  constructor(identityPolicy, reviewPolicy, { storage, bucket, clock = Date.now, ...dependencies } = {}) {
    this.#reviews = new ReviewedRequestArchive(identityPolicy, reviewPolicy, { bucket, clock, ...dependencies });
    this.#store = new AuthorizationStore(storage, { clock });
    this.#archive = new ImmutableArchive(bucket);
    this.#clock = clock;
  }

  async prepare(token, leaseToken) {
    // No supplied Job, history, ticket, request, Ref or claimed validation input.
    const readback = await this.#reviews.readForValidation(token);
    const bundle = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(readback.approval_archive.bundle_bytes));
    const alive = () => {
      const now = this.#clock();
      if (!Number.isSafeInteger(now) || now < Date.parse(bundle.observed_at) || now >= bundle.identity.expires_at * 1000) {
        throw new Error("authorization_preparation_identity_expired");
      }
    };
    alive();
    const ticket = this.#store.prepareValidation(bundle.identity.job, leaseToken, readback.approval_evidence_ref);
    const historyBytes = [];
    for (const item of ticket.history) {
      alive();
      historyBytes.push(await this.#archive.read(item.archive.key,
        { sha256: item.archive.sha256, size_bytes: item.archive.size_bytes }));
    }
    alive();
    const currentTicket = this.#store.readPreparedValidation(bundle.identity.job, leaseToken, ticket.ticket_id);
    alive();
    return { ...readback, validation_ticket: currentTicket, history_bytes: historyBytes };
  }
}
