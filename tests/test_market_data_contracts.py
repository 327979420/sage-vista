import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

from services.contracts import (
    ContractError,
    canonical_fingerprint,
    market_data_snapshot_id,
    revision_record,
    select_universe_snapshot,
    stable_instrument_id,
    universe_snapshot_id,
    validate_market_data_snapshot,
    validate_revision_chain,
    validate_universe_snapshot,
)
from services.market_data import (
    ADJUSTMENT_POLICY,
    adjusted_point_in_time_rows,
    bars_fingerprint,
    read_legacy_cache,
    validate_raw_rows,
)
from services.scanner.macd_factor_backtest import adjusted_rows as legacy_adjusted_rows


def raw_rows():
    return [
        {
            "date": "2026-08-27",
            "open": 90.0,
            "high": 110.0,
            "low": 80.0,
            "close": 100.0,
            "adjusted_close": 50.0,
            "volume": 1000,
        },
        {
            "date": "2026-08-28",
            "open": 51.0,
            "high": 53.0,
            "low": 49.0,
            "close": 52.0,
            "adjusted_close": 52.0,
            "volume": 1200,
        },
        {
            "date": "2026-08-31",
            "open": 54.0,
            "high": 56.0,
            "low": 53.0,
            "close": 55.0,
            "adjusted_close": 55.0,
            "volume": 1400,
        },
    ]


def member(symbol="ABC", lifecycle="listing-1", tier="main"):
    return {
        "instrument_id": stable_instrument_id(
            provider="EODHD", market="US", provider_code=symbol, listing_lifecycle=lifecycle
        ),
        "symbol": symbol,
        "tier": tier,
        "listing_status": "active",
    }


def universe(**changes):
    members = changes.pop("members", [member()])
    payload = {
        "schema_version": "1.0.0",
        "as_of": "2026-08-28",
        "generated_at": "2026-08-28T23:00:00Z",
        "source_version": {"provider": "EODHD-symbol-list", "policy": "m02-shadow-1"},
        "future_data_used": False,
        "members": members,
        "eligibility_rule_version": "legacy-current-rules-1",
        "effective_from": "2026-08-28",
        "path_status": "formal",
        "coverage_status": "complete",
    }
    payload.update(changes)
    payload["universe_id"] = universe_snapshot_id(
        as_of=payload["as_of"],
        effective_from=payload["effective_from"],
        source_version=payload["source_version"],
        eligibility_rule_version=payload["eligibility_rule_version"],
        members=payload["members"],
    )
    return payload


def market_snapshot():
    instrument = member()
    rows = adjusted_point_in_time_rows(raw_rows(), as_of="2026-08-28")
    payload = {
        "schema_version": "1.0.0",
        "as_of": "2026-08-28",
        "generated_at": "2026-08-28T23:05:00Z",
        "source_version": {"provider_adapter": "eodhd-shadow-1", "raw_schema": "eodhd-eod-v1"},
        "future_data_used": False,
        "market": "US",
        "symbols": [{
            "instrument_id": instrument["instrument_id"],
            "symbol": instrument["symbol"],
            "row_count": len(rows),
            "first_date": rows[0]["date"],
            "max_returned_date": rows[-1]["date"],
            "content_fingerprint": bars_fingerprint(rows),
        }],
        "adjustment_policy": ADJUSTMENT_POLICY,
        "data_source": {"provider": "EODHD", "dataset": "US EOD"},
        "universe_id": universe()["universe_id"],
        "raw_revision": canonical_fingerprint(raw_rows()),
        "max_returned_date": rows[-1]["date"],
    }
    payload["snapshot_id"] = market_data_snapshot_id(payload)
    return payload


