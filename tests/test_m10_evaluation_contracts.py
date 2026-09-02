"""Contract-only tests for M10-A; no outcome value is calculated here."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import itertools
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
    current_experiment_run,
    current_result,
    finalize_result,
    result_input_fingerprint,
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
UNIVERSE = "universe:sha256:" + "b" * 64


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
    }


def forward_values(*, role="authoritative", path="formal", biases=None):
    return {
        **common(role=role, path=path, biases=biases),
        "event_id": EVENT,
        "event_content_fingerprint": SHA,
        "instrument_id": INSTRUMENT,
        "signal_date": "2026-09-01",
        "signal_market_snapshot_id": MARKET,
        "evaluation_market_snapshot_id": MARKET,
        "evaluation_market_snapshot_fingerprint": SHA_2,
        "universe_id": UNIVERSE,
        "universe_content_fingerprint": SHA,
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


def partial_forward(prior):
    values = mature_forward(prior)
    values.update({
        "status": "partial",
        "status_reason": "trading_halt_before_full_window",
        "observed_session_count": 4,
        "mfe": None,
        "mae": None,
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
        "evaluation_market_snapshot_id": MARKET,
        "evaluation_market_snapshot_fingerprint": SHA_2,
        "universe_id": UNIVERSE,
        "universe_content_fingerprint": SHA,
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
        "mfe_reason": "exit_day_inclusion_and_intraday_order_not_approved",
        "mae_reason": "exit_day_inclusion_and_intraday_order_not_approved",
        "exit_reason": "target",
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
                "policy_kind": "adjustment",
                "policy_version": ADJUSTMENT_POLICY["version"],
                "policy_fingerprint": canonical_fingerprint(ADJUSTMENT_POLICY),
            },
            {
                "policy_kind": "evaluation",
                "policy_version": EVALUATION_POLICY["policy_version"],
                "policy_fingerprint": EVALUATION_POLICY["policy_fingerprint"],
            },
            {
                "policy_kind": "forward_window",
                "policy_version": FORWARD_WINDOW_POLICY["policy_version"],
                "policy_fingerprint": FORWARD_WINDOW_POLICY["policy_fingerprint"],
            },
            {
                "policy_kind": "partition",
                "policy_version": PARTITION_POLICY["policy_version"],
                "policy_fingerprint": PARTITION_POLICY["policy_fingerprint"],
            },
        ],
        "input_refs": [
            {"id": EVENT, "content_fingerprint": SHA},
            {"id": MARKET, "content_fingerprint": SHA_2},
            {"id": UNIVERSE, "content_fingerprint": SHA},
        ],
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

    def test_run_identity_binds_source_window_and_bias_set(self):
        forward = finalize_result("ForwardOutcome", forward_values())
        base = build_experiment_run_receipt(**receipt_values(forward))

        changes = []
        source = receipt_values(forward)
        source["source_version"] = {"evaluation_contracts": "m10-a-2.0.0"}
        changes.append(build_experiment_run_receipt(**source))
        start = receipt_values(forward)
        start["evidence_window"]["start"] = "2026-08-29"
        changes.append(build_experiment_run_receipt(**start))
        end = receipt_values(forward)
        end["evidence_window"]["end"] = "2026-09-02"
        changes.append(build_experiment_run_receipt(**end))
        for changed in changes:
            self.assertNotEqual(base["run_id"], changed["run_id"])

        first_bias = receipt_values(forward)
        first_bias.update({
            "path_status": "legacy",
            "result_role": "comparison",
            "bias_labels": ["survivorship_bias", "current_membership_bias"],
        })
        reversed_bias = receipt_values(forward)
        reversed_bias.update({
            "path_status": "legacy",
            "result_role": "comparison",
            "bias_labels": ["current_membership_bias", "survivorship_bias"],
        })
        first = build_experiment_run_receipt(**first_bias)
        second = build_experiment_run_receipt(**reversed_bias)
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(
            ["current_membership_bias", "survivorship_bias"],
            list(first["bias_labels"]),
        )

        other_bias = receipt_values(forward)
        other_bias.update({
            "path_status": "legacy",
            "result_role": "comparison",
            "bias_labels": ["legacy_market_data"],
        })
        self.assertNotEqual(
            first["run_id"],
            build_experiment_run_receipt(**other_bias)["run_id"],
        )

    def test_modified_run_identity_cannot_reuse_old_ids(self):
        forward = finalize_result("ForwardOutcome", forward_values())
        receipt = plain(build_experiment_run_receipt(**receipt_values(forward)))
        receipt["source_version"] = {"evaluation_contracts": "changed"}
        with self.assertRaises(ContractError):
            validate_experiment_run(receipt)
        unknown_source = receipt_values(forward)
        unknown_source["source_version"] = {
            "evaluation_contracts": "m10-a-test",
            "unapproved_source": "garbage",
        }
        with self.assertRaises(ContractError):
            build_experiment_run_receipt(**unknown_source)

    def test_pending_run_receipt_completes_by_append_only_revision(self):
        forward = finalize_result("ForwardOutcome", forward_values())
        pending_values = receipt_values(forward)
        pending_values.update({
            "status": "pending",
            "result_refs": [],
            "finished_at": None,
        })
        pending = build_experiment_run_receipt(**pending_values)
        completed_values = receipt_values(forward)
        completed_values["supersedes_run_receipt_id"] = pending["run_receipt_id"]
        completed = build_experiment_run_receipt(**completed_values)

        self.assertEqual(pending["run_id"], completed["run_id"])
        self.assertNotEqual(pending["run_receipt_id"], completed["run_receipt_id"])
        self.assertEqual(
            completed["run_receipt_id"],
            current_experiment_run([completed, pending])["run_receipt_id"],
        )
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationShadowStore(Path(directory) / "m10")
            pending_path = store.write_run_receipt(pending)
            completed_path = store.write_run_receipt(completed)
            self.assertNotEqual(pending_path, completed_path)
            self.assertEqual(2, len(list((Path(directory) / "m10").rglob("*.json"))))

    def test_run_receipt_store_rejects_dangling_and_forked_revisions(self):
        forward = finalize_result("ForwardOutcome", forward_values())
        pending_values = receipt_values(forward)
        pending_values.update({
            "status": "pending", "result_refs": [], "finished_at": None,
        })
        pending = build_experiment_run_receipt(**pending_values)
        first_values = receipt_values(forward)
        first_values["supersedes_run_receipt_id"] = pending["run_receipt_id"]
        first = build_experiment_run_receipt(**first_values)
        second_values = receipt_values(forward)
        second_values["supersedes_run_receipt_id"] = pending["run_receipt_id"]
        second_values["result_refs"][0]["content_fingerprint"] = SHA_2
        second = build_experiment_run_receipt(**second_values)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "m10"
            store = EvaluationShadowStore(root)
            with self.assertRaises(ContractError):
                store.write_run_receipt(first)
            self.assertEqual([], list(root.rglob("*.json")))

            store.write_run_receipt(pending)
            store.write_run_receipt(first)
            before = {path: path.read_bytes() for path in root.rglob("*.json")}
            with self.assertRaises(ContractError):
                store.write_run_receipt(second)
            self.assertEqual(
                before, {path: path.read_bytes() for path in root.rglob("*.json")}
            )

    def test_reference_roles_are_exact_and_order_is_canonical(self):
        forward = finalize_result("ForwardOutcome", forward_values())
        trade = finalize_result("TradeOutcome", trade_values())

        portfolio = portfolio_values(trade)
        portfolio["trade_outcome_refs"][0]["id"] = "trade-outcome:not-a-hash"
        with self.assertRaises(ContractError):
            finalize_result("PortfolioRun", portfolio)
        portfolio = portfolio_values(trade)
        portfolio["trade_outcome_refs"][0] = {
            "id": forward["forward_outcome_id"],
            "content_fingerprint": forward["forward_content_fingerprint"],
        }
        with self.assertRaises(ContractError):
            finalize_result("PortfolioRun", portfolio)

        aggregate = aggregate_values(forward)
        aggregate["result_refs"][0]["id"] = "bogus"
        with self.assertRaises(ContractError):
            finalize_result("ResearchAggregate", aggregate)
        recursive = aggregate_values(forward)
        recursive["result_refs"][0]["id"] = "research-aggregate:sha256:" + "e" * 64
        with self.assertRaises(ContractError):
            finalize_result("ResearchAggregate", recursive)

        first = receipt_values(forward)
        first["input_refs"] = [
            {"id": EVENT, "content_fingerprint": SHA},
            {"id": MARKET, "content_fingerprint": SHA_2},
            {"id": UNIVERSE, "content_fingerprint": SHA},
        ]
        second = receipt_values(forward)
        second["input_refs"] = list(reversed(first["input_refs"]))
        self.assertEqual(
            build_experiment_run_receipt(**first)["run_id"],
            build_experiment_run_receipt(**second)["run_id"],
        )

    def test_run_receipt_rejects_invalid_duplicate_and_wrong_role_refs(self):
        forward = finalize_result("ForwardOutcome", forward_values())
        invalid_input = receipt_values(forward)
        invalid_input["input_refs"] = [{"id": "bogus", "content_fingerprint": SHA}]
        with self.assertRaises(ContractError):
            build_experiment_run_receipt(**invalid_input)
        wrong_result = receipt_values(forward)
        wrong_result["result_refs"] = [{"id": EVENT, "content_fingerprint": SHA}]
        with self.assertRaises(ContractError):
            build_experiment_run_receipt(**wrong_result)
        duplicate = receipt_values(forward)
        duplicate["input_refs"] = [
            {"id": EVENT, "content_fingerprint": SHA},
            {"id": EVENT, "content_fingerprint": SHA_2},
        ]
        with self.assertRaises(ContractError):
            build_experiment_run_receipt(**duplicate)

    def test_run_policy_set_rejects_unknown_missing_and_duplicate_kinds(self):
        forward = finalize_result("ForwardOutcome", forward_values())
        banana = receipt_values(forward)
        banana["policy_refs"] = [{
            "policy_kind": "banana",
            "policy_version": "1.0.0",
            "policy_fingerprint": SHA,
        }]
        with self.assertRaises(ContractError):
            build_experiment_run_receipt(**banana)

        for missing_kind in ("evaluation", "partition"):
            values = receipt_values(forward)
            values["policy_refs"] = [
                item for item in values["policy_refs"]
                if item["policy_kind"] != missing_kind
            ]
            with self.subTest(missing_kind=missing_kind):
                with self.assertRaises(ContractError):
                    build_experiment_run_receipt(**values)

        duplicate = receipt_values(forward)
        duplicate["policy_refs"].append({
            "policy_kind": "evaluation",
            "policy_version": "1.0.0",
            "policy_fingerprint": SHA_2,
        })
        with self.assertRaises(ContractError):
            build_experiment_run_receipt(**duplicate)

        reversed_policies = receipt_values(forward)
        reversed_policies["policy_refs"].reverse()
        self.assertEqual(
            build_experiment_run_receipt(**receipt_values(forward))["run_id"],
            build_experiment_run_receipt(**reversed_policies)["run_id"],
        )

    def test_price_outcome_run_requires_market_universe_and_adjustment_evidence(self):
        forward = finalize_result("ForwardOutcome", forward_values())
        for missing_role, stable_id in (
            ("market", MARKET),
            ("universe", UNIVERSE),
        ):
            values = receipt_values(forward)
            values["input_refs"] = [
                item for item in values["input_refs"] if item["id"] != stable_id
            ]
            with self.subTest(missing_role=missing_role):
                with self.assertRaises(ContractError):
                    build_experiment_run_receipt(**values)
        missing_adjustment = receipt_values(forward)
        missing_adjustment["policy_refs"] = [
            item for item in missing_adjustment["policy_refs"]
            if item["policy_kind"] != "adjustment"
        ]
        with self.assertRaises(ContractError):
            build_experiment_run_receipt(**missing_adjustment)

    def test_result_identity_binds_run_market_and_upstream_evidence(self):
        base = finalize_result("ForwardOutcome", forward_values())
        changes = []
        for field, value in (
            ("run_id", "experiment-run:sha256:" + "e" * 64),
            ("signal_market_snapshot_id", "market:sha256:" + "e" * 64),
            ("market_data_fingerprint", "sha256:" + "e" * 64),
            ("event_content_fingerprint", "sha256:" + "e" * 64),
        ):
            values = forward_values()
            values[field] = value
            changes.append(finalize_result("ForwardOutcome", values))
        for changed in changes:
            self.assertNotEqual(
                base["forward_outcome_id"], changed["forward_outcome_id"]
            )
            self.assertNotEqual(
                base["input_fingerprint"], changed["input_fingerprint"]
            )

        trade = finalize_result("TradeOutcome", trade_values())
        changed_trade = trade_values()
        changed_trade["market_data_fingerprint"] = "sha256:" + "e" * 64
        changed_trade = finalize_result("TradeOutcome", changed_trade)
        self.assertNotEqual(trade["trade_outcome_id"], changed_trade["trade_outcome_id"])

    def test_invalid_run_and_forged_input_fingerprint_fail(self):
        invalid = forward_values()
        invalid["run_id"] = "not-a-run-id"
        with self.assertRaises(ContractError):
            finalize_result("ForwardOutcome", invalid)
        forged = forward_values()
        forged["input_fingerprint"] = SHA
        with self.assertRaises(ContractError):
            finalize_result("ForwardOutcome", forged)
        valid = forward_values()
        outcome = finalize_result("ForwardOutcome", valid)
        self.assertEqual(
            outcome["input_fingerprint"],
            result_input_fingerprint("ForwardOutcome", outcome),
        )

    def test_unknown_top_level_fields_fail_for_all_five_contracts(self):
        forward = finalize_result("ForwardOutcome", forward_values())
        trade = finalize_result("TradeOutcome", trade_values())
        candidates = (
            ("ForwardOutcome", forward_values()),
            ("TradeOutcome", trade_values()),
            ("PortfolioRun", portfolio_values(trade)),
            ("ResearchAggregate", aggregate_values(forward)),
        )
        for contract_name, values in candidates:
            values["unexpected"] = "not-approved"
            with self.subTest(contract_name=contract_name):
                with self.assertRaises(ContractError):
                    finalize_result(contract_name, values)
        receipt = receipt_values(forward)
        receipt["unexpected"] = "not-approved"
        with self.assertRaises(ContractError):
            build_experiment_run_receipt(**receipt)

    def test_unknown_nested_fields_fail(self):
        forward = forward_values()
        forward["entry"]["vendor_note"] = "not-approved"
        with self.assertRaises(ContractError):
            finalize_result("ForwardOutcome", forward)
        trade = trade_values()
        trade["execution_policy"]["method"] = "not-approved"
        with self.assertRaises(ContractError):
            finalize_result("TradeOutcome", trade)
        valid_forward = finalize_result("ForwardOutcome", forward_values())
        receipt = receipt_values(valid_forward)
        receipt["config_ref"]["label"] = "not-approved"
        with self.assertRaises(ContractError):
            build_experiment_run_receipt(**receipt)

    def test_unimplemented_contracts_reject_renamed_metrics_and_market_rows(self):
        forward = finalize_result("ForwardOutcome", forward_values())
        trade = finalize_result("TradeOutcome", trade_values())
        portfolio = portfolio_values(trade)
        portfolio["portfolio_return"] = 9.99
        with self.assertRaises(ContractError):
            finalize_result("PortfolioRun", portfolio)
        aggregate = aggregate_values(forward)
        aggregate["computed_metrics"] = {"mean_return": 0.42}
        with self.assertRaises(ContractError):
            finalize_result("ResearchAggregate", aggregate)
        aggregate = aggregate_values(forward)
        aggregate["ohlcv"] = [{"date": "2026-09-03", "close": 100.0}]
        with self.assertRaises(ContractError):
            finalize_result("ResearchAggregate", aggregate)

    def test_store_rejects_dangling_revision_without_creating_result_files(self):
        pending = finalize_result("ForwardOutcome", forward_values())
        orphan = finalize_result(
            "ForwardOutcome", mature_forward(pending["forward_outcome_id"])
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "m10"
            store = EvaluationShadowStore(root)
            with self.assertRaises(ContractError):
                store.write_result("ForwardOutcome", orphan)
            self.assertEqual([], list(root.rglob("*.json")))

    def test_store_rejects_fork_and_preserves_every_existing_byte(self):
        pending = finalize_result("ForwardOutcome", forward_values())
        partial = finalize_result(
            "ForwardOutcome", partial_forward(pending["forward_outcome_id"])
        )
        competing = finalize_result(
            "ForwardOutcome", mature_forward(pending["forward_outcome_id"])
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "m10"
            store = EvaluationShadowStore(root)
            store.write_result("ForwardOutcome", pending)
            store.write_result("ForwardOutcome", partial)
            before = {path: path.read_bytes() for path in root.rglob("*.json")}
            with self.assertRaises(ContractError):
                store.write_result("ForwardOutcome", competing)
            self.assertEqual(before, {path: path.read_bytes() for path in root.rglob("*.json")})

    def test_store_accepts_three_generations_and_chain_order_is_irrelevant(self):
        pending = finalize_result("ForwardOutcome", forward_values())
        partial = finalize_result(
            "ForwardOutcome", partial_forward(pending["forward_outcome_id"])
        )
        mature_values = mature_forward(partial["forward_outcome_id"])
        mature_values["as_of"] = "2026-09-10"
        mature_values["generated_at"] = "2026-09-10T22:00:00Z"
        mature = finalize_result("ForwardOutcome", mature_values)
        for order in itertools.permutations((pending, partial, mature)):
            self.assertEqual(
                mature["forward_outcome_id"],
                current_result("ForwardOutcome", order)["forward_outcome_id"],
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "m10"
            store = EvaluationShadowStore(root)
            for item in (pending, partial, mature):
                store.write_result("ForwardOutcome", item)
            self.assertEqual(3, len(list(root.rglob("*.json"))))
            self.assertEqual(
                store.write_result("ForwardOutcome", pending),
                store.write_result("ForwardOutcome", pending),
            )

    def test_store_rejects_cross_root_and_cross_path_revisions(self):
        pending = finalize_result("ForwardOutcome", forward_values())
        different_root = mature_forward(pending["forward_outcome_id"])
        different_root["event_id"] = "opportunity:sha256:" + "e" * 64
        different_root["event_content_fingerprint"] = "sha256:" + "e" * 64
        different_root = finalize_result("ForwardOutcome", different_root)
        cross_path = forward_values(
            role="comparison", path="legacy", biases=["legacy_membership"]
        )
        cross_path["supersedes_result_id"] = pending["forward_outcome_id"]
        cross_path = finalize_result("ForwardOutcome", cross_path)
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationShadowStore(Path(directory) / "m10")
            store.write_result("ForwardOutcome", pending)
            for invalid in (different_root, cross_path):
                with self.assertRaises(ContractError):
                    store.write_result("ForwardOutcome", invalid)

    def test_concurrent_children_cannot_create_two_chain_heads(self):
        pending = finalize_result("ForwardOutcome", forward_values())
        first = finalize_result(
            "ForwardOutcome", partial_forward(pending["forward_outcome_id"])
        )
        second = finalize_result(
            "ForwardOutcome", mature_forward(pending["forward_outcome_id"])
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "m10"
            store = EvaluationShadowStore(root)
            store.write_result("ForwardOutcome", pending)

            def attempt(item):
                try:
                    store.write_result("ForwardOutcome", item)
                    return "written"
                except ContractError:
                    return "rejected"

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(attempt, (first, second)))
            self.assertEqual(["rejected", "written"], sorted(outcomes))
            self.assertEqual(2, len(list(root.rglob("*.json"))))


if __name__ == "__main__":
    unittest.main()
