"""Pure receipt/target contracts; no platform action occurs in these tests."""

from copy import deepcopy
import hashlib
import unittest

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, M12_CHECK_NAMES, M12_PAGE_PATHS, validate_contract, validate_contracts
from services.publication.manifest import build_release_manifest
from services.publication.receipts import build_publication_receipt
from tests.test_m12_manifest import preparation, raw
from tests.test_m12_evaluation import ref, TIME


def receipt_ref(receipt):
    return {"id": receipt["receipt_id"], "content_fingerprint": receipt["content_fingerprint"]}


def reseal(payload):
    body = {k: v for k, v in payload.items() if k not in ("receipt_id", "content_fingerprint", "generated_at")}
    digest = canonical_fingerprint(body)
    payload.update(receipt_id="publication-receipt:" + digest, content_fingerprint=digest)
    return payload


class ReceiptFixture:
    def __init__(self):
        self.preparation = preparation()
        self.release = build_release_manifest(self.preparation, generated_at=TIME)
        self.release_ref = {"id": self.release["release_id"], "content_fingerprint": self.release["content_fingerprint"]}
        self.target = {"kind": "release", "release_ref": self.release_ref, "renderer_version_id": "renderer-new"}
        self.legacy = {"kind": "legacy", "baseline_ref": ref("legacy"), "renderer_version_id": "renderer-old"}
        self.files = [{k: f[k] for k in ("path", "sha256", "size_bytes")} for f in self.release["files"]]
        self.targets = [
            {"target": self.target, "manifest_hash": "sha256:" + hashlib.sha256(raw(self.release)).hexdigest(),
             "files": self.files, "public_paths": [f["path"] for f in self.release["files"] if "web" in f["roles"]]},
            {"target": self.legacy, "manifest_hash": ref("legacy-manifest")["content_fingerprint"],
             "files": [{"path": "old.json", "size_bytes": 3, "sha256": ref("old-file")["content_fingerprint"]}], "public_paths": ["old.json"]},
        ]
        self.checks = [{"name": name, "result": "pass", "evidence_ref": ref("check-" + name)} for name in sorted(M12_CHECK_NAMES)]
        refs = [c["evidence_ref"] for c in self.checks] + [self.release["source_inventory_ref"], ref("notification-plan")]
        self.references = sorted(refs, key=lambda r: r["id"])
        self.history = []

    def observation(self, kind, details, outcome="success", reason=None):
        return {"release_ref": self.release_ref, "previous_receipt_ref": receipt_ref(self.history[-1]) if self.history else None,
                "job": self.preparation["authorization"]["job"], "fence": 1, "occurred_at": TIME,
                "kind": kind, "outcome": outcome, "reason_code": reason, "details": deepcopy(details)}

    def evidence(self, observation):
        return deepcopy({"observation": observation, "history": self.history, "release": self.release,
                         "release_evidence": self.preparation, "release_bytes": raw(self.release),
                         "targets": self.targets, "references": self.references, "prepared_files": {}})

    def append(self, kind, details, outcome="success", reason=None):
        evidence = self.evidence(self.observation(kind, details, outcome, reason))
        receipt = build_publication_receipt(evidence, generated_at=TIME)
        self.history.append(receipt)
        return receipt, evidence

    def prepare(self):
        return self.append("prepare", {"inventory_ref": self.release["source_inventory_ref"], "checked_files": self.files, "checks": self.checks})

    def verification(self, *, legacy=False, online=False, generation=1):
        record = self.targets[1 if legacy else 0]
        details = {"target": record["target"], "renderer_version_id": record["target"]["renderer_version_id"],
                   "provider_deployment_id": None, "manifest_hash": record["manifest_hash"], "checked_files": record["files"],
                   "page_paths": list(M12_PAGE_PATHS), "checks": self.checks}
        details.update({"pointer_generation": generation} if online else {"candidate_url": "https://preview.invalid/candidate"})
        return details

    def switch_and_online(self, fail=False):
        self.prepare()
        preflight, _ = self.append("preflight", self.verification())
        self.append("promote", {"before": self.legacy, "after": self.target, "expected_generation": 0, "resulting_generation": 1, "preflight_ref": receipt_ref(preflight)})
        details = self.verification(online=True)
        if fail:
            details["checks"] = [{**c, "result": "fail" if c["name"] == "hash" else "pass"} for c in details["checks"]]
        return self.append("online", details, "failed" if fail else "success", "hash_mismatch" if fail else None)

    def notify_details(self, online):
        return {"online_receipt_ref": receipt_ref(online), "notification_plan_ref": ref("notification-plan"),
                "items": [{"key": ref("day-key")["content_fingerprint"], "status": "sent", "platform_message_id": "msg-1", "attempt": 1}]}


