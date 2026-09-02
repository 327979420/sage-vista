"""Fixed synthetic evidence for the M10-B internal baseline evaluator."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
import unittest

from services.contracts.market_data import (
    canonical_fingerprint,
    market_data_snapshot_id,
)
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError
from services.evaluation import (
    BASELINE_ADAPTER_VERSION,
    BASELINE_ENGINE_NAME,
    BASELINE_ENGINE_VERSION,
    EVALUATION_POLICY,
    FORWARD_WINDOWS,
    FORWARD_WINDOW_POLICY,
    PARTITION_POLICY,
    build_experiment_run_receipt,
    build_session_calendar_evidence,
    market_snapshot_evidence_fingerprint,
    produce_forward_outcomes,
)
from services.market_data import RepositoryRead
from tests import test_m09_ledger as m09_fixtures


ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_CONTENT = "sha256:" + "c" * 64
CODE_COMMIT = "d" * 40


def plain(value):
    if hasattr(value, "items"):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def post_signal_sessions(signal_date: str, count: int = 110) -> tuple[str, ...]:
    current = date.fromisoformat(signal_date) + timedelta(days=1)
    sessions: list[str] = []
    # Freeze one synthetic exchange holiday so the tests prove that neither a
    # weekend nor an absent weekday is counted merely because a date elapsed.
    holiday = current
    while holiday.weekday() >= 5:
        holiday += timedelta(days=1)
    while len(sessions) < count:
        if current.weekday() < 5 and current != holiday:
            sessions.append(current.isoformat())
        current += timedelta(days=1)
    return tuple(sessions)


def adjusted_rows(event, sessions, *, through: str, missing=()):
    rows = [{
        "date": event["signal_date"],
        "open": 500.0,
        "high": 1000.0,
        "low": 400.0,
        "close": 999.0,
        "volume": 1_000_000,
    }]
    missing = set(missing)
    for index, day in enumerate(sessions, 1):
        if day > through or day in missing:
            continue
        rows.append({
            "date": day,
            "open": 99.0 + index,
            "high": 101.0 + index,
            "low": 98.0 + index,
            "close": 100.0 + index,
            "volume": 1_000_000 + index,
        })
    return tuple(rows)


def market_evidence(event, rows, *, as_of):
    fingerprint = canonical_fingerprint(list(rows))
    snapshot = {
        "schema_version": "1.0.0",
        "as_of": as_of,
        "generated_at": f"{as_of}T22:00:00Z",
        "source_version": {"m10_fixture": "1.0.0"},
        "future_data_used": False,
        "market": "US",
        "symbols": [{
            "instrument_id": event["instrument_id"],
            "symbol": event["symbol"],
            "row_count": len(rows),
            "first_date": rows[0]["date"],
            "max_returned_date": rows[-1]["date"],
            "content_fingerprint": fingerprint,
        }],
        "adjustment_policy": dict(ADJUSTMENT_POLICY),
        "data_source": {"provider": "fixture", "dataset": "adjusted-daily"},
        "universe_id": event["input_identity"]["universe_id"],
        "raw_revision": canonical_fingerprint([{
            "instrument_id": event["instrument_id"],
            "point_in_time_fingerprint": fingerprint,
        }]),
        "max_returned_date": rows[-1]["date"],
    }
    snapshot["snapshot_id"] = market_data_snapshot_id(snapshot)
    read = RepositoryRead(
        instrument_id=event["instrument_id"],
        as_of=as_of,
        rows=rows,
        point_in_time_fingerprint=fingerprint,
    )
    return read, snapshot


def policy_ref(kind, policy):
    return {
        "policy_kind": kind,
        "policy_version": policy["policy_version"],
        "policy_fingerprint": policy["policy_fingerprint"],
    }


def pending_receipt(event, snapshot, calendar, *, attempt="forward-fixture"):
    return build_experiment_run_receipt(
        as_of=calendar["as_of"],
        generated_at=f"{calendar['as_of']}T22:01:00Z",
        source_version={"evaluation_contracts": "m10-b-internal-1.0.0"},
        attempt_id=attempt,
        experiment_id="M10-B-forward-fixed-sample",
        status="pending",
        evidence_window={
            "start": event["signal_date"],
            "end": calendar["as_of"],
            "evidence_as_of": calendar["as_of"],
        },
        path_status="formal",
        result_role="authoritative",
        partition_role="forward",
        bias_labels=[],
        code_commit=CODE_COMMIT,
        config_ref={
            "config_id": "m10-b-forward-fixed-sample",
            "config_version": "1.0.0",
            "content_fingerprint": canonical_fingerprint({"windows": list(FORWARD_WINDOWS)}),
        },
        engine={
            "name": BASELINE_ENGINE_NAME,
            "version": BASELINE_ENGINE_VERSION,
            "adapter_version": BASELINE_ADAPTER_VERSION,
        },
        policy_refs=[
            {
                "policy_kind": "adjustment",
                "policy_version": ADJUSTMENT_POLICY["version"],
                "policy_fingerprint": canonical_fingerprint(ADJUSTMENT_POLICY),
            },
            policy_ref("evaluation", EVALUATION_POLICY),
            policy_ref("forward_window", FORWARD_WINDOW_POLICY),
            policy_ref("partition", PARTITION_POLICY),
        ],
        input_refs=[
            {
                "id": event["event_id"],
                "content_fingerprint": event["event_content_fingerprint"],
            },
            {
                "id": snapshot["snapshot_id"],
                "content_fingerprint": market_snapshot_evidence_fingerprint(snapshot),
            },
            {
                "id": event["input_identity"]["universe_id"],
                "content_fingerprint": UNIVERSE_CONTENT,
            },
            {
                "id": calendar["calendar_id"],
                "content_fingerprint": calendar["content_fingerprint"],
            },
        ],
        result_refs=[],
        started_at=f"{calendar['as_of']}T22:00:00Z",
        finished_at=None,
        parent_run_id=None,
        checkpoint_ref=None,
        error=None,
    )


class M10ForwardBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = m09_fixtures.M09LedgerTests(
            "test_all_authoritative_ranked_entries_create_one_root"
        )
        fixture.setUp()
        cls.event = fixture.batch.events[0]
        cls.sessions = post_signal_sessions(cls.event["signal_date"])

    def produce(self, *, elapsed, missing=(), previous=(), attempt=None):
        as_of = self.sessions[elapsed - 1] if elapsed else self.event["signal_date"]
        calendar = build_session_calendar_evidence(
            calendar_name="fixed-us-session-fixture",
            calendar_version="1.0.0",
            signal_date=self.event["signal_date"],
            as_of=as_of,
            sessions=self.sessions[:elapsed],
        )
        rows = adjusted_rows(
            self.event, self.sessions, through=as_of, missing=missing
        )
        read, snapshot = market_evidence(self.event, rows, as_of=as_of)
        receipt = pending_receipt(
            self.event,
            snapshot,
            calendar,
            attempt=attempt or f"forward-{elapsed}-{'-'.join(missing) or 'complete'}",
        )
        outcomes = produce_forward_outcomes(
            self.event,
            read,
            snapshot,
            calendar,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{as_of}T22:02:00Z",
            previous_outcomes=previous,
        )
        return outcomes, read, snapshot, calendar, receipt

    def test_all_windows_use_next_adjusted_open_not_signal_close(self):
        outcomes, _, _, calendar, _ = self.produce(elapsed=100)
        by_window = {item["window_sessions"]: item for item in outcomes}
        self.assertEqual(tuple(by_window), FORWARD_WINDOWS)
        for item in outcomes:
            self.assertEqual(item["entry"], {"date": self.sessions[0], "price": 100.0})
            self.assertNotEqual(item["entry"]["price"], 999.0)
        self.assertEqual(by_window[1]["endpoint"]["date"], self.sessions[0])
        self.assertEqual(by_window[5]["endpoint"]["date"], self.sessions[4])
        self.assertNotIn("2026-08-31", calendar["sessions"])

    def test_weekends_holiday_endpoint_and_excursions_are_exact(self):
        outcomes, _, _, _, _ = self.produce(elapsed=5)
        five = next(item for item in outcomes if item["window_sessions"] == 5)
        self.assertEqual(five["status"], "mature")
        self.assertEqual(five["gross_return"], 0.05)
        self.assertEqual(five["mfe"], 0.06)
        self.assertEqual(five["mae"], -0.01)
        self.assertEqual(five["elapsed_session_count"], 5)
        self.assertEqual(five["observed_session_count"], 5)

    def test_immature_window_is_pending_and_future_rows_are_not_visible(self):
        outcomes, read, _, _, _ = self.produce(elapsed=3)
        five = next(item for item in outcomes if item["window_sessions"] == 5)
        self.assertEqual(five["status"], "pending")
        self.assertEqual(five["status_reason"], "window_not_mature")
        self.assertIsNone(five["endpoint"])
        self.assertTrue(all(row["date"] <= read.as_of for row in read.rows))

    def test_missing_next_open_never_falls_back_to_signal_close(self):
        outcomes, _, _, _, _ = self.produce(
            elapsed=5, missing=(self.sessions[0],)
        )
        five = next(item for item in outcomes if item["window_sessions"] == 5)
        self.assertEqual(five["status"], "unavailable")
        self.assertEqual(
            five["status_reason"], "next_session_adjusted_open_unavailable"
        )
        self.assertIsNone(five["entry"])
        self.assertIsNone(five["gross_return"])

    def test_missing_middle_session_is_partial_without_guessed_excursions(self):
        outcomes, _, _, _, _ = self.produce(
            elapsed=5, missing=(self.sessions[2],)
        )
        five = next(item for item in outcomes if item["window_sessions"] == 5)
        self.assertEqual(five["status"], "partial")
        self.assertEqual(five["gross_return"], 0.05)
        self.assertEqual(five["observed_session_count"], 4)
        self.assertIsNone(five["mfe"])
        self.assertIsNone(five["mae"])

    def test_pending_matures_by_revision_and_same_replay_is_idempotent(self):
        pending, _, _, _, _ = self.produce(elapsed=3)
        mature, _, _, _, _ = self.produce(elapsed=5, previous=pending)
        pending_five = next(item for item in pending if item["window_sessions"] == 5)
        mature_five = next(item for item in mature if item["window_sessions"] == 5)
        self.assertEqual(mature_five["status"], "mature")
        self.assertEqual(
            mature_five["supersedes_result_id"], pending_five["forward_outcome_id"]
        )
        replay, _, _, _, _ = self.produce(
            elapsed=5, previous=(*pending, *mature)
        )
        replay_five = next(item for item in replay if item["window_sessions"] == 5)
        self.assertEqual(replay_five, mature_five)
        self.assertEqual(pending_five["status"], "pending")

    def test_tampered_read_fingerprint_fails_before_outcome_creation(self):
        _, read, snapshot, calendar, receipt = self.produce(elapsed=5)
        tampered = replace(read, point_in_time_fingerprint="sha256:" + "0" * 64)
        with self.assertRaisesRegex(ContractError, "fingerprint"):
            produce_forward_outcomes(
                self.event,
                tampered,
                snapshot,
                calendar,
                universe_content_fingerprint=UNIVERSE_CONTENT,
                pending_run_receipt=receipt,
                generated_at=f"{calendar['as_of']}T22:02:00Z",
            )

    def test_market_snapshot_and_calendar_must_bind_delivered_evidence(self):
        _, read, snapshot, calendar, receipt = self.produce(elapsed=5)
        crossed = plain(snapshot)
        crossed["symbols"][0]["content_fingerprint"] = "sha256:" + "0" * 64
        with self.assertRaises(ContractError):
            produce_forward_outcomes(
                self.event,
                read,
                crossed,
                calendar,
                universe_content_fingerprint=UNIVERSE_CONTENT,
                pending_run_receipt=receipt,
                generated_at=f"{calendar['as_of']}T22:02:00Z",
            )
        with self.assertRaises(ContractError):
            build_session_calendar_evidence(
                calendar_name="bad-order",
                calendar_version="1.0.0",
                signal_date=self.event["signal_date"],
                as_of=self.sessions[1],
                sessions=(self.sessions[1], self.sessions[0]),
            )

    def test_run_receipt_must_bind_event_market_universe_and_calendar(self):
        _, read, snapshot, calendar, receipt = self.produce(elapsed=5)
        changed = plain(receipt)
        changed["input_refs"] = [
            item for item in changed["input_refs"]
            if item["id"] != calendar["calendar_id"]
        ]
        # Rebuild a valid receipt with incomplete evidence; the producer, not
        # the generic M10-A receipt schema, owns this M10-B completeness check.
        changed.pop("run_id")
        changed.pop("run_receipt_id")
        changed.pop("run_content_fingerprint")
        changed.pop("input_set_fingerprint")
        changed.pop("result_set_fingerprint")
        incomplete = build_experiment_run_receipt(**changed)
        with self.assertRaisesRegex(ContractError, "omits"):
            produce_forward_outcomes(
                self.event,
                read,
                snapshot,
                calendar,
                universe_content_fingerprint=UNIVERSE_CONTENT,
                pending_run_receipt=incomplete,
                generated_at=f"{calendar['as_of']}T22:02:00Z",
            )


if __name__ == "__main__":
    unittest.main()
