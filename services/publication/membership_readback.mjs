// Read-only fixed registration input. No RPC, input ticket or append authority.
import { ImmutableArchive } from './archive.mjs';
import { PreparationValidationSession } from './preparation_session.mjs';
import { PreparationEvidenceReadback } from './preparation_readback.mjs';
import { MembershipUseFactory } from './membership_use.mjs';
import { MembershipObservationIndex } from './membership_index.mjs';
import { base64 } from './job_wire.mjs';

const MAX_INPUT = 32 * 1024 * 1024;
const SOURCE = 'https://eodhd.com/api/exchange-symbol-list/US?delisted=0&fmt=json';
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ?
  Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const same = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
const parse = bytes => JSON.parse(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes));
function location(value, limit) {
  if (!value || Object.keys(value).sort().join() !== 'key,sha256,size_bytes' ||
      typeof value.sha256 !== 'string' || !/^sha256:[a-f0-9]{64}$/.test(value.sha256) ||
      value.key !== 'raw/' + value.sha256.slice(7) || !Number.isSafeInteger(value.size_bytes) ||
      value.size_bytes < 1 || value.size_bytes > limit) throw new Error('membership_readback_location_invalid');
  return { key: value.key, sha256: value.sha256, size_bytes: value.size_bytes };
}

export class MembershipRegistrationReadback {
  #policy;
  #license;
  #options;
  #identityPolicy;
  #preparation;
  #selected;
  #index;
  #archive;
  #resource;

  constructor(identityPolicy, { preparationPolicy, licensePolicy = null, ...dependencies } = {}) {
    if (licensePolicy === null) return;
    if (!licensePolicy || Object.keys(licensePolicy).sort().join() !== 'license_archive,license_valid_from,license_valid_until,purpose') {
      throw new Error('membership_readback_fixed_license_required');
    }
    this.#policy = structuredClone(preparationPolicy);
    this.#license = structuredClone(licensePolicy);
    this.#identityPolicy = structuredClone(identityPolicy);
    this.#options = { ...dependencies, preparationPolicy: this.#policy };
    this.#preparation = new PreparationEvidenceReadback(identityPolicy, this.#options);
    this.#selected = new PreparationValidationSession(identityPolicy, this.#options);
    this.#index = new MembershipObservationIndex(dependencies.storage, dependencies);
    this.#archive = new ImmutableArchive(dependencies.bucket);
    this.#resource = `daily/${this.#policy.as_of}/${this.#policy.config_ref.id}`;
  }

  async capture(token, candidateArchive) {
    if (!this.#license) throw new Error('membership_readback_disabled');
    const candidate = location(candidateArchive, 16384);
    const selected = await this.#selected.selectedForUse(token);
    const use = new MembershipUseFactory(this.#identityPolicy, { ...this.#options,
      acquisitionPolicy: { ...this.#license, ...selected } });
    const preparedRaw = await this.#preparation.readValidationInput(token, selected.lease_token);
    const identity = parse(preparedRaw).identity;
    const currentIndex = this.#index.readCurrent(identity, selected.lease_token, this.#resource);
    const currentCheck = async () => {
      if (!same(selected, await this.#selected.selectedForUse(token))) throw new Error('membership_readback_selection_changed');
      await use.acquisitionEvidence(token, this.#policy.as_of, SOURCE);
      if (!same(selected, await this.#selected.selectedForUse(token))) throw new Error('membership_readback_selection_changed');
      if (!same(currentIndex, this.#index.readCurrent(identity, selected.lease_token, this.#resource))) {
        throw new Error('membership_readback_index_changed');
      }
    };
    await currentCheck();
    let budget = preparedRaw.length * 4 / 3;
    const read = async (descriptor, own) => {
      const { key, sha256, size_bytes } = descriptor;
      const data = own ? await use.read(token, key, { sha256, size_bytes }) :
        await this.#archive.read(key, { sha256, size_bytes });
      await currentCheck();
      budget += Math.ceil(data.length / 3) * 4;
      if (budget > MAX_INPUT) throw new Error('membership_readback_input_too_large');
      return data;
    };
    const source = async (descriptor, own) => {
      const observation = await read(location(descriptor, 16384), own);
      // Routing only: Python alone validates the collector protocol and meaning.
      // Pending objects retain current-session ownership checks for EVERY read.
      const body = parse(observation);
      const response = await read(location(body.response, 32 * 1024 * 1024), own);
      const acquisition = await read(location(body.acquisition_evidence, 1024 * 1024), own);
      return { observation_bytes: base64(observation), response_bytes: base64(response), acquisition_bytes: base64(acquisition) };
    };
    const originals = [];
    for (const descriptor of currentIndex.history) originals.push(await source(descriptor, false));
    if (!same(candidate, currentIndex.head)) originals.push(await source(candidate, true));
    const raw = new TextEncoder().encode(JSON.stringify({ protocol: 'm12-membership-registration/1', identity,
      preparation_base64: base64(preparedRaw), expected_index: currentIndex, candidate_archive: candidate,
      acquisition_archive: this.#license.license_archive, observations_base64: originals }));
    if (raw.length > MAX_INPUT) throw new Error('membership_readback_input_too_large');
    await currentCheck();
    return raw; // Persist and bind this actual input before dispatch/registration.
  }
}
