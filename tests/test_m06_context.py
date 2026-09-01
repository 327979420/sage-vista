from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
from types import MappingProxyType
import unittest

from services.context import (
    evaluate_etf_state,
    produce_market_industry_context,
    select_membership_snapshot,
    validate_etf_registry,
    validate_market_industry_context,
    validate_membership_registry,
)
from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, validate_contract
from services.factors import produce_technical_evidence
from services.market_data import RepositoryRead, prepare_shadow_consumer_input
from services.scanner.factor_snapshot import build_shadow_market_industry_context
from services.scanner.unified_v2_scan import shadow_market_industry_context
from services.selectors import produce_model_assessments
from tests.test_m03_gates import GENERATED_AT, event_from
from tests.test_market_data_consumers import (
    DAY,
    complete_gate_rows,
    forward_member,
    forward_snapshot,
    qualification,
)


ROOT = Path(__file__).resolve().parents[1]


def price_rows(*, end=DAY, count=300, final_multiplier=1.0):
    start = date.fromisoformat(end) - timedelta(days=count - 1)
    rows = []
    for offset in range(count):
        close = (70.0 + offset * 0.1) * (final_multiplier if offset == count - 1 else 1.0)
        rows.append({
            "date": (start + timedelta(days=offset)).isoformat(),
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000_000,
        })
    return tuple(rows)


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


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value


