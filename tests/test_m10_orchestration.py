"""Fixed synthetic tests for the M10-E config and orchestration boundary."""

from __future__ import annotations

import json
import hashlib
import io
from decimal import Decimal
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
import unittest

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError
from services.evaluation import (
    EvaluationShadowStore,
    GitState,
    build_evaluation_query,
    build_export_config,
    build_research_run_checkpoint,
    build_research_run_config,
    current_experiment_run,
    current_research_run_checkpoint,
    load_research_run_config,
    market_snapshot_evidence_fingerprint,
    validate_formal_git_state,
    validate_research_run_config,
)
from services.evaluation.orchestration import (
    ORCHESTRATOR_ENGINE,
    _checkpoint,
    _orchestrator_pending,
    execute_research_run,
)
from services.evaluation.policies import (
    AGGREGATION_POLICY, EVALUATION_POLICY, FORWARD_WINDOW_POLICY, PARTITION_POLICY,
)
from services.contracts.policies import ADJUSTMENT_POLICY
from services.execution import EXIT_POLICY, advance_exit_state
from tests import test_m09_ledger as m09_fixtures
from tests import test_m10_aggregate as aggregate_fixtures
from tests import test_m10_baseline_evaluator as baseline_fixtures


SHA = "sha256:" + "a" * 64
COMMIT = "b" * 40


def ref(prefix="opportunity", digit="1"):
    return {"id": f"{prefix}:sha256:{digit * 64}", "content_fingerprint": SHA}


def policy(kind):
    return {"policy_kind": kind, "policy_version": "1.0.0", "policy_fingerprint": SHA}


def real_policy(kind, value):
    return {
        "policy_kind": kind,
        "policy_version": value.get("policy_version", value.get("version")),
        "policy_fingerprint": value.get(
            "policy_fingerprint", canonical_fingerprint(plain(value))
        ),
    }


def config_values(operation="forward_evaluation"):
    specifications = {
        "forward_evaluation": (
            "ForwardOutcome", "2.1.0", "m10-b-internal-1.1.0",
            ("sage-vista-internal-baseline", "1.0.0", "internal-1.0.0"),
            ["adjustment", "evaluation", "forward_window", "partition"], 5,
            [1, 5, 20, 60, 100],
        ),
        "trade_evaluation": (
            "TradeOutcome", "2.0.0", "m10-b-internal-1.1.0",
            ("sage-vista-internal-baseline", "1.0.0", "internal-1.0.0"),
            ["adjustment", "evaluation", "execution", "partition"], 1, [],
        ),
        "portfolio_boundary": (
            "PortfolioRun", "2.1.0", "m10-c-readonly-1.0.0",
            ("sage-vista-readonly-aggregate", "1.0.0", "shadow-1.0.0"),
            ["adjustment", "aggregation", "evaluation", "execution", "partition"], 1, [],
        ),
        "research_aggregate": (
            "ResearchAggregate", "2.1.0", "m10-c-readonly-1.0.0",
            ("sage-vista-readonly-aggregate", "1.0.0", "shadow-1.0.0"),
            ["adjustment", "aggregation", "evaluation", "forward_window", "partition"], 1, [],
        ),
    }
    contract, schema, source, engine, policies, count, windows = specifications[operation]
    selection = [] if operation in {"portfolio_boundary", "research_aggregate"} else [ref()]
    execution = [ref("plan", "2"), ref("exit-state", "3")] if operation == "trade_evaluation" else []
    input_ref = (
        ref("trade-outcome", "4") if operation == "portfolio_boundary"
        else ref("forward-outcome", "5") if operation == "research_aggregate"
        else ref()
    )
    return {
        "schema_version": "2.0.0",
        "source_version": {"evaluation_contracts": "m10-e-cli-1.0.0"},
        "operation_type": operation,
        "as_of": "2026-09-05",
        "evidence_window": {"start": "2026-09-01", "end": "2026-09-05"},
        "path_status": "formal", "result_role": "authoritative",
        "partition_role": "forward", "bias_labels": [],
        "universe_ref": ref("universe", "6") if operation in {"forward_evaluation", "trade_evaluation"} else None,
        "market_snapshot_ref": ref("market", "7") if operation in {"forward_evaluation", "trade_evaluation"} else None,
        "adjustment_policy_ref": (
            ref("policy", "8")
            if operation in {"forward_evaluation", "trade_evaluation"} else None
        ),
        "selection_refs": selection,
        "execution_refs": execution,
        "input_selector": {
            "mode": "bundle", "refs": [input_ref],
            "bundle_path": "/tmp/m10-e-input.json", "bundle_sha256": SHA,
            "query": None,
        },
        "policy_refs": [policy(item) for item in reversed(policies)],
        "engine": {"name": engine[0], "version": engine[1], "adapter_version": engine[2]},
        "producer_source_version": source,
        "output_contract": {"name": contract, "schema_version": schema, "source_version": source},
        "storage": {"root_kind": "temporary", "root_path": "/tmp/m10-e-store"},
        "export_plan": {"enabled": False, "query": None, "config": None, "formats": [], "output_root": None},
        "resume": {"mode": "fresh", "parent_run_id": None, "checkpoint_ref": None},
        "work_units": [{
            "work_unit_id": "unit-1", "start": "2026-09-01", "end": "2026-09-05",
            "input_refs": [input_ref],
        }],
        "expected_results": {
            "contract": contract, "schema_version": schema,
            "source_version": source, "per_work_unit_count": count,
            "forward_windows": windows,
            "source_result_contract": (
                "TradeOutcome" if operation == "portfolio_boundary"
                else "ForwardOutcome" if operation == "research_aggregate"
                else None
            ),
        },
        "code_commit": COMMIT,
    }


def plain(value):
    if hasattr(value, "items"):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


