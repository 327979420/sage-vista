"""Fixed synthetic tests for the M10-E config and orchestration boundary."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError
from services.evaluation import (
    GitState,
    build_research_run_config,
    load_research_run_config,
    validate_formal_git_state,
    validate_research_run_config,
)


SHA = "sha256:" + "a" * 64
COMMIT = "b" * 40


def ref(prefix="opportunity", digit="1"):
    return {"id": f"{prefix}:sha256:{digit * 64}", "content_fingerprint": SHA}


def policy(kind):
    return {"policy_kind": kind, "policy_version": "1.0.0", "policy_fingerprint": SHA}


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
            ("sage-vista-m10c-readonly", "1.0.0", "readonly-1.0.0"),
            ["adjustment", "aggregation", "evaluation", "partition"], 1, [],
        ),
        "research_aggregate": (
            "ResearchAggregate", "2.1.0", "m10-c-readonly-1.0.0",
            ("sage-vista-m10c-readonly", "1.0.0", "readonly-1.0.0"),
            ["adjustment", "aggregation", "evaluation", "partition"], 1, [],
        ),
    }
    contract, schema, source, engine, policies, count, windows = specifications[operation]
    selection = [ref()]
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
        "adjustment_policy_ref": ref("policy", "8"),
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
        values["bias_labels"] = ["z", "a"]
        second = build_research_run_config(**values)
        values["bias_labels"] = ["a", "z"]
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

    def test_work_unit_order_is_semantic(self):
        values = config_values()
        second = plain(values["work_units"][0])
        second["work_unit_id"] = "unit-2"
        values["work_units"] = [values["work_units"][0], second]
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

    def test_wrong_policy_set_and_unknown_field_fail(self):
        values = config_values()
        values["policy_refs"].append(policy("banana"))
        with self.assertRaises(ContractError):
            build_research_run_config(**values)
        built = plain(build_research_run_config(**config_values()))
        built["latest"] = True
        with self.assertRaises(ContractError):
            validate_research_run_config(built)

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


if __name__ == "__main__":
    unittest.main()
