from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest

from services.contracts.validation import ContractError, validate_contract
from services.factors import (
    GATE_REFERENCE_FACTOR_IDS,
    adapt_legacy_factor_state,
    produce_technical_evidence,
    validate_technical_evidence,
)
from services.scanner.factor_detectors import evaluate_all_factors
from services.scanner.factor_registry import FACTORS, FACTORS_BY_ID, REGISTRY_VERSION
from services.scanner.factor_snapshot import build_shadow_technical_evidence
from services.scanner.unified_v2_scan import shadow_technical_evidence
from tests.test_m03_gates import GENERATED_AT, event_from, prepare


ROOT = Path(__file__).resolve().parents[1]


def evidence_map(batch):
    return {item["factor_id"]: item for item in batch.evidence}


def plain(value):
    if hasattr(value, "items"):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


class M04FactorEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.daily_input = prepare("factor_snapshot")
        self.event = event_from(self.daily_input)

    def produce(self, **changes):
        return produce_technical_evidence(
            self.daily_input,
            gate_events=(self.event,),
            generated_at=GENERATED_AT,
            **changes,
        )

    def test_every_registry_factor_has_one_v2_evidence(self):
        batch = self.produce()
        self.assertEqual(len(batch.evidence), len(FACTORS))
        self.assertEqual(
            [item["factor_id"] for item in batch.evidence],
            sorted(factor.id for factor in FACTORS),
        )
        self.assertTrue(all(item["schema_version"] == "2.0.0" for item in batch.evidence))
        self.assertTrue(all(item["path_status"] == "formal" for item in batch.evidence))
        for item in batch.evidence:
            validate_technical_evidence(item)

    def test_gate_facts_are_injected_as_references(self):
        seen = {}

        def detector(rows, as_of, *, fact_references):
            seen.update(fact_references)
            return evaluate_all_factors(rows, as_of, fact_references=fact_references)

        items = evidence_map(self.produce(detector=detector))
        self.assertEqual(set(seen), GATE_REFERENCE_FACTOR_IDS)
        for factor_id in GATE_REFERENCE_FACTOR_IDS:
            self.assertEqual(items[factor_id]["source_kind"], "gate_reference")
            self.assertEqual(items[factor_id]["evidence"]["gate_event_id"], self.event["gate_event_id"])
        self.assertTrue(items["macd.daily_bull_cross"]["raw_hit"])
        self.assertEqual(
            items["qualification.long_trend"]["raw_hit"],
            self.event["baseline_passed"],
        )

    def test_non_gate_facts_match_the_existing_detector(self):
        rows = self.daily_input.symbol_rows[self.event["symbol"]]
        old = {state.factor_id: state for state in evaluate_all_factors(rows, self.daily_input.as_of)}
        new = evidence_map(self.produce())
        for factor in FACTORS:
            if factor.id in GATE_REFERENCE_FACTOR_IDS:
                continue
            with self.subTest(factor=factor.id):
                self.assertEqual(new[factor.id]["available"], old[factor.id].available)
                self.assertEqual(new[factor.id]["raw_hit"], old[factor.id].hit)
                self.assertEqual(new[factor.id]["recent_hit"], old[factor.id].recent_hit)
                self.assertEqual(new[factor.id]["latest_hit_date"], old[factor.id].latest_hit_date)
                self.assertEqual(new[factor.id]["value"], old[factor.id].value)
                self.assertEqual(plain(new[factor.id]["evidence"]), old[factor.id].evidence)

    def test_parent_failure_preserves_raw_fact_but_blocks_qualified_hit(self):
        child_id = "structure.trendline_three_push_retest"
        parent_id = "structure.trendline_three_push"

        def detector(rows, as_of, *, fact_references):
            states = evaluate_all_factors(rows, as_of, fact_references=fact_references)
            return [
                replace(state, hit=True, available=True)
                if state.factor_id == child_id
                else replace(state, hit=False, available=True)
                if state.factor_id == parent_id
                else state
                for state in states
            ]

        child = evidence_map(self.produce(detector=detector))[child_id]
        self.assertTrue(child["raw_hit"])
        self.assertFalse(child["qualified_hit"])
        self.assertEqual(tuple(child["blocked_by"]), (parent_id,))

    def test_repeated_input_is_deterministic(self):
        first = self.produce()
        second = self.produce()
        self.assertEqual(first.batch_id, second.batch_id)
        self.assertEqual(first.evidence, second.evidence)

    def test_daily_and_replay_call_the_same_producer(self):
        replay_input = prepare("unified_v2_backtest")
        replay_event = event_from(replay_input)
        daily = build_shadow_technical_evidence(
            self.daily_input, gate_events=(self.event,), generated_at=GENERATED_AT
        )
        replay = shadow_technical_evidence(
            replay_input, gate_events=(replay_event,), generated_at=GENERATED_AT
        )
        self.assertEqual(daily.batch_id, replay.batch_id)
        self.assertEqual(daily.evidence, replay.evidence)

    def test_gate_and_market_identity_must_match(self):
        wrong_input = prepare("factor_snapshot")
        object.__setattr__(wrong_input, "universe_id", "universe:sha256:" + "f" * 64)
        with self.assertRaisesRegex(ContractError, "universe"):
            produce_technical_evidence(
                wrong_input,
                gate_events=(self.event,),
                generated_at=GENERATED_AT,
            )

    def test_detector_must_return_exact_registry_once(self):
        def missing(rows, as_of, *, fact_references):
            return evaluate_all_factors(rows, as_of, fact_references=fact_references)[:-1]

        with self.assertRaisesRegex(ContractError, "active registry"):
            self.produce(detector=missing)

        def duplicate(rows, as_of, *, fact_references):
            states = evaluate_all_factors(rows, as_of, fact_references=fact_references)
            return [*states, states[0]]

        with self.assertRaisesRegex(ContractError, "duplicate factor"):
            self.produce(detector=duplicate)

    def test_v2_identity_and_content_tampering_fail(self):
        item = dict(self.produce().evidence[0])
        item["evidence_id"] = "evidence:sha256:" + "0" * 64
        with self.assertRaisesRegex(ContractError, "canonical M04 identity"):
            validate_technical_evidence(item)

        item = dict(self.produce().evidence[0])
        item["raw_hit"] = not item["raw_hit"]
        with self.assertRaises(ContractError):
            validate_technical_evidence(item)

    def test_formal_validator_rejects_v1_and_unknown_major(self):
        old = {
            "schema_version": "1.0.0",
            "as_of": self.daily_input.as_of,
            "generated_at": GENERATED_AT,
            "source_version": {"legacy": "v1"},
            "future_data_used": False,
            "evidence_id": "evidence:legacy",
            "factor_id": FACTORS[0].id,
            "factor_version": FACTORS[0].version,
            "timeframe": FACTORS[0].timeframe,
            "evidence_date": self.daily_input.as_of,
            "available": True,
        }
        validate_contract("TechnicalEvidence", old)
        with self.assertRaisesRegex(ContractError, "2.x"):
            validate_technical_evidence(old)
        with self.assertRaises(ContractError):
            validate_contract("TechnicalEvidence", {**old, "schema_version": "3.0.0"})

    def test_producer_does_not_upgrade_a_legacy_gate(self):
        legacy_gate = {
            "schema_version": "1.0.0",
            "as_of": self.daily_input.as_of,
            "generated_at": GENERATED_AT,
            "source_version": {"gate": "legacy"},
            "future_data_used": False,
            "gate_event_id": f"gate:ABC:{self.daily_input.as_of}:legacy-v1",
            "symbol": "ABC",
            "signal_date": self.daily_input.as_of,
            "gate_policy_version": "legacy-v1",
            "passed": True,
        }
        object.__setattr__(self.daily_input, "mode", "legacy")
        with self.assertRaisesRegex(ContractError, "explicit legacy adapter"):
            produce_technical_evidence(
                self.daily_input,
                gate_events=(legacy_gate,),
                generated_at=GENERATED_AT,
            )

    def test_legacy_adapter_reads_the_current_snapshot_without_changing_source(self):
        path = ROOT / "public" / "daily-factor-snapshot.json"
        before = path.read_bytes()
        snapshot = json.loads(before)
        adapted = [
            adapt_legacy_factor_state(
                state,
                symbol=symbol["symbol"],
                as_of=snapshot["as_of"],
                generated_at=GENERATED_AT,
                registry_version=snapshot["registry_version"],
            )
            for symbol in snapshot["symbols"]
            for state in symbol["factors"]
        ]
        self.assertEqual(len(adapted), len(snapshot["symbols"]) * len(FACTORS))
        self.assertTrue(all(item["schema_version"] == "1.0.0" for item in adapted))
        self.assertTrue(all(item["path_status"] == "legacy" for item in adapted))
        self.assertTrue(all(item["bias_labels"] for item in adapted))
        self.assertEqual(path.read_bytes(), before)

    def test_output_contains_no_score_rank_or_trade_contract(self):
        encoded = json.dumps(
            [dict(item) for item in self.produce().evidence],
            default=lambda value: dict(value),
            sort_keys=True,
        )
        for forbidden in (
            "technical_score", "score_policy_version", "ranking_policy_version",
            "trade_plan", "entry", "stop", "target",
        ):
            self.assertNotIn(f'"{forbidden}"', encoded)

    def test_only_services_factors_creates_new_evidence_identity(self):
        creators = set()
        marker = 'payload["evidence_id"] = "evidence:" + canonical_fingerprint'
        for path in sorted((ROOT / "services").rglob("*.py")):
            if marker in path.read_text():
                creators.add(str(path.relative_to(ROOT)))
        self.assertEqual(creators, {"services/factors/producer.py"})


if __name__ == "__main__":
    unittest.main()