class PublicationReceiptTests(unittest.TestCase):
    def setUp(self):
        self.f = ReceiptFixture()

    def test_normal_prepare_preflight_promote_online_notify(self):
        online, _ = self.f.switch_and_online()
        receipt, evidence = self.f.append("notify", self.f.notify_details(online))
        validate_contracts([("PublicationReceipt", receipt)], publication_receipt_evidence=evidence)
        self.assertEqual([r["kind"] for r in self.f.history], ["prepare", "preflight", "promote", "online", "notify"])

    def test_early_failure_can_archive_partial_bytes_without_fabricated_manifest(self):
        observation = self.f.observation("prepare", {"inventory_ref": None, "checked_files": [], "checks": []}, "failed", "source_missing")
        observation["release_ref"] = None
        evidence = self.f.evidence(observation)
        evidence.update(release=None, release_evidence=None, release_bytes=None, targets=[])
        evidence["prepared_files"] = {"overview.json": b"partial"}
        observation = evidence["observation"]
        observation["details"]["checked_files"] = [{"path": "overview.json", "size_bytes": 7, "sha256": "sha256:" + hashlib.sha256(b"partial").hexdigest()}]
        receipt = build_publication_receipt(evidence, generated_at=TIME)
        self.assertIsNone(receipt["release_ref"])
        evidence["observation"]["outcome"] = "success"
        evidence["observation"]["reason_code"] = None
        with self.assertRaises(ContractError): build_publication_receipt(evidence, generated_at=TIME)

    def test_rollback_to_legacy_then_online_cannot_notify_failed_new_release(self):
        failed, _ = self.f.switch_and_online(fail=True)
        check, _ = self.f.append("preflight", self.f.verification(legacy=True))
        self.f.append("rollback", {"before": self.f.target, "after": self.f.legacy, "failed_receipt_ref": receipt_ref(failed),
                                   "rollback_check_ref": receipt_ref(check), "expected_generation": 1, "resulting_generation": 2})
        restored, _ = self.f.append("online", self.f.verification(legacy=True, online=True, generation=2))
        with self.assertRaises(ContractError): self.f.append("notify", self.f.notify_details(restored))

    def test_failed_switch_does_not_advance_generation(self):
        preflight, _ = self.f.append("preflight", self.f.verification())
        details = {"before": self.f.legacy, "after": self.f.target, "preflight_ref": receipt_ref(preflight), "expected_generation": 3, "resulting_generation": 3}
        self.f.append("promote", details, "failed", "switch_conflict")
        details["resulting_generation"] = 4
        with self.assertRaises(ContractError): self.f.append("promote", details, "failed", "switch_conflict")

    def test_missing_evidence_and_resealed_job_fence_and_observation_changes_rejected(self):
        receipt, evidence = self.f.prepare()
        with self.assertRaises(ContractError): validate_contract("PublicationReceipt", receipt)
        for field, value in (("fence", 2), ("occurred_at", "2026-09-11T00:00:00Z"), ("release_ref", ref("other")), ("previous_receipt_ref", ref("stale"))):
            payload = deepcopy(receipt)
            payload[field] = value
            with self.subTest(field=field), self.assertRaises(ContractError):
                validate_contract("PublicationReceipt", reseal(payload), publication_receipt_evidence=evidence)

    def test_success_cannot_omit_checks_files_pages_or_contain_failed_check(self):
        for mutation in ("checks", "files", "fail", "pages"):
            details = self.f.verification()
            if mutation == "checks": details["checks"] = []
            elif mutation == "files": details["checked_files"] = []
            elif mutation == "fail": details["checks"] = [{**details["checks"][0], "result": "fail"}] + details["checks"][1:]
            else: details["page_paths"] = ["/"]
            with self.subTest(mutation=mutation), self.assertRaises(ContractError): self.f.append("preflight", details)

    def test_failed_verification_preserves_observed_bad_bytes_and_manifest_hash(self):
        self.f.switch_and_online()
        details = deepcopy(self.f.verification(online=True))
        details["manifest_hash"] = ref("wrong-manifest")["content_fingerprint"]
        details["checked_files"][0]["sha256"] = ref("wrong-file")["content_fingerprint"]
        details["checked_files"][0]["size_bytes"] = 2
        details["checks"] = [{**c, "result": "fail" if c["name"] == "hash" else "pass"} for c in details["checks"]]
        receipt, _ = self.f.append("online", details, "failed", "hash_mismatch")
        self.assertEqual(receipt["details"]["checked_files"][0]["sha256"], ref("wrong-file")["content_fingerprint"])
        with self.assertRaises(ContractError): self.f.append("online", details)

    def test_targets_are_closed_and_renderer_or_hash_cannot_change(self):
        for mutation in ("extra", "kind", "renderer", "hash"):
            details = deepcopy(self.f.verification())
            if mutation == "extra": details["target"]["baseline_ref"] = ref("injected")
            elif mutation == "kind": details["target"]["kind"] = "url"
            elif mutation == "renderer": details["renderer_version_id"] = "other"
            else: details["manifest_hash"] = ref("wrong")["content_fingerprint"]
            with self.subTest(mutation=mutation), self.assertRaises(ContractError): self.f.append("preflight", details)

    def test_notify_requires_current_successful_online_and_sent_message_id(self):
        failed, _ = self.f.switch_and_online(fail=True)
        with self.assertRaises(ContractError): self.f.append("notify", self.f.notify_details(failed))
        self.f = ReceiptFixture()
        online, _ = self.f.switch_and_online()
        details = self.f.notify_details(online)
        details["items"][0]["platform_message_id"] = None
        with self.assertRaises(ContractError): self.f.append("notify", details)

    def test_uncertain_notification_is_preserved_not_success(self):
        online, _ = self.f.switch_and_online()
        details = self.f.notify_details(online)
        details["items"][0].update(status="uncertain", platform_message_id=None)
        receipt, _ = self.f.append("notify", details, "uncertain", "transport_unknown")
        self.assertEqual(receipt["outcome"], "uncertain")
        with self.assertRaises(ContractError): self.f.append("notify", details)

    def test_online_requires_matching_switch_generation(self):
        with self.assertRaises(ContractError): self.f.append("online", self.f.verification(online=True))
        self.f.switch_and_online()
        with self.assertRaises(ContractError): self.f.append("online", self.f.verification(online=True, generation=2))

    def test_direct_history_cannot_be_skipped_or_cross_release(self):
        self.f.prepare()
        receipt, evidence = self.f.append("preflight", self.f.verification())
        for mutation in ("skip", "cross", "duplicate"):
            bad = deepcopy(evidence)
            if mutation == "skip": bad["history"] = []
            elif mutation == "cross":
                bad["history"][0]["release_ref"] = ref("other")
                reseal(bad["history"][0])
            else: bad["history"] *= 2
            with self.subTest(mutation=mutation), self.assertRaises(ContractError):
                validate_contract("PublicationReceipt", receipt, publication_receipt_evidence=bad)

    def test_supporting_evidence_and_manifest_bytes_must_resolve(self):
        receipt, evidence = self.f.prepare()
        for mutation in ("references", "manifest", "bytes"):
            bad = deepcopy(evidence)
            if mutation == "references": bad["references"] = []
            elif mutation == "manifest": bad["release"]["files"].pop()
            else: bad["release_bytes"] = bad["release_bytes"].replace(b'"future_data_used":false', b'"future_data_used":0')
            with self.subTest(mutation=mutation), self.assertRaises(ContractError):
                validate_contract("PublicationReceipt", receipt, publication_receipt_evidence=bad)

    def test_unknown_version_wrong_kind_fields_bool_uint_and_duplicate_collection(self):
        receipt, evidence = self.f.prepare()
        for field, value in (("schema_version", "1.0.1"), ("fence", True), ("extra", None), ("kind", "deploy")):
            payload = deepcopy(receipt)
            payload[field] = value
            with self.subTest(field=field), self.assertRaises(ContractError):
                validate_contract("PublicationReceipt", reseal(payload), publication_receipt_evidence=evidence)
        with self.assertRaises(ContractError):
            validate_contracts([("PublicationReceipt", receipt)] * 2, publication_receipt_evidence=evidence)
        payload = deepcopy(receipt)
        payload["details"]["target"] = self.f.target
        with self.assertRaises(ContractError): validate_contract("PublicationReceipt", reseal(payload), publication_receipt_evidence=evidence)

    def test_timestamp_identity_and_input_isolation(self):
        receipt, evidence = self.f.prepare()
        before = deepcopy(evidence)
        other = build_publication_receipt(evidence, generated_at="2026-09-11T00:00:00Z")
        self.assertEqual(other["receipt_id"], receipt["receipt_id"])
        other["details"]["checked_files"].clear()
        self.assertEqual(evidence, before)


if __name__ == "__main__": unittest.main()
