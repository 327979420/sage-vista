"""Public M12 contract boundary tests using a synthetic trusted index only."""

from copy import deepcopy
import unittest

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, validate_contract, validate_contracts
from services.publication.inventory import build_source_inventory


TIME = "2026-09-06T00:00:00Z"


def ref(name):
    return {"id": name, "content_fingerprint": canonical_fingerprint({"name": name})}


def index():
    config, root, left, right, shared = [ref(n) for n in ("config", "root", "left", "right", "shared")]
    return {
        "as_of": "2026-09-04", "config_ref": config, "roots": [root],
        "nodes": [
            {"ref": config, "dependencies": []},
            {"ref": root, "dependencies": [left, right]},
            {"ref": left, "dependencies": [shared]},
            {"ref": right, "dependencies": [shared]},
            {"ref": shared, "dependencies": []},
        ],
    }


def resign(payload):
    body = {k: v for k, v in payload.items() if k not in {
        "inventory_id", "content_fingerprint", "generated_at",
    }}
    fingerprint = canonical_fingerprint(body)
    payload.update(content_fingerprint=fingerprint, inventory_id="source-inventory:" + fingerprint)
    return payload


class SourceInventoryTests(unittest.TestCase):
    def setUp(self):
        self.evidence = index()
        self.payload = build_source_inventory(self.evidence, generated_at=TIME)

    def validate(self, payload):
        validate_contract("SourceInventory", payload, source_inventory_evidence=self.evidence)

    def test_diamond_closure_includes_root_and_shared_dependency_once(self):
        self.validate(self.payload)
        self.assertEqual([r["id"] for r in self.payload["records"]], ["left", "right", "root", "shared"])

    def test_no_authoritative_evidence_fails_closed(self):
        with self.assertRaises(ContractError):
            validate_contract("SourceInventory", self.payload)

    def test_resealed_deleted_added_replaced_records_are_rejected(self):
        for mutation in ("delete", "add", "replace"):
            with self.subTest(mutation=mutation):
                payload = deepcopy(self.payload)
                if mutation == "delete":
                    payload["records"].pop()
                elif mutation == "add":
                    payload["records"].append(ref("z-forged"))
                else:
                    payload["records"][0]["content_fingerprint"] = ref("forged")["content_fingerprint"]
                with self.assertRaises(ContractError):
                    self.validate(resign(payload))

    def test_resealed_root_date_and_config_changes_rejected(self):
        for key, value in (("roots", [ref("left")]), ("as_of", "2026-09-03"), ("config_ref", ref("other"))):
            with self.subTest(key=key):
                payload = deepcopy(self.payload)
                payload[key] = value
                with self.assertRaises(ContractError):
                    self.validate(resign(payload))

    def test_unknown_fields_versions_and_bad_ref_types_rejected(self):
        candidates = []
        for key, value in (("schema_version", "1.0.1"), ("schema_version", "2.0.0"), ("extra", True)):
            payload = deepcopy(self.payload)
            payload[key] = value
            candidates.append(payload)
        for key, value in (("id", True), ("id", " left "), ("content_fingerprint", "invalid"), ("extra", None)):
            payload = deepcopy(self.payload)
            payload["records"][0][key] = value
            candidates.append(payload)
        for payload in candidates:
            with self.subTest(payload=payload):
                with self.assertRaises(ContractError):
                    self.validate(resign(payload))

    def test_unsorted_and_duplicate_refs_rejected(self):
        for value in (list(reversed(self.payload["records"])), [self.payload["records"][0]] * 2):
            payload = deepcopy(self.payload)
            payload["records"] = value
            with self.assertRaises(ContractError):
                self.validate(resign(payload))

    def test_unknown_root_and_unresolved_content_fail(self):
        for case in ("missing", "conflict", "config"):
            evidence = deepcopy(self.evidence)
            if case == "missing":
                evidence["nodes"].pop()
            elif case == "conflict":
                evidence["nodes"][-1]["ref"] = {**ref("shared"), "content_fingerprint": ref("bad")["content_fingerprint"]}
            else:
                evidence["config_ref"] = ref("missing")
            with self.subTest(case=case), self.assertRaises(ContractError):
                build_source_inventory(evidence, generated_at=TIME)

    def test_cycles_and_duplicate_index_nodes_fail(self):
        for case in ("cycle", "duplicate", "empty"):
            evidence = deepcopy(self.evidence)
            if case == "cycle":
                evidence["nodes"][-1]["dependencies"] = [ref("root")]
            elif case == "duplicate":
                evidence["nodes"].append(deepcopy(evidence["nodes"][0]))
            else:
                evidence["roots"] = []
            with self.subTest(case=case), self.assertRaises(ContractError):
                build_source_inventory(evidence, generated_at=TIME)

    def test_identity_stable_across_generation_time_and_index_order(self):
        evidence = deepcopy(self.evidence)
        evidence["nodes"].reverse()
        other = build_source_inventory(evidence, generated_at="2026-09-07T00:00:00Z")
        self.assertEqual(other["inventory_id"], self.payload["inventory_id"])
        self.assertEqual(other["content_fingerprint"], self.payload["content_fingerprint"])

    def test_bad_timestamps_and_identity_are_rejected(self):
        for timestamp in ("2026-09-06", "2026-09-06T00:00:00+00:00", "2026-09-06T00:00:00.1Z", "2026-02-30T00:00:00Z"):
            with self.subTest(timestamp=timestamp), self.assertRaises(ContractError):
                build_source_inventory(self.evidence, generated_at=timestamp)
        for key in ("inventory_id", "content_fingerprint"):
            payload = deepcopy(self.payload)
            payload[key] = "forged"
            with self.assertRaises(ContractError):
                self.validate(payload)

    def test_long_history_does_not_exhaust_python_recursion(self):
        refs = [ref(f"node-{i:04}") for i in range(1500)]
        evidence = {"as_of": self.evidence["as_of"], "config_ref": refs[-1], "roots": [refs[0]],
                    "nodes": [{"ref": item, "dependencies": refs[i+1:i+2]} for i, item in enumerate(refs)]}
        self.assertEqual(len(build_source_inventory(evidence, generated_at=TIME)["records"]), 1500)

    def test_builder_does_not_mutate_or_alias_input(self):
        before = deepcopy(self.evidence)
        payload = build_source_inventory(self.evidence, generated_at=TIME)
        payload["roots"][0]["id"] = "changed"
        self.assertEqual(self.evidence, before)

    def test_collection_keeps_same_fail_closed_and_duplicate_boundary(self):
        validate_contracts([("SourceInventory", self.payload)], source_inventory_evidence=self.evidence)
        with self.assertRaises(ContractError):
            validate_contracts([("SourceInventory", self.payload)])
        with self.assertRaises(ContractError):
            validate_contracts([("SourceInventory", self.payload)] * 2, source_inventory_evidence=self.evidence)


if __name__ == "__main__":
    unittest.main()
