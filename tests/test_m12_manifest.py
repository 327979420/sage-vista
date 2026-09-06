"""M12 manifest verifies raw bytes and trusted preparation inputs without I/O."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, M12_PROJECTION_KINDS, validate_contract, validate_contracts
from services.publication.authorization import build_publication_authorization
from services.publication.evaluation import build_evaluation_snapshot
from services.publication.inventory import build_source_inventory
from services.publication.manifest import build_release_manifest
from tests.test_m12_authorization import approval
from tests.test_m12_evaluation import source, DAY, TIME, ref


def raw(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def seal(payload):
    body = {k: v for k, v in payload.items() if k not in ("release_id", "content_fingerprint", "generated_at")}
    fingerprint = canonical_fingerprint(body)
    payload.update(release_id="release:" + fingerprint, content_fingerprint=fingerprint)
    return payload


def preparation():
    eval_evidence = source()
    evaluation = build_evaluation_snapshot(eval_evidence, generated_at=TIME)
    eval_ref = {"id": evaluation["evaluation_snapshot_id"], "content_fingerprint": evaluation["content_fingerprint"]}
    config = eval_evidence["inventory"]["config_ref"]
    auth_evidence = approval()
    auth_evidence["request"]["config_ref"] = config
    authorization = build_publication_authorization(auth_evidence, generated_at=TIME)
    scan, registry = ref("scan"), ref("registry")
    graph = {"as_of": DAY, "config_ref": config, "roots": sorted([scan, eval_ref], key=lambda r: r["id"]), "nodes": [
        {"ref": config, "dependencies": []}, {"ref": scan, "dependencies": [registry]},
        {"ref": registry, "dependencies": []}, {"ref": eval_ref, "dependencies": [evaluation["inventory_ref"]]},
        {"ref": evaluation["inventory_ref"], "dependencies": []},
    ]}
    inventory = build_source_inventory(graph, generated_at=TIME)
    expectations = {path: {"schema_version": "1.0.0", "kind": kind, "as_of": DAY, "source_refs": [scan],
                            "data": {"status": "unavailable", "reason": "synthetic_empty"}}
                    for path, kind in M12_PROJECTION_KINDS.items()}
    registry_bytes = (Path(__file__).parents[1] / "public/factor-registry.json").read_bytes()
    files = {path: raw(content) for path, content in expectations.items()}
    files.update({"factor-registry.json": registry_bytes, "evaluation.json": raw(evaluation)})
    return {"as_of": DAY, "code_commit": "a" * 40, "config_ref": config,
            "policy_refs": [{"module": "M07", "name": "test-policy", "version": "1.0.0",
                             "content_fingerprint": ref("policy")["content_fingerprint"], "definition_commit": "b" * 40,
                             "source_path": "services/ranking/policies.py", "source_blob": "c" * 40}],
            "last_verified_release_ref": None, "inventory": inventory, "inventory_evidence": graph,
            "source_dates": {r["id"]: DAY for r in inventory["records"]},
            "authorization": authorization, "authorization_evidence": auth_evidence,
            "evaluation": evaluation, "evaluation_evidence": eval_evidence, "registry_ref": registry,
            "registry_bytes": registry_bytes, "projection_expectations": expectations, "files": files}


class ReleaseManifestTests(unittest.TestCase):
    def setUp(self):
        self.evidence = preparation()
        self.payload = build_release_manifest(self.evidence, generated_at=TIME)

    def validate(self, payload, evidence=None, **kwargs):
        validate_contract("ReleaseManifest", payload, release_manifest_evidence=self.evidence if evidence is None else evidence, **kwargs)

    def test_exact_ten_files_roles_metadata_and_empty_evaluation(self):
        self.validate(self.payload)
        files = {f["path"]: f for f in self.payload["files"]}
        self.assertEqual(len(files), 10)
        self.assertEqual(files["notification-plan.json"]["roles"], ["audit", "discord"])
        self.assertEqual(files["factor-registry.json"]["registry_version"], "0.10.0")
        self.assertIsNone(files["evaluation.json"]["coverage_end"])
        for path, entry in files.items():
            self.assertEqual(entry["size_bytes"], len(self.evidence["files"][path]))
            self.assertEqual(entry["sha256"], "sha256:" + hashlib.sha256(self.evidence["files"][path]).hexdigest())

    def test_missing_trusted_context_is_rejected_even_with_partial_flag(self):
        for kwargs in ({}, {"allow_partial_manifest": True}):
            with self.assertRaises(ContractError): validate_contract("ReleaseManifest", self.payload, **kwargs)

    def test_resealed_missing_extra_duplicate_and_private_role_changes(self):
        for mutation in ("missing", "extra", "duplicate", "private", "size", "required"):
            payload = deepcopy(self.payload)
            if mutation == "missing": payload["files"].pop()
            elif mutation == "extra": payload["files"].append({**payload["files"][0], "path": "other.json"})
            elif mutation == "duplicate": payload["files"].append(payload["files"][0])
            elif mutation == "private": next(f for f in payload["files"] if f["path"] == "notification-plan.json")["roles"].append("web")
            elif mutation == "size": payload["files"][0]["size_bytes"] = True
            else: payload["files"][0]["required"] = 1
            with self.subTest(mutation=mutation), self.assertRaises(ContractError): self.validate(seal(payload), allow_partial_manifest=True)

    def test_same_json_different_bytes_needs_new_manifest_identity(self):
        evidence = deepcopy(self.evidence)
        evidence["files"]["overview.json"] += b"\n"
        with self.assertRaises(ContractError): self.validate(self.payload, evidence)
        other = build_release_manifest(evidence, generated_at=TIME)
        self.assertNotEqual(other["release_id"], self.payload["release_id"])

    def test_changed_business_data_does_not_pass_by_rehashing(self):
        evidence = deepcopy(self.evidence)
        content = deepcopy(evidence["projection_expectations"]["rankings.json"])
        content["data"] = {"fabricated_winner": "A"}
        evidence["files"]["rankings.json"] = raw(content)
        with self.assertRaises(ContractError): build_release_manifest(evidence, generated_at=TIME)

    def test_unknown_missing_and_traversal_files_rejected(self):
        for filename in ("../overview.json", "/overview.json", "folder/overview.json", "unknown.json"):
            evidence = deepcopy(self.evidence)
            evidence["files"][filename] = evidence["files"].pop("overview.json")
            with self.subTest(filename=filename), self.assertRaises(ContractError): build_release_manifest(evidence, generated_at=TIME)

    def test_duplicate_keys_nonfinite_and_release_self_reference_rejected(self):
        samples = [b'{"kind":"overview","kind":"other"}', b'{"x":NaN}', b'{"x":1e999}', b'\xff', b'[]', b'{"nested":{"release_id":"self"}}']
        for content in samples:
            evidence = deepcopy(self.evidence)
            evidence["files"]["overview.json"] = content
            with self.subTest(content=content), self.assertRaises(ContractError): build_release_manifest(evidence, generated_at=TIME)

    def test_projection_kind_date_and_sources_cannot_be_forged(self):
        for key, value in (("kind", "rankings"), ("as_of", "2026-09-10"), ("source_refs", [ref("fake")]), ("source_refs", []), ("schema_version", "2.0.0")):
            evidence = deepcopy(self.evidence)
            content = evidence["projection_expectations"]["overview.json"]
            content[key] = value
            evidence["files"]["overview.json"] = raw(content)
            with self.subTest(key=key), self.assertRaises(ContractError): build_release_manifest(evidence, generated_at=TIME)

    def test_evaluation_and_registry_bytes_must_match_frozen_objects(self):
        for path in ("evaluation.json", "factor-registry.json"):
            evidence = deepcopy(self.evidence)
            content = json.loads(evidence["files"][path])
            content["generated_at" if path == "evaluation.json" else "registry_version"] = "2026-09-11T00:00:00Z" if path == "evaluation.json" else "0.99.0"
            evidence["files"][path] = raw(content)
            with self.subTest(path=path), self.assertRaises(ContractError): build_release_manifest(evidence, generated_at=TIME)

    def test_release_grant_must_match_code_and_scan_date(self):
        for mutation in ("code", "expired", "future", "revoke"):
            evidence = deepcopy(self.evidence)
            if mutation == "code": evidence["code_commit"] = "d" * 40
            else:
                approval = evidence["authorization_evidence"]
                if mutation == "expired": approval["request"]["valid_until"] = "2026-09-08"
                elif mutation == "future": approval["request"]["effective_from"] = "2026-09-10"
                else:
                    prior = evidence["authorization"]
                    approval["history"] = [prior]
                    approval["request"].update(action="revoke", permissions=[], prior_authorization_ref={"id": prior["authorization_id"], "content_fingerprint": prior["content_fingerprint"]})
                evidence["authorization"] = build_publication_authorization(approval, generated_at=TIME)
            with self.subTest(mutation=mutation), self.assertRaises(ContractError): build_release_manifest(evidence, generated_at=TIME)

    def test_previous_target_and_policies_are_bound_against_resealed_changes(self):
        for key, value in (("previous_release_ref", ref("other-release")), ("policy_refs", []), ("authorization_ref", ref("other-grant")), ("evaluation_snapshot_ref", ref("other-eval"))):
            payload = deepcopy(self.payload)
            payload[key] = value
            with self.subTest(key=key), self.assertRaises(ContractError): self.validate(seal(payload))
        evidence = deepcopy(self.evidence)
        evidence["last_verified_release_ref"] = ref("previous-release")
        self.assertEqual(build_release_manifest(evidence, generated_at=TIME)["previous_release_ref"], ref("previous-release"))

    def test_future_source_and_bad_policy_source_rejected(self):
        evidence = deepcopy(self.evidence)
        evidence["source_dates"]["scan"] = "2026-09-10"
        with self.assertRaises(ContractError): build_release_manifest(evidence, generated_at=TIME)
        for key, value in (("source_path", "../policies.py"), ("source_blob", "short"), ("module", "M13")):
            evidence = deepcopy(self.evidence)
            evidence["policy_refs"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ContractError): build_release_manifest(evidence, generated_at=TIME)

    def test_unknown_version_and_fields_rejected_collection_keeps_identity_rules(self):
        for key, value in (("schema_version", "2.1.0"), ("extra", True), ("future_data_used", 0)):
            payload = deepcopy(self.payload)
            payload[key] = value
            with self.subTest(key=key), self.assertRaises(ContractError): self.validate(seal(payload))
        validate_contracts([("ReleaseManifest", self.payload)], release_manifest_evidence=self.evidence)
        with self.assertRaises(ContractError): validate_contracts([("ReleaseManifest", self.payload)] * 2, release_manifest_evidence=self.evidence)

    def test_generation_time_is_not_identity_and_inputs_are_not_aliased(self):
        before = deepcopy(self.evidence)
        payload = build_release_manifest(self.evidence, generated_at="2026-09-11T00:00:00Z")
        self.assertEqual(payload["release_id"], self.payload["release_id"])
        payload["files"][0]["source_refs"][0]["id"] = "changed"
        self.assertEqual(self.evidence, before)


if __name__ == "__main__": unittest.main()
