"""CurrentPointer transitions use synthetic trusted state, never a live DO."""

from copy import deepcopy
import unittest

from services.contracts.validation import ContractError, validate_contract, validate_contracts
from services.publication.pointer import build_current_pointer, public_current_pointer
from tests.test_m12_receipts import ReceiptFixture, receipt_ref
from tests.test_m12_evaluation import ref, TIME


def transition(previous=None, *, operation="initialize", receipt=None, receipt_evidence=None, bootstrap=None):
    return {"operation": operation, "previous": previous,
            "expected_generation": 0 if previous is None else previous["generation"], "updated_at": TIME,
            "receipt": receipt, "receipt_evidence": receipt_evidence, "bootstrap": bootstrap}


class CurrentPointerTests(unittest.TestCase):
    def setUp(self):
        self.f = ReceiptFixture()
        self.empty_evidence = transition()
        self.empty = build_current_pointer(self.empty_evidence)
        self.bootstrap_evidence = transition(self.empty, operation="bootstrap", bootstrap={"target": self.f.legacy, "verification_ref": ref("verified-legacy-baseline")})
        self.bootstrap = build_current_pointer(self.bootstrap_evidence)

    def promote(self):
        self.f.prepare()
        preflight, _ = self.f.append("preflight", self.f.verification())
        receipt, source = self.f.append("promote", {"before": self.f.legacy, "after": self.f.target,
                                                   "expected_generation": 1, "resulting_generation": 2, "preflight_ref": receipt_ref(preflight)})
        evidence = transition(self.bootstrap, operation="apply_receipt", receipt=receipt, receipt_evidence=source)
        return build_current_pointer(evidence), evidence

    def online(self, previous, *, failure=False, legacy=False):
        details = self.f.verification(online=True, legacy=legacy, generation=previous["generation"])
        if failure:
            details["checks"] = [{**c, "result": "fail" if c["name"] == "hash" else "pass"} for c in details["checks"]]
        receipt, source = self.f.append("online", details, "failed" if failure else "success", "hash_mismatch" if failure else None)
        evidence = transition(previous, operation="apply_receipt", receipt=receipt, receipt_evidence=source)
        return build_current_pointer(evidence), evidence

    def rollback(self, previous, failed_receipt, *, failure=False):
        check, _ = self.f.append("preflight", self.f.verification(legacy=True))
        generation = previous["generation"]
        receipt, source = self.f.append("rollback", {"before": self.f.target, "after": self.f.legacy,
            "failed_receipt_ref": receipt_ref(failed_receipt), "rollback_check_ref": receipt_ref(check),
            "expected_generation": generation, "resulting_generation": generation if failure else generation + 1},
            "failed" if failure else "success", "provider_error" if failure else None)
        evidence = transition(previous, operation="apply_receipt", receipt=receipt, receipt_evidence=source)
        return build_current_pointer(evidence), evidence

    def test_initialize_bootstrap_promote_then_online_verifies_new_target(self):
        self.assertEqual(self.empty["generation"], 0)
        self.assertEqual(self.bootstrap["generation"], 1)
        pending, _ = self.promote()
        self.assertEqual(pending["phase"], "switching")
        self.assertEqual(pending["last_verified"], self.f.legacy)
        verified, _ = self.online(pending)
        self.assertEqual(verified["generation"], 2)
        self.assertEqual(verified["visible"], verified["last_verified"])
        self.assertEqual(verified["phase"], "verified")
        self.assertIsNone(verified["pending_receipt_ref"])

    def test_bootstrap_cannot_bypass_publication_with_new_release_or_overwrite(self):
        evidence = deepcopy(self.bootstrap_evidence)
        evidence["bootstrap"]["target"] = self.f.target
        with self.assertRaises(ContractError): build_current_pointer(evidence)
        evidence = deepcopy(self.bootstrap_evidence)
        evidence.update(previous=self.bootstrap, expected_generation=1)
        with self.assertRaises(ContractError): build_current_pointer(evidence)
        with self.assertRaises(ContractError): build_current_pointer(transition(self.bootstrap))

    def test_failed_online_and_rollback_require_old_target_reverification(self):
        pending, _ = self.promote()
        failed, source = self.online(pending, failure=True)
        self.assertEqual(failed["phase"], "rollback_pending")
        self.assertEqual(failed["generation"], 2)
        restored, _ = self.rollback(failed, source["receipt"])
        self.assertEqual(restored["generation"], 3)
        self.assertEqual(restored["visible"], self.f.legacy)
        self.assertEqual(restored["phase"], "switching")
        verified, _ = self.online(restored, legacy=True)
        self.assertEqual(verified["phase"], "verified")
        self.assertEqual(verified["generation"], 3)

    def test_failed_rollback_stays_frozen_and_can_retry_without_resetting_generation(self):
        pending, _ = self.promote()
        failed, failed_source = self.online(pending, failure=True)
        retry, _ = self.rollback(failed, failed_source["receipt"], failure=True)
        self.assertEqual((retry["phase"], retry["generation"]), ("rollback_pending", 2))
        restored, _ = self.rollback(retry, failed_source["receipt"])
        self.assertEqual(restored["generation"], 3)

    def test_rollback_cannot_choose_a_third_target(self):
        pending, _ = self.promote()
        failed, failed_source = self.online(pending, failure=True)
        _, evidence = self.rollback(failed, failed_source["receipt"])
        evidence["previous"]["last_verified"] = {"kind": "legacy", "baseline_ref": ref("third-target"), "renderer_version_id": "third-renderer"}
        with self.assertRaises(ContractError): build_current_pointer(evidence)

    def test_rollback_verification_failure_stays_pending_until_old_target_rechecks(self):
        pending, _ = self.promote()
        failed, failed_source = self.online(pending, failure=True)
        restored, _ = self.rollback(failed, failed_source["receipt"])
        failed_restore, _ = self.online(restored, failure=True, legacy=True)
        self.assertEqual(failed_restore["phase"], "rollback_pending")
        self.assertEqual(failed_restore["generation"], 3)
        verified, _ = self.online(failed_restore, legacy=True)
        self.assertEqual((verified["phase"], verified["generation"]), ("verified", 3))

    def test_failed_candidate_cannot_resume_by_relabeling_online_success(self):
        pending, _ = self.promote()
        failed, _ = self.online(pending, failure=True)
        with self.assertRaises(ContractError): self.online(failed)

    def test_failed_promote_leaves_verified_target_visible(self):
        preflight, _ = self.f.append("preflight", self.f.verification())
        receipt, source = self.f.append("promote", {"before": self.f.legacy, "after": self.f.target,
            "expected_generation": 1, "resulting_generation": 1, "preflight_ref": receipt_ref(preflight)}, "failed", "switch_conflict")
        pointer = build_current_pointer(transition(self.bootstrap, operation="apply_receipt", receipt=receipt, receipt_evidence=source))
        self.assertEqual((pointer["generation"], pointer["phase"], pointer["visible"]), (1, "verified", self.f.legacy))

    def test_stale_generation_and_other_target_are_rejected(self):
        _, evidence = self.promote()
        for mutation in ("cas", "receipt-generation", "target"):
            bad = deepcopy(evidence)
            if mutation == "cas": bad["expected_generation"] = 0
            elif mutation == "receipt-generation":
                bad["previous"]["generation"] = 5
                bad["expected_generation"] = 5
            else:
                bad["previous"]["visible"]["renderer_version_id"] = "other"
                bad["previous"]["last_verified"]["renderer_version_id"] = "other"
            with self.subTest(mutation=mutation), self.assertRaises(ContractError): build_current_pointer(bad)

    def test_same_receipt_retry_preserves_entire_pointer_including_time(self):
        pending, evidence = self.promote()
        retry = deepcopy(evidence)
        retry.update(previous=pending, expected_generation=2, updated_at="2026-09-11T00:00:00Z")
        self.assertEqual(build_current_pointer(retry), pending)
        verified, online_source = self.online(pending)
        online_source.update(previous=verified, expected_generation=2)
        self.assertEqual(build_current_pointer(online_source), verified)

    def test_cannot_reset_generation_phase_or_mix_renderer_after_derivation(self):
        pending, evidence = self.promote()
        for key, value in (("generation", 0), ("generation", True), ("phase", "verified"), ("pending_receipt_ref", None), ("extra", 1)):
            payload = deepcopy(pending)
            payload[key] = value
            with self.subTest(key=key), self.assertRaises(ContractError): validate_contract("CurrentPointer", payload, current_pointer_evidence=evidence)
        payload = deepcopy(pending)
        payload["visible"]["renderer_version_id"] = "old-renderer-new-data"
        with self.assertRaises(ContractError): validate_contract("CurrentPointer", payload, current_pointer_evidence=evidence)

    def test_empty_state_requires_fallback_and_non_switch_receipts_do_not_mutate_pointer(self):
        pending, evidence = self.promote()
        evidence.update(previous=self.empty, expected_generation=0)
        with self.assertRaises(ContractError): build_current_pointer(evidence)
        # Obtain the original prepare evidence independently, not a forged history.
        f = ReceiptFixture()
        receipt, source = f.prepare()
        with self.assertRaises(ContractError): build_current_pointer(transition(self.bootstrap, operation="apply_receipt", receipt=receipt, receipt_evidence=source))

    def test_missing_evidence_and_duplicate_singletons_rejected(self):
        with self.assertRaises(ContractError): validate_contract("CurrentPointer", self.empty)
        validate_contracts([("CurrentPointer", self.empty)], current_pointer_evidence=self.empty_evidence)
        with self.assertRaises(ContractError): validate_contracts([("CurrentPointer", self.empty)] * 2, current_pointer_evidence=self.empty_evidence)

    def test_public_projection_contains_only_generation_target_phase_and_no_aliases(self):
        pending, evidence = self.promote()
        public = public_current_pointer(pending, current_pointer_evidence=evidence)
        self.assertEqual(set(public), {"generation", "visible", "phase"})
        public["visible"]["renderer_version_id"] = "modified"
        self.assertEqual(pending["visible"], self.f.target)
        before = deepcopy(evidence)
        build_current_pointer(evidence)["last_verified"]["renderer_version_id"] = "changed"
        self.assertEqual(evidence, before)

    def test_unknown_version_and_backwards_update_time_rejected(self):
        bad = deepcopy(self.bootstrap)
        bad["schema_version"] = "1.0.1"
        with self.assertRaises(ContractError): validate_contract("CurrentPointer", bad, current_pointer_evidence=self.bootstrap_evidence)
        bad_source = deepcopy(self.bootstrap_evidence)
        bad_source["updated_at"] = "2026-09-01T00:00:00Z"
        with self.assertRaises(ContractError): build_current_pointer(bad_source)


if __name__ == "__main__": unittest.main()
