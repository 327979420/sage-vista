"""Fixed-sample tests for the M10-C portfolio and aggregate boundary."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from services.contracts.validation import ContractError
from services.evaluation import (
    AGGREGATION_POLICY,
    EvaluationShadowStore,
    M10_C_SOURCE_VERSION,
    ReadonlyEvaluationBatch,
    build_aggregate_scope,
    build_experiment_run_receipt,
    build_readonly_pending_run,
    evaluate_portfolio_boundary,
    evaluate_research_aggregate,
    finalize_result,
    produce_portfolio_boundary,
    produce_research_aggregate,
    store_readonly_evaluation_batch,
    validate_readonly_evaluation_batch,
    validate_result,
)
from tests.test_m10_evaluation_contracts import (
    aggregate_values,
    forward_2_1_values,
    portfolio_values,
    trade_values,
)


def plain(value):
    if hasattr(value, "items"):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def stable(prefix: str, digit: str) -> str:
    return f"{prefix}:sha256:{digit * 64}"


def forward(
    digit: str,
    *,
    gross: float | None = None,
    status: str = "mature",
    window: int = 5,
    role: str = "authoritative",
    partition: str = "forward",
):
    values = forward_2_1_values(mature=status != "pending")
    values.update({
        "event_id": stable("opportunity", digit),
        "instrument_id": stable("instrument", digit),
        "run_id": stable("experiment-run", digit),
        "window_sessions": window,
        "result_role": role,
        "partition_role": partition,
    })
    if status == "pending":
        values.update({
            "as_of": "2026-09-03",
            "generated_at": "2026-09-03T22:00:00Z",
            "elapsed_session_count": 2,
            "observed_session_count": 2,
            "observed_through": "2026-09-03",
            "target_session_date": None,
            "status": "pending",
            "status_reason": "window_not_mature",
            "endpoint": None,
            "gross_return": None,
            "mfe": None,
            "mae": None,
        })
    elif status == "partial":
        values.update({
            "status": "partial",
            "status_reason": "trading_halt_before_full_window",
            "observed_session_count": max(window - 1, 0),
            "gross_return": gross,
            "mfe": None,
            "mae": None,
        })
    elif status == "unavailable":
        values.update({
            "status": "unavailable",
            "status_reason": "endpoint_price_unavailable",
            "observed_session_count": max(window - 1, 0),
            "endpoint": None,
            "gross_return": None,
            "mfe": None,
            "mae": None,
        })
    else:
        values["gross_return"] = gross
    return finalize_result("ForwardOutcome", values)


def trade(
    digit: str,
    *,
    gross: float | None = 0.1,
    status: str = "completed",
    role: str = "authoritative",
    partition: str = "forward",
):
    values = trade_values(role=role)
    values.update({
        "event_id": stable("opportunity", digit),
        "instrument_id": stable("instrument", digit),
        "run_id": stable("experiment-run", digit),
        "trade_plan_id": stable("plan", digit),
        "exit_state_id": stable("exit-state", digit),
        "gross_return": gross,
        "gross_r_multiple": gross * 10 if gross is not None else None,
        "partition_role": partition,
    })
    if status == "pending":
        values.update({
            "status": "pending", "status_reason": "trade_open",
            "exit": None, "exit_reason": None, "gross_return": None,
            "gross_r_multiple": None, "holding_sessions": 3,
        })
    elif status in {"no_trade", "unavailable"}:
        values.update({
            "status": status,
            "status_reason": (
                "ranking_entry_not_selected"
                if status == "no_trade"
                else "entry_price_unavailable"
            ),
            "trade_plan_id": None,
            "trade_plan_content_fingerprint": None,
            "exit_state_id": None,
            "exit_state_content_fingerprint": None,
            "entry": None,
            "exit": None,
            "exit_reason": None,
            "gross_return": None,
            "gross_r_multiple": None,
            "holding_sessions": 0,
        })
    return finalize_result("TradeOutcome", values)


def forward_scope(window: int = 5, *, role: str = "authoritative", partition="forward"):
    return build_aggregate_scope(
        source_result_type="forward_outcome",
        window_sessions=window,
        path_status="formal",
        result_role=role,
        partition_role=partition,
    )


def trade_scope(sample, *, role: str = "authoritative", partition="forward"):
    return build_aggregate_scope(
        source_result_type="trade_outcome",
        window_sessions=None,
        path_status="formal",
        result_role=role,
        partition_role=partition,
        execution_policy=sample["execution_policy"],
        cost_policy=sample["cost_policy"],
    )


def pending(contract, outcomes, scope, *, suffix="1", as_of="2026-09-09"):
    return build_readonly_pending_run(
        contract,
        outcomes,
        evidence_scope=scope,
        as_of=as_of,
        generated_at=f"2026-09-09T22:0{suffix}:00Z",
        attempt_id=f"m10-c-attempt-{suffix}",
        experiment_id="M10-C-fixed-sample",
        code_commit="c" * 40,
        started_at="2026-09-09T22:00:00Z",
    )


def resign_result(contract_name, original, **changes):
    values = plain(original)
    id_field = {
        "PortfolioRun": "portfolio_run_id",
        "ResearchAggregate": "research_aggregate_id",
    }[contract_name]
    fingerprint_field = {
        "PortfolioRun": "portfolio_content_fingerprint",
        "ResearchAggregate": "aggregate_content_fingerprint",
    }[contract_name]
    for field in (
        id_field, fingerprint_field, "logical_result_id", "input_fingerprint"
    ):
        values.pop(field, None)
    values.update(changes)
    return finalize_result(contract_name, values)


def resign_receipt(original, **changes):
    values = plain(original)
    for field in (
        "run_id", "run_receipt_id", "run_content_fingerprint",
        "input_set_fingerprint", "result_set_fingerprint",
    ):
        values.pop(field, None)
    values.update(changes)
    return build_experiment_run_receipt(**values)


def research_batch(outcomes, scope, *, suffix="1"):
    receipt = pending("ResearchAggregate", outcomes, scope, suffix=suffix)
    return evaluate_research_aggregate(
        outcomes,
        aggregate_scope=scope,
        pending_run_receipt=receipt,
        generated_at="2026-09-09T22:10:00Z",
        finished_at="2026-09-09T22:11:00Z",
    )


class M10AggregateTests(unittest.TestCase):
    def test_input_order_is_deterministic_and_same_entry_serves_replay(self):
        outcomes = [
            forward("1", gross=0.1),
            forward("2", gross=-0.05),
            forward("3", gross=0.0),
        ]
        first = research_batch(outcomes, forward_scope())
        second = research_batch(list(reversed(outcomes)), forward_scope())
        self.assertEqual(first.pending_run_receipt, second.pending_run_receipt)
        self.assertEqual(first.result, second.result)
        self.assertEqual(1, first.result["win_count"])
        self.assertEqual(1, first.result["loss_count"])
        self.assertEqual(1, first.result["flat_count"])

    def test_duplicate_ids_and_logical_revisions_fail(self):
        item = forward("1", gross=0.1)
        with self.assertRaises(ContractError):
            pending("ResearchAggregate", [item, item], forward_scope())

        immature = forward("2", status="pending")
        mature_values = forward_2_1_values(
            mature=True, prior=immature["forward_outcome_id"]
        )
        mature_values.update({
            "event_id": immature["event_id"],
            "instrument_id": immature["instrument_id"],
            "run_id": immature["run_id"],
        })
        mature = finalize_result("ForwardOutcome", mature_values)
        with self.assertRaises(ContractError):
            pending("ResearchAggregate", [immature, mature], forward_scope())

    def test_bad_fingerprint_and_bare_references_fail(self):
        item = forward("1", gross=0.1)
        corrupted = plain(item)
        corrupted["forward_content_fingerprint"] = "sha256:" + "f" * 64
        with self.assertRaises(ContractError):
            pending("ResearchAggregate", [corrupted], forward_scope())
        with self.assertRaises(ContractError):
            pending(
                "ResearchAggregate",
                [{
                    "id": item["forward_outcome_id"],
                    "content_fingerprint": item["forward_content_fingerprint"],
                }],
                forward_scope(),
            )

    def test_cross_window_and_result_type_mixing_fail(self):
        five = forward("1", gross=0.1, window=5)
        twenty = forward("2", status="pending", window=20)
        with self.assertRaises(ContractError):
            pending("ResearchAggregate", [five, twenty], forward_scope(5))
        with self.assertRaises(ContractError):
            pending(
                "ResearchAggregate", [five, trade("3")], forward_scope(5)
            )

    def test_role_and_partition_mixing_fail(self):
        authoritative = forward("1", gross=0.1)
        comparison = forward("2", gross=0.1, role="comparison")
        validation = forward("3", gross=0.1, partition="validation")
        for mixed in ([authoritative, comparison], [authoritative, validation]):
            with self.assertRaises(ContractError):
                pending("ResearchAggregate", mixed, forward_scope())

    def test_forward_status_counts_and_conservation_are_exact(self):
        outcomes = [
            forward("1", status="pending"),
            forward("2", gross=0.1),
            forward("3", gross=-0.05, status="partial"),
            forward("4", status="unavailable"),
        ]
        result = research_batch(outcomes, forward_scope()).result
        self.assertEqual(
            {"pending": 1, "mature": 1, "partial": 1, "unavailable": 1},
            plain(result["status_counts"]),
        )
        self.assertEqual(4, result["total_count"])
        self.assertEqual(2, result["evaluated_count"])
        self.assertEqual(2, result["missing_count"])
        self.assertEqual(0.5, result["missing_rate"])

    def test_trade_open_and_no_trade_are_preserved_separately(self):
        completed = trade("1", gross=0.1)
        outcomes = [
            completed,
            trade("2", status="pending"),
            trade("3", status="no_trade"),
            trade("4", status="unavailable"),
        ]
        result = research_batch(outcomes, trade_scope(completed)).result
        self.assertEqual(
            {"completed": 1, "open": 1, "no_trade": 1, "unavailable": 1},
            plain(result["status_counts"]),
        )
        self.assertEqual(1, result["evaluated_count"])
        self.assertEqual(3, result["missing_count"])
        self.assertEqual(0.75, result["missing_rate"])

    def test_unknown_pending_trade_status_is_not_silently_mapped(self):
        opened = plain(trade("1", status="pending"))
        opened["status_reason"] = "unknown_pending_state"
        # Re-signing cannot make this an aggregatable open state.
        opened.pop("input_fingerprint")
        opened.pop("trade_outcome_id")
        opened.pop("trade_content_fingerprint")
        opened.pop("logical_result_id")
        resigned = finalize_result("TradeOutcome", opened)
        with self.assertRaises(ContractError):
            research_batch([resigned], trade_scope(resigned))

    def test_empty_sample_has_null_metrics_and_conserves_zero(self):
        scope = forward_scope()
        batch = research_batch([], scope)
        result = batch.result
        self.assertEqual(0, result["total_count"])
        self.assertEqual(0, result["missing_count"])
        self.assertIsNone(result["missing_rate"])
        self.assertEqual("unavailable", result["metric_status"])
        self.assertEqual("empty_sample", result["metric_reason"])
        for field in (
            "win_rate", "mean_gross_return", "median_gross_return",
            "gross_profit", "gross_loss_abs", "profit_factor",
            "gross_expectancy",
        ):
            self.assertIsNone(result[field])

    def test_profit_factor_special_semantics(self):
        no_losses = research_batch(
            [forward("1", gross=0.1), forward("2", gross=0.0)],
            forward_scope(),
        ).result
        self.assertIsNone(no_losses["profit_factor"])
        self.assertEqual("unbounded_no_losses", no_losses["metric_reason"])

        only_losses = research_batch(
            [forward("3", gross=-0.1), forward("4", gross=-0.2)],
            forward_scope(), suffix="2",
        ).result
        self.assertEqual(0.0, only_losses["profit_factor"])
        self.assertIsNone(only_losses["metric_reason"])

        all_flat = research_batch(
            [forward("5", gross=0.0), forward("6", gross=0.0)],
            forward_scope(), suffix="3",
        ).result
        self.assertIsNone(all_flat["profit_factor"])
        self.assertEqual(
            "undefined_zero_profit_and_loss", all_flat["metric_reason"]
        )

    def test_decimal_statistics_and_expectancy_are_deterministic(self):
        result = research_batch(
            [
                forward("1", gross=0.1),
                forward("2", gross=-0.05),
                forward("3", gross=0.2),
                forward("4", gross=0.0),
            ],
            forward_scope(),
        ).result
        self.assertEqual(0.0625, result["mean_gross_return"])
        self.assertEqual(0.05, result["median_gross_return"])
        self.assertEqual(0.3, result["gross_profit"])
        self.assertEqual(0.05, result["gross_loss_abs"])
        self.assertEqual(6.0, result["profit_factor"])
        self.assertEqual(result["mean_gross_return"], result["gross_expectancy"])

    def test_non_finite_input_and_output_injection_fail(self):
        item = plain(forward("1", gross=0.1))
        item["gross_return"] = float("nan")
        with self.assertRaises(ContractError):
            pending("ResearchAggregate", [item], forward_scope())

        valid = plain(research_batch([forward("2", gross=0.1)], forward_scope()).result)
        valid["mean_gross_return"] = float("inf")
        with self.assertRaises(ContractError):
            validate_result("ResearchAggregate", valid)

    def test_status_buckets_cannot_be_resigned_as_evaluated_samples(self):
        pending_result = plain(
            research_batch([forward("1", status="pending")], forward_scope()).result
        )
        forged_fields = {
            "evaluated_count": 1,
            "missing_count": 0,
            "missing_rate": 0.0,
            "win_count": 1,
            "loss_count": 0,
            "flat_count": 0,
            "win_rate": 1.0,
            "mean_gross_return": 0.5,
            "median_gross_return": 0.5,
            "gross_profit": 0.5,
            "gross_loss_abs": 0.0,
            "profit_factor": None,
            "gross_expectancy": 0.5,
            "metric_status": "available",
            "metric_reason": "unbounded_no_losses",
        }
        pending_result.update(forged_fields)
        with self.assertRaises(ContractError):
            resign_result("ResearchAggregate", pending_result)

        opened = trade("2", status="pending")
        open_result = plain(research_batch([opened], trade_scope(opened)).result)
        open_result.update(forged_fields)
        with self.assertRaises(ContractError):
            resign_result("ResearchAggregate", open_result)

    def test_full_outcomes_reject_resigned_statistics_in_completion_and_store(self):
        source = forward("1", gross=0.1)
        batch = research_batch([source], forward_scope())
        forged = resign_result(
            "ResearchAggregate",
            batch.result,
            mean_gross_return=0.9,
            median_gross_return=0.9,
            gross_profit=0.9,
            gross_expectancy=0.9,
        )
        from services.evaluation import complete_readonly_run

        with self.assertRaises(ContractError):
            complete_readonly_run(
                batch.pending_run_receipt,
                "ResearchAggregate",
                forged,
                [source],
                generated_at="2026-09-09T22:11:00Z",
                finished_at="2026-09-09T22:11:00Z",
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "m10"
            store = EvaluationShadowStore(root)
            store.write_run_receipt(batch.pending_run_receipt)
            before = {path: path.read_bytes() for path in root.rglob("*.json")}
            with self.assertRaises(ContractError):
                store.write_result(
                    "ResearchAggregate", forged, source_records=[source]
                )
            self.assertEqual(before, {path: path.read_bytes() for path in root.rglob("*.json")})

    def test_result_as_of_cannot_move_beyond_pending_receipt(self):
        source = forward("1", gross=0.1)
        batch = research_batch([source], forward_scope())
        forged = resign_result(
            "ResearchAggregate", batch.result, as_of="2026-09-10"
        )
        from services.evaluation import complete_readonly_run

        with self.assertRaises(ContractError):
            complete_readonly_run(
                batch.pending_run_receipt,
                "ResearchAggregate",
                forged,
                [source],
                generated_at="2026-09-10T22:00:00Z",
                finished_at="2026-09-10T22:00:00Z",
            )

    def test_profit_factor_uses_one_shared_quantization_order(self):
        result = research_batch(
            [
                forward("1", gross=1.8589043739974798),
                forward("2", gross=-1.5200657880305704),
            ],
            forward_scope(),
        ).result
        self.assertEqual(1.2229104745, result["profit_factor"])

    def test_contract_rejects_raw_market_or_metric_override_fields(self):
        result = plain(research_batch([forward("1", gross=0.1)], forward_scope()).result)
        for field, value in (
            ("ohlcv", [{"date": "2026-09-09", "close": 1.0}]),
            ("rows", []),
            ("net_return", 9.99),
        ):
            injected = dict(result)
            injected[field] = value
            with self.assertRaises(ContractError):
                validate_result("ResearchAggregate", injected)

    def test_portfolio_is_unavailable_order_independent_and_has_no_metrics(self):
        outcomes = [trade("1", gross=0.1), trade("2", gross=-0.05)]
        scope = trade_scope(outcomes[0])
        first_pending = pending("PortfolioRun", outcomes, scope)
        second_pending = pending("PortfolioRun", reversed(outcomes), scope)
        first = produce_portfolio_boundary(
            outcomes,
            portfolio_scope=scope,
            pending_run_receipt=first_pending,
            generated_at="2026-09-09T22:10:00Z",
        )
        second = produce_portfolio_boundary(
            reversed(outcomes),
            portfolio_scope=scope,
            pending_run_receipt=second_pending,
            generated_at="2026-09-09T22:10:00Z",
        )
        self.assertEqual(first, second)
        self.assertEqual("unavailable", first["status"])
        self.assertEqual(
            "capital_allocation_policy_not_approved", first["status_reason"]
        )
        self.assertNotIn("total_return", first)
        self.assertNotIn("equity_curve", first)

    def test_portfolio_rejects_duplicate_logical_or_mixed_trade_evidence(self):
        item = trade("1")
        scope = trade_scope(item)
        with self.assertRaises(ContractError):
            pending("PortfolioRun", [item, item], scope)
        comparison = trade("2", role="comparison")
        with self.assertRaises(ContractError):
            pending("PortfolioRun", [item, comparison], scope)

    def test_2_0_readonly_and_2_1_field_sets_are_isolated(self):
        fwd = forward("1", gross=0.1)
        trd = trade("2", gross=0.1)
        old_portfolio = finalize_result("PortfolioRun", portfolio_values(trd))
        old_aggregate = finalize_result("ResearchAggregate", aggregate_values(fwd))
        validate_result("PortfolioRun", old_portfolio)
        validate_result("ResearchAggregate", old_aggregate)
        self.assertEqual("2.0.0", old_portfolio["schema_version"])
        self.assertEqual("2.0.0", old_aggregate["schema_version"])

        old_with_new = plain(old_portfolio)
        old_with_new["result_set_fingerprint"] = "sha256:" + "1" * 64
        with self.assertRaises(ContractError):
            validate_result("PortfolioRun", old_with_new)

        new = research_batch([fwd], forward_scope()).result
        self.assertEqual("2.1.0", new["schema_version"])
        self.assertEqual(
            {"evaluation_contracts": M10_C_SOURCE_VERSION},
            plain(new["source_version"]),
        )
        missing = plain(new)
        missing.pop("aggregate_scope")
        with self.assertRaises(ContractError):
            validate_result("ResearchAggregate", missing)

    def test_run_receipts_are_source_consistent_and_store_is_append_only(self):
        item = forward("1", gross=0.1)
        batch = research_batch([item], forward_scope())
        expected_source = {"evaluation_contracts": M10_C_SOURCE_VERSION}
        self.assertEqual(expected_source, plain(batch.pending_run_receipt["source_version"]))
        self.assertEqual(expected_source, plain(batch.result["source_version"]))
        self.assertEqual(expected_source, plain(batch.completed_run_receipt["source_version"]))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "m10"
            store = EvaluationShadowStore(root)
            paths = store_readonly_evaluation_batch(store, batch)
            before = {path: path.read_bytes() for path in root.rglob("*.json")}
            self.assertEqual(paths, store_readonly_evaluation_batch(store, batch))
            self.assertEqual(before, {path: path.read_bytes() for path in root.rglob("*.json")})

    def test_public_store_rejects_orphan_m10c_result(self):
        item = forward("1", gross=0.1)
        batch = research_batch([item], forward_scope())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "m10"
            store = EvaluationShadowStore(root)
            with self.assertRaises(ContractError):
                store.write_result("ResearchAggregate", batch.result)
            self.assertEqual([], list(root.rglob("*.json")))

    def test_public_store_requires_complete_sources_and_exact_receipt_identity(self):
        source = forward("1", gross=0.1)
        batch = research_batch([source], forward_scope())
        wrong_source = resign_receipt(
            batch.pending_run_receipt,
            source_version={"evaluation_contracts": "m10-c-readonly-0.9.0"},
        )
        wrong_engine = resign_receipt(
            batch.pending_run_receipt,
            engine={
                "name": "not-the-readonly-engine",
                "version": "1.0.0",
                "adapter_version": "shadow-1.0.0",
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "m10"
            store = EvaluationShadowStore(root)
            for invalid in (wrong_source, wrong_engine):
                with self.assertRaises(ContractError):
                    store.write_run_receipt(invalid)
            self.assertEqual([], list(root.rglob("*.json")))

            store.write_run_receipt(batch.pending_run_receipt)
            with self.assertRaises(ContractError):
                store.write_result("ResearchAggregate", batch.result)
            store.write_result(
                "ResearchAggregate", batch.result, source_records=[source]
            )

    def test_failed_receipt_cannot_masquerade_as_completed_batch(self):
        source = forward("1", gross=0.1)
        batch = research_batch([source], forward_scope())
        failed = resign_receipt(
            batch.pending_run_receipt,
            status="failed",
            result_refs=plain(batch.completed_run_receipt["result_refs"]),
            finished_at="2026-09-09T22:11:00Z",
            supersedes_run_receipt_id=batch.pending_run_receipt["run_receipt_id"],
            error={"category": "fixed_sample_failure", "message": "expected"},
        )
        forged_batch = ReadonlyEvaluationBatch(
            "ResearchAggregate",
            "ForwardOutcome",
            (source,),
            batch.pending_run_receipt,
            batch.result,
            failed,
        )
        with self.assertRaises(ContractError):
            validate_readonly_evaluation_batch(forged_batch)

    def test_completed_run_seals_m10c_result_set(self):
        item = forward("1", gross=0.1)
        batch = research_batch([item], forward_scope())
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationShadowStore(Path(directory) / "m10")
            store_readonly_evaluation_batch(store, batch)
            changed_values = plain(batch.result)
            changed_values["generated_at"] = "2026-09-09T23:00:00Z"
            changed_values["mean_gross_return"] = 0.2
            with self.assertRaises(ContractError):
                validate_result("ResearchAggregate", changed_values)

    def test_aggregation_policy_is_exact_and_unknown_fields_fail(self):
        item = forward("1", gross=0.1)
        result = plain(research_batch([item], forward_scope()).result)
        self.assertEqual(plain(AGGREGATION_POLICY), result["aggregation_policy"])
        changed = plain(result)
        changed["aggregation_policy"]["rules"]["missing_values_are_zero"] = True
        with self.assertRaises(ContractError):
            validate_result("ResearchAggregate", changed)

    def test_portfolio_2_1_rejects_any_performance_field(self):
        source = trade("1")
        scope = trade_scope(source)
        receipt = pending("PortfolioRun", [source], scope)
        result = plain(produce_portfolio_boundary(
            [source], portfolio_scope=scope,
            pending_run_receipt=receipt,
            generated_at="2026-09-09T22:10:00Z",
        ))
        result["total_return"] = 9.99
        with self.assertRaises(ContractError):
            validate_result("PortfolioRun", result)


if __name__ == "__main__":
    unittest.main()
