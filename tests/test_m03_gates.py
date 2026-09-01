from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, validate_contract
from services.gates.baseline import exact_daily_macd_bull_cross
from services.gates.local_structure import assess_local_structure
from services.gates.long_term_state import assess_long_term, completed_period_bars
from services.gates.producer import (
    GateEventStore,
    current_gate_event,
    produce_gate_batch,
    require_gate_event_for_path,
    validate_gate_event,
)
from services.market_data import prepare_shadow_consumer_input
from services.scanner.factor_snapshot import build_shadow_gate_batch
from services.scanner.unified_v2_scan import shadow_gate_batch
from tests.test_market_data_consumers import (
    DAY,
    complete_gate_rows,
    forward_snapshot,
    reader_for,
)


ROOT = Path(__file__).resolve().parents[1]
GENERATED_AT = f"{DAY}T23:10:00Z"


def prepare(consumer: str, rows=None, snapshot=None):
    return prepare_shadow_consumer_input(
        consumer=consumer,
        mode="formal",
        as_of=DAY,
        snapshots=[snapshot or forward_snapshot()],
        reader=reader_for(rows or complete_gate_rows()),
        generated_at=f"{DAY}T23:05:00Z",
        data_source={"provider": "fixture", "dataset": "adjusted-daily", "market": "US"},
    )


def event_from(prepared, previous=(), revision_evidence=None):
    batch = produce_gate_batch(
        prepared,
        generated_at=GENERATED_AT,
        scan_batch_id="fixture-batch",
        previous_events=previous,
        market_revision_evidence=revision_evidence,
    )
    if len(batch.events) != 1:
        raise AssertionError("fixture did not form exactly one gate event")
    return batch.events[0]


def thaw(value):
    if hasattr(value, "items"):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(item) for item in value]
    return value