class MarketDataContractTests(unittest.TestCase):
    def test_as_of_is_required_and_future_rows_never_escape(self):
        with self.assertRaises(TypeError):
            adjusted_point_in_time_rows(raw_rows())
        rows = adjusted_point_in_time_rows(raw_rows(), as_of="2026-08-28")
        self.assertEqual([row["date"] for row in rows], ["2026-08-27", "2026-08-28"])
        self.assertTrue(all(row["date"] <= "2026-08-28" for row in rows))

    def test_invalid_duplicate_unordered_and_abnormal_rows_fail_closed(self):
        cases = {}
        missing = raw_rows()
        del missing[0]["adjusted_close"]
        cases["missing"] = missing
        duplicate = raw_rows()
        duplicate[1]["date"] = duplicate[0]["date"]
        cases["duplicate"] = duplicate
        unordered = raw_rows()
        unordered[0], unordered[1] = unordered[1], unordered[0]
        cases["unordered"] = unordered
        impossible = raw_rows()
        impossible[0]["high"] = 89.0
        cases["impossible_ohlc"] = impossible
        non_finite = raw_rows()
        non_finite[0]["close"] = float("nan")
        cases["non_finite"] = non_finite
        for name, rows in cases.items():
            with self.subTest(name=name), self.assertRaises(ContractError):
                validate_raw_rows(rows)

    def test_adjustment_formula_matches_current_valid_row_behavior(self):
        raw = raw_rows()[:2]
        current = legacy_adjusted_rows(copy.deepcopy(raw))
        shadow = list(adjusted_point_in_time_rows(copy.deepcopy(raw), as_of="2026-08-28"))
        self.assertEqual(shadow, current)
        self.assertEqual(shadow[0]["open"], 45.0)
        self.assertEqual(shadow[0]["close"], 50.0)

    def test_stable_ids_and_fingerprints_ignore_generation_order(self):
        first = stable_instrument_id(
            provider="EODHD", market="US", provider_code="ABC", listing_lifecycle="listing-1"
        )
        second = stable_instrument_id(
            provider="EODHD", market="US", provider_code="ABC", listing_lifecycle="listing-1"
        )
        self.assertEqual(first, second)
        with self.assertRaises(ContractError):
            stable_instrument_id(
                provider="EODHD", market="US", provider_code="ABC", listing_lifecycle="unknown"
            )
        self.assertEqual(canonical_fingerprint({"b": 2, "a": 1}), canonical_fingerprint({"a": 1, "b": 2}))

        left, right = member("ABC", "one"), member("XYZ", "two")
        first_universe = universe_snapshot_id(
            as_of="2026-08-28",
            effective_from="2026-08-28",
            source_version={"source": "fixed"},
            eligibility_rule_version="v1",
            members=[left, right],
        )
        second_universe = universe_snapshot_id(
            as_of="2026-08-28",
            effective_from="2026-08-28",
            source_version={"source": "fixed"},
            eligibility_rule_version="v1",
            members=[right, left],
        )
        self.assertEqual(first_universe, second_universe)

    def test_universe_contract_rejects_tampering_and_duplicate_identity(self):
        payload = universe()
        validate_universe_snapshot(payload)
        payload["members"][0]["symbol"] = "CHANGED"
        with self.assertRaises(ContractError):
            validate_universe_snapshot(payload)
        with self.assertRaises(ContractError):
            universe(members=[member(), member()])

    def test_formal_history_fails_closed_without_point_in_time_universe(self):
        future = universe(as_of="2026-08-31", effective_from="2026-08-31")
        with self.assertRaisesRegex(ContractError, "universe_unavailable"):
            select_universe_snapshot([future], as_of="2026-08-28", path_status="formal")
        self.assertIsNone(
            select_universe_snapshot([future], as_of="2026-08-28", path_status="legacy")
        )

    def test_legacy_observed_universe_cannot_become_formal(self):
        observed = universe(path_status="legacy", coverage_status="legacy_observed")
        validate_universe_snapshot(observed)
        with self.assertRaisesRegex(ContractError, "universe_unavailable"):
            select_universe_snapshot([observed], as_of="2026-08-28", path_status="formal")
        self.assertEqual(
            select_universe_snapshot([observed], as_of="2026-08-28", path_status="legacy"), observed
        )

    def test_market_snapshot_recomputes_identity_and_rejects_future_evidence(self):
        payload = market_snapshot()
        validate_market_data_snapshot(payload)
        tampered = copy.deepcopy(payload)
        tampered["symbols"][0]["content_fingerprint"] = canonical_fingerprint(["changed"])
        with self.assertRaises(ContractError):
            validate_market_data_snapshot(tampered)
        future = copy.deepcopy(payload)
        future["max_returned_date"] = "2026-08-31"
        future["symbols"][0]["max_returned_date"] = "2026-08-31"
        future["snapshot_id"] = market_data_snapshot_id(future)
        with self.assertRaises(ContractError):
            validate_market_data_snapshot(future)

    def test_revision_records_preserve_changed_date_rows_and_fingerprint_chain(self):
        old = raw_rows()[0]
        new = {**old, "adjusted_close": 49.5}
        before = canonical_fingerprint([old])
        after = canonical_fingerprint([new])
        first = revision_record(
            changed_date=old["date"],
            old_row=old,
            new_row=new,
            before_fingerprint=before,
            after_fingerprint=after,
            previous_revision_id=None,
        )
        newer = {**new, "volume": 1001}
        second_after = canonical_fingerprint([newer])
        second = revision_record(
            changed_date=old["date"],
            old_row=new,
            new_row=newer,
            before_fingerprint=after,
            after_fingerprint=second_after,
            previous_revision_id=first["revision_id"],
        )
        validate_revision_chain([first, second])
        self.assertEqual(first["old_row"], old)
        self.assertEqual(first["new_row"], new)
        broken = copy.deepcopy(second)
        broken["before_fingerprint"] = before
        with self.assertRaises(ContractError):
            validate_revision_chain([first, broken])

    def test_unreconstructible_revision_requires_an_explicit_reason(self):
        old = raw_rows()[0]
        new = {**old, "close": 99.0}
        with self.assertRaises(ContractError):
            revision_record(
                changed_date=old["date"],
                old_row=old,
                new_row=new,
                before_fingerprint=canonical_fingerprint([old]),
                after_fingerprint=canonical_fingerprint([new]),
                previous_revision_id=None,
                reconstruction_status="not_reconstructible",
            )
        record = revision_record(
            changed_date=old["date"],
            old_row=old,
            new_row=new,
            before_fingerprint=canonical_fingerprint([old]),
            after_fingerprint=canonical_fingerprint([new]),
            previous_revision_id=None,
            reconstruction_status="not_reconstructible",
            reconstruction_reason="Earlier full-history fingerprint predates the retained revision chain.",
        )
        validate_revision_chain([record])

    def test_legacy_adapter_leaves_source_bytes_exactly_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ABC.json"
            path.write_text(json.dumps(raw_rows(), separators=(",", ":")))
            before = path.read_bytes()
            result = read_legacy_cache(path, as_of="2026-08-28")
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(result.max_returned_date, "2026-08-28")
            self.assertEqual(len(result.rows), 2)
            self.assertTrue(result.source_fingerprint.startswith("sha256:"))

    def test_legacy_adapter_rejects_invalid_json_without_modification(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ABC.json"
            path.write_bytes(b"not-json")
            before = path.read_bytes()
            with self.assertRaises(ContractError):
                read_legacy_cache(path, as_of="2026-08-28")
            self.assertEqual(path.read_bytes(), before)

    def test_pure_logic_does_not_call_network_git_or_processes(self):
        with patch.object(urllib.request, "urlopen", side_effect=AssertionError("network called")), patch.object(
            subprocess, "run", side_effect=AssertionError("process called")
        ):
            rows = adjusted_point_in_time_rows(raw_rows(), as_of="2026-08-28")
            self.assertEqual(len(rows), 2)
            validate_universe_snapshot(universe())
            validate_market_data_snapshot(market_snapshot())


if __name__ == "__main__":
    unittest.main()
