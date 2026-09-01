from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest

from services.contracts.validation import ContractError, validate_contract
from services.contracts.market_data import canonical_fingerprint
from services.factors import produce_technical_evidence
from services.scanner.factor_snapshot import build_shadow_model_assessments
from services.scanner.favorite_pattern_tracker import evaluate, evaluate_v3_model_facts
from services.scanner.unified_v2_scan import shadow_model_assessments
from services.selectors import (
    adapt_legacy_model_assessment,
    produce_model_assessments,
    validate_model_assessment,
)
from tests.test_m03_gates import GENERATED_AT, event_from, prepare


ROOT = Path(__file__).resolve().parents[1]


def plain(value):
    if hasattr(value, "items"):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


class M05SelectorTests(unittest.TestCase):
    def setUp(self):
        self.prepared = prepare("factor_snapshot")
        self.event = event_from(self.prepared)
        self.evidence = produce_technical_evidence(
            self.prepared,
            gate_events=(self.event,),
            generated_at=GENERATED_AT,
        )

    def produce(self, **changes):
        return produce_model_assessments(
            self.prepared,
            gate_events=(self.event,),
            technical_evidence=self.evidence,
            generated_at=GENERATED_AT,
            **changes,
        )

    def by_model(self, batch=None):
        return {item["model_id"]: item for item in (batch or self.produce()).assessments}

    def test_same_gate_creates_two_v2_score_free_assessments(self):
        assessments = self.by_model()
        self.assertEqual(set(assessments), {"complex_multifactor", "favorite_pattern"})
        self.assertEqual(
            {item["gate_event_id"] for item in assessments.values()},
            {self.event["gate_event_id"]},
        )
        for item in assessments.values():
            self.assertEqual(item["schema_version"], "2.0.0")
            self.assertFalse(item["production_effect"])
            validate_model_assessment(item)
            encoded = json.dumps(plain(item), sort_keys=True)
            for forbidden in (
                '"score"', '"weight"', '"rank"', '"ranking"',
                '"market_adjustment"', '"industry_adjustment"',
                '"trade_plan"', '"entry"', '"stop"', '"target"',
            ):
                self.assertNotIn(forbidden, encoded)

    def test_complex_selector_only_references_m04_facts(self):
        item = self.by_model()["complex_multifactor"]
        expected_ids = sorted(evidence["evidence_id"] for evidence in self.evidence.evidence)
        self.assertEqual(list(item["technical_evidence_ids"]), expected_ids)
        self.assertEqual(
            item["model_specific_facts"],
            {"assessment_kind": "technical_fact_inventory"},
        )
        referenced = {
            fact["evidence_id"]
            for field in ("matched_facts", "missing_facts", "risk_facts")
            for fact in item[field]
        }
        self.assertTrue(referenced <= set(expected_ids))

    def test_favorite_specific_facts_are_namespaced_and_traceable(self):
        item = self.by_model()["favorite_pattern"]
        facts = item["model_specific_facts"]
        self.assertEqual(facts["definition_version"], "favorite-pattern-v3.0.0")
        self.assertTrue(facts["facts"])
        self.assertTrue(
            all(fact["fact_id"].startswith("favorite_pattern.v3.") for fact in facts["facts"])
        )
        self.assertTrue(facts["risk"]["fact_id"].startswith("favorite_pattern.v3."))
        self.assertFalse(facts["lookahead_audit"]["future_data_used"])

    def test_formal_favorite_uses_the_existing_v3_rules_on_a_fixed_sample(self):
        rows = self.prepared.symbol_rows[self.event["symbol"]]
        legacy_view = evaluate(rows)
        formal_facts = evaluate_v3_model_facts(rows)
        old_conditions = {
            f"favorite_pattern.v3.{item['id']}": bool(item["hit"])
            for item in legacy_view["conditions"]
        }
        new_conditions = {item["fact_id"]: bool(item["hit"]) for item in formal_facts["facts"]}
        self.assertEqual(new_conditions, old_conditions)
        self.assertEqual(formal_facts["status"], legacy_view["stage"])
        self.assertEqual(formal_facts["risk"]["blocked"], legacy_view["risk_gate"]["blocked"])

    def test_missing_or_mixed_m04_evidence_fails_closed(self):
        incomplete = replace(self.evidence, evidence=self.evidence.evidence[:-1])
        with self.assertRaisesRegex(ContractError, "Batch identity"):
            produce_model_assessments(
                self.prepared,
                gate_events=(self.event,),
                technical_evidence=incomplete,
                generated_at=GENERATED_AT,
            )
        incomplete_identity = {
            "as_of": incomplete.as_of,
            "path_status": incomplete.path_status,
            "registry_version": incomplete.registry_version,
            "evidence": [
                {
                    "evidence_id": item["evidence_id"],
                    "content": item["evidence_content_fingerprint"],
                }
                for item in incomplete.evidence
            ],
        }
        incomplete = replace(
            incomplete,
            batch_id="technical-evidence-batch:" + canonical_fingerprint(incomplete_identity),
        )
        with self.assertRaisesRegex(ContractError, "complete M04 evidence"):
            produce_model_assessments(
                self.prepared,
                gate_events=(self.event,),
                technical_evidence=incomplete,
                generated_at=GENERATED_AT,
            )
        wrong = prepare("factor_snapshot")
        object.__setattr__(wrong, "universe_id", "universe:sha256:" + "f" * 64)
        with self.assertRaisesRegex(ContractError, "GateEvent identity"):
            produce_model_assessments(
                wrong,
                gate_events=(self.event,),
                technical_evidence=self.evidence,
                generated_at=GENERATED_AT,
            )

    def test_evidence_for_unknown_gate_fails(self):
        with self.assertRaisesRegex(ContractError, "unknown GateEvent"):
            produce_model_assessments(
                self.prepared,
                gate_events=(),
                technical_evidence=self.evidence,
                generated_at=GENERATED_AT,
            )

    def test_identical_input_and_order_are_deterministic(self):
        first = self.produce()
        reversed_evidence = replace(
            self.evidence,
            evidence=tuple(reversed(self.evidence.evidence)),
        )
        with self.assertRaisesRegex(ContractError, "canonical order"):
            produce_model_assessments(
                self.prepared,
                gate_events=(self.event,),
                technical_evidence=reversed_evidence,
                generated_at=GENERATED_AT,
            )
        second = self.produce()
        self.assertEqual(first.batch_id, second.batch_id)
        self.assertEqual(first.assessments, second.assessments)

    def test_content_or_identity_tampering_fails(self):
        item = plain(self.produce().assessments[0])
        item["assessment_id"] = "assessment:sha256:" + "0" * 64
        with self.assertRaisesRegex(ContractError, "canonical M05 identity"):
            validate_model_assessment(item)
        item = plain(self.produce().assessments[0])
        item["eligible"] = not item["eligible"]
        with self.assertRaisesRegex(ContractError, "content fingerprint"):
            validate_model_assessment(item)

    def test_personal_fact_cannot_masquerade_as_a_shared_factor(self):
        def bad_facts(rows):
            result = plain(evaluate_v3_model_facts(rows))
            result["facts"][0]["fact_id"] = "support.ema_proximity"
            return result

        with self.assertRaisesRegex(ContractError, "not namespaced"):
            self.produce(favorite_fact_evaluator=bad_facts)

    def test_legacy_is_explicit_and_cannot_enter_formal(self):
        source = {"symbol": "ABC", "stage": "entry_ready", "eligible": True}
        adapted = adapt_legacy_model_assessment(
            source,
            model_id="favorite_pattern",
            model_version="favorite-pattern-v3.0.0",
            symbol="ABC",
            as_of=self.prepared.as_of,
            generated_at=GENERATED_AT,
        )
        self.assertEqual(adapted["schema_version"], "1.0.0")
        self.assertEqual(adapted["path_status"], "legacy")
        self.assertTrue(adapted["bias_labels"])
        validate_contract("ModelAssessment", adapted)
        with self.assertRaisesRegex(ContractError, "2.x"):
            validate_model_assessment(adapted)

    def test_v2_cannot_be_reidentified_as_legacy(self):
        item = plain(self.produce().assessments[0])
        item["path_status"] = "legacy"
        item["bias_labels"] = ["forged_legacy_path"]
        identity = {
            "gate_event_id": item["gate_event_id"],
            "instrument_id": item["instrument_id"],
            "as_of": item["as_of"],
            "path_status": item["path_status"],
            "input_identity": item["input_identity"],
            "model_id": item["model_id"],
            "model_version": item["model_version"],
            "evidence_batch_id": item["evidence_batch_id"],
            "technical_evidence_ids": item["technical_evidence_ids"],
            "model_specific_facts_fingerprint": item["model_specific_facts_fingerprint"],
        }
        item["assessment_id"] = "assessment:" + canonical_fingerprint(identity)
        semantic = {
            key: value for key, value in item.items()
            if key not in {"generated_at", "assessment_content_fingerprint"}
        }
        item["assessment_content_fingerprint"] = canonical_fingerprint(semantic)
        with self.assertRaisesRegex(ContractError, "must use the formal path"):
            validate_model_assessment(item)

    def test_unknown_model_contract_major_fails(self):
        old = {
            "schema_version": "1.0.0",
            "as_of": self.prepared.as_of,
            "generated_at": GENERATED_AT,
            "source_version": {"legacy": "v1"},
            "future_data_used": False,
            "assessment_id": "assessment:legacy",
            "gate_event_id": "gate:legacy",
            "model_id": "legacy",
            "model_version": "legacy-v1",
            "eligible": False,
        }
        validate_contract("ModelAssessment", old)
        with self.assertRaises(ContractError):
            validate_contract("ModelAssessment", {**old, "schema_version": "3.0.0"})

    def test_daily_and_replay_use_the_same_selector_producer(self):
        replay = prepare("unified_v2_backtest")
        replay_event = event_from(replay)
        replay_evidence = produce_technical_evidence(
            replay,
            gate_events=(replay_event,),
            generated_at=GENERATED_AT,
        )
        daily_batch = build_shadow_model_assessments(
            self.prepared,
            gate_events=(self.event,),
            technical_evidence=self.evidence,
            generated_at=GENERATED_AT,
        )
        replay_batch = shadow_model_assessments(
            replay,
            gate_events=(replay_event,),
            technical_evidence=replay_evidence,
            generated_at=GENERATED_AT,
        )
        self.assertEqual(daily_batch.batch_id, replay_batch.batch_id)
        self.assertEqual(daily_batch.assessments, replay_batch.assessments)

    def test_legacy_adapter_does_not_modify_current_outputs(self):
        paths = [
            ROOT / "public" / "favorite-pattern.json",
            ROOT / "public" / "unified-v2-latest.json",
        ]
        before = {path: path.read_bytes() for path in paths}
        for path in paths:
            payload = json.loads(before[path])
            adapt_legacy_model_assessment(
                payload,
                model_id="favorite_pattern" if "favorite" in path.name else "complex_multifactor",
                model_version=str(payload.get("pattern_version") or payload.get("version") or "legacy"),
                symbol="legacy-batch",
                as_of=str(payload.get("as_of") or payload.get("coverage", {}).get("end")),
                generated_at=GENERATED_AT,
            )
        self.assertEqual({path: path.read_bytes() for path in paths}, before)

    def test_m05_does_not_recompute_m03_or_m04_shared_facts(self):
        text = "\n".join(
            path.read_text()
            for path in sorted((ROOT / "services" / "selectors").glob("*.py"))
        )
        for forbidden in (
            "evaluate_all_factors", "produce_gate_batch", "produce_technical_evidence",
            "long_trend_ok", "exact_daily_macd_bull_cross", "_find_double_bottom",
        ):
            self.assertNotIn(forbidden, text)

    def test_only_services_selectors_creates_formal_assessment_identity(self):
        creators = set()
        marker = 'payload["assessment_id"] = "assessment:" + canonical_fingerprint'
        for path in sorted((ROOT / "services").rglob("*.py")):
            if marker in path.read_text():
                creators.add(str(path.relative_to(ROOT)))
        self.assertEqual(creators, {"services/selectors/producer.py"})


if __name__ == "__main__":
    unittest.main()
