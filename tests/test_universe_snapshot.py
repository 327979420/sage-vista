import copy
from pathlib import Path
import tempfile
import unittest

from services.contracts import ContractError, stable_instrument_id, validate_universe_snapshot
from services.market_data import UniverseSnapshotStore, build_universe_snapshot


ROOT = Path(__file__).resolve().parents[1]


def member(
    symbol="ABC",
    *,
    lifecycle="listing-1",
    listing_status="active",
    source="fixed-point-in-time-membership",
    effective_from="2026-08-28",
):
    return {
        "instrument_id": stable_instrument_id(
            provider="EODHD",
            market="US",
            provider_code=symbol,
            listing_lifecycle=lifecycle,
        ),
        "symbol": symbol,
        "tier": "main",
        "listing_status": listing_status,
        "membership_source": source,
        "membership_effective_from": effective_from,
    }


def qualification(
    instrument_id,
    *,
    as_of="2026-08-28",
    eligible=True,
    price_complete=True,
):
    return {
        "instrument_id": instrument_id,
        "as_of": as_of,
        "price_complete": price_complete,
        "minimum_price_passed": True,
        "dollar_volume_passed": True,
        "history_length_passed": True,
        "eligible": eligible,
        "inclusion_reasons": ["all-frozen-eligibility-checks-passed"] if eligible else [],
        "exclusion_reasons": [] if eligible else ["price-data-incomplete"],
    }


def snapshot(*, members=None, qualifications=None, **changes):
    members = list(members or [member()])
    as_of = changes.pop("as_of", "2026-08-28")
    if qualifications is None:
        qualifications = [qualification(item["instrument_id"], as_of=as_of) for item in members]
    values = {
        "as_of": as_of,
        "generated_at": "2026-08-28T23:00:00Z",
        "source_version": {
            "membership": "fixed-membership-source-v1",
            "qualification_policy": "current-shadow-policy-v1",
        },
        "eligibility_rule_version": "eligibility-v1",
        "effective_from": as_of,
        "path_status": "formal",
        "coverage_status": "complete",
        "members": members,
        "qualifications": qualifications,
    }
    values.update(changes)
    return build_universe_snapshot(**values)


