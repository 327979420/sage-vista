from datetime import date, timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services.contracts import (
    ContractError,
    canonical_fingerprint,
    forward_membership_fingerprint,
    observed_instrument_id,
    stable_instrument_id,
    validate_universe_snapshot,
)
from services.market_data import (
    RepositoryRead,
    UniverseSnapshotStore,
    build_forward_universe_snapshot,
    build_universe_snapshot,
    open_internal_shadow_repository,
    prepare_shadow_consumer_input,
)
from services.scanner.factor_snapshot import (
    build_shadow_snapshot,
    build_snapshot,
    exact_daily_macd_bull_cross,
)
from services.scanner.industry_radar import shadow_etf_rows
from services.scanner.market_etf_watch import shadow_fund_rows
from services.scanner.resonance_tracker import shadow_symbol_rows
from services.scanner.unified_v2_scan import shadow_scan_inputs


ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-01"


def forward_member(symbol="ABC", *, exchange="XNYS", epoch=DAY):
    instrument_id = observed_instrument_id(
        provider="EODHD",
        market="US",
        exchange=exchange,
        provider_code=symbol,
        observed_listing_epoch=epoch,
    )
    return {
        "instrument_id": instrument_id,
        "symbol": symbol,
        "tier": "main",
        "listing_status": "active",
        "membership_source": "complete-forward-list",
        "membership_effective_from": epoch,
        "provider": "EODHD",
        "market": "US",
        "exchange": exchange,
        "provider_code": symbol,
        "observed_listing_epoch": epoch,
        "identity_source": "daily-complete-provider-input",
    }


def qualification(instrument_id, *, as_of=DAY, eligible=True):
    return {
        "instrument_id": instrument_id,
        "as_of": as_of,
        "price_complete": eligible,
        "minimum_price_passed": eligible,
        "dollar_volume_passed": eligible,
        "history_length_passed": eligible,
        "eligible": eligible,
        "inclusion_reasons": ["all-frozen-eligibility-checks-passed"] if eligible else [],
        "exclusion_reasons": [] if eligible else ["price-data-incomplete"],
    }


def forward_snapshot(*, as_of=DAY, members=None, qualifications=None, evidence=None):
    members = list(members or [forward_member()])
    qualifications = list(
        qualifications
        or [qualification(item["instrument_id"], as_of=as_of) for item in members]
    )
    evidence = dict(evidence or {
        "source_id": "provider-active-common-complete-v1",
        "source_as_of": as_of,
        "complete": True,
        "member_count": len(members),
        "content_fingerprint": forward_membership_fingerprint(members),
    })
    return build_forward_universe_snapshot(
        as_of=as_of,
        generated_at=f"{as_of}T23:00:00Z",
        source_version={"membership": "forward-v1", "qualification": "rules-v1"},
        eligibility_rule_version="eligibility-v1",
        effective_from=as_of,
        membership_evidence=evidence,
        members=members,
        qualifications=qualifications,
    )


def legacy_snapshot(
    as_of="2026-08-28", *, path_status="legacy", coverage_status="legacy_observed"
):
    instrument_id = stable_instrument_id(
        provider="EODHD",
        market="US",
        provider_code="ABC",
        listing_lifecycle="observed-cache-era-1",
    )
    member = {
        "instrument_id": instrument_id,
        "symbol": "ABC",
        "tier": "main",
        "listing_status": "active",
        "membership_source": "legacy-observed-test",
        "membership_effective_from": as_of,
    }
    return build_universe_snapshot(
        as_of=as_of,
        generated_at=f"{as_of}T23:00:00Z",
        source_version={"membership": "legacy-observed", "qualification": "legacy"},
        eligibility_rule_version="legacy-v1",
        effective_from=as_of,
        path_status=path_status,
        coverage_status=coverage_status,
        members=[member],
        qualifications=[qualification(instrument_id, as_of=as_of)],
    )


def adjusted_rows(as_of=DAY):
    rows = (
        {"date": "2026-08-28", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "volume": 1000},
        {"date": as_of, "open": 11.0, "high": 12.0, "low": 10.0, "close": 11.5, "volume": 1200},
    )
    return rows


