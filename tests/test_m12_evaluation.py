"""Evaluation snapshots reuse real M10 contracts with synthetic stored evidence."""

from copy import deepcopy
import unittest

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, validate_contract, validate_contracts
from services.evaluation.contracts import finalize_result, RESULT_TYPES
from services.publication.evaluation import build_evaluation_snapshot
from services.publication.inventory import build_source_inventory
from tests.test_m10_evaluation_contracts import mature_forward, forward_values, trade_values, portfolio_values, aggregate_values, plain

TIME = "2026-09-10T00:00:00Z"
DAY = "2026-09-09"


def ref(name):
    return {"id": name, "content_fingerprint": canonical_fingerprint({"name": name})}


def stored(contract, values):
    return {"contract_name": contract, "payload": plain(finalize_result(contract, values))}


def source(tasks=(), results=()):
    tasks, results = deepcopy(list(tasks)), deepcopy(list(results))
    tasks.sort(key=lambda task: task["task_ref"]["id"])
    config, root = ref("config"), ref("task-index")
    nodes = [{"ref": config, "dependencies": []}, {"ref": root, "dependencies": [t["task_ref"] for t in tasks]}]
    nodes += [{"ref": t["task_ref"], "dependencies": [t["result_ref"]] if t["result_ref"] else []} for t in tasks]
    for item in results:
        id_key, fp_key, _, _ = RESULT_TYPES[item["contract_name"]]
        nodes.append({"ref": {"id": item["payload"][id_key], "content_fingerprint": item["payload"][fp_key]}, "dependencies": []})
    evidence = {"as_of": DAY, "config_ref": config, "roots": [root], "nodes": nodes}
    return {"scan_as_of": DAY, "inventory": build_source_inventory(evidence, generated_at=TIME),
            "inventory_evidence": evidence, "task_index_ref": root, "tasks": tasks, "results": results}


def task(name, result=None, *, state="completed", due=DAY):
    contract = "ForwardOutcome" if result is None else result["contract_name"]
    payload = {} if result is None else result["payload"]
    id_key, fp_key, _, _ = RESULT_TYPES[contract]
    return {"task_ref": ref(name), "due_on": due, "state": state,
            "result_ref": None if result is None else {"id": payload[id_key], "content_fingerprint": payload[fp_key]},
            "result_contract": contract, "event_id": payload.get("event_id"), "window_sessions": payload.get("window_sessions"),
            "reason_codes": ["source_missing"] if state in ("blocked", "retry_wait") else []}


def resign(payload):
    body = {k: v for k, v in payload.items() if k not in ("evaluation_snapshot_id", "content_fingerprint", "generated_at")}
    digest = canonical_fingerprint(body)
    payload.update(evaluation_snapshot_id="evaluation-snapshot:" + digest, content_fingerprint=digest)
    return payload


class EvaluationSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.result = stored("ForwardOutcome", mature_forward())
        self.evidence = source([task("task-a", self.result)], [self.result])
        self.payload = build_evaluation_snapshot(self.evidence, generated_at=TIME)

    def validate(self, payload):
        validate_contract("EvaluationSnapshot", payload, evaluation_snapshot_evidence=self.evidence)

    def test_complete_result_metrics_are_projected_unchanged(self):
        self.validate(self.payload)
        self.assertEqual(self.payload["state"], "current")
        self.assertEqual(self.payload["completed_through"], DAY)
        self.assertEqual(self.payload["result_rows"][0]["gross_return"], .1)
        self.assertIsNone(self.payload["result_rows"][0]["net_return"])

    def test_empty_and_immature_have_no_mature_samples(self):
        for evidence in (source(), source([task("future", state="queued", due="2026-09-10")])):
            payload = build_evaluation_snapshot(evidence, generated_at=TIME)
            self.assertEqual(payload["state"], "current")
            self.assertEqual(payload["due_count"], 0)
            self.assertIsNone(payload["completed_through"])
        self.assertEqual(payload["immature_count"], 1)

    def test_all_failed_is_unavailable_and_failure_counts_are_conserved(self):
        evidence = source([task("a", state="retry_wait"), task("b", state="blocked"), task("c", state="queued")])
        payload = build_evaluation_snapshot(evidence, generated_at=TIME)
        self.assertEqual((payload["due_count"], payload["failed_count"], payload["pending_due_count"]), (3, 2, 1))
        self.assertEqual(payload["state"], "unavailable")
        self.assertIsNone(payload["completed_through"])
        self.assertEqual(payload["reason_codes"], ["source_missing"])

    def test_failed_middle_day_blocks_watermark_despite_later_success(self):
        other = stored("TradeOutcome", trade_values())
        evidence = source([task("a", self.result, due="2026-09-04"), task("b", state="blocked", due="2026-09-07"), task("c", other)], [self.result, other])
        payload = build_evaluation_snapshot(evidence, generated_at=TIME)
        self.assertEqual(payload["completed_through"], "2026-09-04")
        self.assertEqual(payload["state"], "lagging")
        self.assertEqual(payload["completed_count"], 2)

    def test_failure_on_same_due_day_prevents_that_day_completing(self):
        evidence = source([task("a", self.result), task("b", state="running")], [self.result])
        payload = build_evaluation_snapshot(evidence, generated_at=TIME)
        self.assertIsNone(payload["completed_through"])
        self.assertEqual(payload["state"], "lagging")

    def test_completed_requires_due_terminal_readable_result(self):
        pending = stored("ForwardOutcome", forward_values())
        cases = [source([task("a")]), source([task("a", self.result, due="2026-09-10")], [self.result]),
                 source([task("a", pending)], [pending])]
        for evidence in cases:
            with self.subTest(evidence=evidence), self.assertRaises(ContractError):
                build_evaluation_snapshot(evidence, generated_at=TIME)

    def test_trade_cost_and_portfolio_and_old_aggregate_remain_unavailable(self):
        trade = stored("TradeOutcome", trade_values())
        portfolio = stored("PortfolioRun", portfolio_values(trade["payload"]))
        aggregate = stored("ResearchAggregate", aggregate_values(self.result["payload"]))
        items = [trade, portfolio, aggregate]
        evidence = source([task(str(i), item) for i, item in enumerate(items)], items)
        payload = build_evaluation_snapshot(evidence, generated_at=TIME)
        by_type = {r["result_contract"]: r for r in payload["result_rows"]}
        self.assertIsNone(by_type["TradeOutcome"]["net_return"])
        self.assertEqual(by_type["TradeOutcome"]["unavailable_reason"], "cost_slippage_policy_not_approved")
        self.assertIsNone(by_type["PortfolioRun"]["gross_return"])
        self.assertIsNone(by_type["ResearchAggregate"]["mean_gross_return"])

    def test_current_aggregate_projects_saved_metrics_without_recalculation(self):
        from tests.test_m10_aggregate import forward, forward_scope, research_batch
        from unittest.mock import patch
        result = {"contract_name": "ResearchAggregate", "payload": plain(research_batch(
            [forward("1", gross=.1), forward("2", gross=-.05)], forward_scope()).result)}
        evidence = source([task("aggregate", result)], [result])
        with patch("services.evaluation.aggregate._statistics", side_effect=AssertionError("M12 must not calculate returns")):
            payload = build_evaluation_snapshot(evidence, generated_at=TIME)
        row = payload["result_rows"][0]
        self.assertEqual(row["mean_gross_return"], result["payload"]["mean_gross_return"])
        self.assertEqual(row["win_rate"], result["payload"]["win_rate"])
        self.assertEqual(row["status"], "completed")

    def test_missing_trusted_evidence_fails_single_and_collection(self):
        for validate in (lambda: validate_contract("EvaluationSnapshot", self.payload),
                         lambda: validate_contracts([("EvaluationSnapshot", self.payload)])):
            with self.assertRaises(ContractError):
                validate()

    def test_resealed_count_watermark_status_and_metric_tampering(self):
        for key, value in (("due_count", 0), ("completed_through", "2026-09-10"), ("state", "lagging"),
                           ("completed_count", True), ("result_refs", []), ("reason_codes", ["made_up"])):
            payload = deepcopy(self.payload)
            payload[key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                self.validate(resign(payload))
        for field, value in (("gross_return", 1.0), ("net_return", 0), ("mfe", True), ("window_sessions", True), ("extra", 1)):
            payload = deepcopy(self.payload)
            payload["result_rows"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ContractError):
                self.validate(resign(payload))

    def test_task_set_deletion_duplication_or_result_replacement_rejected(self):
        for mutation in ("delete", "duplicate", "result", "event", "window", "family"):
            evidence = deepcopy(self.evidence)
            if mutation == "delete": evidence["tasks"] = []
            elif mutation == "duplicate": evidence["tasks"] *= 2
            elif mutation == "result": evidence["tasks"][0]["result_ref"] = ref("fake")
            elif mutation == "event": evidence["tasks"][0]["event_id"] = "other-event"
            elif mutation == "window": evidence["tasks"][0]["window_sessions"] = 20
            else: evidence["tasks"][0]["result_contract"] = "TradeOutcome"
            with self.subTest(mutation=mutation), self.assertRaises(ContractError):
                build_evaluation_snapshot(evidence, generated_at=TIME)

    def test_actual_m10_contract_is_checked_not_just_its_supplied_ref(self):
        evidence = deepcopy(self.evidence)
        evidence["results"][0]["payload"]["gross_return"] = 999
        with self.assertRaises(ContractError):
            build_evaluation_snapshot(evidence, generated_at=TIME)

    def test_future_or_comparison_results_cannot_be_promoted(self):
        evidence = deepcopy(self.evidence)
        evidence["scan_as_of"] = "2026-09-03"
        evidence["inventory_evidence"]["as_of"] = "2026-09-03"
        evidence["inventory"] = build_source_inventory(evidence["inventory_evidence"], generated_at=TIME)
        with self.assertRaises(ContractError): build_evaluation_snapshot(evidence, generated_at=TIME)
        comparison = stored("TradeOutcome", trade_values(role="comparison"))
        with self.assertRaises(ContractError):
            build_evaluation_snapshot(source([task("a", comparison)], [comparison]), generated_at=TIME)

    def test_unknown_schema_and_bad_fingerprint_and_duplicate_collection(self):
        for key, value in (("schema_version", "2.0.0"), ("evaluation_snapshot_id", "forged"), ("content_fingerprint", "bad")):
            payload = deepcopy(self.payload)
            payload[key] = value
            with self.subTest(key=key), self.assertRaises(ContractError): self.validate(payload)
        with self.assertRaises(ContractError):
            validate_contracts([("EvaluationSnapshot", self.payload)] * 2, evaluation_snapshot_evidence=self.evidence)

    def test_same_evidence_different_timestamp_preserves_identity_without_aliasing(self):
        before = deepcopy(self.evidence)
        other = build_evaluation_snapshot(self.evidence, generated_at="2026-09-11T00:00:00Z")
        self.assertEqual(other["evaluation_snapshot_id"], self.payload["evaluation_snapshot_id"])
        other["result_rows"][0]["result_ref"]["id"] = "changed"
        self.assertEqual(self.evidence, before)


if __name__ == "__main__": unittest.main()