class UniverseSnapshotTests(unittest.TestCase):
    def test_same_evidence_and_different_order_produce_the_same_identity(self):
        left = member("ABC", lifecycle="listing-a")
        right = member("XYZ", lifecycle="listing-b")
        left_q = qualification(left["instrument_id"])
        right_q = qualification(right["instrument_id"])
        first = snapshot(members=[left, right], qualifications=[left_q, right_q])
        second = snapshot(
            members=[right, left],
            qualifications=[right_q, left_q],
            generated_at="2026-08-29T01:00:00Z",
        )
        self.assertEqual(first["universe_id"], second["universe_id"])
        self.assertEqual(first["members"], second["members"])
        self.assertEqual(first["qualifications"], second["qualifications"])

    def test_membership_source_rule_and_qualification_changes_create_new_identities(self):
        base = snapshot()
        changed_member = copy.deepcopy(base["members"])
        changed_member[0]["listing_status"] = "delisted"
        changed_membership_source = copy.deepcopy(base["members"])
        changed_membership_source[0]["membership_source"] = "another-point-in-time-source"
        changed_qualification = copy.deepcopy(base["qualifications"])
        changed_qualification[0].update({
            "price_complete": False,
            "eligible": False,
            "inclusion_reasons": [],
            "exclusion_reasons": ["price-data-incomplete"],
        })
        variants = (
            snapshot(members=changed_member),
            snapshot(members=changed_membership_source),
            snapshot(source_version={"membership": "v2", "qualification_policy": "v1"}),
            snapshot(eligibility_rule_version="eligibility-v2"),
            snapshot(qualifications=changed_qualification),
        )
        self.assertEqual(len({base["universe_id"], *(item["universe_id"] for item in variants)}), 6)

    def test_formal_and_legacy_observed_are_strictly_separate(self):
        legacy = snapshot(path_status="legacy", coverage_status="legacy_observed")
        with tempfile.TemporaryDirectory() as folder:
            store = UniverseSnapshotStore(folder)
            store.save(legacy)
            self.assertEqual(
                store.select(as_of="2026-08-28", path_status="legacy")["universe_id"],
                legacy["universe_id"],
            )
            with self.assertRaisesRegex(ContractError, "universe_unavailable"):
                store.select(as_of="2026-08-28", path_status="formal")
        with self.assertRaisesRegex(ContractError, "legacy universe"):
            snapshot(path_status="legacy", coverage_status="complete")

    def test_missing_or_future_only_history_is_unavailable(self):
        future_member = member(effective_from="2026-08-31")
        future = snapshot(
            as_of="2026-08-31",
            members=[future_member],
            qualifications=[qualification(future_member["instrument_id"], as_of="2026-08-31")],
        )
        with tempfile.TemporaryDirectory() as folder:
            store = UniverseSnapshotStore(folder)
            with self.assertRaisesRegex(ContractError, "universe_unavailable"):
                store.select(as_of="2026-08-28")
            store.save(future)
            with self.assertRaisesRegex(ContractError, "universe_unavailable"):
                store.select(as_of="2026-08-28")

    def test_later_delisting_and_qualification_cannot_rewrite_the_past(self):
        historical_member = member("OLD", lifecycle="listing-old", listing_status="active")
        historical = snapshot(
            members=[historical_member],
            qualifications=[qualification(historical_member["instrument_id"])],
        )
        later_member = member(
            "OLD",
            lifecycle="listing-old",
            listing_status="delisted",
            effective_from="2026-08-31",
        )
        later_qualification = qualification(
            later_member["instrument_id"], as_of="2026-08-31", eligible=False
        )
        later_qualification["price_complete"] = False
        later = snapshot(
            as_of="2026-08-31",
            members=[later_member],
            qualifications=[later_qualification],
        )
        with tempfile.TemporaryDirectory() as folder:
            store = UniverseSnapshotStore(folder)
            historical_path = store.save(historical)
            historical_bytes = historical_path.read_bytes()
            store.save(later)
            selected = store.select(as_of="2026-08-28")
            self.assertEqual(selected["members"][0]["listing_status"], "active")
            self.assertIs(selected["qualifications"][0]["eligible"], True)
            self.assertEqual(historical_path.read_bytes(), historical_bytes)

    def test_incomplete_membership_and_qualification_evidence_fails_closed(self):
        base_member = member()
        cases = []
        missing_source = copy.deepcopy(base_member)
        del missing_source["membership_source"]
        cases.append({"members": [missing_source]})
        bad_id = copy.deepcopy(base_member)
        bad_id["instrument_id"] = "instrument:sha256:not-complete"
        cases.append({"members": [bad_id]})
        cases.append({"members": [base_member, copy.deepcopy(base_member)]})
        future_member = copy.deepcopy(base_member)
        future_member["membership_effective_from"] = "2026-08-31"
        cases.append({"members": [future_member]})
        for values in cases:
            with self.subTest(values=values), self.assertRaises(ContractError):
                snapshot(**values)

        with self.assertRaises(ContractError):
            snapshot(qualifications=[])
        with self.assertRaisesRegex(ContractError, "exactly one daily qualification"):
            snapshot(members=[base_member], qualifications=[qualification(member("XYZ")["instrument_id"])])
        with self.assertRaisesRegex(ContractError, "match snapshot as_of"):
            snapshot(
                members=[base_member],
                qualifications=[qualification(base_member["instrument_id"], as_of="2026-08-31")],
            )

    def test_unknown_contract_major_fails_closed(self):
        payload = snapshot()
        payload["schema_version"] = "3.0.0"
        with self.assertRaisesRegex(ContractError, "unknown schema_version major"):
            validate_universe_snapshot(payload)

    def test_write_failure_leaves_all_previous_snapshot_bytes_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            stable_store = UniverseSnapshotStore(folder)
            stable_store.save(snapshot())
            before = {path: path.read_bytes() for path in Path(folder).rglob("*.json")}

            def fail(_target, _temporary):
                raise RuntimeError("injected-universe-write-failure")

            failing_store = UniverseSnapshotStore(folder, before_replace=fail)
            with self.assertRaisesRegex(RuntimeError, "injected-universe-write-failure"):
                failing_store.save(snapshot(as_of="2026-08-31", effective_from="2026-08-31"))
            self.assertEqual({path: path.read_bytes() for path in before}, before)
            self.assertEqual(set(Path(folder).rglob("*.json")), set(before))
            self.assertEqual(list(Path(folder).rglob("*.tmp")), [])

    def test_store_rejects_non_shadow_roots(self):
        with self.assertRaisesRegex(ContractError, "temp or workspace work"):
            UniverseSnapshotStore(ROOT / "public", workspace_root=ROOT)
        with tempfile.TemporaryDirectory(dir=ROOT / "work") as folder:
            store = UniverseSnapshotStore(folder, workspace_root=ROOT)
            self.assertTrue(store.save(snapshot()).is_file())

    def test_shadow_operations_leave_legacy_and_production_files_unchanged(self):
        protected = (
            ROOT / "public" / "daily-factor-snapshot.json",
            ROOT / "public" / "unified-v2-rankings.json",
            ROOT / "automation" / "production-state.json",
        )
        before = {path: path.read_bytes() for path in protected}
        with tempfile.TemporaryDirectory() as folder:
            store = UniverseSnapshotStore(folder)
            saved = store.save(snapshot())
            self.assertTrue(saved.is_file())
            store.select(as_of="2026-08-28")
        self.assertEqual({path: path.read_bytes() for path in protected}, before)


if __name__ == "__main__":
    unittest.main()