class M10EConfigTests(unittest.TestCase):
    def test_all_four_single_family_configs_validate(self):
        for operation in (
            "forward_evaluation", "trade_evaluation",
            "portfolio_boundary", "research_aggregate",
        ):
            config = build_research_run_config(**config_values(operation))
            validate_research_run_config(config)
            self.assertEqual(config["operation_type"], operation)

    def test_config_identity_is_order_independent_for_sets(self):
        values = config_values()
        first = build_research_run_config(**values)
        values["policy_refs"].reverse()
        values["selection_refs"] = [ref("opportunity", "9"), ref()]
        second = build_research_run_config(**values)
        values["selection_refs"].reverse()
        third = build_research_run_config(**values)
        self.assertNotEqual(first["config_id"], second["config_id"])
        self.assertEqual(second["config_id"], third["config_id"])

    def test_semantic_change_changes_identity_and_old_identity_fails(self):
        original = build_research_run_config(**config_values())
        values = config_values()
        values["as_of"] = "2026-09-06"
        changed = build_research_run_config(**values)
        self.assertNotEqual(original["config_id"], changed["config_id"])
        tampered = plain(changed)
        tampered["config_id"] = original["config_id"]
        with self.assertRaises(ContractError):
            validate_research_run_config(tampered)

    def test_each_mutable_orchestration_fact_changes_config_identity(self):
        baseline = build_research_run_config(**config_values())
        variants = []
        values = config_values()
        values["code_commit"] = "c" * 40
        variants.append(values)
        values = config_values()
        values["storage"]["root_path"] = "/tmp/m10-e-other-store"
        variants.append(values)
        values = config_values()
        values["policy_refs"][0]["policy_fingerprint"] = "sha256:" + "b" * 64
        variants.append(values)
        values = config_values()
        values["input_selector"]["bundle_sha256"] = "sha256:" + "b" * 64
        variants.append(values)
        values = config_values()
        values["work_units"][0]["start"] = "2026-09-02"
        variants.append(values)
        identities = {
            build_research_run_config(**item)["config_id"] for item in variants
        }
        self.assertEqual(len(identities), len(variants))
        self.assertNotIn(baseline["config_id"], identities)

    def test_work_unit_order_is_semantic(self):
        values = config_values()
        second = plain(values["work_units"][0])
        second["work_unit_id"] = "unit-2"
        second["input_refs"] = [ref("opportunity", "9")]
        values["work_units"] = [values["work_units"][0], second]
        values["input_selector"]["refs"] = [ref(), ref("opportunity", "9")]
        first = build_research_run_config(**values)
        values["work_units"].reverse()
        other = build_research_run_config(**values)
        self.assertNotEqual(first["config_id"], other["config_id"])

    def test_strict_json_rejects_duplicate_keys_and_non_finite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"schema_version":"2.0.0","schema_version":"2.0.0"}', encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "duplicate key"):
                load_research_run_config(path)
            path.write_text('{"value":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "non-finite"):
                load_research_run_config(path)

    def test_strict_json_round_trip(self):
        config = build_research_run_config(**config_values())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(plain(config), sort_keys=True), encoding="utf-8")
            loaded = load_research_run_config(path)
        self.assertEqual(plain(config), plain(loaded))

    def test_unknown_dynamic_and_multiple_family_requests_fail(self):
        for field, value in (("operation_type", "latest"), ("as_of", "today")):
            values = config_values()
            values[field] = value
            with self.assertRaises(ContractError):
                build_research_run_config(**values)
        values = config_values()
        values["operation_type"] = ["forward_evaluation", "trade_evaluation"]
        with self.assertRaises(ContractError):
            build_research_run_config(**values)

    def test_legacy_or_wrong_contract_source_fails(self):
        for field, value in (
            ("path_status", "legacy"),
            ("producer_source_version", "m10-b-internal-1.0.0"),
        ):
            values = config_values()
            values[field] = value
            with self.assertRaises(ContractError):
                build_research_run_config(**values)

    def test_integer_fields_reject_coercible_and_boolean_values(self):
        for invalid in (True, False, 1.0, "1", Decimal("1")):
            values = config_values()
            values["expected_results"]["per_work_unit_count"] = invalid
            with self.subTest(field="per_work_unit_count", value=repr(invalid)):
                with self.assertRaises(ContractError):
                    build_research_run_config(**values)

    def test_interrupt_limit_rejects_non_integer_values(self):
        with tempfile.TemporaryDirectory() as directory:
            work, refs = forward_work()
            config = runtime_config("forward_evaluation", directory, [work], [refs])
            for invalid in (True, False, 1.0, "1", Decimal("1")):
                with self.subTest(value=repr(invalid)):
                    with self.assertRaises(ContractError):
                        execute_research_run(
                            config,
                            repo_root=ROOT,
                            git_state_provider=lambda _: GitState(COMMIT, True, True),
                            interrupt_after_work_units=invalid,
                        )
            values = config_values()
            values["expected_results"]["forward_windows"] = [1, 5, invalid, 60, 100]
            with self.subTest(field="forward_windows", value=repr(invalid)):
                with self.assertRaises(ContractError):
                    build_research_run_config(**values)

    def test_wrong_policy_set_and_unknown_field_fail(self):
        values = config_values()
        values["policy_refs"].append(policy("banana"))
        with self.assertRaises(ContractError):
            build_research_run_config(**values)
        built = plain(build_research_run_config(**config_values()))
        built["latest"] = True
        with self.assertRaises(ContractError):
            validate_research_run_config(built)

    def test_aggregate_source_family_is_explicit_and_changes_identity(self):
        original = build_research_run_config(**config_values("research_aggregate"))
        values = config_values("research_aggregate")
        values["expected_results"]["source_result_contract"] = "TradeOutcome"
        values["policy_refs"] = [
            item for item in values["policy_refs"]
            if item["policy_kind"] != "forward_window"
        ] + [policy("execution")]
        changed = build_research_run_config(**values)
        self.assertNotEqual(original["config_id"], changed["config_id"])
        values["expected_results"]["source_result_contract"] = "PortfolioRun"
        with self.assertRaises(ContractError):
            build_research_run_config(**values)

    def test_enabled_export_plan_revalidates_query_config_and_formats(self):
        values = config_values()
        query = build_evaluation_query(
            filters={"result_contracts": ["ForwardOutcome"]},
            revision_mode="current",
        )
        export = build_export_config(formats=("csv",))
        values["export_plan"] = {
            "enabled": True,
            "query": plain(query),
            "config": plain(export),
            "formats": ["csv"],
            "output_root": "/tmp/m10-e-export",
        }
        validate_research_run_config(build_research_run_config(**values))
        values["export_plan"]["formats"] = ["csv", "xlsx"]
        with self.assertRaises(ContractError):
            build_research_run_config(**values)

    def test_git_state_is_injected_and_strict(self):
        config = build_research_run_config(**config_values())
        validate_formal_git_state(
            config, repo_root=".",
            state_provider=lambda _: GitState(COMMIT, True, True),
        )
        for state in (
            GitState("c" * 40, True, True),
            GitState(COMMIT, False, True),
            GitState(COMMIT, True, False),
        ):
            with self.assertRaises(ContractError):
                validate_formal_git_state(
                    config, repo_root=".", state_provider=lambda _, item=state: item
                )