class M06ContextTests(unittest.TestCase):
    def setUp(self):
        avgo = forward_member("AVGO")
        snapshot = forward_snapshot(members=[avgo])
        self.stock = prepare_shadow_consumer_input(
            consumer="factor_snapshot",
            mode="formal",
            as_of=DAY,
            snapshots=[snapshot],
            reader=reader_map({avgo["instrument_id"]: complete_gate_rows()}),
            generated_at=f"{DAY}T23:05:00Z",
            data_source={"provider": "fixture", "dataset": "adjusted-daily", "market": "US"},
        )
        self.event = event_from(self.stock)
        self.evidence = produce_technical_evidence(
            self.stock, gate_events=(self.event,), generated_at=GENERATED_AT
        )
        self.assessments = produce_model_assessments(
            self.stock,
            gate_events=(self.event,),
            technical_evidence=self.evidence,
            generated_at=GENERATED_AT,
        )
        etf_members = [forward_member(symbol) for symbol in ("QQQ", "SOXX", "BOTZ")]
        etf_snapshot = forward_snapshot(members=etf_members)
        rows_by_id = {
            item["instrument_id"]: price_rows(final_multiplier=1.01 if item["symbol"] == "SOXX" else 1.0)
            for item in etf_members
        }
        self.etf = prepare_shadow_consumer_input(
            consumer="market_etf",
            mode="formal",
            as_of=DAY,
            snapshots=[etf_snapshot],
            reader=reader_map(rows_by_id),
            generated_at=f"{DAY}T23:05:00Z",
            data_source={"provider": "fixture", "dataset": "adjusted-daily", "market": "US"},
        )
        self.registry = {
            "schema_version": "1.0.0",
            "registry_version": "test-etf-registry-1.0.0",
            "as_of_date": DAY,
            "etfs": [
                self.etf_entry("QQQ", "broad_market", "nasdaq_100", "1"),
                self.etf_entry("SOXX", "industry", "semiconductors", "2"),
                self.etf_entry("BOTZ", "theme", "robotics_automation", "3"),
            ],
        }
        self.memberships = {
            "schema_version": "1.0.0",
            "mapping_registry_version": "test-memberships-1.0.0",
            "snapshots": [
                self.mapping("SOXX", "soxx-v1"),
                self.mapping("BOTZ", "botz-v1"),
            ],
        }

    def etf_entry(self, symbol, category, label, digit):
        return {
            "symbol": symbol,
            "etf_id": "etf:sha256:" + digit * 64,
            "category": category,
            "label": label,
            "issuer": "fixture issuer",
            "membership_source_url": f"https://example.test/{symbol}",
            "membership_as_of_date": DAY,
            "formal_current_forward_eligible": True,
            "historical_membership_evidence": "stable_instrument_id",
        }

    def mapping(self, symbol, mapping_id, *, effective=DAY, instrument_id=None):
        return {
            "mapping_id": mapping_id,
            "etf_symbol": symbol,
            "membership_as_of_date": effective,
            "effective_from": effective,
            "path_status": "formal",
            "formal_eligible": True,
            "identity_status": "stable_instrument_id",
            "source": {"provider": "official fixture", "url": f"https://example.test/{symbol}"},
            "bias_labels": [],
            "members_source_count": 1,
            "unresolved_member_count": 0,
            "members": [{
                "instrument_id": instrument_id or self.event["instrument_id"],
                "symbol": "AVGO",
                "weight": 0.05,
            }],
        }

    def produce(self, **changes):
        values = {
            "gate_events": (self.event,),
            "technical_evidence": self.evidence,
            "model_assessments": self.assessments,
            "etf_registry": self.registry,
            "membership_registry": self.memberships,
            "generated_at": GENERATED_AT,
        }
        values.update(changes)
        return produce_market_industry_context(self.stock, self.etf, **values)

    def test_soxx_avgo_botz_and_multiple_memberships_are_preserved(self):
        batch = self.produce()
        self.assertEqual(len(batch.contexts), 1)
        links = batch.contexts[0]["membership_links"]
        self.assertEqual({item["etf_symbol"] for item in links}, {"QQQ", "SOXX", "BOTZ"})
        self.assertEqual(
            {item["mapping_id"] for item in links if item["etf_symbol"] != "QQQ"},
            {"soxx-v1", "botz-v1"},
        )
        validate_market_industry_context(batch.contexts[0])

    def test_membership_selection_is_point_in_time_and_append_only(self):
        older = self.mapping("SOXX", "soxx-old", effective="2026-08-30")
        selected = select_membership_snapshot(
            [older, self.mapping("SOXX", "soxx-new")],
            etf_symbol="SOXX", as_of="2026-08-31", path_status="formal",
        )
        self.assertEqual(selected["mapping_id"], "soxx-old")
        with self.assertRaisesRegex(ContractError, "membership_unavailable"):
            select_membership_snapshot(
                [self.mapping("SOXX", "future")],
                etf_symbol="SOXX", as_of="2026-08-31", path_status="formal",
            )
        conflict = dict(self.mapping("SOXX", "other"))
        with self.assertRaisesRegex(ContractError, "conflicting same-date"):
            validate_membership_registry({
                "schema_version": "1.0.0",
                "mapping_registry_version": "v1",
                "snapshots": [self.mapping("SOXX", "first"), conflict],
            })

    def test_repository_ticker_only_evidence_is_legacy_not_formal(self):
        registry = json.loads((ROOT / "data/context/etf-memberships-v1.json").read_text())
        validate_membership_registry(registry)
        with self.assertRaisesRegex(ContractError, "membership_unavailable"):
            select_membership_snapshot(
                registry["snapshots"], etf_symbol="SOXX", as_of=DAY, path_status="formal"
            )
        legacy = select_membership_snapshot(
            registry["snapshots"], etf_symbol="SOXX", as_of=DAY, path_status="legacy"
        )
        self.assertIn("current_membership_bias", legacy["bias_labels"])

    def test_etf_state_boundaries_and_incomplete_history(self):
        item = self.registry["etfs"][1]
        market_id = self.etf.market_snapshot_id
        unavailable = evaluate_etf_state(
            price_rows(count=100), as_of=DAY, etf_id=item["etf_id"], market_snapshot_id=market_id
        )
        self.assertEqual(unavailable["status"], "unavailable")
        base = list(price_rows())
        prior_high = max(row["high"] for row in base[-61:-1])
        base[-1] = {**base[-1], "open": prior_high + 0.5, "high": prior_high + 1.0,
                    "low": prior_high, "close": prior_high + 0.5}
        breakout = evaluate_etf_state(
            base, as_of=DAY, etf_id=item["etf_id"], market_snapshot_id=market_id
        )
        self.assertEqual(breakout["status"], "confirmed_breakout")
        near = list(price_rows())
        prior_high = max(row["high"] for row in near[-61:-1])
        near[-1] = {**near[-1], "open": prior_high * 0.99, "high": prior_high,
                    "low": prior_high * 0.98, "close": prior_high * 0.99}
        self.assertEqual(
            evaluate_etf_state(near, as_of=DAY, etf_id=item["etf_id"], market_snapshot_id=market_id)["status"],
            "near_breakout",
        )

    def test_future_or_unfinished_row_cannot_change_point_in_time_state(self):
        item = self.registry["etfs"][1]
        rows = list(price_rows())
        baseline = evaluate_etf_state(
            rows, as_of=DAY, etf_id=item["etf_id"],
            market_snapshot_id=self.etf.market_snapshot_id,
        )
        future = date.fromisoformat(DAY) + timedelta(days=1)
        rows.append({
            "date": future.isoformat(), "open": 1000.0, "high": 1100.0,
            "low": 900.0, "close": 1050.0, "volume": 9_000_000,
        })
        repeated = evaluate_etf_state(
            rows, as_of=DAY, etf_id=item["etf_id"],
            market_snapshot_id=self.etf.market_snapshot_id,
        )
        self.assertEqual(baseline, repeated)

    def test_missing_etf_market_evidence_fails_closed(self):
        broken = type(self.etf)(
            **{**self.etf.__dict__, "symbol_rows": freeze({"QQQ": list(self.etf.symbol_rows["QQQ"])})}
        )
        with self.assertRaisesRegex(ContractError, "missing for BOTZ|missing for SOXX"):
            produce_market_industry_context(
                self.stock, broken,
                gate_events=(self.event,), technical_evidence=self.evidence,
                model_assessments=self.assessments, etf_registry=self.registry,
                membership_registry=self.memberships, generated_at=GENERATED_AT,
            )

    def test_etf_state_is_calculated_once_and_input_is_deterministic(self):
        calls = {}
        def counted(rows, **kwargs):
            calls[kwargs["etf_id"]] = calls.get(kwargs["etf_id"], 0) + 1
            return evaluate_etf_state(rows, **kwargs)
        first = self.produce(state_evaluator=counted)
        self.assertEqual(set(calls.values()), {1})
        reversed_registry = {**self.registry, "etfs": list(reversed(self.registry["etfs"]))}
        reversed_memberships = {
            **self.memberships, "snapshots": list(reversed(self.memberships["snapshots"]))
        }
        second = self.produce(
            etf_registry=reversed_registry, membership_registry=reversed_memberships
        )
        self.assertEqual(first.batch_id, second.batch_id)
        self.assertEqual(first.contexts, second.contexts)

    def test_upstream_facts_are_references_and_output_is_score_free(self):
        context = self.produce().contexts[0]
        self.assertEqual(context["gate_event_id"], self.event["gate_event_id"])
        self.assertEqual(
            list(context["technical_evidence_ids"]),
            sorted(item["evidence_id"] for item in self.evidence.evidence),
        )
        self.assertEqual(
            list(context["model_assessment_ids"]),
            sorted(item["assessment_id"] for item in self.assessments.assessments),
        )
        self.assertFalse(context["production_effect"])
        encoded = json.dumps({key: str(value) for key, value in context.items()})
        for forbidden in ('"score"', '"rank"', '"trade_plan"', '"entry"', '"stop"'):
            self.assertNotIn(forbidden, encoded)

    def test_legacy_or_v1_context_cannot_enter_formal(self):
        legacy = {
            "schema_version": "1.0.0", "as_of": DAY, "generated_at": GENERATED_AT,
            "source_version": {"legacy": "v1"}, "future_data_used": False,
            "context_id": "context:legacy", "context_type": "industry",
            "status": "available", "evidence": {},
        }
        validate_contract("ContextSnapshot", legacy)
        with self.assertRaisesRegex(ContractError, "2.x"):
            validate_market_industry_context(legacy)
        legacy_input = type(self.stock)(**{**self.stock.__dict__, "mode": "legacy", "bias_labels": ("legacy",)})
        with self.assertRaisesRegex(ContractError, "formal M02 inputs"):
            produce_market_industry_context(
                legacy_input, self.etf,
                gate_events=(self.event,), technical_evidence=self.evidence,
                model_assessments=self.assessments, etf_registry=self.registry,
                membership_registry=self.memberships, generated_at=GENERATED_AT,
            )

    def test_daily_and_replay_call_the_same_context_producer(self):
        replay_stock = type(self.stock)(
            **{**self.stock.__dict__, "consumer": "unified_v2_backtest"}
        )
        replay_etf = type(self.etf)(**{**self.etf.__dict__, "consumer": "industry_etf"})
        daily = build_shadow_market_industry_context(
            self.stock, self.etf, gate_events=(self.event,),
            technical_evidence=self.evidence, model_assessments=self.assessments,
            etf_registry=self.registry, membership_registry=self.memberships,
            generated_at=GENERATED_AT,
        )
        replay = shadow_market_industry_context(
            replay_stock, replay_etf, gate_events=(self.event,),
            technical_evidence=self.evidence, model_assessments=self.assessments,
            etf_registry=self.registry, membership_registry=self.memberships,
            generated_at=GENERATED_AT,
        )
        self.assertEqual(daily.batch_id, replay.batch_id)
        self.assertEqual(daily.contexts, replay.contexts)

    def test_registry_is_selected_and_typos_are_not_registered(self):
        registry = json.loads((ROOT / "data/context/etf-registry-v1.json").read_text())
        validate_etf_registry(registry)
        symbols = {item["symbol"] for item in registry["etfs"]}
        self.assertEqual(symbols, {"SPY", "QQQ", "IWM", "XLE", "SOXX", "BOTZ"})
        self.assertNotIn("BOTT", symbols)
        self.assertNotIn("XOXX", symbols)

    def test_only_context_package_creates_formal_context_identity(self):
        marker = 'payload["context_id"] = "context:" + canonical_fingerprint'
        creators = {
            str(path.relative_to(ROOT))
            for path in (ROOT / "services").rglob("*.py")
            if marker in path.read_text()
        }
        self.assertEqual(creators, {"services/context/producer.py"})
        text = "\n".join(path.read_text() for path in (ROOT / "services/context").glob("*.py"))
        for forbidden in (
            "produce_gate_batch", "produce_technical_evidence", "produce_model_assessments",
            "evaluate_all_factors", "exact_daily_macd_bull_cross",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
