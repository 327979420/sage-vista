"""Fixed-sample M10-D query, inventory, CSV, and package tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from threading import Event
import unittest
import zipfile

from services.contracts.validation import ContractError
from services.evaluation import (
    AuditDataset,
    ColumnSpec,
    EvaluationQueryResult,
    EvaluationShadowStore,
    build_evaluation_query,
    build_audit_datasets,
    build_export_config,
    build_experiment_run_receipt,
    decode_audit_cell,
    encode_audit_cell,
    execute_evaluation_query,
    finalize_result,
    partition_dataset,
    publish_audit_export,
    resolve_ticker_instrument_id,
    store_readonly_evaluation_batch,
    validate_export_manifest,
    validate_query_execution,
    verify_export_package,
)
from tests.test_m10_aggregate import forward, forward_scope, research_batch
from tests.test_m10_evaluation_contracts import (
    forward_2_1_values,
    receipt_values,
)


COMMIT = "d" * 40


def plain(value):
    if hasattr(value, "items"):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def _pending_run_and_forward(values, attempt):
    provisional = finalize_result("ForwardOutcome", values)
    receipt = receipt_values(provisional)
    receipt.update({
        "attempt_id": attempt,
        "source_version": {"evaluation_contracts": "m10-a-test"},
        "status": "pending",
        "result_refs": [],
        "finished_at": None,
        "error": None,
    })
    pending = build_experiment_run_receipt(**receipt)
    rebound = dict(values)
    rebound["run_id"] = pending["run_id"]
    return pending, finalize_result("ForwardOutcome", rebound)


def revision_store(root: Path):
    store = EvaluationShadowStore(root)
    first_receipt, first = _pending_run_and_forward(
        forward_2_1_values(), "m10-d-query-first"
    )
    second_values = forward_2_1_values(
        mature=True, prior=first["forward_outcome_id"]
    )
    second_receipt, second = _pending_run_and_forward(
        second_values, "m10-d-query-second"
    )
    store.write_run_receipt(first_receipt)
    store.write_result("ForwardOutcome", first)
    store.write_run_receipt(second_receipt)
    store.write_result("ForwardOutcome", second)
    return store, first, second


class M10QueryInventoryTests(unittest.TestCase):
    def test_query_identity_normalizes_filter_order(self):
        first = build_evaluation_query(
            filters={
                "statuses": ["mature", "pending"],
                "result_contracts": ["TradeOutcome", "ForwardOutcome"],
            },
            revision_mode="all",
        )
        second = build_evaluation_query(
            filters={
                "result_contracts": ["ForwardOutcome", "TradeOutcome"],
                "statuses": ["pending", "mature"],
            },
            revision_mode="all",
        )
        self.assertEqual(first, second)

    def test_revision_mode_is_explicit_and_all_current_are_correct(self):
        with tempfile.TemporaryDirectory() as directory:
            store, first, second = revision_store(Path(directory) / "m10")
            all_rows = execute_evaluation_query(
                store,
                build_evaluation_query(filters=None, revision_mode="all"),
                code_commit=COMMIT,
            )
            current = execute_evaluation_query(
                store,
                build_evaluation_query(filters=None, revision_mode="current"),
                code_commit=COMMIT,
            )
            self.assertEqual(2, all_rows.result_set["row_count"])
            self.assertEqual(
                {first["forward_outcome_id"], second["forward_outcome_id"]},
                {item[1]["forward_outcome_id"] for item in all_rows.results},
            )
            self.assertEqual(("mature",), tuple(item[1]["status"] for item in current.results))

            pending_filter = execute_evaluation_query(
                store,
                build_evaluation_query(
                    filters={"statuses": ["pending"]}, revision_mode="current"
                ),
                code_commit=COMMIT,
            )
            self.assertEqual("empty", pending_filter.result_set["status"])
            self.assertEqual(0, pending_filter.result_set["row_count"])

        with self.assertRaises(ContractError):
            build_evaluation_query(filters=None, revision_mode="latest")

    def test_exact_filters_and_stable_result_order(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _, second = revision_store(Path(directory) / "m10")
            query = build_evaluation_query(
                filters={
                    "result_contracts": ["ForwardOutcome"],
                    "instrument_ids": [second["instrument_id"]],
                    "event_ids": [second["event_id"]],
                    "run_ids": [second["run_id"]],
                    "window_sessions": [second["window_sessions"]],
                    "statuses": ["mature"],
                    "signal_date_from": second["signal_date"],
                    "signal_date_to": second["signal_date"],
                },
                revision_mode="current",
            )
            result = execute_evaluation_query(store, query, code_commit=COMMIT)
            self.assertEqual(1, result.result_set["row_count"])
            self.assertEqual(second["forward_outcome_id"], result.results[0][1]["forward_outcome_id"])

    def test_historical_inventory_is_not_fabricated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationShadowStore(Path(directory) / "m10")
            result = execute_evaluation_query(
                store,
                build_evaluation_query(
                    filters=None,
                    revision_mode="all",
                    inventory_as_of="2026-01-01",
                ),
                code_commit=COMMIT,
            )
            self.assertEqual("unavailable", result.result_set["status"])
            self.assertEqual(
                ("historical_inventory_unavailable",),
                tuple(result.result_set["diagnostics"]),
            )

    def test_ticker_resolution_never_guesses(self):
        stable = "instrument:sha256:" + "1" * 64
        self.assertEqual(stable, resolve_ticker_instrument_id("abc", lambda _: [stable]))
        with self.assertRaisesRegex(ContractError, "ambiguous"):
            resolve_ticker_instrument_id(
                "abc",
                lambda _: [stable, "instrument:sha256:" + "2" * 64],
            )
        with self.assertRaisesRegex(ContractError, "unavailable"):
            resolve_ticker_instrument_id("abc", lambda _: [])

    def test_inventory_corruption_and_unknown_entries_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _, _ = revision_store(Path(directory) / "m10")
            path = next((store.root / "results").rglob("*.json"))
            payload = json.loads(path.read_text())
            payload["status_reason"] = "tampered"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ContractError):
                store.capture_inventory()

        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationShadowStore(Path(directory) / "m10")
            store.root.mkdir(parents=True)
            (store.root / "unknown").mkdir()
            with self.assertRaises(ContractError):
                store.capture_inventory()

    def test_public_execution_objects_cannot_diverge_from_signed_refs(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _, _ = revision_store(Path(directory) / "m10")
            execution = execute_evaluation_query(
                store,
                build_evaluation_query(filters=None, revision_mode="current"),
                code_commit=COMMIT,
            )
            forged = EvaluationQueryResult(
                execution.query, execution.result_set, (), execution.run_receipts
            )
            with self.assertRaises(ContractError):
                validate_query_execution(forged)

    def test_batch_write_and_inventory_snapshot_are_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationShadowStore(Path(directory) / "m10")
            batch = research_batch([forward("1", gross=0.1)], forward_scope())
            entered = Event()
            release = Event()
            original = store._write_result_inventory_locked

            def pause_result(contract_name, payload, *, source_records=None):
                entered.set()
                if not release.wait(2):
                    raise AssertionError("inventory test did not release writer")
                return original(contract_name, payload, source_records=source_records)

            store._write_result_inventory_locked = pause_result
            with ThreadPoolExecutor(max_workers=2) as pool:
                write_future = pool.submit(store_readonly_evaluation_batch, store, batch)
                self.assertTrue(entered.wait(2))
                snapshot_future = pool.submit(store.capture_inventory)
                with self.assertRaises(TimeoutError):
                    snapshot_future.result(timeout=0.05)
                release.set()
                write_future.result(timeout=2)
                snapshot = snapshot_future.result(timeout=2)
            self.assertEqual(1, len(snapshot.result_records))
            self.assertEqual(2, len(snapshot.run_receipts))

    def test_inventory_transaction_capability_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationShadowStore(Path(directory) / "m10")
            with store.inventory_write_transaction() as writer:
                self.assertEqual([], writer.result_references_for_run(
                    "experiment-run:sha256:" + "1" * 64
                ))
            with self.assertRaises(ContractError):
                writer.result_references_for_run("experiment-run:sha256:" + "1" * 64)


class M10CsvExportTests(unittest.TestCase):
    def _execution(self, directory: str):
        store = EvaluationShadowStore(Path(directory) / "store")
        batch = research_batch([forward("1", gross=0.1)], forward_scope())
        store_readonly_evaluation_batch(store, batch)
        query = build_evaluation_query(filters=None, revision_mode="current")
        return execute_evaluation_query(store, query, code_commit=COMMIT)

    def test_audit_cell_codec_is_reversible_and_formula_safe(self):
        cases = (
            (None, "text"), ("", "text"), ("0", "text"),
            (r"\N", "text"), ("=1+1", "text"), ("+cmd", "text"),
            ("-2", "text"), ("@name", "text"), ("'quoted", "text"),
            (False, "bool"), (0, "int"), (Decimal("123.4500"), "decimal"),
            ({"x": None, "formula": "=1"}, "json"),
        )
        for value, kind in cases:
            encoded = encode_audit_cell(value, kind)
            decoded = decode_audit_cell(encoded, kind)
            expected = Decimal("123.45") if kind == "decimal" else value
            self.assertEqual(expected, decoded)
        self.assertTrue(encode_audit_cell("=1+1", "text").startswith("'"))

    def test_partitioning_is_deterministic_without_loss_or_duplication(self):
        dataset = AuditDataset(
            "Synthetic",
            (ColumnSpec("id"), ColumnSpec("value", "int")),
            tuple({"id": f"id-{index}", "value": index} for index in range(5)),
            ("id",),
        )
        parts = partition_dataset(dataset, 2)
        self.assertEqual((2, 2, 1), tuple(len(part) for part in parts))
        self.assertEqual(list(dataset.rows), [row for part in parts for row in part])

    def test_csv_package_manifest_and_identities_are_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            config = build_export_config(formats=("csv",), max_data_rows=2)
            package = publish_audit_export(
                execution,
                config,
                output_root=Path(directory) / "exports",
                generated_at="2026-09-04T00:00:00Z",
                code_commit=COMMIT,
            )
            manifest = verify_export_package(package)
            self.assertEqual(execution.result_set["row_count"], manifest["query_row_count"])
            self.assertEqual(["csv"], list(manifest["requested_formats"]))
            for item in manifest["artifacts"]:
                raw = (package / item["relative_path"]).read_bytes()
                self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
                self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
            repeated = publish_audit_export(
                execution,
                config,
                output_root=Path(directory) / "exports",
                generated_at="2026-09-04T00:00:00Z",
                code_commit=COMMIT,
            )
            self.assertEqual(package, repeated)
            self.assertEqual(manifest["export_id"], verify_export_package(repeated)["export_id"])

    def test_manifest_rejects_resigned_count_or_reference_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            package = publish_audit_export(
                execution,
                build_export_config(),
                output_root=Path(directory) / "exports",
                generated_at="2026-09-04T00:00:00Z",
                code_commit=COMMIT,
            )
            manifest = plain(verify_export_package(package))
            manifest["query_row_count"] += 1
            from services.contracts.market_data import canonical_fingerprint
            semantic = {key: value for key, value in manifest.items() if key != "manifest_content_fingerprint"}
            manifest["manifest_content_fingerprint"] = canonical_fingerprint(semantic)
            with self.assertRaises(ContractError):
                validate_export_manifest(manifest)

    def test_failed_export_leaves_no_visible_partial_package(self):
        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            output = Path(directory) / "exports"
            with self.assertRaises(RuntimeError):
                publish_audit_export(
                    execution,
                    build_export_config(),
                    output_root=output,
                    generated_at="2026-09-04T00:00:00Z",
                    code_commit=COMMIT,
                    fault_injector=lambda point: (
                        (_ for _ in ()).throw(RuntimeError("fixed failure"))
                        if point == "after_csv" else None
                    ),
                )
            self.assertEqual([], list(output.iterdir()))

    def test_export_rejects_unsafe_root_and_conflicting_existing_package(self):
        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            with self.assertRaises(ContractError):
                publish_audit_export(
                    execution,
                    build_export_config(),
                    output_root=Path(__file__).resolve().parents[1] / "public" / "m10-d",
                    generated_at="2026-09-04T00:00:00Z",
                    code_commit=COMMIT,
                    workspace_root=Path(__file__).resolve().parents[1],
                )


@unittest.skipUnless(
    importlib.util.find_spec("xlsxwriter") is not None,
    "isolated M10-D research/export dependency is not installed",
)
class M10XlsxExportTests(unittest.TestCase):
    def _execution(self, directory: str):
        store = EvaluationShadowStore(Path(directory) / "store")
        batch = research_batch([forward("1", gross=0.1)], forward_scope())
        store_readonly_evaluation_batch(store, batch)
        return execute_evaluation_query(
            store,
            build_evaluation_query(filters=None, revision_mode="current"),
            code_commit=COMMIT,
        )

    def test_dependency_evidence_and_exact_runtime_version(self):
        root = Path(__file__).resolve().parents[1]
        evidence = json.loads(
            (root / "research/export/dependencies/xlsxwriter-3.2.9.evidence.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual("3.2.9", evidence["version"])
        self.assertEqual("BSD-2-Clause", evidence["license"])
        self.assertFalse(evidence["production_dependency"])
        self.assertEqual(
            {
                "9a5db42bc5dff014806c58a20b9eae7322a134abb6fce3c92c181bfb275ec5b3",
                "254b1c37a368c444eac6e2f867405cc9e461b0ed97a3233b2ac1e574efb4140c",
            },
            {item["sha256"] for item in evidence["artifacts"]},
        )
        import xlsxwriter

        self.assertEqual("3.2.9", xlsxwriter.__version__)

    def test_xlsx_export_has_fixed_source_backed_sheets_and_no_formulas(self):
        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            package = publish_audit_export(
                execution,
                build_export_config(formats=("csv", "xlsx"), max_data_rows=2),
                output_root=Path(directory) / "exports",
                generated_at="2026-09-04T00:00:00Z",
                code_commit=COMMIT,
            )
            manifest = plain(verify_export_package(package))
            xlsx_artifacts = [
                item for item in manifest["artifacts"] if item["format"] == "xlsx"
            ]
            self.assertTrue(xlsx_artifacts)
            self.assertEqual(
                1, len({item["relative_path"] for item in xlsx_artifacts})
            )
            self.assertEqual(
                len(xlsx_artifacts),
                len({item["worksheet_name"] for item in xlsx_artifacts}),
            )
            workbook = package / xlsx_artifacts[0]["relative_path"]
            with zipfile.ZipFile(workbook) as archive:
                xml = b"\n".join(
                    archive.read(name)
                    for name in archive.namelist()
                    if name.endswith(".xml")
                )
            self.assertNotIn(b"<f>", xml)
            self.assertNotIn(b"<hyperlink", xml)
            self.assertNotIn(b"sharedStrings", xml)

    def test_xlsx_bytes_are_deterministic_while_receipts_are_materializations(self):
        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            config = build_export_config(formats=("csv", "xlsx"))
            first = publish_audit_export(
                execution, config,
                output_root=Path(directory) / "exports",
                generated_at="2026-09-04T00:00:00Z",
                code_commit=COMMIT,
            )
            second = publish_audit_export(
                execution, config,
                output_root=Path(directory) / "exports",
                generated_at="2026-09-04T00:01:00Z",
                code_commit=COMMIT,
            )
            first_manifest = plain(verify_export_package(first))
            second_manifest = plain(verify_export_package(second))
            self.assertEqual(first_manifest["export_id"], second_manifest["export_id"])
            self.assertNotEqual(
                first_manifest["export_receipt_id"], second_manifest["export_receipt_id"]
            )
            first_path = next(
                item["relative_path"] for item in first_manifest["artifacts"]
                if item["format"] == "xlsx"
            )
            second_path = next(
                item["relative_path"] for item in second_manifest["artifacts"]
                if item["format"] == "xlsx"
            )
            first_bytes = (first / first_path).read_bytes()
            second_bytes = (second / second_path).read_bytes()
            self.assertEqual(first_bytes, second_bytes)
            self.assertEqual(
                hashlib.sha256(first_bytes).hexdigest(),
                hashlib.sha256(second_bytes).hexdigest(),
            )

    def test_untrusted_xlsx_text_remains_a_plain_string(self):
        from services.evaluation.export import excel_safe_decimal
        from services.evaluation.xlsx_export import _write_xlsx_artifact

        self.assertIsNone(excel_safe_decimal(Decimal("99999999999999.9")))

        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            datasets = dict(build_audit_datasets(execution))
            summary = datasets["RunSummary"]
            unsafe = dict(summary.rows[0])
            unsafe["notice"] = "=HYPERLINK(\"https://invalid.example\")"
            datasets["RunSummary"] = AuditDataset(
                summary.name, summary.columns, (unsafe,), summary.sort_key_columns
            )
            artifacts = _write_xlsx_artifact(
                Path(directory), datasets, max_data_rows=2
            )
            workbook = Path(directory) / artifacts[0]["relative_path"]
            with zipfile.ZipFile(workbook) as archive:
                xml = b"\n".join(
                    archive.read(name)
                    for name in archive.namelist()
                    if name.startswith("xl/worksheets/") and name.endswith(".xml")
                )
            self.assertNotIn(b"<f>", xml)
            self.assertNotIn(b"<hyperlink", xml)
            self.assertIn(b"'=HYPERLINK", xml)


if __name__ == "__main__":
    unittest.main()