def write_bundle(directory, operation, work_items, input_refs):
    payload = {
        "schema_version": "1.0.0", "operation_type": operation,
        "input_refs": sorted(input_refs, key=lambda item: item["id"]),
        "work_items": work_items,
    }
    path = Path(directory) / f"{operation}-inputs.json"
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(raw)
    return path, "sha256:" + hashlib.sha256(raw).hexdigest()


def runtime_config(operation, directory, work_items, work_refs):
    all_refs = sorted(
        {item["id"]: item for refs in work_refs for item in refs}.values(),
        key=lambda item: item["id"],
    )
    path, digest = write_bundle(directory, operation, work_items, all_refs)
    values = config_values(operation)
    values["as_of"] = "2026-09-09"
    values["evidence_window"] = {"start": "2026-08-31", "end": "2026-09-09"}
    values["selection_refs"] = (
        [item for item in all_refs if item["id"].startswith("opportunity:")]
        if operation in {"forward_evaluation", "trade_evaluation"}
        else []
    )
    values["execution_refs"] = [
        item for item in all_refs
        if item["id"].startswith(("plan:", "exit-state:", "machine-link:"))
    ] if operation == "trade_evaluation" else []
    values["input_selector"] = {
        "mode": "bundle", "refs": all_refs, "bundle_path": str(path),
        "bundle_sha256": digest, "query": None,
    }
    values["work_units"] = [
        {"work_unit_id": item["work_unit_id"], "start": "2026-08-31",
         "end": "2026-09-09", "input_refs": refs}
        for item, refs in zip(work_items, work_refs)
    ]
    if operation in {"forward_evaluation", "trade_evaluation"}:
        values["universe_ref"] = next(
            item for item in all_refs if item["id"].startswith("universe:")
        )
        values["market_snapshot_ref"] = next(
            item for item in all_refs if item["id"].startswith("market:")
        )
        adjustment_fingerprint = canonical_fingerprint(ADJUSTMENT_POLICY)
        values["adjustment_policy_ref"] = {
            "id": "policy:" + adjustment_fingerprint,
            "content_fingerprint": adjustment_fingerprint,
        }
    common = [
        real_policy("adjustment", ADJUSTMENT_POLICY),
        real_policy("evaluation", EVALUATION_POLICY),
        real_policy("partition", PARTITION_POLICY),
    ]
    if operation == "forward_evaluation":
        common.append(real_policy("forward_window", FORWARD_WINDOW_POLICY))
    elif operation == "trade_evaluation":
        common.append(real_policy("execution", EXIT_POLICY))
    else:
        common.append(real_policy("aggregation", AGGREGATION_POLICY))
        if operation == "portfolio_boundary":
            scope = work_items[0]["arguments"]["scope"]
            common.append({
                "policy_kind": "execution",
                "policy_version": scope["execution_policy_version"],
                "policy_fingerprint": scope["execution_policy_fingerprint"],
            })
        else:
            common.append(real_policy("forward_window", FORWARD_WINDOW_POLICY))
    values["policy_refs"] = common
    values["storage"] = {
        "root_kind": "temporary", "root_path": str(Path(directory) / "store")
    }
    return build_research_run_config(**values)


def forward_work():
    baseline_fixtures.M10ForwardBaselineTests.setUpClass()
    fixture = baseline_fixtures.M10ForwardBaselineTests()
    _, read, snapshot, calendar, _ = fixture.produce(elapsed=5)
    arguments = {
        "event": plain(fixture.event),
        "market_read": {
            "instrument_id": read.instrument_id, "as_of": read.as_of,
            "rows": plain(read.rows),
            "point_in_time_fingerprint": read.point_in_time_fingerprint,
        },
        "market_snapshot": plain(snapshot), "session_calendar": plain(calendar),
        "universe_content_fingerprint": baseline_fixtures.UNIVERSE_CONTENT,
    }
    refs = [
        {"id": fixture.event["event_id"], "content_fingerprint": fixture.event["event_content_fingerprint"]},
        {"id": snapshot["snapshot_id"], "content_fingerprint": baseline_fixtures.market_snapshot_evidence_fingerprint(snapshot)},
        {"id": fixture.event["input_identity"]["universe_id"], "content_fingerprint": baseline_fixtures.UNIVERSE_CONTENT},
        {"id": calendar["calendar_id"], "content_fingerprint": calendar["content_fingerprint"]},
    ]
    return {"work_unit_id": "forward-1", "arguments": arguments}, sorted(refs, key=lambda item: item["id"])


def portfolio_works(outcomes):
    works, refs = [], []
    for index, outcome in enumerate(outcomes, 1):
        scope = aggregate_fixtures.trade_scope(outcome)
        reference = {
            "id": outcome["trade_outcome_id"],
            "content_fingerprint": outcome["trade_content_fingerprint"],
        }
        works.append({
            "work_unit_id": f"portfolio-{index}",
            "arguments": {"trade_outcomes": [plain(outcome)], "scope": plain(scope)},
        })
        refs.append([reference])
    return works, refs


