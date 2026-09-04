"""Fixed-sample M10-D query, inventory, CSV, and package tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from decimal import Decimal
import hashlib
import importlib.util
import csv
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
from threading import Event
import unittest
import zipfile

from services.contracts.validation import ContractError
from services.contracts.market_data import canonical_fingerprint
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
    compute_export_receipt_id,
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
from services.evaluation.export import (
    DATASET_COLUMNS,
    DATASET_SORT_KEYS,
    _file_evidence,
    _sort_key,
    _write_csv_part,
    dataset_row_set_fingerprint,
    read_csv_part,
)
from services.evaluation.contracts import RESULT_TYPES
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


def _rewrite_zip_member(path: Path, member: str, transform) -> None:
    temporary = path.with_name(path.name + ".mutated")
    with zipfile.ZipFile(path, "r") as source:
        entries = [(item, source.read(item.filename)) for item in source.infolist()]
    changed = False
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for item, content in entries:
            if item.filename == member:
                replacement = transform(content)
                changed = replacement != content
                content = replacement
            target.writestr(item, content)
    if not changed:
        temporary.unlink()
        raise AssertionError(f"test mutation did not change {member}")
    os.replace(temporary, path)


def _canonical_bytes(value) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _resign_package_after_xlsx_change(package: Path) -> None:
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    xlsx_path = next(
        package / item["relative_path"]
        for item in manifest["artifacts"] if item["format"] == "xlsx"
    )
    raw = xlsx_path.read_bytes()
    fingerprint = "sha256:" + hashlib.sha256(raw).hexdigest()
    for item in manifest["artifacts"]:
        if item["format"] == "xlsx":
            item["byte_count"] = len(raw)
            item["file_sha256"] = fingerprint
    manifest["artifact_set_fingerprint"] = canonical_fingerprint(manifest["artifacts"])
    manifest["export_receipt_id"] = compute_export_receipt_id(manifest)
    semantic = {
        key: value for key, value in manifest.items()
        if key != "manifest_content_fingerprint"
    }
    manifest["manifest_content_fingerprint"] = canonical_fingerprint(semantic)
    manifest_bytes = _canonical_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)
    completed = {
        "export_receipt_id": manifest["export_receipt_id"],
        "manifest_file_sha256": "sha256:" + hashlib.sha256(manifest_bytes).hexdigest(),
        "artifact_set_fingerprint": manifest["artifact_set_fingerprint"],
        "status": "completed",
        "notice": manifest["notice"],
    }
    (package / "COMPLETED.json").write_bytes(_canonical_bytes(completed))


def _resign_manifest(package: Path) -> None:
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_set_fingerprint"] = canonical_fingerprint(manifest["artifacts"])
    manifest["export_receipt_id"] = compute_export_receipt_id(manifest)
    semantic = {
        key: value for key, value in manifest.items()
        if key != "manifest_content_fingerprint"
    }
    manifest["manifest_content_fingerprint"] = canonical_fingerprint(semantic)
    manifest_bytes = _canonical_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)
    (package / "COMPLETED.json").write_bytes(_canonical_bytes({
        "export_receipt_id": manifest["export_receipt_id"],
        "manifest_file_sha256": "sha256:" + hashlib.sha256(manifest_bytes).hexdigest(),
        "artifact_set_fingerprint": manifest["artifact_set_fingerprint"],
        "status": "completed", "notice": manifest["notice"],
    }))


def _rewrite_csv_typed_cell(
    package: Path, dataset_name: str, column_name: str, value
) -> None:
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = next(
        item for item in manifest["artifacts"]
        if item["format"] == "csv" and item["dataset"] == dataset_name
        and item["data_row_count"] > 0
    )
    dataset = AuditDataset(
        dataset_name, DATASET_COLUMNS[dataset_name], (), DATASET_SORT_KEYS[dataset_name]
    )
    path = package / artifact["relative_path"]
    rows = [dict(item) for item in read_csv_part(path, dataset)]
    rows[0][column_name] = value
    _write_csv_part(path, dataset, rows)
    artifact["data_row_count"] = len(rows)
    artifact["first_sort_key"] = _sort_key(dataset, rows[0]) if rows else None
    artifact["last_sort_key"] = _sort_key(dataset, rows[-1]) if rows else None
    artifact["row_set_fingerprint"] = dataset_row_set_fingerprint(dataset, rows)
    artifact["byte_count"], artifact["file_sha256"] = _file_evidence(path)
    manifest_path.write_bytes(_canonical_bytes(manifest))
    _resign_manifest(package)


def _rewrite_csv_header(package: Path, dataset_name: str, transform) -> None:
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact = next(
        item for item in manifest["artifacts"]
        if item["format"] == "csv" and item["dataset"] == dataset_name
    )
    path = package / artifact["relative_path"]
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"), newline="")))
    rows[0] = transform(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, dialect="excel", lineterminator="\r\n")
        writer.writerows(rows)
    artifact["byte_count"], artifact["file_sha256"] = _file_evidence(path)
    manifest_path.write_bytes(_canonical_bytes(manifest))
    _resign_manifest(package)


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


def _resign_query_execution(execution, results, receipts):
    result_set = plain(execution.result_set)
    result_refs = []
    for contract_name, payload in results:
        id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
        result_refs.append({
            "result_contract": contract_name,
            "schema_version": payload["schema_version"],
            "result_id": payload[id_field],
            "logical_result_id": payload["logical_result_id"],
            "run_id": payload["run_id"],
            "content_fingerprint": payload[fingerprint_field],
        })
    receipt_refs = [{
        "run_id": item["run_id"],
        "run_receipt_id": item["run_receipt_id"],
        "run_content_fingerprint": item["run_content_fingerprint"],
        "supersedes_run_receipt_id": item["supersedes_run_receipt_id"],
        "status": item["status"],
    } for item in receipts]
    result_set.update({
        "result_refs": result_refs,
        "result_set_fingerprint": canonical_fingerprint(result_refs),
        "run_receipt_refs": receipt_refs,
        "run_receipt_set_fingerprint": canonical_fingerprint(receipt_refs),
        "row_count": len(result_refs),
        "status": "complete" if result_refs else "empty",
    })
    identity = {
        key: value for key, value in result_set.items()
        if key not in {"query_result_set_id", "query_result_set_content_fingerprint"}
    }
    fingerprint = canonical_fingerprint(identity)
    result_set["query_result_set_id"] = "query-result-set:" + fingerprint
    result_set["query_result_set_content_fingerprint"] = fingerprint
    return EvaluationQueryResult(
        execution.query, result_set, tuple(results), tuple(receipts)
    )


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

    def test_resigned_query_results_must_equal_complete_inventory_derivation(self):
        with tempfile.TemporaryDirectory() as directory:
            store, first, second = revision_store(Path(directory) / "m10")
            all_rows = execute_evaluation_query(
                store, build_evaluation_query(filters=None, revision_mode="all"),
                code_commit=COMMIT,
            )
            current = execute_evaluation_query(
                store, build_evaluation_query(filters=None, revision_mode="current"),
                code_commit=COMMIT,
            )
            first_receipts = tuple(
                item for item in all_rows.run_receipts if item["run_id"] == first["run_id"]
            )
            attacks = {
                "all_omission": _resign_query_execution(
                    all_rows, all_rows.results[1:], all_rows.run_receipts[1:]
                ),
                "all_duplicate": _resign_query_execution(
                    all_rows, all_rows.results + all_rows.results[:1],
                    all_rows.run_receipts,
                ),
                "all_reorder": _resign_query_execution(
                    all_rows, tuple(reversed(all_rows.results)),
                    tuple(reversed(all_rows.run_receipts)),
                ),
                "current_substitute": _resign_query_execution(
                    current, (("ForwardOutcome", first),), first_receipts
                ),
                "current_add_old": _resign_query_execution(
                    current,
                    (("ForwardOutcome", first), ("ForwardOutcome", second)),
                    all_rows.run_receipts,
                ),
            }
            for name, attack in attacks.items():
                with self.subTest(name=name), self.assertRaises(ContractError):
                    validate_query_execution(attack)

    def test_resigned_empty_set_cannot_erase_four_matching_inventory_results(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationShadowStore(Path(directory) / "m10")
            for index, window in enumerate((5, 20, 60, 100), 1):
                values = forward_2_1_values()
                values["window_sessions"] = window
                receipt, outcome = _pending_run_and_forward(
                    values, f"m10-d-four-{index}"
                )
                store.write_run_receipt(receipt)
                store.write_result("ForwardOutcome", outcome)
            execution = execute_evaluation_query(
                store,
                build_evaluation_query(
                    filters={"result_contracts": ["ForwardOutcome"]},
                    revision_mode="current",
                ),
                code_commit=COMMIT,
            )
            self.assertEqual(4, len(execution.results))
            erased = _resign_query_execution(execution, (), ())
            with self.assertRaisesRegex(ContractError, "complete deterministic"):
                validate_query_execution(erased)
            output = Path(directory) / "exports"
            with self.assertRaisesRegex(ContractError, "complete deterministic"):
                publish_audit_export(
                    erased, build_export_config(), output_root=output,
                    generated_at="2026-09-04T00:00:00Z", code_commit=COMMIT,
                )
            self.assertFalse(output.exists())

    def test_offline_completeness_requires_embedded_inventory_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _, _ = revision_store(Path(directory) / "m10")
            execution = execute_evaluation_query(
                store, build_evaluation_query(filters=None, revision_mode="current"),
                code_commit=COMMIT,
            )
            result_set = plain(execution.result_set)
            del result_set["source_inventory"]["entries"][0]["payload"]
            with self.assertRaisesRegex(ContractError, "inventory_evidence_unavailable"):
                validate_query_execution(EvaluationQueryResult(
                    execution.query, result_set, execution.results,
                    execution.run_receipts,
                ))

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

    def test_csv_business_values_and_reference_rows_are_bound_to_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            base = publish_audit_export(
                execution, build_export_config(),
                output_root=Path(directory) / "exports",
                generated_at="2026-09-04T00:00:00Z", code_commit=COMMIT,
            )
            for index, (dataset, column, value) in enumerate((
                ("ResearchAggregates", "mean_gross_return", Decimal("0.9")),
                ("ResearchAggregates", "mean_gross_return_canonical", "0.9"),
                ("ResearchAggregateRefs", "content_fingerprint", "sha256:" + "a" * 64),
            )):
                with self.subTest(dataset=dataset, column=column):
                    attacked = Path(directory) / f"attack-{index}"
                    shutil.copytree(base, attacked)
                    _rewrite_csv_typed_cell(attacked, dataset, column, value)
                    with self.assertRaises(ContractError):
                        verify_export_package(attacked)

    def test_every_main_and_reference_field_is_bound_to_canonical_projection(self):
        def changed(spec, value):
            if spec.kind == "bool":
                return not value
            if spec.kind == "int":
                return (value or 0) + 1
            if spec.kind == "decimal":
                return Decimal("0.9") if value is None else value + Decimal("0.1")
            if spec.kind == "json":
                if isinstance(value, dict):
                    return {**value, "__tampered__": True}
                if isinstance(value, list):
                    return [*value, "__tampered__"]
                return {"__tampered__": True}
            return "tampered" if value is None else str(value) + "-tampered"

        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            base = publish_audit_export(
                execution, build_export_config(),
                output_root=Path(directory) / "exports",
                generated_at="2026-09-04T00:00:00Z", code_commit=COMMIT,
            )
            manifest = plain(verify_export_package(base))
            for dataset_name in ("ResearchAggregates", "ResearchAggregateRefs"):
                artifact = next(
                    item for item in manifest["artifacts"]
                    if item["format"] == "csv"
                    and item["dataset"] == dataset_name
                    and item["data_row_count"] > 0
                )
                dataset = AuditDataset(
                    dataset_name, DATASET_COLUMNS[dataset_name], (),
                    DATASET_SORT_KEYS[dataset_name],
                )
                source_row = read_csv_part(
                    base / artifact["relative_path"], dataset
                )[0]
                for index, spec in enumerate(dataset.columns):
                    with self.subTest(dataset=dataset_name, column=spec.name):
                        attacked = Path(directory) / f"field-{dataset_name}-{index}"
                        shutil.copytree(base, attacked)
                        _rewrite_csv_typed_cell(
                            attacked, dataset_name, spec.name,
                            changed(spec, source_row[spec.name]),
                        )
                        with self.assertRaises(ContractError):
                            verify_export_package(attacked)

    def test_csv_header_must_be_exact_and_canonical(self):
        transforms = (
            lambda header: header[:-1],
            lambda header: header + ["unknown"],
            lambda header: header[:-1] + [header[0]],
            lambda header: list(reversed(header)),
        )
        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            base = publish_audit_export(
                execution, build_export_config(),
                output_root=Path(directory) / "exports",
                generated_at="2026-09-04T00:00:00Z", code_commit=COMMIT,
            )
            for index, transform in enumerate(transforms):
                with self.subTest(index=index):
                    attacked = Path(directory) / f"header-{index}"
                    shutil.copytree(base, attacked)
                    _rewrite_csv_header(attacked, "ResearchAggregates", transform)
                    with self.assertRaisesRegex(ContractError, "header"):
                        verify_export_package(attacked)

    def test_export_receipt_binds_code_commit_but_export_identity_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            config = build_export_config()
            first = publish_audit_export(
                execution, config, output_root=Path(directory) / "exports",
                generated_at="2026-09-04T00:00:00Z", code_commit="a" * 40,
            )
            second = publish_audit_export(
                execution, config, output_root=Path(directory) / "exports",
                generated_at="2026-09-04T00:00:00Z", code_commit="b" * 40,
            )
            first_manifest = verify_export_package(first)
            second_manifest = verify_export_package(second)
            self.assertEqual(first_manifest["export_id"], second_manifest["export_id"])
            self.assertNotEqual(
                first_manifest["export_receipt_id"],
                second_manifest["export_receipt_id"],
            )

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

        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            real_root = Path(directory) / "real-exports"
            real_root.mkdir()
            linked_root = Path(directory) / "linked-exports"
            linked_root.symlink_to(real_root, target_is_directory=True)
            with self.assertRaisesRegex(ContractError, "symbolic link"):
                publish_audit_export(
                    execution,
                    build_export_config(),
                    output_root=linked_root,
                    generated_at="2026-09-04T00:00:00Z",
                    code_commit=COMMIT,
                )

        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            config = build_export_config()
            output = Path(directory) / "exports"
            package = publish_audit_export(
                execution, config, output_root=output,
                generated_at="2026-09-04T00:00:00Z", code_commit=COMMIT,
            )
            manifest = plain(verify_export_package(package))
            csv_path = package / next(
                item["relative_path"] for item in manifest["artifacts"]
                if item["format"] == "csv"
            )
            csv_path.write_bytes(csv_path.read_bytes() + b"tampered")
            before = csv_path.read_bytes()
            with self.assertRaisesRegex(ContractError, "different bytes"):
                publish_audit_export(
                    execution, config, output_root=output,
                    generated_at="2026-09-04T00:00:00Z", code_commit=COMMIT,
                )
            self.assertEqual(before, csv_path.read_bytes())

    def test_package_verification_rejects_artifact_symlink(self):
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
            artifact = package / next(
                item["relative_path"] for item in manifest["artifacts"]
                if item["format"] == "csv"
            )
            outside = Path(directory) / "outside.csv"
            outside.write_bytes(artifact.read_bytes())
            artifact.unlink()
            artifact.symlink_to(outside)
            with self.assertRaisesRegex(ContractError, "symbolic link"):
                verify_export_package(package)


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
            worksheet_names = {item["worksheet_name"] for item in xlsx_artifacts}
            self.assertIn("Research Aggregates", worksheet_names)
            self.assertNotIn("Forward Outcomes", worksheet_names)
            self.assertNotIn("Trade Outcomes", worksheet_names)
            self.assertNotIn("Portfolio Status", worksheet_names)

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

    def test_xlsx_parts_match_csv_parts_without_loss_or_duplication(self):
        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            package = publish_audit_export(
                execution,
                build_export_config(formats=("csv", "xlsx"), max_data_rows=1),
                output_root=Path(directory) / "exports",
                generated_at="2026-09-04T00:00:00Z",
                code_commit=COMMIT,
            )
            manifest = plain(verify_export_package(package))
            csv_parts = {
                (item["dataset"], item["part_number"]): item
                for item in manifest["artifacts"] if item["format"] == "csv"
            }
            xlsx_parts = [
                item for item in manifest["artifacts"] if item["format"] == "xlsx"
            ]
            for item in xlsx_parts:
                counterpart = csv_parts[(item["dataset"], item["part_number"])]
                self.assertEqual(item["data_row_count"], counterpart["data_row_count"])
                self.assertEqual(
                    item["row_set_fingerprint"], counterpart["row_set_fingerprint"]
                )
                self.assertEqual(item["first_sort_key"], counterpart["first_sort_key"])
                self.assertEqual(item["last_sort_key"], counterpart["last_sort_key"])
            for dataset, expected in manifest["dataset_counts"].items():
                self.assertEqual(
                    expected,
                    sum(
                        item["data_row_count"] for item in manifest["artifacts"]
                        if item["format"] == "csv" and item["dataset"] == dataset
                    ),
                )

    def test_resigned_xlsx_cell_tampering_still_fails_csv_parity(self):
        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            package = publish_audit_export(
                execution,
                build_export_config(formats=("csv", "xlsx")),
                output_root=Path(directory) / "exports",
                generated_at="2026-09-04T00:00:00Z",
                code_commit=COMMIT,
            )
            workbook = package / "xlsx/sage-vista-m10-audit.xlsx"
            _rewrite_zip_member(
                workbook,
                "xl/worksheets/sheet1.xml",
                lambda raw: raw.replace(
                    b"Non-authoritative audit copy.",
                    b"Tampered audit copy........",
                    1,
                ),
            )
            _resign_package_after_xlsx_change(package)
            with self.assertRaisesRegex(ContractError, "differs from its CSV"):
                verify_export_package(package)

    def test_ooxml_formula_external_link_and_unknown_cell_type_fail(self):
        mutations = (
            (
                "xl/worksheets/sheet1.xml",
                lambda raw: raw.replace(
                    b'<c r="F2" s="3"><v>1</v></c>',
                    b'<c r="F2" s="3"><f>1+1</f><v>2</v></c>',
                    1,
                ),
            ),
            (
                "xl/_rels/workbook.xml.rels",
                lambda raw: raw.replace(
                    b"</Relationships>",
                    b'<Relationship Id="external" Type="x" Target="https://invalid.example" TargetMode="External"/></Relationships>',
                    1,
                ),
            ),
            (
                "xl/worksheets/sheet1.xml",
                lambda raw: raw.replace(b't="inlineStr"', b't="s"', 1),
            ),
        )
        for index, (member, transform) in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                execution = self._execution(directory)
                package = publish_audit_export(
                    execution,
                    build_export_config(formats=("csv", "xlsx")),
                    output_root=Path(directory) / "exports",
                    generated_at="2026-09-04T00:00:00Z",
                    code_commit=COMMIT,
                )
                workbook = package / "xlsx/sage-vista-m10-audit.xlsx"
                _rewrite_zip_member(workbook, member, transform)
                _resign_package_after_xlsx_change(package)
                with self.assertRaises(ContractError):
                    verify_export_package(package)

    def test_resigned_defined_name_data_validation_and_hidden_style_fail(self):
        mutations = (
            (
                "xl/workbook.xml",
                lambda raw: raw.replace(
                    b"</definedNames>",
                    b'<definedName name="attack">WEBSERVICE("https://invalid.example")</definedName></definedNames>',
                    1,
                ),
            ),
            (
                "xl/worksheets/sheet1.xml",
                lambda raw: raw.replace(
                    b"<pageMargins ",
                    b'<dataValidations count="1"><dataValidation type="custom" sqref="A2"><formula1>WEBSERVICE("https://invalid.example")</formula1></dataValidation></dataValidations><pageMargins ',
                    1,
                ),
            ),
            (
                "xl/styles.xml",
                lambda raw: raw.replace(
                    b'formatCode="0.0000000000"',
                    b'formatCode=";;;@@@@@@@@"',
                    1,
                ),
            ),
            (
                "xl/worksheets/sheet2.xml",
                lambda raw: raw.replace(
                    b'<c r="AJ2" s="5">', b'<c r="AJ2" s="2">', 1
                ),
            ),
        )
        for index, (member, transform) in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                execution = self._execution(directory)
                package = publish_audit_export(
                    execution,
                    build_export_config(formats=("csv", "xlsx")),
                    output_root=Path(directory) / "exports",
                    generated_at="2026-09-04T00:00:00Z",
                    code_commit=COMMIT,
                )
                workbook = package / "xlsx/sage-vista-m10-audit.xlsx"
                _rewrite_zip_member(workbook, member, transform)
                _resign_package_after_xlsx_change(package)
                with self.assertRaises(ContractError):
                    verify_export_package(package)

    def test_manual_xlsx_edit_invalidates_sha_and_has_no_import_entrypoint(self):
        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            package = publish_audit_export(
                execution,
                build_export_config(formats=("csv", "xlsx")),
                output_root=Path(directory) / "exports",
                generated_at="2026-09-04T00:00:00Z",
                code_commit=COMMIT,
            )
            workbook = package / "xlsx/sage-vista-m10-audit.xlsx"
            _rewrite_zip_member(
                workbook,
                "xl/worksheets/sheet1.xml",
                lambda raw: raw.replace(b"current", b"all....", 1),
            )
            with self.assertRaisesRegex(ContractError, "bytes do not match"):
                verify_export_package(package)
            import services.evaluation as evaluation

            self.assertFalse(any(name.startswith("import_") for name in evaluation.__all__))

    def test_xlsx_failure_leaves_no_visible_partial_package(self):
        with tempfile.TemporaryDirectory() as directory:
            execution = self._execution(directory)
            output = Path(directory) / "exports"
            with self.assertRaises(RuntimeError):
                publish_audit_export(
                    execution,
                    build_export_config(formats=("csv", "xlsx")),
                    output_root=output,
                    generated_at="2026-09-04T00:00:00Z",
                    code_commit=COMMIT,
                    fault_injector=lambda point: (
                        (_ for _ in ()).throw(RuntimeError("fixed XLSX failure"))
                        if point == "after_artifacts" else None
                    ),
                )
            self.assertEqual([], list(output.iterdir()))


if __name__ == "__main__":
    unittest.main()