def reader_for(rows):
    def read(instrument_id, *, as_of):
        return RepositoryRead(
            instrument_id=instrument_id,
            as_of=as_of,
            rows=tuple(rows),
            point_in_time_fingerprint=canonical_fingerprint(list(rows)),
        )

    return read


def reader_with_fingerprint(rows, fingerprint):
    def read(instrument_id, *, as_of):
        return RepositoryRead(
            instrument_id=instrument_id,
            as_of=as_of,
            rows=tuple(rows),
            point_in_time_fingerprint=fingerprint,
        )

    return read


def complete_gate_rows():
    end = date.fromisoformat(DAY)
    rows = []
    for index in range(420):
        day = (end - timedelta(days=419 - index)).isoformat()
        close = 90.0 if index == 418 else 110.0 if index == 419 else 100.0
        rows.append({
            "date": day,
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1_000_000,
        })
    return tuple(rows)


def prepare(consumer, *, mode="formal", as_of=DAY, snapshots=None, rows=None):
    return prepare_shadow_consumer_input(
        consumer=consumer,
        mode=mode,
        as_of=as_of,
        snapshots=list(snapshots or [forward_snapshot()]),
        reader=reader_for(rows or adjusted_rows(as_of)),
        generated_at=f"{as_of}T23:05:00Z",
        data_source={"provider": "fixture", "dataset": "adjusted-daily", "market": "US"},
    )


