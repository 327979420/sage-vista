"""Contract-only tests for M10-A; no outcome value is calculated here."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from services.contracts.market_data import canonical_fingerprint
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError
from services.evaluation import (
    EVALUATION_POLICY,
    FORWARD_WINDOW_POLICY,
    PARTITION_POLICY,
    UNAPPROVED_COST_REFERENCE,
    ZERO_COST_COMPARISON_POLICY,
    EvaluationShadowStore,
    assert_immutable_compatible,
    build_experiment_run_receipt,
    current_result,
    finalize_result,
    validate_experiment_run,
    validate_result,
)


SHA = "sha256:" + "1" * 64
SHA_2 = "sha256:" + "2" * 64
INSTRUMENT = "instrument:sha256:" + "3" * 64
EVENT = "opportunity:sha256:" + "4" * 64
RUN = "experiment-run:sha256:" + "5" * 64
PLAN = "plan:sha256:" + "6" * 64
LINK = "machine-link:sha256:" + "7" * 64
EXIT_STATE = "exit-state:sha256:" + "8" * 64
MARKET = "market:sha256:" + "9" * 64
CALENDAR = "session-calendar:sha256:" + "a" * 64


def plain(value):
    if hasattr(value, "items"):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def common(*, role="authoritative", path="formal", biases=None):
    return {
        "schema_version": "2.0.0",
        "as_of": "2026-09-03",
        "generated_at": "2026-09-03T22:00:00Z",
        "source_version": {"evaluation_contracts": "m10-a-test"},
        "future_data_used": False,
        "run_id": RUN,
        "logical_result_id": "assigned-by-finalizer",
        "supersedes_result_id": None,
        "path_status": path,
        "result_role": role,
        "partition_role": "forward",
        "bias_labels": [] if biases is None else biases,
        "evaluation_policy": EVALUATION_POLICY,
        "partition_policy": PARTITION_POLICY,
        "input_fingerprint": SHA,
    }


def forward_values(*, role="authoritative", path="formal", biases=None):
    return {
        **common(role=role, path=path, biases=biases),
        "event_id": EVENT,
        "event_content_fingerprint": SHA,
        "instrument_id": INSTRUMENT,
        "signal_date": "2026-09-01",
        "signal_market_snapshot_id": MARKET,
        "window_sessions": 5,
        "window_policy": FORWARD_WINDOW_POLICY,
        "session_calendar_id": CALENDAR,
        "session_calendar_fingerprint": SHA,
        "status": "pending",
        "elapsed_session_count": 2,
        "observed_session_count": 2,
        "observed_through": "2026-09-03",
        "status_reason": "window_not_mature",
        "entry": {"date": "2026-09-02", "price": 100.0},
        "endpoint": None,
        "gross_return": None,
        "mfe": None,
        "mae": None,
        "price_basis": "provider_adjusted_ohlcv",
        "adjustment_policy": ADJUSTMENT_POLICY,
        "market_data_fingerprint": SHA,
    }


def mature_forward(prior=None):
    values = forward_values()
    values.update({
        "as_of": "2026-09-09",
        "generated_at": "2026-09-09T22:00:00Z",
        "supersedes_result_id": prior,
        "input_fingerprint": SHA_2,
        "status": "mature",
        "elapsed_session_count": 5,
        "observed_session_count": 5,
        "observed_through": "2026-09-09",
        "status_reason": None,
        "endpoint": {"date": "2026-09-09", "price": 110.0},
        "gross_return": 0.1,
        "mfe": 0.12,
        "mae": -0.03,
    })
    return values


def trade_values(*, role="authoritative", path="formal", biases=None):
    comparison = role == "comparison"
    values = {
        **common(role=role, path=path, biases=biases),
        "event_id": EVENT,
        "event_content_fingerprint": SHA,
        "instrument_id": INSTRUMENT,
        "signal_date": "2026-09-01",
        "trade_plan_id": PLAN,
        "trade_plan_content_fingerprint": SHA,
        "trade_plan_link_id": LINK,
        "trade_plan_link_content_fingerprint": SHA,
        "exit_state_id": EXIT_STATE,
        "exit_state_content_fingerprint": SHA,
        "status": "completed",
        "status_reason": None,
        "entry": {"date": "2026-09-02", "price": 100.0},
        "exit": {"date": "2026-09-09", "price": 110.0},
        "holding_sessions": 5,
        "gross_return": 0.1,
        "gross_r_multiple": 1.0,
        "net_return": 0.1 if comparison else None,
        "net_return_status": "available" if comparison else "unavailable",
        "net_return_reason": None if comparison else "cost_slippage_policy_not_approved",
        "mfe": None,
        "mae": None,
        "mfe_status": "unavailable",
        "mae_status": "unavailable",
        "cost_policy": ZERO_COST_COMPARISON_POLICY if comparison else UNAPPROVED_COST_REFERENCE,
        "price_basis": "provider_adjusted_ohlcv",
        "adjustment_policy": ADJUSTMENT_POLICY,
        "market_data_fingerprint": SHA,
        "execution_policy": {
            "policy_version": "1.0.0",
            "policy_fingerprint": SHA,
        },
    }
    values["as_of"] = "2026-09-09"
    values["generated_at"] = "2026-09-09T22:00:00Z"
    return values


def portfolio_values(trade):
    return {
        **common(),
        "status": "unavailable",
        "status_reason": "portfolio_policy_not_approved",
        "trade_outcome_refs": [{
            "id": trade["trade_outcome_id"],
            "content_fingerprint": trade["trade_content_fingerprint"],
        }],
    }


def aggregate_values(forward):
    return {
        **common(),
        "status": "unavailable",
        "status_reason": "research_aggregate_not_implemented",
        "result_refs": [{
            "id": forward["forward_outcome_id"],
            "content_fingerprint": forward["forward_content_fingerprint"],
        }],
    }


def receipt_values(forward):
    return {
        "as_of": "2026-09-03",
        "generated_at": "2026-09-03T22:05:00Z",
        "attempt_id": "attempt-1",
        "experiment_id": "M10-A-contract-test",
        "status": "completed",
        "evidence_window": {
            "start": "2026-09-01",
            "end": "2026-09-03",
            "evidence_as_of": "2026-09-03",
        },
        "path_status": "formal",
        "result_role": "authoritative",
        "partition_role": "forward",
        "bias_labels": [],
        "code_commit": "b" * 40,
        "config_ref": {
            "config_id": "m10-a-fixed-test",
            "config_version": "1.0.0",
            "content_fingerprint": SHA,
        },
        "engine": {
            "name": "m10-contract-only",
            "version": "1.0.0",
            "adapter_version": "none-1.0.0",
        },
        "policy_refs": [
            {
                "policy_kind": "evaluation",
                "policy_fingerprint": EVALUATION_POLICY["policy_fingerprint"],
            },
            {
                "policy_kind": "partition",
                "policy_fingerprint": PARTITION_POLICY["policy_fingerprint"],
            },
        ],
        "input_refs": [{"id": EVENT, "content_fingerprint": SHA}],
        "result_refs": [{
            "id": forward["forward_outcome_id"],
            "content_fingerprint": forward["forward_content_fingerprint"],
        }],
        "started_at": "2026-09-03T22:00:00Z",
        "finished_at": "2026-09-03T22:01:00Z",
        "parent_run_id": None,
        "checkpoint_ref": None,
        "error": None,
    }


class M10EvaluationContractsTests(unittest.TestCase):
    def test_all_four_result_contracts_and_run_receipt_are_valid_2x(self):
        forward = finalize_result("ForwardOutcome", forward_values())
        trade = finalize_result("TradeOutcome", trade_values())
        portfolio = finalize_result("PortfolioRun", portfolio_values(trade))
        aggregate = finalize_result("ResearchAggregate", aggregate_values(forward))
        receipt = build_experiment_run_receipt(**receipt_values(forward))
        for name, result in (
            ("ForwardOutcome", forward),
            ("TradeOutcome", trade),
            ("PortfolioRun", portfolio),
            ("ResearchAggregate", aggregate),
        ):
            self.assertEqual("2.0.0", result["schema_version"])
            validate_result(name, result)
        validate_experiment_run(receipt)

    def test_formal_comparison_and_legacy_identities_are_isolated(self):
        formal = finalize_result("ForwardOutcome", forward_values())
        comparison = finalize_result(
            "ForwardOutcome", forward_values(role="comparison")
        )
        legacy = finalize_result(
            "ForwardOutcome",
            forward_values(role="comparison", path="legacy", biases=["legacy_membership"]),
        )
        self.assertEqual(3, len({
            formal["logical_result_id"], comparison["logical_result_id"],
            legacy["logical_result_id"],
        }))
        with self.assertRaises(ContractError):
            finalize_result(
                "ForwardOutcome",
                forward_values(path="legacy", biases=["legacy_membership"]),
            )

    def test_identity_and_content_fingerprint_are_deterministic(self):
        first = finalize_result("ForwardOutcome", forward_values())
        second = finalize_result("ForwardOutcome", forward_values())
        self.assertEqual(first, second)
        self.assertIs(first, assert_immutable_compatible("ForwardOutcome", first, second))

    def test_same_identity_with_different_content_is_a_conflict(self):
        first = finalize_result("ForwardOutcome", forward_values())
        changed = forward_values()
        changed["observed_session_count"] = 1
        second = finalize_result("ForwardOutcome", changed)
        self.assertEqual(first["forward_outcome_id"], second["forward_outcome_id"])
        self.assertNotEqual(
            first["forward_content_fingerprint"], second["forward_content_fingerprint"]
        )
        with self.assertRaises(ContractError):
            assert_immutable_compatible("ForwardOutcome", first, second)

    def test_pending_matures_only_by_appending_a_revision(self):
        pending = finalize_result("ForwardOutcome", forward_values())
        mature = finalize_result(
            "ForwardOutcome", mature_forward(pending["forward_outcome_id"])
        )
        self.assertEqual(
            mature["forward_outcome_id"],
            current_result("ForwardOutcome", [mature, pending])["forward_outcome_id"],
        )
        self.assertEqual("pending", pending["status"])
        self.assertEqual(pending["forward_outcome_id"], mature["supersedes_result_id"])

    def test_partial_and_unavailable_are_explicit_due_states(self):
        partial = mature_forward()
        partial.update({
            "status": "partial",
            "observed_session_count": 4,
            "status_reason": "trading_halt_before_full_window",
            "mfe": None,
            "mae": None,
        })
        unavailable = mature_forward()
        unavailable.update({
            "status": "unavailable",
            "observed_session_count": 3,
            "status_reason": "endpoint_price_unavailable",
            "endpoint": None,
            "gross_return": None,
            "mfe": None,
            "mae": None,
        })
        self.assertEqual(
            "partial", finalize_result("ForwardOutcome", partial)["status"]
        )
        self.assertEqual(
            "unavailable", finalize_result("ForwardOutcome", unavailable)["status"]
        )

    def test_injected_price_dates_cannot_exceed_as_of(self):
        values = mature_forward()
        values["endpoint"] = {"date": "2026-09-10", "price": 110.0}
        with self.assertRaises(ContractError):
            finalize_result("ForwardOutcome", values)
        trade = trade_values()
        trade["exit"] = {"date": "2026-09-10", "price": 110.0}
        with self.assertRaises(ContractError):
            finalize_result("TradeOutcome", trade)

    def test_authoritative_net_return_cannot_claim_fake_precision(self):
        values = trade_values()
        values["net_return"] = 0.1
        values["net_return_status"] = "available"
        values["net_return_reason"] = None
        with self.assertRaises(ContractError):
            finalize_result("TradeOutcome", values)
        comparison = finalize_result(
            "TradeOutcome", trade_values(role="comparison")
        )
        self.assertEqual("comparison", comparison["result_role"])

    def test_portfolio_and_aggregate_calculation_remain_unavailable(self):
        forward = finalize_result("ForwardOutcome", forward_values())
        trade = finalize_result("TradeOutcome", trade_values())
        portfolio = portfolio_values(trade)
        portfolio["total_return"] = 1.5
        with self.assertRaises(ContractError):
            finalize_result("PortfolioRun", portfolio)
        aggregate = aggregate_values(forward)
        aggregate["statistics"] = {"mean": 0.1}
        with self.assertRaises(ContractError):
            finalize_result("ResearchAggregate", aggregate)

    def test_non_finite_numbers_are_rejected(self):
        for invalid in (float("nan"), float("inf"), float("-inf")):
            values = mature_forward()
            values["gross_return"] = invalid
            with self.assertRaises(ContractError):
                finalize_result("ForwardOutcome", values)

    def test_unknown_contract_major_is_rejected(self):
        result = plain(finalize_result("ForwardOutcome", forward_values()))
        result["schema_version"] = "3.0.0"
        with self.assertRaises(ContractError):
            validate_result("ForwardOutcome", result)

    def test_append_only_store_is_idempotent_and_preserves_revisions(self):
        pending = finalize_result("ForwardOutcome", forward_values())
        mature = finalize_result(
            "ForwardOutcome", mature_forward(pending["forward_outcome_id"])
        )
        receipt = build_experiment_run_receipt(**receipt_values(pending))
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationShadowStore(Path(directory) / "m10")
            pending_path = store.write_result("ForwardOutcome", pending)
            self.assertEqual(pending_path, store.write_result("ForwardOutcome", pending))
            mature_path = store.write_result("ForwardOutcome", mature)
            receipt_path = store.write_run_receipt(receipt)
            self.assertTrue(pending_path.exists())
            self.assertTrue(mature_path.exists())
            self.assertTrue(receipt_path.exists())
            self.assertNotEqual(pending_path, mature_path)

    def test_append_only_store_rejects_existing_identity_with_new_content(self):
        first = finalize_result("ForwardOutcome", forward_values())
        changed = forward_values()
        changed["observed_session_count"] = 1
        second = finalize_result("ForwardOutcome", changed)
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationShadowStore(Path(directory) / "m10")
            path = store.write_result("ForwardOutcome", first)
            before = path.read_bytes()
            with self.assertRaises(ContractError):
                store.write_result("ForwardOutcome", second)
            self.assertEqual(before, path.read_bytes())

    def test_store_rejects_production_paths(self):
        with self.assertRaises(ContractError):
            EvaluationShadowStore(Path.cwd() / "public" / "m10")

    def test_receipt_identity_binds_inputs_results_and_attempt(self):
        forward = finalize_result("ForwardOutcome", forward_values())
        first = build_experiment_run_receipt(**receipt_values(forward))
        second = build_experiment_run_receipt(**receipt_values(forward))
        self.assertEqual(first, second)
        changed = receipt_values(forward)
        changed["attempt_id"] = "attempt-2"
        third = build_experiment_run_receipt(**changed)
        self.assertNotEqual(first["run_id"], third["run_id"])
        self.assertEqual(
            first["input_set_fingerprint"],
            canonical_fingerprint(plain(first["input_refs"])),
        )


if __name__ == "__main__":
    unittest.main()
