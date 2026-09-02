from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from services.context import produce_market_industry_context
from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError
from services.execution import (
    ExecutionShadowStore,
    adapt_legacy_support_plan_bytes,
    advance_exit_state,
    produce_trade_plans,
    validate_exit_state,
    validate_trade_plan,
)
from services.factors import produce_support_evidence, produce_technical_evidence
from services.gates import produce_gate_batch
from services.market_data import RepositoryRead, prepare_shadow_consumer_input
from services.ranking import RANKING_POLICY, build_policy, produce_versioned_ranking
from services.scanner.factor_detectors import evaluate_all_factors
from services.scanner.factor_snapshot import build_shadow_trade_plans
from services.scanner.support_risk import executable_stop, simulate_execution
from services.scanner.unified_v2_scan import shadow_trade_plans
from services.selectors import produce_model_assessments
from tests.test_m03_gates import GENERATED_AT
from tests.test_m06_context import price_rows
from tests.test_market_data_consumers import DAY, complete_gate_rows, forward_member, forward_snapshot


ROOT = Path(__file__).resolve().parents[1]
ENTRY_DAY = "2026-09-02"
ENTRY_GENERATED_AT = f"{ENTRY_DAY}T23:00:00Z"


def reader_map(rows_by_id):
    def read(instrument_id, *, as_of):
        rows = tuple(row for row in rows_by_id[instrument_id] if row["date"] <= as_of)
        return RepositoryRead(
            instrument_id=instrument_id,
            as_of=as_of,
            rows=rows,
            point_in_time_fingerprint=canonical_fingerprint(list(rows)),
        )

    return read


def plain(value):
    if hasattr(value, "items"):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def refingerprint_exit_state(original, **changes):
    payload = plain(original)
    payload.update(changes)
    identity = {
        "schema_major": 2,
        "plan_id": payload["plan_id"],
        "as_of": payload["as_of"],
        "previous_exit_state_id": payload["previous_exit_state_id"],
        "holding_sessions": payload["holding_sessions"],
        "state": payload["state"],
        "market_data_fingerprint": payload["market_data_fingerprint"],
        "exit_policy_version": payload["exit_policy_version"],
        "exit_policy_fingerprint": payload["exit_policy_fingerprint"],
    }
    payload["exit_state_id"] = "exit-state:" + canonical_fingerprint(identity)
    payload["exit_state_content_fingerprint"] = canonical_fingerprint({
        key: plain(value) for key, value in payload.items()
        if key not in {"generated_at", "exit_state_content_fingerprint"}
    })
    return payload


