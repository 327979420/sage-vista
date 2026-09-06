// Internal evidence acquisition only. No grant decision, route or runtime factory.
import { GitHubIdentityVerifier } from './identity.mjs';
import { ImmutableArchive } from './archive.mjs';
import { AuthorizationStore } from './authorization_store.mjs';

export class PreparationEvidenceReadback {
  #policy;
  #identity;
  #archive;
  #store;
  #clock;
  #resource;

  constructor(identityPolicy, { preparationPolicy = null, storage, bucket, clock = Date.now, fetchKeys } = {}) {
    if (preparationPolicy === null) return;
    const p = JSON.parse(JSON.stringify(preparationPolicy));
    if (!p || Object.keys(p).sort().join() !== 'actor_id,as_of,config_archive,config_ref' ||
        typeof p.actor_id !== 'string' || !/^[1-9][0-9]*$/.test(p.actor_id) ||
        typeof p.as_of !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(p.as_of) ||
        !Number.isFinite(Date.parse(p.as_of + 'T00:00:00Z')) || new Date(p.as_of).toISOString().slice(0, 10) !== p.as_of ||
        !p.config_ref || Object.keys(p.config_ref).sort().join() !== 'content_fingerprint,id' ||
        typeof p.config_ref.id !== 'string' || !/^[A-Za-z0-9_:.-]+$/.test(p.config_ref.id) ||
        typeof p.config_ref.content_fingerprint !== 'string' || !/^sha256:[a-f0-9]{64}$/.test(p.config_ref.content_fingerprint) ||
        !p.config_archive || Object.keys(p.config_archive).sort().join() !== 'key,sha256,size_bytes' ||
        typeof p.config_archive.key !== 'string' || !/^raw\/[a-f0-9]{64}$/.test(p.config_archive.key) ||
        p.config_archive.sha256 !== 'sha256:' + p.config_archive.key.slice(4) ||
        !Number.isSafeInteger(p.config_archive.size_bytes) || p.config_archive.size_bytes < 1 ||
        p.config_archive.size_bytes > 1024 * 1024) throw new Error('preparation_readback_policy_invalid');
    this.#identity = new GitHubIdentityVerifier(identityPolicy, { clock, fetchKeys });
    this.#archive = new ImmutableArchive(bucket);
    this.#store = new AuthorizationStore(storage, { clock });
    this.#clock = clock;
    this.#policy = p;
    this.#resource = `daily/${p.as_of}/${p.config_ref.id}`;
  }

  async read(token, leaseToken) {
    if (!this.#policy) throw new Error('preparation_readback_disabled');
    if (!leaseToken || Object.keys(leaseToken).sort().join() !== 'epoch,fence' ||
        typeof leaseToken.epoch !== 'string' || !Number.isSafeInteger(leaseToken.fence)) {
      throw new Error('preparation_readback_lease_invalid');
    }
    // Freeze the supplied handle before key retrieval. Identity, history and
    // target objects are always obtained internally, never supplied to read().
    const handle = { ...leaseToken };
    const identity = await this.#identity.verify(token);
    if (identity.actor_id !== this.#policy.actor_id) throw new Error('preparation_readback_actor_mismatch');
    const snapshot = this.#store.readCurrentForPreparation(identity, handle, this.#resource);
    const expected = JSON.stringify(snapshot);
    const current = () => {
      const value = this.#store.readCurrentForPreparation(identity, handle, this.#resource);
      if (JSON.stringify(value) !== expected) throw new Error('preparation_readback_history_changed');
    };
    const historyBytes = [];
    for (const item of snapshot.history) {
      const { key, sha256, size_bytes } = item.archive;
      historyBytes.push(await this.#archive.read(key, { sha256, size_bytes }));
      current();
    }
    const { key, sha256, size_bytes } = this.#policy.config_archive;
    const configBytes = await this.#archive.read(key, { sha256, size_bytes });
    current();
    const now = this.#clock();
    if (!Number.isSafeInteger(now) || now < 0 || now > 8640000000000000) throw new Error('preparation_readback_clock_invalid');
    const evidence = { current_history: snapshot, history_bytes: historyBytes,
      config_ref: { ...this.#policy.config_ref }, config_archive: { ...this.#policy.config_archive },
      config_bytes: configBytes, code_commit: identity.code_commit, as_of: this.#policy.as_of,
      checked_at: new Date(now).toISOString().replace(/\.\d{3}Z$/, 'Z') };
    current();
    // No permission token: the sole Python validator must validate these bytes,
    // policies and rights. Its consumer must recheck authority at actual use.
    return { identity, evidence };
  }
}
