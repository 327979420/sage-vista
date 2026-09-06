import { AuthorizationValidationArchive } from "./authorization_validation_archive.mjs";
import { AuthorizationStore } from "./authorization_store.mjs";

const REQUEST_FIELDS = ["action", "code_commit", "config_ref", "effective_from", "permissions",
  "prior_authorization_ref", "publication_mode", "reason", "scope", "valid_until"];

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
  }
  return value;
}
const encode = value => JSON.stringify(canonical(value));

export class AuthorizationRegistration {
  #policy;
  #archive;
  #store;

  constructor(identityPolicy, { registrationPolicy = null, ...dependencies } = {}) {
    // Server-owned permission to register one exact approved request. This is
    // not a request argument, config producer or second business validator.
    if (registrationPolicy === null) return;
    const policy = JSON.parse(JSON.stringify(registrationPolicy));
    if (Object.keys(policy).sort().join() !== "actor_id,approver_id,request" ||
        typeof policy.actor_id !== "string" || !/^[1-9][0-9]*$/.test(policy.actor_id) ||
        typeof policy.approver_id !== "string" || !/^[1-9][0-9]*$/.test(policy.approver_id) ||
        !policy.request || Object.keys(policy.request).sort().join() !== REQUEST_FIELDS.join()) {
      throw new Error("authorization_registration_policy_invalid");
    }
    this.#policy = encode(policy); // Immutable server snapshot, never caller mutable state.
    this.#archive = new AuthorizationValidationArchive(identityPolicy, dependencies);
    this.#store = new AuthorizationStore(dependencies.storage, { clock: dependencies.clock });
  }

  async register(token, leaseToken, dispatchId, resultBytes) {
    if (!this.#policy) throw new Error("authorization_registration_disabled");
    const verified = await this.#archive.archive(token, leaseToken, dispatchId, resultBytes);
    const authorization = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(verified.authorization_bytes));
    const actual = encode({ actor_id: verified.identity.actor_id, approver_id: authorization.approver_id,
      request: Object.fromEntries(REQUEST_FIELDS.map(key => [key, authorization[key]])) });
    const permission = () => actual === this.#policy;
    const snapshot = { dispatch: verified.dispatch, validation_ticket: verified.validation_ticket,
      return_record: verified.return_record };
    return this.#store.registerValidatedAuthorization(verified.identity, leaseToken, dispatchId, snapshot, permission);
  }
}
