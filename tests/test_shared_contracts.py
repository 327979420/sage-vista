import copy
import json
from pathlib import Path
import tempfile
import unittest

from services.contracts import (
    ContractError,
    adapt_legacy_file,
    build_shadow_manifest,
    validate_contract,
    validate_contracts,
    verify_shadow_manifest,
    write_shadow_manifest,
)
from services.contracts.manifest import FROZEN_RELEASE_NAMES


ROOT = Path(__file__).parents[1]


def experiment_ids():
    return {
        json.loads(line)["experiment_id"]
        for line in (ROOT / "research" / "experiments.jsonl").read_text().splitlines()
        if line.strip()
    }


def gate(**changes):
    payload = {
        "schema_version": "1.0.0",
        "as_of": "2026-08-28",
        "generated_at": "2026-08-28T22:00:00Z",
        "source_version": {"gate_policy": "v1"},
        "future_data_used": False,
        "gate_event_id": "gate:ABC:2026-08-28:v1",
        "symbol": "ABC",
        "signal_date": "2026-08-28",
        "gate_policy_version": "v1",
        "passed": True,
    }
    payload.update(changes)
    return payload


class SharedContractTests(unittest.TestCase):
    def test_missing_required_field_fails(self):
        payload = gate()
        del payload["as_of"]
        with self.assertRaises(ContractError):
            validate_contract("GateEvent", payload)

    def test_future_data_must_be_boolean_false(self):
        for value in (None, "false", True):
            with self.subTest(value=value), self.assertRaises(ContractError):
                validate_contract("GateEvent", gate(future_data_used=value))

    def test_unknown_major_fails_but_same_major_optional_field_is_allowed(self):
        validate_contract("GateEvent", gate(optional_note="compatible"))
        with self.assertRaises(ContractError):
            validate_contract("GateEvent", gate(schema_version="2.0.0"))

    def test_schema_version_cannot_contain_adapter_identity(self):
        with self.assertRaises(ContractError):
            validate_contract("GateEvent", gate(schema_version="legacy-adapter-1.0.0"))

    def test_duplicate_stable_id_fails(self):
        with self.assertRaises(ContractError):
            validate_contracts([("GateEvent", gate()), ("GateEvent", copy.deepcopy(gate()))])

    def test_same_symbol_day_cannot_be_two_opportunity_events(self):
        base = {
            "schema_version": "1.0.0",
            "as_of": "2026-08-28",
            "generated_at": "2026-08-28T22:00:00Z",
            "source_version": {"model": "v1"},
            "future_data_used": False,
            "symbol": "ABC",
            "signal_date": "2026-08-28",
            "gate_event_id": "gate:ABC:2026-08-28:v1",
            "gate_policy_version": "v1",
            "model_assessments": {},
        }
        with self.assertRaises(ContractError):
            validate_contracts([
                ("OpportunityEvent", {**base, "event_id": "event:one"}),
                ("OpportunityEvent", {**base, "event_id": "event:two"}),
            ])

    def test_current_2026_08_28_files_adapt_without_modification(self):
        paths = [
            ROOT / "public" / "update-status.json",
            ROOT / "public" / "unified-v2-latest.json",
            ROOT / "public" / "daily-factor-snapshot.json",
            ROOT / "public" / "favorite-pattern.json",
            ROOT / "public" / "market-etf-watch.json",
            ROOT / "public" / "industry-radar.json",
            ROOT / "public" / "opportunity-ledger.json",
            ROOT / "public" / "opportunity-ledger-latest.json",
            ROOT / "public" / "signal-history.json",
            ROOT / "public" / "signal-history-summary.json",
        ]
        before = {path: path.read_bytes() for path in paths}
        adapted = [adapt_legacy_file(path) for path in paths]
        self.assertTrue(all(item.as_of == "2026-08-28" for item in adapted))
        self.assertTrue(all(item.future_data_used is False for item in adapted))
        self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_unknown_legacy_file_has_no_fallback_adapter(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "unknown.json"
            path.write_text("{}")
            with self.assertRaises(ContractError):
                adapt_legacy_file(path)

    def test_manifest_rejects_date_mismatch_and_hash_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            folder_path = Path(folder)
            first = folder_path / "update-status.json"
            second = folder_path / "signal-history-summary.json"
            first.write_text(json.dumps({
                "source_latest_complete_date": "2026-08-28",
                "last_successful_update_at": "2026-08-29T00:00:00Z",
                "future_data_used": False,
                "provider": "test",
            }))
            second.write_text(json.dumps({"as_of": "2026-08-27", "future_data_used": False}))
            with self.assertRaises(ContractError):
                build_shadow_manifest([first, second], allow_partial=True)

    def test_shadow_manifest_has_exact_hashes_and_roles(self):
        paths = [ROOT / "public" / "update-status.json", ROOT / "public" / "signal-history-summary.json"]
        manifest = build_shadow_manifest(paths, generated_at="2026-08-30T00:00:00Z", allow_partial=True)
        self.assertTrue(manifest["shadow_only"])
        self.assertEqual(manifest["as_of"], "2026-08-28")
        self.assertEqual({entry["path"] for entry in manifest["files"]}, {path.name for path in paths})
        self.assertTrue(all(len(entry["sha256"]) == 64 for entry in manifest["files"]))
        verify_shadow_manifest(manifest, ROOT / "public", allow_partial=True)

    def test_manifest_missing_file_and_hash_mismatch_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            path = source / "update-status.json"
            path.write_text(json.dumps({
                "source_latest_complete_date": "2026-08-28",
                "last_successful_update_at": "2026-08-29T00:00:00Z",
                "future_data_used": False,
                "provider": "test",
            }))
            manifest = build_shadow_manifest([path], generated_at="2026-08-30T00:00:00Z", allow_partial=True)
            path.unlink()
            with self.assertRaises(ContractError):
                verify_shadow_manifest(manifest, source, allow_partial=True)
            path.write_text("changed")
            with self.assertRaises(ContractError):
                verify_shadow_manifest(manifest, source, allow_partial=True)

    def test_shadow_writer_rejects_public_and_allows_work(self):
        manifest = build_shadow_manifest(
            [ROOT / "public" / "update-status.json"], generated_at="2026-08-30T00:00:00Z", allow_partial=True
        )
        with self.assertRaises(ContractError):
            write_shadow_manifest(manifest, ROOT / "public" / "release-manifest.json", ROOT)
        with tempfile.TemporaryDirectory(dir=ROOT / "work") as folder:
            output = Path(folder) / "release-manifest.json"
            write_shadow_manifest(manifest, output, ROOT)
            self.assertEqual(json.loads(output.read_text())["release_id"], manifest["release_id"])

    def test_full_2026_08_28_shadow_release_uses_three_temporal_classes(self):
        manifest = build_shadow_manifest(
            [ROOT / "public" / name for name in FROZEN_RELEASE_NAMES],
            generated_at="2026-08-30T00:00:00Z",
            known_experiment_ids=experiment_ids(),
        )
        verify_shadow_manifest(manifest, ROOT / "public", known_experiment_ids=experiment_ids())
        entries = {entry["path"]: entry for entry in manifest["files"]}
        self.assertEqual(len(entries), 15)

        registry = entries["factor-registry.json"]
        self.assertEqual(registry["temporal_class"], "versioned_config")
        self.assertEqual(registry["registry_version"], "0.10.0")
        self.assertNotIn("as_of", registry)
        self.assertNotIn("future_data_used", registry)

        research = entries["decision-summary.json"]
        self.assertEqual(research["temporal_class"], "research_summary")
        self.assertLessEqual(research["coverage_end"], manifest["as_of"])
        self.assertTrue(research["source_experiment"])
        self.assertEqual(research["prohibited_uses"], ["scan", "score", "rank"])
        self.assertNotIn("as_of", research)
        self.assertNotIn("future_data_used", research)

        daily = entries["daily-factor-snapshot.json"]
        self.assertEqual(daily["temporal_class"], "daily_snapshot")
        self.assertEqual(daily["as_of"], manifest["as_of"])
        self.assertIs(daily["future_data_used"], False)

    def test_d1_daily_snapshot_wrong_date_or_future_evidence_fails(self):
        manifest = build_shadow_manifest(
            [ROOT / "public" / name for name in FROZEN_RELEASE_NAMES],
            generated_at="2026-08-30T00:00:00Z",
            known_experiment_ids=experiment_ids(),
        )
        daily = next(entry for entry in manifest["files"] if entry["temporal_class"] == "daily_snapshot")
        daily["as_of"] = "2026-08-27"
        with self.assertRaises(ContractError):
            validate_contract("ReleaseManifest", manifest, known_experiment_ids=experiment_ids())
        daily["as_of"] = "2026-08-28"
        daily["future_data_used"] = True
        with self.assertRaises(ContractError):
            validate_contract("ReleaseManifest", manifest, known_experiment_ids=experiment_ids())

    def test_d1_registry_version_mismatch_fails_without_daily_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            replacement = Path(folder) / "factor-registry.json"
            payload = json.loads((ROOT / "public" / "factor-registry.json").read_text())
            payload["registry_version"] = "mismatched-version"
            replacement.write_text(json.dumps(payload))
            paths = [
                replacement if name == replacement.name else ROOT / "public" / name
                for name in FROZEN_RELEASE_NAMES
            ]
            with self.assertRaises(ContractError):
                build_shadow_manifest(
                    paths,
                    generated_at="2026-08-30T00:00:00Z",
                    known_experiment_ids=experiment_ids(),
                )

    def test_d1_research_summary_future_coverage_or_missing_source_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            replacement = Path(folder) / "decision-summary.json"
            payload = json.loads((ROOT / "public" / "decision-summary.json").read_text())
            payload["coverage"]["end"] = "2026-08-29"
            replacement.write_text(json.dumps(payload))
            paths = [
                replacement if name == replacement.name else ROOT / "public" / name
                for name in FROZEN_RELEASE_NAMES
            ]
            with self.assertRaises(ContractError):
                build_shadow_manifest(
                    paths,
                    generated_at="2026-08-30T00:00:00Z",
                    known_experiment_ids=experiment_ids(),
                )
            del payload["source_experiment"]
            payload["coverage"]["end"] = "2026-08-28"
            replacement.write_text(json.dumps(payload))
            with self.assertRaises(ContractError):
                build_shadow_manifest(
                    paths,
                    generated_at="2026-08-30T00:00:00Z",
                    known_experiment_ids=experiment_ids(),
                )

    def test_d1b_full_verifier_rejects_missing_and_extra_members(self):
        missing_name = "daily-factor-snapshot.json"
        paths = [ROOT / "public" / name for name in sorted(FROZEN_RELEASE_NAMES)]
        partial = build_shadow_manifest(
            [path for path in paths if path.name != missing_name],
            generated_at="2026-08-30T00:00:00Z",
            allow_partial=True,
            known_experiment_ids=experiment_ids(),
        )
        with self.assertRaises(ContractError):
            verify_shadow_manifest(partial, ROOT / "public", known_experiment_ids=experiment_ids())

        complete = build_shadow_manifest(
            paths,
            generated_at="2026-08-30T00:00:00Z",
            known_experiment_ids=experiment_ids(),
        )
        extra = copy.deepcopy(complete["files"][0])
        extra["path"] = "extra.json"
        complete["files"].append(extra)
        with self.assertRaises(ContractError):
            verify_shadow_manifest(complete, ROOT / "public", known_experiment_ids=experiment_ids())

    def test_d1c_partial_registry_comparisons_are_deterministic_when_related_files_are_missing(self):
        for missing_name in (
            "daily-factor-snapshot.json",
            "unified-v2-latest.json",
            "unified-v2-rankings.json",
        ):
            with self.subTest(missing=missing_name):
                paths = [
                    ROOT / "public" / name
                    for name in sorted(FROZEN_RELEASE_NAMES)
                    if name != missing_name
                ]
                try:
                    manifest = build_shadow_manifest(
                        paths,
                        generated_at="2026-08-30T00:00:00Z",
                        allow_partial=True,
                        known_experiment_ids=experiment_ids(),
                    )
                except StopIteration as exc:
                    self.fail(f"raw StopIteration leaked for missing {missing_name}: {exc}")
                self.assertNotIn(missing_name, {entry["path"] for entry in manifest["files"]})

    def test_d1b_manifest_paths_must_be_safe_canonical_relative_paths(self):
        manifest = build_shadow_manifest(
            [ROOT / "public" / name for name in FROZEN_RELEASE_NAMES],
            generated_at="2026-08-30T00:00:00Z",
            known_experiment_ids=experiment_ids(),
        )
        for unsafe in ("../public/update-status.json", "/tmp/update-status.json", "C:/data.json", "folder\\data.json", "./data.json"):
            candidate = copy.deepcopy(manifest)
            candidate["files"][0]["path"] = unsafe
            with self.subTest(path=unsafe), self.assertRaises(ContractError):
                verify_shadow_manifest(candidate, ROOT / "public", known_experiment_ids=experiment_ids())

    def test_d1b_release_id_is_recomputed_from_complete_entries(self):
        manifest = build_shadow_manifest(
            [ROOT / "public" / name for name in FROZEN_RELEASE_NAMES],
            generated_at="2026-08-30T00:00:00Z",
            known_experiment_ids=experiment_ids(),
        )
        declared = copy.deepcopy(manifest)
        declared["release_id"] = "sha256:" + "0" * 64
        with self.assertRaises(ContractError):
            verify_shadow_manifest(declared, ROOT / "public", known_experiment_ids=experiment_ids())
        changed_entry = copy.deepcopy(manifest)
        changed_entry["files"][0]["roles"] = ["audit"]
        with self.assertRaises(ContractError):
            verify_shadow_manifest(changed_entry, ROOT / "public", known_experiment_ids=experiment_ids())

    def test_d1b_research_experiment_must_exist_in_injected_authority(self):
        paths = [ROOT / "public" / name for name in FROZEN_RELEASE_NAMES]
        with self.assertRaises(ContractError):
            build_shadow_manifest(
                paths,
                generated_at="2026-08-30T00:00:00Z",
                known_experiment_ids={"well-formed-but-not-real-v1.0.0"},
            )
        manifest = build_shadow_manifest(
            paths,
            generated_at="2026-08-30T00:00:00Z",
            known_experiment_ids=experiment_ids(),
        )
        verify_shadow_manifest(manifest, ROOT / "public", known_experiment_ids=experiment_ids())


if __name__ == "__main__":
    unittest.main()