class M08ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.members = [forward_member(symbol) for symbol in ("AAA", "BBB")]
        snapshot = forward_snapshot(members=self.members)
        rows_by_id = {item["instrument_id"]: complete_gate_rows() for item in self.members}
        self.stock = prepare_shadow_consumer_input(
            consumer="factor_snapshot",
            mode="formal",
            as_of=DAY,
            snapshots=[snapshot],
            reader=reader_map(rows_by_id),
            generated_at=f"{DAY}T23:05:00Z",
            data_source={"provider": "fixture", "dataset": "adjusted-daily", "market": "US"},
        )
        gates = produce_gate_batch(self.stock, generated_at=GENERATED_AT, scan_batch_id="m08-fixture")
        self.events = gates.events

        def complete_detector(rows, as_of, *, fact_references):
            return [replace(state, available=True) for state in evaluate_all_factors(rows, as_of, fact_references=fact_references)]

        self.technical = produce_technical_evidence(
            self.stock, gate_events=self.events, generated_at=GENERATED_AT, detector=complete_detector
        )
        self.support = produce_support_evidence(
            self.stock,
            gate_events=self.events,
            technical_evidence=self.technical,
            generated_at=GENERATED_AT,
        )
        assessments = produce_model_assessments(
            self.stock,
            gate_events=self.events,
            technical_evidence=self.technical,
            generated_at=GENERATED_AT,
        )
        etf_member = forward_member("QQQ")
        etf = prepare_shadow_consumer_input(
            consumer="market_etf",
            mode="formal",
            as_of=DAY,
            snapshots=[forward_snapshot(members=[etf_member])],
            reader=reader_map({etf_member["instrument_id"]: price_rows()}),
            generated_at=f"{DAY}T23:05:00Z",
            data_source={"provider": "fixture", "dataset": "adjusted-daily", "market": "US"},
        )
        contexts = produce_market_industry_context(
            self.stock,
            etf,
            gate_events=self.events,
            technical_evidence=self.technical,
            model_assessments=assessments,
            etf_registry={
                "schema_version": "1.0.0",
                "registry_version": "m08-etf-fixture-1.0.0",
                "as_of_date": DAY,
                "etfs": [{
                    "symbol": "QQQ",
                    "etf_id": "etf:sha256:" + "1" * 64,
                    "category": "broad_market",
                    "label": "nasdaq_100",
                    "issuer": "fixture",
                    "membership_source_url": "https://example.test/QQQ",
                    "membership_as_of_date": DAY,
                    "formal_current_forward_eligible": True,
                    "historical_membership_evidence": "stable_instrument_id",
                }],
            },
            membership_registry={"schema_version": "1.0.0", "mapping_registry_version": "m08-empty-1.0.0", "snapshots": []},
            generated_at=GENERATED_AT,
        )
        ranking_rules = plain(RANKING_POLICY["rules"])
        ranking_rules["selected_limit"] = 1
        ranking_policy = build_policy(kind="ranking", version="1.0.1", name="m08_single_selected_fixture", rules=ranking_rules)
        self.ranking = produce_versioned_ranking(
            gate_events=self.events,
            technical_evidence=self.technical,
            model_assessments=assessments,
            contexts=contexts,
            generated_at=GENERATED_AT,
            ranking_policy=ranking_policy,
        ).snapshot
        self.entry_reads = {}
        for member in self.members:
            rows = [dict(row) for row in complete_gate_rows()]
            rows.append({"date": ENTRY_DAY, "open": 100.0, "high": 104.0, "low": 96.0, "close": 101.0, "volume": 1_000_000})
            self.entry_reads[member["instrument_id"]] = RepositoryRead(
                instrument_id=member["instrument_id"],
                as_of=ENTRY_DAY,
                rows=tuple(rows),
                point_in_time_fingerprint=canonical_fingerprint(rows),
            )

    def plans(self, **changes):
        values = {"entry_reads": self.entry_reads, "generated_at": ENTRY_GENERATED_AT}
        values.update(changes)
        return produce_trade_plans(self.ranking, self.support, **values)

    def test_only_selected_entries_receive_plans_and_others_keep_reason(self):
        batch = self.plans()
        self.assertEqual(len(batch.plans), 1)
        self.assertEqual([item["status"] for item in batch.decisions].count("created"), 1)
        self.assertIn("not_selected_for_plan", [item["reason"] for item in batch.decisions])

    def test_plan_waits_for_real_next_adjusted_open(self):
        batch = self.plans(entry_reads={})
        self.assertEqual(batch.plans, ())
        selected = next(item for item in batch.decisions if item["score_result_id"] == self.ranking["selected_entries"][0]["score_result_id"])
        self.assertEqual(selected["reason"], "next_adjusted_open_unavailable")

    def test_plan_matches_current_entry_stop_target_and_holding_behavior(self):
        plan = self.plans().plans[0]
        support = next(item for item in self.support.evidence if item["gate_event_id"] == plan["gate_event_id"])
        legacy = executable_stop(100.0, support["support_plan"])
        self.assertEqual(plan["entry"]["price"], legacy["entry"])
        self.assertEqual(plan["stop"]["price"], legacy["stop"])
        self.assertEqual(plan["target"]["price"], legacy["target"])
        self.assertEqual(plan["max_hold_sessions"], legacy["max_hold_sessions"])
        self.assertEqual(plan["price_basis"], "provider_adjusted_ohlcv")

    def test_support_is_a_stable_m04_evidence_reference_not_ranking_text(self):
        plan = self.plans().plans[0]
        support = next(item for item in self.support.evidence if item["support_evidence_id"] == plan["support_evidence_id"])
        self.assertEqual(plan["technical_evidence_ids"], support["technical_evidence_ids"])
        source = (ROOT / "services/execution/producer.py").read_text()
        for forbidden in (" ema", "pivots(", "fibonacci", "signal_support_plan", "evaluate_all_factors"):
            self.assertNotIn(forbidden, source)

    def test_tampered_entry_fingerprint_and_plan_content_fail(self):
        instrument_id = self.ranking["selected_entries"][0]["instrument_id"]
        read = self.entry_reads[instrument_id]
        bad = dict(self.entry_reads)
        bad[instrument_id] = replace(read, point_in_time_fingerprint="sha256:" + "0" * 64)
        with self.assertRaises(ContractError):
            self.plans(entry_reads=bad)
        plan = plain(self.plans().plans[0])
        plan["stop"]["price"] -= 1
        with self.assertRaises(ContractError):
            validate_trade_plan(plan)

    def test_same_bar_is_stop_first_and_matches_legacy(self):
        plan = self.plans().plans[0]
        bar = {"date": ENTRY_DAY, "open": plan["entry"]["price"], "high": plan["target"]["price"] + 1, "low": plan["stop"]["price"] - 1, "close": plan["entry"]["price"], "volume": 1000}
        state = advance_exit_state(plan, completed_bars=[bar], generated_at=ENTRY_GENERATED_AT)
        legacy = simulate_execution(plan["entry"]["price"], {"level": plan["support"]["level"], "source": plan["support"]["source"]}, [bar])
        self.assertEqual(state["state"], "closed_stop")
        self.assertEqual(state["execution_price"], legacy["exit_price"])

    def test_gap_stop_uses_open_and_target_uses_range(self):
        plan = self.plans().plans[0]
        gap = {"date": ENTRY_DAY, "open": plan["stop"]["price"] - 2, "high": plan["entry"]["price"], "low": plan["stop"]["price"] - 3, "close": plan["stop"]["price"] - 1, "volume": 1000}
        state = advance_exit_state(plan, completed_bars=[gap], generated_at=ENTRY_GENERATED_AT)
        self.assertEqual((state["state"], state["execution_price"]), ("closed_stop_gap", gap["open"]))
        target = {"date": ENTRY_DAY, "open": plan["entry"]["price"], "high": plan["target"]["price"] + 1, "low": plan["stop"]["price"] + 1, "close": plan["entry"]["price"], "volume": 1000}
        state = advance_exit_state(plan, completed_bars=[target], generated_at=ENTRY_GENERATED_AT)
        self.assertEqual((state["state"], state["execution_price"]), ("closed_target", plan["target"]["price"]))

    def test_exit_state_rejects_contradictory_state_reason_and_dates(self):
        plan = self.plans().plans[0]
        target_bar = {
            "date": ENTRY_DAY,
            "open": plan["entry"]["price"],
            "high": plan["target"]["price"] + 1,
            "low": plan["stop"]["price"] + 1,
            "close": plan["entry"]["price"],
            "volume": 1000,
        }
        target = advance_exit_state(
            plan, completed_bars=[target_bar], generated_at=ENTRY_GENERATED_AT
        )
        attacks = (
            {"exit_reason": "stop"},
            {"state": "closed_stop", "exit_reason": "target"},
            {"exit_date": plan["signal_date"]},
            {"exit_date": "2026-09-03"},
        )
        for changes in attacks:
            with self.subTest(changes=changes):
                with self.assertRaises(ContractError):
                    validate_exit_state(refingerprint_exit_state(target, **changes))

    def test_active_exit_state_cannot_fabricate_terminal_execution(self):
        plan = self.plans().plans[0]
        active_bar = {
            "date": ENTRY_DAY,
            "open": plan["entry"]["price"],
            "high": plan["target"]["price"] - 1,
            "low": plan["stop"]["price"] + 1,
            "close": plan["entry"]["price"],
            "volume": 1000,
        }
        active = advance_exit_state(
            plan, completed_bars=[active_bar], generated_at=ENTRY_GENERATED_AT
        )
        before = json.dumps(plain(active), sort_keys=True)
        validate_exit_state(active)
        self.assertEqual(before, json.dumps(plain(active), sort_keys=True))
        attacked = refingerprint_exit_state(active, execution_price=99.0)
        with self.assertRaises(ContractError):
            validate_exit_state(attacked)

    def test_forty_completed_sessions_exit_at_close_without_performance_metrics(self):
        plan = self.plans().plans[0]
        start = date.fromisoformat(ENTRY_DAY)
        bars = []
        for index in range(40):
            day = (start + timedelta(days=index)).isoformat()
            bars.append({"date": day, "open": plan["entry"]["price"], "high": plan["target"]["price"] - 1, "low": plan["stop"]["price"] + 1, "close": 101.0, "volume": 1000})
        state = advance_exit_state(plan, completed_bars=bars, generated_at="2026-10-11T23:00:00Z")
        self.assertEqual((state["state"], state["holding_sessions"], state["execution_price"]), ("closed_time_40d", 40, 101.0))
        self.assertFalse({"return", "r_multiple", "mfe", "mae"} & set(state))

    def test_daily_replay_and_repeated_inputs_are_identical(self):
        expected = self.plans()
        daily = build_shadow_trade_plans(self.ranking, self.support, entry_reads=self.entry_reads, generated_at=ENTRY_GENERATED_AT)
        replay = shadow_trade_plans(self.ranking, self.support, entry_reads=self.entry_reads, generated_at=ENTRY_GENERATED_AT)
        self.assertEqual(expected, self.plans())
        self.assertEqual(daily, replay)

    def test_exit_state_is_append_only_and_rejects_rewritten_prior_bars(self):
        plan = self.plans().plans[0]
        first_bar = {"date": ENTRY_DAY, "open": 100.0, "high": plan["target"]["price"] - 1, "low": plan["stop"]["price"] + 1, "close": 101.0, "volume": 1000}
        first = advance_exit_state(plan, completed_bars=[first_bar], generated_at=ENTRY_GENERATED_AT)
        self.assertEqual(
            advance_exit_state(plan, completed_bars=[first_bar], generated_at="2026-09-03T00:00:00Z", previous_state=first),
            first,
        )
        changed = dict(first_bar)
        changed["close"] = 102.0
        with self.assertRaises(ContractError):
            advance_exit_state(plan, completed_bars=[changed], generated_at="2026-09-03T00:00:00Z", previous_state=first)

    def test_legacy_support_view_cannot_enter_formal_plan_producer(self):
        raw = json.dumps({"available": True, "level": 95, "source": "EMA21"}).encode()
        legacy = adapt_legacy_support_plan_bytes(raw)
        with self.assertRaises(ContractError):
            produce_trade_plans(self.ranking, legacy, entry_reads=self.entry_reads, generated_at=ENTRY_GENERATED_AT)

    def test_append_only_store_and_legacy_adapter(self):
        plan = self.plans().plans[0]
        state = advance_exit_state(plan, completed_bars=[], generated_at=ENTRY_GENERATED_AT)
        with tempfile.TemporaryDirectory() as folder:
            store = ExecutionShadowStore(folder)
            plan_path = store.write_plan(plan)
            state_path = store.write_exit_state(state)
            before = plan_path.read_bytes()
            self.assertEqual(store.write_plan(plan), plan_path)
            self.assertEqual(plan_path.read_bytes(), before)
            self.assertTrue(state_path.exists())
        raw = json.dumps({"available": True, "level": 95, "source": "EMA21"}, sort_keys=True).encode()
        adapted = adapt_legacy_support_plan_bytes(raw)
        self.assertEqual(adapted.path_status, "legacy")
        self.assertEqual(raw, json.dumps({"available": True, "level": 95, "source": "EMA21"}, sort_keys=True).encode())

    def test_deferred_experiments_are_disabled(self):
        plan = self.plans().plans[0]
        self.assertEqual(len(plan["disabled_experiments"]), 5)
        text = json.dumps(plain(plan), sort_keys=True)
        for forbidden in ("return", "mfe", "mae", "excel"):
            self.assertNotIn(f'"{forbidden}"', text.lower())


if __name__ == "__main__":
    unittest.main()