def aggregate_work(outcome=None, *, work_unit_id="aggregate-1"):
    outcome = outcome or aggregate_fixtures.forward("9", gross=0.125)
    scope = aggregate_fixtures.forward_scope(window=outcome["window_sessions"])
    reference = {
        "id": outcome["forward_outcome_id"],
        "content_fingerprint": outcome["forward_content_fingerprint"],
    }
    return {
        "work_unit_id": work_unit_id,
        "arguments": {"outcomes": [plain(outcome)], "scope": plain(scope)},
    }, [reference]


def trade_work():
    baseline_fixtures.M10TradeBaselineTests.setUpClass()
    fixture = baseline_fixtures.M10TradeBaselineTests()
    bar = fixture.safe_bar(fixture.plan["entry_date"])
    bar["high"] = fixture.plan["target"]["price"] + 1
    state = advance_exit_state(
        fixture.plan,
        completed_bars=[bar],
        generated_at=m09_fixtures.ENTRY_GENERATED_AT,
    )
    _, read, snapshot, _, state_link = fixture.evaluate(
        (state,), (bar,), attempt="m10-e-trade-fixture"
    )
    arguments = {
        "event": plain(fixture.event),
        "trade_plan_link": plain(fixture.plan_link),
        "trade_plan": plain(fixture.plan),
        "exit_states": [plain(state)],
        "exit_state_link": plain(state_link),
        "market_read": {
            "instrument_id": read.instrument_id,
            "as_of": read.as_of,
            "rows": plain(read.rows),
            "point_in_time_fingerprint": read.point_in_time_fingerprint,
        },
        "market_snapshot": plain(snapshot),
        "universe_content_fingerprint": baseline_fixtures.UNIVERSE_CONTENT,
    }
    refs = [
        {"id": fixture.event["event_id"], "content_fingerprint": fixture.event["event_content_fingerprint"]},
        {"id": snapshot["snapshot_id"], "content_fingerprint": market_snapshot_evidence_fingerprint(snapshot)},
        {"id": fixture.event["input_identity"]["universe_id"], "content_fingerprint": baseline_fixtures.UNIVERSE_CONTENT},
        {"id": fixture.plan_link["link_id"], "content_fingerprint": fixture.plan_link["link_content_fingerprint"]},
        {"id": fixture.plan["plan_id"], "content_fingerprint": fixture.plan["plan_content_fingerprint"]},
        {"id": state["exit_state_id"], "content_fingerprint": state["exit_state_content_fingerprint"]},
        {"id": state_link["link_id"], "content_fingerprint": state_link["link_content_fingerprint"]},
    ]
    return {"work_unit_id": "trade-1", "arguments": arguments}, sorted(
        refs, key=lambda item: item["id"]
    )