class ForwardUniverseAndConsumerTests(unittest.TestCase):
    def test_consumer_rejects_a_fingerprint_not_derived_from_delivered_rows(self):
        with self.assertRaisesRegex(ContractError, "fingerprint does not match"):
            prepare_shadow_consumer_input(
                consumer="factor_snapshot",
                mode="formal",
                as_of=DAY,
                snapshots=[forward_snapshot()],
                reader=reader_with_fingerprint(
                    adjusted_rows(), "sha256:" + "0" * 64
                ),
                generated_at=f"{DAY}T23:05:00Z",
                data_source={
                    "provider": "fixture",
                    "dataset": "adjusted-daily",
                    "market": "US",
                },
            )

    def test_consumer_rejects_invalid_adjusted_ohlcv_values(self):
        cases = {
            "negative_price": {"close": -1.0},
            "non_finite_price": {"high": float("inf")},
            "nan_price": {"low": float("nan")},
            "negative_volume": {"volume": -1},
            "non_integer_volume": {"volume": 1.5},
        }
        for name, change in cases.items():
            rows = [dict(row) for row in adjusted_rows()]
            rows[-1].update(change)
            with self.subTest(name=name), self.assertRaises(ContractError):
                prepare("factor_snapshot", rows=rows)

    def test_consumer_rejects_impossible_adjusted_ohlc_relationships(self):
        cases = {
            "high_below_close": {"high": 11.0, "close": 11.5},
            "low_above_open": {"low": 11.5, "open": 11.0},
        }
        for name, change in cases.items():
            rows = [dict(row) for row in adjusted_rows()]
            rows[-1].update(change)
            with self.subTest(name=name), self.assertRaisesRegex(
                ContractError, "OHLC relationship"
            ):
                prepare("factor_snapshot", rows=rows)

    def test_delivered_rows_are_detached_and_immutable(self):
        source_rows = [dict(row) for row in adjusted_rows()]
        prepared = prepare("factor_snapshot", rows=source_rows)
        original_snapshot_id = prepared.market_snapshot_id
        original_close = prepared.symbol_rows["ABC"][-1]["close"]

        source_rows[-1]["close"] = 999.0
        self.assertEqual(prepared.symbol_rows["ABC"][-1]["close"], original_close)
        self.assertEqual(prepared.market_snapshot_id, original_snapshot_id)
        with self.assertRaises(TypeError):
            prepared.symbol_rows["ABC"][-1]["close"] = 999.0
        with self.assertRaises(TypeError):
            prepared.symbol_rows["ABC"] = ()
        with self.assertRaises(TypeError):
            prepared.market_snapshot["snapshot_id"] = "changed"

    def test_2026_08_28_repository_sample_is_only_count_and_trigger_evidence(self):
        payload = json.loads((ROOT / "public/daily-factor-snapshot.json").read_bytes())
        self.assertEqual(payload["as_of"], "2026-08-28")
        self.assertEqual(payload["universe_eligible_count"], 1337)
        self.assertEqual(payload["triggered_count"], 31)
        self.assertEqual(len(payload["symbols"]), 31)
        self.assertTrue(all(
            item["trigger"] == {
                "date": "2026-08-28",
                "exact_completed_cross": True,
                "factor_id": "macd.daily_bull_cross",
            }
            for item in payload["symbols"]
        ))
        self.assertNotIn("members", payload)
        self.assertNotIn("qualifications", payload)

    def test_forward_3x_and_legacy_2x_are_both_readable_without_redefinition(self):
        forward = forward_snapshot()
        legacy = legacy_snapshot()
        self.assertEqual(forward["schema_version"], "3.0.0")
        self.assertEqual(legacy["schema_version"], "2.0.0")
        validate_universe_snapshot(forward)
        validate_universe_snapshot(legacy)
        self.assertIn("observed_listing_epoch", forward["members"][0])
        self.assertNotIn("observed_listing_epoch", legacy["members"][0])

    def test_old_2x_formal_can_be_validated_but_not_used_by_the_new_formal_bridge(self):
        old_formal = legacy_snapshot(
            DAY, path_status="formal", coverage_status="complete"
        )
        validate_universe_snapshot(old_formal)
        with self.assertRaisesRegex(ContractError, "requires UniverseSnapshot 3.x"):
            prepare("factor_snapshot", snapshots=[old_formal])

    def test_incomplete_source_or_missing_member_qualification_rejects_whole_day(self):
        member = forward_member()
        cases = (
            {"complete": False},
            {"member_count": 2},
            {"content_fingerprint": "sha256:" + "0" * 64},
        )
        base = {
            "source_id": "complete-source",
            "source_as_of": DAY,
            "complete": True,
            "member_count": 1,
            "content_fingerprint": forward_membership_fingerprint([member]),
        }
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ContractError):
                forward_snapshot(members=[member], evidence={**base, **change})
        with self.assertRaisesRegex(ContractError, "exactly one daily qualification"):
            forward_snapshot(
                members=[member],
                qualifications=[qualification(forward_member("XYZ")["instrument_id"])],
            )

    def test_2026_08_28_formal_is_unavailable_and_never_falls_back_to_legacy(self):
        legacy = legacy_snapshot()
        future = forward_snapshot()
        with self.assertRaisesRegex(ContractError, "universe_unavailable"):
            prepare(
                "factor_snapshot",
                as_of="2026-08-28",
                snapshots=[legacy, future],
                rows=adjusted_rows("2026-08-28")[:1],
            )

    def test_legacy_is_explicit_and_always_discloses_bias(self):
        legacy = legacy_snapshot()
        prepared = prepare(
            "tracker",
            mode="legacy",
            as_of="2026-08-28",
            snapshots=[legacy],
            rows=adjusted_rows("2026-08-28")[:1],
        )
        self.assertEqual(prepared.mode, "legacy")
        self.assertIn("survivorship_bias", prepared.bias_labels)
        self.assertEqual(shadow_symbol_rows(prepared)["ABC"][-1]["date"], "2026-08-28")
        with self.assertRaisesRegex(ContractError, "universe_unavailable"):
            prepare(
                "factor_snapshot",
                mode="formal",
                as_of="2026-08-28",
                snapshots=[legacy],
                rows=adjusted_rows("2026-08-28")[:1],
            )

    def test_daily_and_backtest_share_the_same_point_in_time_identity(self):
        snapshot = forward_snapshot()
        daily = prepare("factor_snapshot", snapshots=[snapshot])
        backtest = prepare("unified_v2_backtest", snapshots=[snapshot])
        self.assertEqual(daily.universe_id, backtest.universe_id)
        self.assertEqual(daily.market_snapshot_id, backtest.market_snapshot_id)
        self.assertEqual(daily.adjustment_policy, backtest.adjustment_policy)
        self.assertEqual(
            build_shadow_snapshot(daily)["input_audit"]["market_snapshot_id"],
            shadow_scan_inputs(backtest)["input_audit"]["market_snapshot_id"],
        )

    def test_daily_shadow_preserves_ohlcv_gate_and_factor_builder_inputs(self):
        rows = complete_gate_rows()
        daily = prepare("factor_snapshot", rows=rows)
        backtest = prepare("unified_v2_backtest", rows=rows)
        self.assertEqual(daily.symbol_rows, backtest.symbol_rows)
        self.assertEqual(
            exact_daily_macd_bull_cross(daily.symbol_rows["ABC"]),
            exact_daily_macd_bull_cross(backtest.symbol_rows["ABC"]),
        )
        shadow = build_shadow_snapshot(daily)["snapshot"]
        self.assertEqual(shadow, build_snapshot({"ABC": rows}, DAY))

    def test_market_etf_hook_accepts_a_complete_injected_fund_set(self):
        from services.scanner.market_etf_watch import FUNDS

        members = [forward_member(symbol, exchange="ARCX") for symbol in FUNDS]
        snapshot = forward_snapshot(members=members)
        prepared = prepare("market_etf", snapshots=[snapshot])
        self.assertEqual(set(shadow_fund_rows(prepared)), set(FUNDS))

    def test_consumer_hooks_do_not_accept_another_consumers_input(self):
        prepared = prepare("industry_etf")
        self.assertEqual(shadow_etf_rows(prepared)["ABC"][-1]["date"], DAY)
        with self.assertRaisesRegex(ContractError, "different consumer"):
            shadow_symbol_rows(prepared)
        with self.assertRaisesRegex(ContractError, "different consumer"):
            shadow_fund_rows(prepared)

    def test_future_market_rows_and_future_identity_metadata_fail_closed(self):
        future_rows = adjusted_rows() + (
            {"date": "2026-09-02", "open": 12.0, "high": 13.0, "low": 11.0, "close": 12.5, "volume": 1300},
        )
        with self.assertRaisesRegex(ContractError, "future rows"):
            prepare("unified_v2_backtest", rows=future_rows)
        future_identity = forward_member(epoch="2026-09-02")
        future_identity["membership_effective_from"] = DAY
        with self.assertRaisesRegex(ContractError, "cannot predate"):
            forward_snapshot(members=[future_identity])

    def test_reappearance_or_exchange_change_creates_a_new_identity_without_overwrite(self):
        original = forward_member()
        relisted = forward_member(epoch="2026-09-02")
        moved = forward_member(exchange="XNAS")
        self.assertNotEqual(original["instrument_id"], relisted["instrument_id"])
        self.assertNotEqual(original["instrument_id"], moved["instrument_id"])
        first = forward_snapshot(members=[original])
        second = forward_snapshot(
            as_of="2026-09-02",
            members=[relisted],
            qualifications=[qualification(relisted["instrument_id"], as_of="2026-09-02")],
        )
        with tempfile.TemporaryDirectory() as folder:
            store = UniverseSnapshotStore(folder)
            first_path = store.save(first)
            first_bytes = first_path.read_bytes()
            store.save(second)
            self.assertEqual(first_path.read_bytes(), first_bytes)

    def test_consumer_repository_root_cannot_be_injected_by_env_cwd_or_argument(self):
        class Source:
            calls = 0

            def fetch(self, instrument_id, dates):
                self.calls += 1
                return []

        source = Source()
        expected = (ROOT / "work/m02-shadow/market-data").resolve()
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"SAGE_VISTA_WORKSPACE_ROOT": folder}
        ):
            os.chdir(folder)
            try:
                repository = open_internal_shadow_repository(source)
            finally:
                os.chdir(original_cwd)
        self.assertEqual(repository._root, expected)
        self.assertEqual(source.calls, 0)
        with self.assertRaises(TypeError):
            open_internal_shadow_repository(source, workspace_root=folder)
        self.assertFalse((Path(folder) / "work").exists())


if __name__ == "__main__":
    unittest.main()