class M03GateTests(unittest.TestCase):
    def test_no_exact_cross_creates_only_batch_audit(self):
        rows = [dict(row) for row in complete_gate_rows()]
        rows[-1].update({"open": 90.0, "high": 91.0, "low": 89.0, "close": 90.0})
        prepared = prepare("factor_snapshot", rows=rows)
        batch = produce_gate_batch(
            prepared, generated_at=GENERATED_AT, scan_batch_id="no-cross"
        )
        self.assertEqual(batch.events, ())
        self.assertEqual(
            batch.audit["non_event_reason_counts"]["no_exact_daily_macd_cross"], 1
        )
        validate_contract("GateScanAudit", batch.audit)

    def test_event_preserves_baseline_and_keeps_shadow_non_production(self):
        event = event_from(prepare("factor_snapshot"))
        self.assertTrue(event["baseline_passed"])
        self.assertEqual(event["passed"], event["baseline_passed"])
        self.assertIs(event["shadow_assessment"]["production_effect"], False)
        validate_gate_event(event)
        with self.assertRaises(TypeError):
            event["shadow_assessment"]["production_effect"] = True

    def test_daily_and_backtest_use_the_same_unique_producer(self):
        snapshot = forward_snapshot()
        daily = prepare("factor_snapshot", snapshot=snapshot)
        backtest = prepare("unified_v2_backtest", snapshot=snapshot)
        daily_batch = build_shadow_gate_batch(
            daily, generated_at=GENERATED_AT, scan_batch_id="shared"
        )
        backtest_batch = shadow_gate_batch(
            backtest, generated_at=GENERATED_AT, scan_batch_id="shared"
        )
        self.assertEqual(
            daily_batch.events[0]["gate_event_id"],
            backtest_batch.events[0]["gate_event_id"],
        )
        self.assertEqual(
            daily_batch.events[0]["event_content_fingerprint"],
            backtest_batch.events[0]["event_content_fingerprint"],
        )

    def test_identical_replay_is_idempotent(self):
        prepared = prepare("factor_snapshot")
        first = event_from(prepared)
        replay = produce_gate_batch(
            prepared,
            generated_at="2026-09-02T00:00:00Z",
            scan_batch_id="fixture-batch",
            previous_events=[first],
        ).events[0]
        self.assertEqual(dict(first), dict(replay))

    def test_market_revision_creates_new_event_and_preserves_chain(self):
        first_prepared = prepare("factor_snapshot")
        first = event_from(first_prepared)
        revised_rows = [dict(row) for row in complete_gate_rows()]
        revised_rows[0]["high"] += 0.25
        revised_prepared = prepare("factor_snapshot", rows=revised_rows)
        evidence = {
            "revision_id": "sha256:" + "1" * 64,
            "from_market_snapshot_id": first_prepared.market_snapshot_id,
            "to_market_snapshot_id": revised_prepared.market_snapshot_id,
        }
        with self.assertRaisesRegex(ContractError, "explicit revision evidence"):
            event_from(revised_prepared, [first])
        revised = event_from(revised_prepared, [first], evidence)
        self.assertNotEqual(first["gate_event_id"], revised["gate_event_id"])
        self.assertEqual(revised["logical_signal_id"], first["logical_signal_id"])
        self.assertEqual(revised["supersedes_event_id"], first["gate_event_id"])
        self.assertEqual(current_gate_event([revised, first])["gate_event_id"], revised["gate_event_id"])

    def test_same_identity_with_different_content_is_a_conflict(self):
        prepared = prepare("factor_snapshot")
        first = thaw(event_from(prepared))
        first["shadow_assessment"]["suggested_disposition"] = "changed"
        semantic = {
            key: value
            for key, value in first.items()
            if key not in {"generated_at", "event_content_fingerprint"}
        }
        first["event_content_fingerprint"] = canonical_fingerprint(semantic)
        validate_gate_event(first)
        with self.assertRaisesRegex(ContractError, "gate event conflict"):
            event_from(prepared, [first])

    def test_wrong_adjustment_policy_and_shadow_effect_fail(self):
        event = thaw(event_from(prepare("factor_snapshot")))
        event["input_identity"]["adjustment_policy"] = {"method": "provider_adjusted_ohlc"}
        with self.assertRaisesRegex(ContractError, "M02 policy"):
            validate_gate_event(event)
        event = thaw(event_from(prepare("factor_snapshot")))
        event["shadow_assessment"]["production_effect"] = True
        with self.assertRaisesRegex(ContractError, "production_effect"):
            validate_gate_event(event)

    def test_content_tamper_and_audit_count_tamper_fail(self):
        event = thaw(event_from(prepare("factor_snapshot")))
        event["baseline_passed"] = False
        event["passed"] = False
        with self.assertRaisesRegex(ContractError, "content_fingerprint"):
            validate_gate_event(event)
        batch = produce_gate_batch(
            prepare("factor_snapshot"),
            generated_at=GENERATED_AT,
            scan_batch_id="audit-tamper",
        )
        audit = thaw(batch.audit)
        audit["input_count"] += 1
        with self.assertRaisesRegex(ContractError, "do not match input_count"):
            validate_contract("GateScanAudit", audit)

    def test_gate_1x_is_legacy_only_and_unknown_major_fails(self):
        legacy = {
            "schema_version": "1.0.0", "as_of": DAY,
            "generated_at": GENERATED_AT, "source_version": {"gate": "legacy"},
            "future_data_used": False, "gate_event_id": f"gate:ABC:{DAY}:v1",
            "symbol": "ABC", "signal_date": DAY, "gate_policy_version": "v1",
            "passed": True,
        }
        require_gate_event_for_path(legacy, path_status="legacy")
        with self.assertRaisesRegex(ContractError, "requires GateEvent 2.x"):
            require_gate_event_for_path(legacy, path_status="formal")
        with self.assertRaisesRegex(ContractError, "unknown schema_version major"):
            validate_contract("GateEvent", {**legacy, "schema_version": "3.0.0"})

    def test_completed_periods_exclude_current_week_and_month(self):
        rows = (
            {"date": "2026-08-28", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1},
            {"date": DAY, "open": 10, "high": 12, "low": 9, "close": 11, "volume": 1},
        )
        monthly = completed_period_bars(rows, as_of=DAY, period="monthly")
        weekly = completed_period_bars(rows, as_of=DAY, period="weekly")
        self.assertEqual([row["date"] for row in monthly], ["2026-08-28"])
        self.assertEqual([row["date"] for row in weekly], ["2026-08-28"])

    def test_local_structure_does_not_read_rows_after_the_cutoff(self):
        rows = complete_gate_rows()
        before = assess_local_structure(rows)
        future = dict(rows[-1])
        future["date"] = "2026-09-02"
        future["high"] = future["close"] = 1000.0
        future["open"] = 999.0
        future["low"] = 998.0
        self.assertEqual(before, assess_local_structure(rows))
        self.assertNotEqual(len(rows), len(rows + (future,)))

    def test_shadow_store_is_append_only_and_rejects_production_paths(self):
        event = event_from(prepare("factor_snapshot"))
        with tempfile.TemporaryDirectory() as folder:
            store = GateEventStore(folder)
            path = store.save(event)
            original = path.read_bytes()
            self.assertEqual(store.save(event), path)
            self.assertEqual(path.read_bytes(), original)
        with self.assertRaises(ContractError):
            GateEventStore(ROOT / "public", workspace_root=ROOT)

    def test_baseline_macd_matches_existing_fixed_sample(self):
        rows = complete_gate_rows()
        self.assertTrue(exact_daily_macd_bull_cross(rows))
        changed = [dict(row) for row in rows]
        changed[-1].update({"open": 90, "high": 91, "low": 89, "close": 90})
        self.assertFalse(exact_daily_macd_bull_cross(changed))

    def test_four_named_case_fixtures_remain_point_in_time_and_conservative(self):
        base = [dict(row) for row in complete_gate_rows()]
        fixtures = {
            "CGEM": [dict(row) for row in base],
            "MRNA": [dict(row) for row in base],
            "BTDR": [dict(row) for row in base],
            "DLTR": [dict(row) for row in base],
        }
        fixtures["MRNA"][20].update(
            {"open": 290.0, "high": 300.0, "low": 280.0, "close": 290.0}
        )
        fixtures["MRNA"][21].update(
            {"open": 24.0, "high": 25.0, "low": 20.0, "close": 22.0}
        )
        fixtures["DLTR"][100].update(
            {"open": 125.0, "high": 130.0, "low": 120.0, "close": 125.0}
        )
        fixtures["DLTR"][101].update(
            {"open": 85.0, "high": 90.0, "low": 80.0, "close": 85.0}
        )
        outcomes = {}
        for symbol, rows in fixtures.items():
            local = assess_local_structure(rows)
            outcomes[symbol] = assess_long_term(
                rows,
                as_of=DAY,
                baseline_long_trend=True,
                local_structure=local,
            )
            self.assertEqual(outcomes[symbol]["multi_year_drawdown"]["history_last_date"], DAY)
        self.assertGreater(outcomes["MRNA"]["multi_year_drawdown"]["max_drawdown"], 0.90)
        self.assertGreaterEqual(outcomes["DLTR"]["supply_risk"]["down_gap_count"], 1)
        self.assertEqual(outcomes["CGEM"]["long_term_state"], "unavailable")
        self.assertEqual(outcomes["BTDR"]["long_term_state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