class M10EOrchestrationTests(unittest.TestCase):
    def state(self, _):
        return GitState(COMMIT, True, True)

    def run_forward_source(self, directory):
        work, refs = forward_work()
        config = runtime_config("forward_evaluation", directory, [work], [refs])
        result = execute_research_run(
            config, repo_root=ROOT, git_state_provider=self.state,
            clock=lambda: "2026-09-09T22:40:00Z",
        )
        self.assertEqual(result.exit_code, 0)
        inventory = EvaluationShadowStore(
            Path(directory) / "store", workspace_root=ROOT
        ).capture_inventory()
        return sorted(
            [payload for contract, payload in inventory.result_records
             if contract == "ForwardOutcome"],
            key=lambda item: item["window_sessions"],
        )

    def run_trade_source(self, directory):
        work, refs = trade_work()
        config = runtime_config("trade_evaluation", directory, [work], [refs])
        result = execute_research_run(
            config, repo_root=ROOT, git_state_provider=self.state,
            clock=lambda: "2026-09-09T22:45:00Z",
        )
        self.assertEqual(result.exit_code, 0)
        inventory = EvaluationShadowStore(
            Path(directory) / "store", workspace_root=ROOT
        ).capture_inventory()
        return [payload for contract, payload in inventory.result_records
                if contract == "TradeOutcome"]

    def store_bytes(self, directory):
        root = Path(directory) / "store"
        return {
            path.relative_to(root): path.read_bytes()
            for path in root.rglob("*") if path.is_file()
        }

    def test_naked_m10c_sources_fail_before_any_orchestrator_evidence(self):
        cases = (
            ("research_aggregate", aggregate_work()),
            ("portfolio_boundary", portfolio_works([
                aggregate_fixtures.trade("8", gross=0.2)
            ])),
        )
        for operation, pair in cases:
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                if operation == "research_aggregate":
                    works, refs = [pair[0]], [pair[1]]
                else:
                    works, refs = pair
                config = runtime_config(operation, directory, works, refs)
                with self.assertRaisesRegex(ContractError, "not uniquely persisted"):
                    execute_research_run(
                        config, repo_root=ROOT, git_state_provider=self.state
                    )
                self.assertFalse((Path(directory) / "store").exists())

    def test_persisted_m10c_sources_allow_portfolio_and_aggregate(self):
        with tempfile.TemporaryDirectory() as directory:
            trade_sources = self.run_trade_source(directory)
            works, refs = portfolio_works(trade_sources)
            portfolio = execute_research_run(
                runtime_config("portfolio_boundary", directory, works, refs),
                repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:00:00Z",
            )
            forward = self.run_forward_source(directory)[1]
            aggregate, aggregate_refs = aggregate_work(forward)
            research = execute_research_run(
                runtime_config(
                    "research_aggregate", directory, [aggregate], [aggregate_refs]
                ),
                repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:10:00Z",
            )
            self.assertEqual(portfolio.exit_code, 0)
            self.assertEqual(research.exit_code, 0)

    def test_m10c_bundle_copy_must_equal_the_persisted_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.run_forward_source(directory)[1]
            changed = plain(source)
            changed["generated_at"] = "2026-09-09T23:59:00Z"
            work, refs = aggregate_work(changed)
            config = runtime_config(
                "research_aggregate", directory, [work], [refs]
            )
            before = self.store_bytes(directory)
            with self.assertRaises(ContractError):
                execute_research_run(
                    config, repo_root=ROOT, git_state_provider=self.state
                )
            self.assertEqual(before, self.store_bytes(directory))

    def test_saved_forward_results_are_reconciled_after_producer_raises(self):
        import services.evaluation.orchestration as module

        with tempfile.TemporaryDirectory() as directory:
            work, refs = forward_work()
            config = runtime_config("forward_evaluation", directory, [work], [refs])
            original = module.store_baseline_evaluation_batch

            def save_then_raise(*args, **kwargs):
                original(*args, **kwargs)
                raise RuntimeError("injected after durable producer write")

            with patch.object(module, "store_baseline_evaluation_batch", save_then_raise):
                result = execute_research_run(
                    config, repo_root=ROOT, git_state_provider=self.state,
                    clock=lambda: "2026-09-09T23:00:00Z",
                )
            store = EvaluationShadowStore(
                Path(directory) / "store", workspace_root=ROOT
            )
            state = store.reconcile_m10e_run(config, result.summary["run_id"])
            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.summary["status"], "failed")
            self.assertEqual(result.summary["completed_result_count"], 5)
            self.assertEqual(len(state["result_refs"]), 5)
            self.assertEqual(state["run_status"], "failed")

    def test_checkpoint_write_failure_uses_disk_state_and_does_not_fork(self):
        with tempfile.TemporaryDirectory() as directory:
            work, refs = forward_work()
            config = runtime_config("forward_evaluation", directory, [work], [refs])
            original = EvaluationShadowStore.write_checkpoint
            calls = {"failed": False}

            def fail_once(store, payload):
                if not calls["failed"]:
                    calls["failed"] = True
                    raise OSError("injected checkpoint failure")
                return original(store, payload)

            with patch.object(EvaluationShadowStore, "write_checkpoint", fail_once):
                result = execute_research_run(
                    config, repo_root=ROOT, git_state_provider=self.state,
                    clock=lambda: "2026-09-09T23:00:00Z",
                )
            inventory = EvaluationShadowStore(
                Path(directory) / "store", workspace_root=ROOT
            ).capture_inventory()
            chain = [item for item in inventory.checkpoints
                     if item["run_id"] == result.summary["run_id"]]
            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.summary["completed_result_count"], 5)
            self.assertEqual(len(chain), 1)
            self.assertEqual(chain[0]["status"], "ready_to_finalize")

    def test_completed_receipt_failure_once_records_truthful_failed_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            work, refs = forward_work()
            config = runtime_config("forward_evaluation", directory, [work], [refs])
            original = EvaluationShadowStore.write_run_receipt
            calls = {"failed": False}

            def fail_completed_once(store, payload):
                if (
                    payload["engine"]["name"] == ORCHESTRATOR_ENGINE["name"]
                    and payload["status"] == "completed"
                    and not calls["failed"]
                ):
                    calls["failed"] = True
                    raise OSError("injected completed receipt failure")
                return original(store, payload)

            with patch.object(
                EvaluationShadowStore, "write_run_receipt", fail_completed_once
            ):
                result = execute_research_run(
                    config, repo_root=ROOT, git_state_provider=self.state,
                    clock=lambda: "2026-09-09T23:00:00Z",
                )
            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.summary["status"], "failed")
            self.assertTrue(result.summary["terminal_persisted"])
            self.assertEqual(result.summary["completed_result_count"], 5)

    def test_unwritable_terminal_stays_pending_and_retry_only_finalizes(self):
        import services.evaluation.orchestration as module

        with tempfile.TemporaryDirectory() as directory:
            work, refs = forward_work()
            config = runtime_config("forward_evaluation", directory, [work], [refs])
            original = EvaluationShadowStore.write_run_receipt

            def reject_terminal(store, payload):
                if (
                    payload["engine"]["name"] == ORCHESTRATOR_ENGINE["name"]
                    and payload["status"] != "pending"
                ):
                    raise OSError("injected terminal storage outage")
                return original(store, payload)

            with patch.object(EvaluationShadowStore, "write_run_receipt", reject_terminal):
                first = execute_research_run(
                    config, repo_root=ROOT, git_state_provider=self.state,
                    clock=lambda: "2026-09-09T23:00:00Z",
                )
            self.assertEqual(first.exit_code, 2)
            self.assertEqual(first.summary["status"], "pending")
            self.assertFalse(first.summary["terminal_persisted"])
            self.assertEqual(first.summary["completed_result_count"], 5)
            with patch.object(
                module, "_execute_work_unit",
                side_effect=AssertionError("completed work was rerun"),
            ):
                def retry():
                    return execute_research_run(
                        config, repo_root=ROOT, git_state_provider=self.state,
                        clock=lambda: "2026-09-09T23:10:00Z",
                    )
                with ThreadPoolExecutor(max_workers=2) as pool:
                    retried = list(pool.map(lambda _: retry(), range(2)))
            self.assertEqual([item.exit_code for item in retried], [0, 0])
            self.assertEqual(
                {item.summary["status"] for item in retried}, {"completed"}
            )
            self.assertEqual(
                {item.summary["completed_result_count"] for item in retried}, {5}
            )
            inventory = EvaluationShadowStore(
                Path(directory) / "store", workspace_root=ROOT
            ).capture_inventory()
            run_chain = [
                item for item in inventory.run_receipts
                if item["run_id"] == first.summary["run_id"]
            ]
            self.assertEqual(len(run_chain), 2)
            self.assertEqual(current_experiment_run(run_chain)["status"], "completed")

    def test_forward_uses_existing_producer_and_replay_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            work, refs = forward_work()
            config = runtime_config("forward_evaluation", directory, [work], [refs])
            first = execute_research_run(
                config, repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:00:00Z",
            )
            second = execute_research_run(
                config, repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:10:00Z",
            )
            self.assertEqual(first.exit_code, 0)
            self.assertEqual(first.summary["run_id"], second.summary["run_id"])
            self.assertEqual(first.summary["completed_result_count"], 5)

    def test_daily_and_partitioned_labels_keep_identical_outcome_facts(self):
        with tempfile.TemporaryDirectory() as daily_dir, tempfile.TemporaryDirectory() as replay_dir:
            daily_work, daily_refs = forward_work()
            daily = runtime_config(
                "forward_evaluation", daily_dir, [daily_work], [daily_refs]
            )
            replay_work, replay_refs = forward_work()
            replay_work["work_unit_id"] = "replay-partition-001"
            replay = runtime_config(
                "forward_evaluation", replay_dir, [replay_work], [replay_refs]
            )
            for config in (daily, replay):
                execute_research_run(
                    config, repo_root=ROOT, git_state_provider=self.state,
                    clock=lambda: "2026-09-09T23:00:00Z",
                )
            def forward_facts(directory):
                inventory = EvaluationShadowStore(
                    Path(directory) / "store", workspace_root=ROOT
                ).capture_inventory()
                return sorted(
                    (
                        result["forward_outcome_id"],
                        result["forward_content_fingerprint"],
                    )
                    for contract, result in inventory.result_records
                    if contract == "ForwardOutcome"
                )
            self.assertEqual(forward_facts(daily_dir), forward_facts(replay_dir))

    def test_aggregate_interrupt_checkpoint_and_explicit_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            sources = self.run_forward_source(directory)[:2]
            pairs = [
                aggregate_work(item, work_unit_id=f"aggregate-{index}")
                for index, item in enumerate(sources, 1)
            ]
            works, refs = [item[0] for item in pairs], [item[1] for item in pairs]
            config = runtime_config("research_aggregate", directory, works, refs)
            interrupted = execute_research_run(
                config, repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:00:00Z",
                interrupt_after_work_units=1,
            )
            self.assertEqual(interrupted.exit_code, 130)
            self.assertEqual(interrupted.summary["completed_result_count"], 1)
            values = plain(config)
            for field in ("config_id", "config_content_fingerprint"):
                values.pop(field)
            values["resume"] = {
                "mode": "checkpoint", "parent_run_id": interrupted.summary["run_id"],
                "checkpoint_ref": {
                    "id": interrupted.summary["checkpoint_id"],
                    "content_fingerprint": "sha256:" + interrupted.summary["checkpoint_id"].rsplit(":", 1)[-1],
                },
            }
            resumed_config = build_research_run_config(**values)
            resumed = execute_research_run(
                resumed_config, repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:30:00Z",
            )
            self.assertEqual(resumed.exit_code, 0)
            self.assertEqual(resumed.summary["completed_result_count"], 2)

    def test_concurrent_same_config_has_one_authoritative_run(self):
        with tempfile.TemporaryDirectory() as directory:
            work, refs = forward_work()
            config = runtime_config("forward_evaluation", directory, [work], [refs])
            def run():
                return execute_research_run(
                    config, repo_root=ROOT, git_state_provider=self.state,
                    clock=lambda: "2026-09-09T23:00:00Z",
                )
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: run(), range(2)))
            self.assertEqual({item.summary["run_id"] for item in results}, {results[0].summary["run_id"]})
            self.assertEqual([item.exit_code for item in results], [0, 0])

    def test_cli_stdout_is_one_json_document(self):
        from research import run as cli
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            work, refs = forward_work()
            config = runtime_config("forward_evaluation", directory, [work], [refs])
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(plain(config), sort_keys=True), encoding="utf-8")
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(cli, "current_git_state", self.state), redirect_stdout(stdout), redirect_stderr(stderr):
                code = cli.main(["--config", str(path)])
            self.assertEqual(code, 0)
            self.assertEqual(len(stdout.getvalue().splitlines()), 1)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "completed")
            self.assertEqual(stderr.getvalue(), "")

    def test_trade_and_aggregate_each_use_the_existing_single_family_producer(self):
        with tempfile.TemporaryDirectory() as directory:
            trade, trade_refs = trade_work()
            trade_config = runtime_config(
                "trade_evaluation", directory, [trade], [trade_refs]
            )
            trade_run = execute_research_run(
                trade_config, repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:00:00Z",
            )
            source = self.run_forward_source(directory)[1]
            aggregate, aggregate_refs = aggregate_work(source)
            aggregate_config = runtime_config(
                "research_aggregate", directory, [aggregate], [aggregate_refs]
            )
            aggregate_run = execute_research_run(
                aggregate_config, repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:10:00Z",
            )
            self.assertEqual(trade_run.exit_code, 0)
            self.assertEqual(aggregate_run.exit_code, 0)
            self.assertEqual(trade_run.summary["expected_result_count"], 1)
            self.assertEqual(aggregate_run.summary["expected_result_count"], 1)

    def test_query_selector_resolves_persisted_outcome_for_aggregate(self):
        with tempfile.TemporaryDirectory() as directory:
            work, refs = forward_work()
            forward_config = runtime_config(
                "forward_evaluation", directory, [work], [refs]
            )
            execute_research_run(
                forward_config, repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:00:00Z",
            )
            store = EvaluationShadowStore(
                Path(directory) / "store", workspace_root=ROOT
            )
            selected = next(
                result for contract, result in store.capture_inventory().result_records
                if contract == "ForwardOutcome" and result["window_sessions"] == 5
            )
            selected_ref = {
                "id": selected["forward_outcome_id"],
                "content_fingerprint": selected["forward_content_fingerprint"],
            }
            values = config_values("research_aggregate")
            values["as_of"] = "2026-09-09"
            values["evidence_window"] = {"start": "2026-08-31", "end": "2026-09-09"}
            values["storage"] = {
                "root_kind": "temporary", "root_path": str(Path(directory) / "store")
            }
            values["policy_refs"] = [
                real_policy("adjustment", ADJUSTMENT_POLICY),
                real_policy("aggregation", AGGREGATION_POLICY),
                real_policy("evaluation", EVALUATION_POLICY),
                real_policy("forward_window", FORWARD_WINDOW_POLICY),
                real_policy("partition", PARTITION_POLICY),
            ]
            values["input_selector"] = {
                "mode": "query", "refs": [], "bundle_path": None,
                "bundle_sha256": None,
                "query": plain(build_evaluation_query(
                    filters={
                        "result_contracts": ["ForwardOutcome"],
                        "window_sessions": [5],
                    },
                    revision_mode="current",
                )),
            }
            values["work_units"] = [{
                "work_unit_id": "query-aggregate-1",
                "start": "2026-08-31", "end": "2026-09-09",
                "input_refs": [selected_ref],
            }]
            config = build_research_run_config(**values)
            result = execute_research_run(
                config, repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:10:00Z",
            )
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.summary["input_count"], 1)
            self.assertEqual(result.summary["completed_result_count"], 1)

    def test_query_and_bundle_use_the_same_persisted_m10c_source(self):
        with tempfile.TemporaryDirectory() as bundle_dir, tempfile.TemporaryDirectory() as query_dir:
            source = self.run_forward_source(bundle_dir)[1]
            query_source = self.run_forward_source(query_dir)[1]
            self.assertEqual(
                source["forward_outcome_id"], query_source["forward_outcome_id"]
            )
            work, refs = aggregate_work(source)
            bundle_config = runtime_config(
                "research_aggregate", bundle_dir, [work], [refs]
            )
            bundle_run = execute_research_run(
                bundle_config, repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:10:00Z",
            )

            values = plain(runtime_config(
                "research_aggregate", query_dir,
                [aggregate_work(query_source)[0]],
                [aggregate_work(query_source)[1]],
            ))
            for field in ("config_id", "config_content_fingerprint"):
                values.pop(field)
            values["input_selector"] = {
                "mode": "query", "refs": [], "bundle_path": None,
                "bundle_sha256": None,
                "query": plain(build_evaluation_query(
                    filters={
                        "result_contracts": ["ForwardOutcome"],
                        "window_sessions": [5],
                    },
                    revision_mode="current",
                )),
            }
            query_config = build_research_run_config(**values)
            query_run = execute_research_run(
                query_config, repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:10:00Z",
            )
            bundle_state = EvaluationShadowStore(
                Path(bundle_dir) / "store", workspace_root=ROOT
            ).reconcile_m10e_run(bundle_config, bundle_run.summary["run_id"])
            query_state = EvaluationShadowStore(
                Path(query_dir) / "store", workspace_root=ROOT
            ).reconcile_m10e_run(query_config, query_run.summary["run_id"])
            self.assertEqual(
                [(item["id"], item["content_fingerprint"])
                 for item in bundle_state["result_refs"]],
                [(item["id"], item["content_fingerprint"])
                 for item in query_state["result_refs"]],
            )

    def test_bundle_hash_or_unknown_bundle_field_fails_before_pending(self):
        with tempfile.TemporaryDirectory() as directory:
            work, refs = forward_work()
            config = runtime_config("forward_evaluation", directory, [work], [refs])
            bundle_path = Path(config["input_selector"]["bundle_path"])
            bundle_path.write_bytes(bundle_path.read_bytes() + b" ")
            with self.assertRaisesRegex(ContractError, "bundle hash"):
                execute_research_run(
                    config, repo_root=ROOT, git_state_provider=self.state
                )
            self.assertFalse((Path(directory) / "store" / "runs").exists())

    def test_public_store_rejects_terminal_without_persisted_pending(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            work, refs = forward_work()
            config = runtime_config(
                "forward_evaluation", source_dir, [work], [refs]
            )
            completed = execute_research_run(
                config, repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:00:00Z",
            )
            source_store = EvaluationShadowStore(
                Path(source_dir) / "store", workspace_root=ROOT
            )
            receipt = next(
                item for item in source_store.capture_inventory().run_receipts
                if item["run_id"] == completed.summary["run_id"]
                and item["status"] == "completed"
            )
            target_store = EvaluationShadowStore(
                Path(target_dir) / "store", workspace_root=ROOT
            )
            with self.assertRaisesRegex(ContractError, "ResearchRunConfig"):
                target_store.write_run_receipt(receipt)
            self.assertFalse((Path(target_dir) / "store" / "runs").exists())

    def test_public_checkpoint_storage_rejects_unstored_results_and_bad_prior(self):
        with tempfile.TemporaryDirectory() as directory:
            work, refs = forward_work()
            config = runtime_config("forward_evaluation", directory, [work], [refs])
            store = EvaluationShadowStore(
                Path(directory) / "store", workspace_root=ROOT
            )
            pending = _orchestrator_pending(
                config, generated_at="2026-09-09T23:00:00Z"
            )
            store.write_research_config(config)
            store.write_run_receipt(pending)
            root = _checkpoint(
                config, pending, [], [], status="in_progress",
                generated_at="2026-09-09T23:01:00Z", prior=None,
            )
            store.write_checkpoint(root)
            forged_result = _checkpoint(
                config, pending, ["forward-1"],
                [
                    {"work_unit_id": "forward-1", **ref("forward-outcome", digit)}
                    for digit in "abcde"
                ],
                status="ready_to_finalize", generated_at="2026-09-09T23:02:00Z",
                prior=root,
            )
            with self.assertRaisesRegex(ContractError, "not present"):
                store.write_checkpoint(forged_result)
            bad_prior = build_research_run_checkpoint(**{
                **{
                    key: plain(value) for key, value in root.items()
                    if key not in {
                        "checkpoint_id", "checkpoint_content_fingerprint",
                        "supersedes_checkpoint_id", "generated_at",
                    }
                },
                "supersedes_checkpoint_id": "research-run-checkpoint:sha256:" + "e" * 64,
                "generated_at": "2026-09-09T23:03:00Z",
            })
            with self.assertRaisesRegex(ContractError, "unique current leaf"):
                store.write_checkpoint(bad_prior)
            self.assertEqual(current_research_run_checkpoint(store.capture_inventory().checkpoints), root)

    def test_changed_config_cannot_resume_a_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            sources = self.run_forward_source(directory)[:2]
            pairs = [
                aggregate_work(item, work_unit_id=f"aggregate-{index}")
                for index, item in enumerate(sources, 1)
            ]
            works, refs = [item[0] for item in pairs], [item[1] for item in pairs]
            config = runtime_config("research_aggregate", directory, works, refs)
            interrupted = execute_research_run(
                config, repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:00:00Z",
                interrupt_after_work_units=1,
            )
            values = plain(config)
            for field in ("config_id", "config_content_fingerprint"):
                values.pop(field)
            values["work_units"][0]["start"] = "2026-09-01"
            values["resume"] = {
                "mode": "checkpoint",
                "parent_run_id": interrupted.summary["run_id"],
                "checkpoint_ref": {
                    "id": interrupted.summary["checkpoint_id"],
                    "content_fingerprint": "sha256:" + interrupted.summary["checkpoint_id"].rsplit(":", 1)[-1],
                },
            }
            changed = build_research_run_config(**values)
            with self.assertRaisesRegex(ContractError, "resume evidence"):
                execute_research_run(
                    changed, repo_root=ROOT, git_state_provider=self.state
                )

    def test_export_failure_does_not_change_completed_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            work, refs = forward_work()
            values = plain(runtime_config(
                "forward_evaluation", directory, [work], [refs]
            ))
            for field in ("config_id", "config_content_fingerprint"):
                values.pop(field)
            values["export_plan"] = {
                "enabled": True,
                "query": plain(build_evaluation_query(
                    filters={"result_contracts": ["ForwardOutcome"]},
                    revision_mode="current",
                )),
                "config": plain(build_export_config(formats=("csv",))),
                "formats": ["csv"],
                "output_root": str(Path(directory) / "exports"),
            }
            config = build_research_run_config(**values)
            def fail_export(*args, **kwargs):
                raise OSError("injected export failure")
            result = execute_research_run(
                config, repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:00:00Z",
                export_publisher=fail_export,
            )
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.summary["status"], "completed")
            self.assertEqual(result.summary["export"]["status"], "failed")
            self.assertFalse((Path(directory) / "exports").exists())

    def test_producer_failure_appends_failed_checkpoint_and_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            work, refs = forward_work()
            del work["arguments"]["universe_content_fingerprint"]
            config = runtime_config("forward_evaluation", directory, [work], [refs])
            result = execute_research_run(
                config, repo_root=ROOT, git_state_provider=self.state,
                clock=lambda: "2026-09-09T23:00:00Z",
            )
            inventory = EvaluationShadowStore(
                Path(directory) / "store", workspace_root=ROOT
            ).capture_inventory()
            run_chain = [
                item for item in inventory.run_receipts
                if item["run_id"] == result.summary["run_id"]
            ]
            checkpoint_chain = [
                item for item in inventory.checkpoints
                if item["run_id"] == result.summary["run_id"]
            ]
            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.summary["status"], "failed")
            self.assertEqual(current_experiment_run(run_chain)["status"], "failed")
            self.assertEqual(
                current_research_run_checkpoint(checkpoint_chain)["status"], "in_progress"
            )

    def test_aggregate_mixed_result_families_fail_with_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            forward = self.run_forward_source(directory)[1]
            trade = self.run_trade_source(directory)[0]
            work, refs = aggregate_work(forward)
            work["arguments"]["outcomes"].append(plain(trade))
            refs.append({
                "id": trade["trade_outcome_id"],
                "content_fingerprint": trade["trade_content_fingerprint"],
            })
            refs.sort(key=lambda item: item["id"])
            config = runtime_config(
                "research_aggregate", directory, [work], [refs]
            )
            before = EvaluationShadowStore(
                Path(directory) / "store", workspace_root=ROOT
            ).capture_inventory()
            with self.assertRaises(ContractError):
                execute_research_run(
                    config, repo_root=ROOT, git_state_provider=self.state,
                    clock=lambda: "2026-09-09T23:00:00Z",
                )
            after = EvaluationShadowStore(
                Path(directory) / "store", workspace_root=ROOT
            ).capture_inventory()
            self.assertEqual(before, after)

    def test_checkpoint_graph_rejects_fork_and_cross_run(self):
        with tempfile.TemporaryDirectory() as directory:
            work, refs = forward_work()
            config = runtime_config("forward_evaluation", directory, [work], [refs])
            pending = _orchestrator_pending(
                config, generated_at="2026-09-09T23:00:00Z"
            )
            root = _checkpoint(
                config, pending, [], [], status="in_progress",
                generated_at="2026-09-09T23:01:00Z", prior=None,
            )
            child_a = _checkpoint(
                config, pending, [], [], status="in_progress",
                generated_at="2026-09-09T23:02:00Z", prior=root,
            )
            child_b = _checkpoint(
                config, pending, [], [], status="in_progress",
                generated_at="2026-09-09T23:03:00Z", prior=root,
            )
            with self.assertRaisesRegex(ContractError, "forks"):
                current_research_run_checkpoint([root, child_a, child_b])
            changed_values = plain(config)
            for field in ("config_id", "config_content_fingerprint"):
                changed_values.pop(field)
            changed_values["code_commit"] = "c" * 40
            changed = build_research_run_config(**changed_values)
            other_pending = _orchestrator_pending(
                changed, generated_at="2026-09-09T23:00:00Z"
            )
            other_root = _checkpoint(
                changed, other_pending, [], [], status="in_progress",
                generated_at="2026-09-09T23:01:00Z", prior=None,
            )
            with self.assertRaisesRegex(ContractError, "crosses runs"):
                current_research_run_checkpoint([root, other_root])


ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
