"""Fixed synthetic evidence for the M10-B internal baseline evaluator."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest

from services.contracts.market_data import (
    canonical_fingerprint,
    market_data_snapshot_id,
)
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError
from services.execution import (
    EXIT_POLICY,
    advance_exit_state,
    current_exit_state,
    produce_trade_plans,
)
from services.evaluation import (
    BASELINE_ADAPTER_VERSION,
    BASELINE_ENGINE_NAME,
    BASELINE_ENGINE_VERSION,
    BaselineEvaluationBatch,
    EvaluationShadowStore,
    EVALUATION_POLICY,
    FORWARD_WINDOWS,
    FORWARD_WINDOW_POLICY,
    PARTITION_POLICY,
    ZERO_COST_COMPARISON_POLICY,
    baseline_run_scope_fingerprint,
    build_experiment_run_receipt,
    build_session_calendar_evidence,
    complete_baseline_run,
    evaluate_forward_baseline,
    evaluate_trade_baseline,
    finalize_result,
    market_snapshot_evidence_fingerprint,
    produce_forward_outcomes,
    produce_trade_outcome,
    store_baseline_evaluation_batch,
    validate_baseline_evaluation_batch,
    validate_result,
)
from services.evaluation.baseline import forward_result_scope_keys
from services.ledger import produce_exit_state_link, produce_trade_plan_links
from services.market_data import RepositoryRead
from services.scanner.factor_snapshot import (
    build_shadow_forward_evaluation,
    build_shadow_trade_evaluation,
)
from services.scanner.unified_v2_scan import (
    shadow_forward_evaluation,
    shadow_trade_evaluation,
)
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


def refingerprint_machine_link(original, **changes):
    payload = plain(original)
    payload.update(changes)
    payload["link_id"] = "machine-link:" + canonical_fingerprint({
        "event_id": payload["event_id"],
        "link_type": payload["link_type"],
        "source_identity": payload["source_identity"],
    })
    payload["link_content_fingerprint"] = canonical_fingerprint({
        key: plain(value) for key, value in payload.items()
        if key not in {"generated_at", "link_content_fingerprint"}
    })
    return payload


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


def pending_receipt(event, read, snapshot, calendar, *, attempt="forward-fixture"):
    input_refs = [
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
    ]
    policies = [
        {
            "policy_kind": "adjustment",
            "policy_version": ADJUSTMENT_POLICY["version"],
            "policy_fingerprint": canonical_fingerprint(ADJUSTMENT_POLICY),
        },
        policy_ref("evaluation", EVALUATION_POLICY),
        policy_ref("forward_window", FORWARD_WINDOW_POLICY),
        policy_ref("partition", PARTITION_POLICY),
    ]
    market_fingerprint = next(
        item["content_fingerprint"] for item in snapshot["symbols"]
        if item["instrument_id"] == event["instrument_id"]
    )
    scope_fingerprint = baseline_run_scope_fingerprint(
        "ForwardOutcome",
        input_refs=input_refs,
        policy_refs=policies,
        path_status="formal",
        result_role="authoritative",
        partition_role="forward",
        instrument_id=event["instrument_id"],
        signal_date=event["signal_date"],
        market_data_fingerprint=market_fingerprint,
        expected_result_keys=forward_result_scope_keys(
            event,
            snapshot,
            UNIVERSE_CONTENT,
            calendar,
            read.rows,
        ),
    )
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
            "content_fingerprint": scope_fingerprint,
        },
        engine={
            "name": BASELINE_ENGINE_NAME,
            "version": BASELINE_ENGINE_VERSION,
            "adapter_version": BASELINE_ADAPTER_VERSION,
        },
        policy_refs=policies,
        input_refs=input_refs,
        result_refs=[],
        started_at=f"{calendar['as_of']}T22:00:00Z",
        finished_at=None,
        parent_run_id=None,
        checkpoint_ref=None,
        error=None,
    )


def trade_pending_receipt(
    event,
    snapshot,
    plan_link,
    plan,
    state,
    state_link,
    *,
    role="authoritative",
    attempt="trade-fixture",
):
    input_refs = [
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
            "id": plan_link["link_id"],
            "content_fingerprint": plan_link["link_content_fingerprint"],
        },
    ]
    if plan is not None:
        input_refs.append({
            "id": plan["plan_id"],
            "content_fingerprint": plan["plan_content_fingerprint"],
        })
    if state is not None:
        input_refs.append({
            "id": state["exit_state_id"],
            "content_fingerprint": state["exit_state_content_fingerprint"],
        })
    if state_link is not None:
        input_refs.append({
            "id": state_link["link_id"],
            "content_fingerprint": state_link["link_content_fingerprint"],
        })
    policies = [
        {
            "policy_kind": "adjustment",
            "policy_version": ADJUSTMENT_POLICY["version"],
            "policy_fingerprint": canonical_fingerprint(ADJUSTMENT_POLICY),
        },
        policy_ref("evaluation", EVALUATION_POLICY),
        {
            "policy_kind": "execution",
            "policy_version": EXIT_POLICY["policy_version"],
            "policy_fingerprint": EXIT_POLICY["policy_fingerprint"],
        },
        policy_ref("partition", PARTITION_POLICY),
    ]
    if role == "comparison":
        policies.append(policy_ref("cost_slippage", ZERO_COST_COMPARISON_POLICY))
    as_of = state["as_of"] if state is not None else event["signal_date"]
    market_fingerprint = next(
        item["content_fingerprint"] for item in snapshot["symbols"]
        if item["instrument_id"] == event["instrument_id"]
    )
    scope_fingerprint = baseline_run_scope_fingerprint(
        "TradeOutcome",
        input_refs=input_refs,
        policy_refs=policies,
        path_status="formal",
        result_role=role,
        partition_role="forward",
        instrument_id=event["instrument_id"],
        signal_date=event["signal_date"],
        market_data_fingerprint=market_fingerprint,
        expected_result_keys=[{
            "event_id": event["event_id"],
            "event_content_fingerprint": event["event_content_fingerprint"],
            "instrument_id": event["instrument_id"],
            "signal_date": event["signal_date"],
            "evaluation_market_snapshot_id": snapshot["snapshot_id"],
            "evaluation_market_snapshot_fingerprint": market_snapshot_evidence_fingerprint(
                snapshot
            ),
            "universe_id": event["input_identity"]["universe_id"],
            "universe_content_fingerprint": UNIVERSE_CONTENT,
            "trade_plan_link_id": plan_link["link_id"],
            "trade_plan_link_content_fingerprint": plan_link[
                "link_content_fingerprint"
            ],
            "trade_plan_id": plan["plan_id"] if plan is not None else None,
            "trade_plan_content_fingerprint": (
                plan["plan_content_fingerprint"] if plan is not None else None
            ),
            "exit_state_id": state["exit_state_id"] if state is not None else None,
            "exit_state_content_fingerprint": (
                state["exit_state_content_fingerprint"] if state is not None else None
            ),
        }],
    )
    return build_experiment_run_receipt(
        as_of=as_of,
        generated_at=f"{as_of}T22:01:00Z",
        source_version={"evaluation_contracts": "m10-b-internal-1.0.0"},
        attempt_id=attempt,
        experiment_id="M10-B-trade-fixed-sample",
        status="pending",
        evidence_window={
            "start": event["signal_date"],
            "end": as_of,
            "evidence_as_of": as_of,
        },
        path_status="formal",
        result_role=role,
        partition_role="forward",
        bias_labels=[],
        code_commit=CODE_COMMIT,
        config_ref={
            "config_id": "m10-b-trade-fixed-sample",
            "config_version": "1.0.0",
            "content_fingerprint": scope_fingerprint,
        },
        engine={
            "name": BASELINE_ENGINE_NAME,
            "version": BASELINE_ENGINE_VERSION,
            "adapter_version": BASELINE_ADAPTER_VERSION,
        },
        policy_refs=policies,
        input_refs=input_refs,
        result_refs=[],
        started_at=f"{as_of}T22:00:00Z",
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
        cls.other_event = fixture.batch.events[1]
        cls.sessions = post_signal_sessions(cls.event["signal_date"])

    def produce(self, *, elapsed, missing=(), previous=(), attempt=None):
        as_of = self.sessions[elapsed - 1] if elapsed else self.event["signal_date"]
        calendar = build_session_calendar_evidence(
            calendar_name="fixed-us-session-fixture",
            calendar_version="1.0.0",
            signal_date=self.event["signal_date"],
            as_of=as_of,
            sessions=self.sessions[:elapsed],
            target_sessions=self.sessions,
        )
        rows = adjusted_rows(
            self.event, self.sessions, through=as_of, missing=missing
        )
        read, snapshot = market_evidence(self.event, rows, as_of=as_of)
        receipt = pending_receipt(
            self.event,
            read,
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

    def test_pending_calendar_freezes_all_authoritative_window_targets(self):
        calendar = build_session_calendar_evidence(
            calendar_name="fixed-us-session-fixture",
            calendar_version="1.0.0",
            signal_date=self.event["signal_date"],
            as_of=self.sessions[4],
            sessions=self.sessions[:5],
            target_sessions=self.sessions,
        )
        self.assertEqual(calendar["sessions"], tuple(self.sessions[:5]))
        self.assertEqual(calendar["target_sessions"], tuple(self.sessions))
        self.assertEqual(
            {
                window: calendar["target_sessions"][window - 1]
                for window in FORWARD_WINDOWS
            },
            {
                window: self.sessions[window - 1]
                for window in FORWARD_WINDOWS
            },
        )

    def test_all_windows_use_next_adjusted_open_not_signal_close(self):
        outcomes, _, _, calendar, _ = self.produce(elapsed=100)
        by_window = {item["window_sessions"]: item for item in outcomes}
        self.assertEqual(tuple(by_window), FORWARD_WINDOWS)
        for item in outcomes:
            self.assertEqual(item["entry"], {"date": self.sessions[0], "price": 100.0})
            self.assertNotEqual(item["entry"]["price"], 999.0)
        self.assertEqual(by_window[1]["endpoint"]["date"], self.sessions[0])
        self.assertEqual(by_window[5]["endpoint"]["date"], self.sessions[4])
        self.assertEqual(
            {item["target_session_date"] for item in outcomes},
            {self.sessions[window - 1] for window in FORWARD_WINDOWS},
        )
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
        self.assertEqual(five["target_session_date"], self.sessions[4])
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
        self.assertEqual(five["target_session_date"], self.sessions[4])

    def test_missing_middle_session_is_partial_without_guessed_excursions(self):
        outcomes, _, _, _, _ = self.produce(
            elapsed=5, missing=(self.sessions[2],)
        )
        five = next(item for item in outcomes if item["window_sessions"] == 5)
        self.assertEqual(five["status"], "partial")
        self.assertEqual(five["gross_return"], 0.05)
        self.assertEqual(five["observed_session_count"], 4)
        self.assertEqual(five["target_session_date"], self.sessions[4])
        self.assertIsNone(five["mfe"])
        self.assertIsNone(five["mae"])

    def test_missing_target_session_never_falls_back_to_an_adjacent_close(self):
        outcomes, _, _, _, _ = self.produce(
            elapsed=5, missing=(self.sessions[4],)
        )
        five = next(item for item in outcomes if item["window_sessions"] == 5)
        self.assertEqual(five["target_session_date"], self.sessions[4])
        self.assertEqual(five["status"], "unavailable")
        self.assertEqual(
            five["status_reason"], "endpoint_adjusted_close_unavailable"
        )
        self.assertIsNone(five["endpoint"])

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


class M10TradeBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = m09_fixtures.M09LedgerTests(
            "test_event_exists_before_next_open_and_m08_links_append_later"
        )
        fixture.setUp()
        plan_batch = produce_trade_plans(
            fixture.ranking,
            fixture.support,
            entry_reads=fixture.entry_reads(),
            generated_at=m09_fixtures.ENTRY_GENERATED_AT,
        )
        links = produce_trade_plan_links(
            fixture.batch,
            plan_batch,
            generated_at=m09_fixtures.ENTRY_GENERATED_AT,
        )
        events = {item["event_id"]: item for item in fixture.batch.events}
        plans = {item["plan_id"]: item for item in plan_batch.plans}
        cls.plan_link = next(item for item in links if item["status"] == "created")
        cls.event = events[cls.plan_link["event_id"]]
        cls.plan = plans[cls.plan_link["source_reference"]["plan_id"]]
        cls.no_plan_link = next(item for item in links if item["status"] == "not_created")
        cls.no_plan_event = events[cls.no_plan_link["event_id"]]
        reads = fixture.entry_reads()
        cls.history = tuple(
            row for row in reads[cls.plan["instrument_id"]].rows
            if row["date"] < cls.plan["entry_date"]
        )
        cls.no_plan_history = tuple(
            row for row in reads[cls.no_plan_event["instrument_id"]].rows
            if row["date"] <= cls.no_plan_event["signal_date"]
        )

    def safe_bar(self, day):
        return {
            "date": day,
            "open": self.plan["entry"]["price"],
            "high": self.plan["target"]["price"] - 1,
            "low": self.plan["stop"]["price"] + 1,
            "close": self.plan["entry"]["price"] + 1,
            "volume": 1_000_000,
        }

    def trading_days(self, count):
        current = date.fromisoformat(self.plan["entry_date"])
        result = []
        while len(result) < count:
            if current.weekday() < 5:
                result.append(current.isoformat())
            current += timedelta(days=1)
        return result

    def evaluate(
        self,
        states,
        bars,
        *,
        role="authoritative",
        previous=(),
        attempt="trade-case",
    ):
        current = current_exit_state(states)
        state_link = produce_exit_state_link(
            self.event,
            self.plan_link,
            current,
            generated_at=f"{current['as_of']}T21:59:00Z",
        )
        rows = (*self.history, *bars)
        read, snapshot = market_evidence(
            self.event, rows, as_of=current["as_of"]
        )
        receipt = trade_pending_receipt(
            self.event,
            snapshot,
            self.plan_link,
            self.plan,
            current,
            state_link,
            role=role,
            attempt=attempt,
        )
        outcome = produce_trade_outcome(
            self.event,
            self.plan_link,
            self.plan,
            states,
            state_link,
            read,
            snapshot,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{current['as_of']}T22:02:00Z",
            previous_outcomes=previous,
        )
        return outcome, read, snapshot, receipt, state_link

    def test_target_exit_calculates_only_gross_return_and_r(self):
        bar = self.safe_bar(self.plan["entry_date"])
        bar["high"] = self.plan["target"]["price"] + 1
        state = advance_exit_state(
            self.plan,
            completed_bars=[bar],
            generated_at=m09_fixtures.ENTRY_GENERATED_AT,
        )
        outcome, *_ = self.evaluate((state,), (bar,), attempt="target")
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["exit_reason"], "target")
        self.assertEqual(outcome["gross_r_multiple"], 2.0)
        self.assertGreater(outcome["gross_return"], 0)
        self.assertEqual(outcome["holding_sessions"], 1)

    def test_stop_gap_and_same_bar_stop_priority_are_reused_from_m08(self):
        gap = self.safe_bar(self.plan["entry_date"])
        gap.update({
            "open": self.plan["stop"]["price"] - 2,
            "low": self.plan["stop"]["price"] - 3,
            "close": self.plan["stop"]["price"] - 1,
        })
        gap_state = advance_exit_state(
            self.plan, completed_bars=[gap], generated_at=m09_fixtures.ENTRY_GENERATED_AT
        )
        gap_outcome, *_ = self.evaluate((gap_state,), (gap,), attempt="gap")
        self.assertEqual(gap_outcome["exit_reason"], "stop_gap")
        self.assertEqual(gap_outcome["exit"]["price"], gap["open"])

        same = self.safe_bar(self.plan["entry_date"])
        same.update({
            "high": self.plan["target"]["price"] + 1,
            "low": self.plan["stop"]["price"] - 1,
        })
        same_state = advance_exit_state(
            self.plan, completed_bars=[same], generated_at=m09_fixtures.ENTRY_GENERATED_AT
        )
        same_outcome, *_ = self.evaluate((same_state,), (same,), attempt="same-bar")
        self.assertEqual(same_outcome["exit_reason"], "stop")
        self.assertEqual(same_outcome["exit"]["price"], self.plan["stop"]["price"])

    def test_forty_session_exit_copies_m08_execution_without_redeciding(self):
        bars = tuple(self.safe_bar(day) for day in self.trading_days(40))
        state = advance_exit_state(
            self.plan,
            completed_bars=bars,
            generated_at=f"{bars[-1]['date']}T22:00:00Z",
        )
        outcome, *_ = self.evaluate((state,), bars, attempt="time-40")
        self.assertEqual(outcome["exit_reason"], "time_40d")
        self.assertEqual(outcome["holding_sessions"], 40)
        self.assertEqual(outcome["exit"]["price"], bars[-1]["close"])

    def test_open_trade_is_pending_without_final_results(self):
        bar = self.safe_bar(self.plan["entry_date"])
        state = advance_exit_state(
            self.plan,
            completed_bars=[bar],
            generated_at=m09_fixtures.ENTRY_GENERATED_AT,
        )
        outcome, *_ = self.evaluate((state,), (bar,), attempt="open")
        self.assertEqual(outcome["status"], "pending")
        self.assertEqual(outcome["status_reason"], "trade_open")
        self.assertIsNone(outcome["gross_return"])
        self.assertIsNone(outcome["exit"])

    def test_formal_net_is_unavailable_and_zero_cost_is_comparison_only(self):
        bar = self.safe_bar(self.plan["entry_date"])
        bar["high"] = self.plan["target"]["price"] + 1
        state = advance_exit_state(
            self.plan, completed_bars=[bar], generated_at=m09_fixtures.ENTRY_GENERATED_AT
        )
        formal, *_ = self.evaluate((state,), (bar,), attempt="formal-cost")
        comparison, *_ = self.evaluate(
            (state,), (bar,), role="comparison", attempt="comparison-cost"
        )
        self.assertIsNone(formal["net_return"])
        self.assertEqual(formal["net_return_status"], "unavailable")
        self.assertEqual(comparison["net_return"], comparison["gross_return"])
        self.assertEqual(comparison["result_role"], "comparison")

    def test_trade_mfe_and_mae_are_always_unavailable_with_reason(self):
        bar = self.safe_bar(self.plan["entry_date"])
        bar["high"] = self.plan["target"]["price"] + 1
        state = advance_exit_state(
            self.plan, completed_bars=[bar], generated_at=m09_fixtures.ENTRY_GENERATED_AT
        )
        outcome, *_ = self.evaluate((state,), (bar,), attempt="excursions")
        for metric in ("mfe", "mae"):
            self.assertIsNone(outcome[metric])
            self.assertEqual(outcome[f"{metric}_status"], "unavailable")
            self.assertEqual(
                outcome[f"{metric}_reason"],
                "exit_day_inclusion_and_intraday_order_not_approved",
            )
        injected = plain(outcome)
        for field in (
            "trade_outcome_id", "trade_content_fingerprint", "input_fingerprint"
        ):
            injected.pop(field)
        injected["mfe"] = 9.99
        with self.assertRaises(ContractError):
            from services.evaluation import finalize_result
            finalize_result("TradeOutcome", injected)

    def test_exit_state_maturity_appends_outcome_revision_order_independently(self):
        days = self.trading_days(2)
        first_bar = self.safe_bar(days[0])
        active = advance_exit_state(
            self.plan,
            completed_bars=[first_bar],
            generated_at=f"{days[0]}T22:00:00Z",
        )
        pending, *_ = self.evaluate((active,), (first_bar,), attempt="revision-open")
        target_bar = self.safe_bar(days[1])
        target_bar["high"] = self.plan["target"]["price"] + 1
        closed = advance_exit_state(
            self.plan,
            completed_bars=[first_bar, target_bar],
            generated_at=f"{days[1]}T22:00:00Z",
            previous_state=active,
        )
        mature, *_ = self.evaluate(
            (closed, active),
            (first_bar, target_bar),
            previous=(pending,),
            attempt="revision-closed",
        )
        self.assertEqual(mature["logical_result_id"], pending["logical_result_id"])
        self.assertEqual(mature["supersedes_result_id"], pending["trade_outcome_id"])
        replay, *_ = self.evaluate(
            (active, closed),
            (first_bar, target_bar),
            previous=(pending, mature),
            attempt="revision-closed",
        )
        self.assertEqual(replay, mature)

    def test_no_plan_event_is_preserved_as_no_trade(self):
        rows = self.no_plan_history
        read, snapshot = market_evidence(
            self.no_plan_event, rows, as_of=self.no_plan_event["signal_date"]
        )
        receipt = trade_pending_receipt(
            self.no_plan_event,
            snapshot,
            self.no_plan_link,
            None,
            None,
            None,
            attempt="no-trade",
        )
        outcome = produce_trade_outcome(
            self.no_plan_event,
            self.no_plan_link,
            None,
            (),
            None,
            read,
            snapshot,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{self.no_plan_event['signal_date']}T22:02:00Z",
        )
        self.assertEqual(outcome["status"], "no_trade")
        self.assertEqual(outcome["status_reason"], "not_selected_for_plan")
        self.assertIsNone(outcome["trade_plan_id"])

    def test_exit_path_fingerprint_and_unique_chain_are_mandatory(self):
        days = self.trading_days(2)
        first = self.safe_bar(days[0])
        active = advance_exit_state(
            self.plan, completed_bars=[first], generated_at=f"{days[0]}T22:00:00Z"
        )
        second = self.safe_bar(days[1])
        second["high"] = self.plan["target"]["price"] + 1
        closed = advance_exit_state(
            self.plan,
            completed_bars=[first, second],
            generated_at=f"{days[1]}T22:00:00Z",
            previous_state=active,
        )
        outcome, read, snapshot, receipt, state_link = self.evaluate(
            (active, closed), (first, second), attempt="chain"
        )
        self.assertEqual(outcome["status"], "completed")
        changed = list(read.rows)
        changed[-1] = {**changed[-1], "close": changed[-1]["close"] + 0.5}
        changed[-1]["high"] = max(changed[-1]["high"], changed[-1]["close"])
        changed_read, changed_snapshot = market_evidence(
            self.event, tuple(changed), as_of=closed["as_of"]
        )
        changed_receipt = trade_pending_receipt(
            self.event,
            changed_snapshot,
            self.plan_link,
            self.plan,
            closed,
            state_link,
            attempt="changed-path",
        )
        with self.assertRaisesRegex(ContractError, "ExitState path"):
            produce_trade_outcome(
                self.event,
                self.plan_link,
                self.plan,
                (active, closed),
                state_link,
                changed_read,
                changed_snapshot,
                universe_content_fingerprint=UNIVERSE_CONTENT,
                pending_run_receipt=changed_receipt,
                generated_at=f"{closed['as_of']}T22:02:00Z",
            )
        with self.assertRaisesRegex(ContractError, "missing predecessor"):
            self.evaluate((closed,), (first, second), attempt="dangling")

    def test_event_links_cannot_switch_instrument_or_signal_date(self):
        bar = self.safe_bar(self.plan["entry_date"])
        bar["high"] = self.plan["target"]["price"] + 1
        state = advance_exit_state(
            self.plan, completed_bars=[bar], generated_at=m09_fixtures.ENTRY_GENERATED_AT
        )
        state_link = produce_exit_state_link(
            self.event,
            self.plan_link,
            state,
            generated_at=f"{state['as_of']}T21:59:00Z",
        )
        rows = (*self.history, bar)
        read, snapshot = market_evidence(self.event, rows, as_of=state["as_of"])
        attacks = (
            refingerprint_machine_link(
                state_link, instrument_id="instrument:sha256:" + "e" * 64
            ),
            refingerprint_machine_link(
                state_link, signal_date="2026-08-27", as_of="2026-08-27"
            ),
        )
        for attacked_link in attacks:
            with self.subTest(link=attacked_link):
                receipt = trade_pending_receipt(
                    self.event,
                    snapshot,
                    self.plan_link,
                    self.plan,
                    state,
                    attacked_link,
                    attempt="crossed-event-link",
                )
                with self.assertRaises(ContractError):
                    produce_trade_outcome(
                        self.event,
                        self.plan_link,
                        self.plan,
                        (state,),
                        attacked_link,
                        read,
                        snapshot,
                        universe_content_fingerprint=UNIVERSE_CONTENT,
                        pending_run_receipt=receipt,
                        generated_at=f"{state['as_of']}T22:02:00Z",
                    )


class M10RunIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        M10ForwardBaselineTests.setUpClass()
        M10TradeBaselineTests.setUpClass()

    def forward_inputs(self):
        fixture = M10ForwardBaselineTests()
        _, read, snapshot, calendar, receipt = fixture.produce(elapsed=5)
        return fixture.event, read, snapshot, calendar, receipt

    def trade_inputs(self):
        fixture = M10TradeBaselineTests()
        bar = fixture.safe_bar(fixture.plan["entry_date"])
        bar["high"] = fixture.plan["target"]["price"] + 1
        state = advance_exit_state(
            fixture.plan,
            completed_bars=[bar],
            generated_at=m09_fixtures.ENTRY_GENERATED_AT,
        )
        _, read, snapshot, receipt, state_link = fixture.evaluate(
            (state,), (bar,), attempt="run-integration"
        )
        return fixture, state, read, snapshot, receipt, state_link

    def test_forward_run_closes_with_exact_result_reference_set(self):
        event, read, snapshot, calendar, receipt = self.forward_inputs()
        batch = evaluate_forward_baseline(
            event,
            read,
            snapshot,
            calendar,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{calendar['as_of']}T22:02:00Z",
            finished_at=f"{calendar['as_of']}T22:03:00Z",
        )
        validate_baseline_evaluation_batch(batch)
        self.assertEqual(batch.pending_run_receipt["status"], "pending")
        self.assertEqual(batch.completed_run_receipt["status"], "completed")
        self.assertEqual(
            batch.completed_run_receipt["supersedes_run_receipt_id"],
            batch.pending_run_receipt["run_receipt_id"],
        )
        self.assertEqual(len(batch.outcomes), len(FORWARD_WINDOWS))
        self.assertEqual(
            {item["id"] for item in batch.completed_run_receipt["result_refs"]},
            {item["forward_outcome_id"] for item in batch.outcomes},
        )

    def test_daily_and_replay_forward_use_the_same_runner(self):
        event, read, snapshot, calendar, receipt = self.forward_inputs()
        kwargs = {
            "universe_content_fingerprint": UNIVERSE_CONTENT,
            "pending_run_receipt": receipt,
            "generated_at": f"{calendar['as_of']}T22:02:00Z",
            "finished_at": f"{calendar['as_of']}T22:03:00Z",
        }
        daily = build_shadow_forward_evaluation(
            event, read, snapshot, calendar, **kwargs
        )
        replay = shadow_forward_evaluation(
            event, read, snapshot, calendar, **kwargs
        )
        self.assertEqual(daily, replay)

    def test_daily_and_replay_trade_use_the_same_runner(self):
        fixture, state, read, snapshot, receipt, state_link = self.trade_inputs()
        args = (
            fixture.event,
            fixture.plan_link,
            fixture.plan,
            (state,),
            state_link,
            read,
            snapshot,
        )
        kwargs = {
            "universe_content_fingerprint": UNIVERSE_CONTENT,
            "pending_run_receipt": receipt,
            "generated_at": f"{state['as_of']}T22:02:00Z",
            "finished_at": f"{state['as_of']}T22:03:00Z",
        }
        daily = build_shadow_trade_evaluation(*args, **kwargs)
        replay = shadow_trade_evaluation(*args, **kwargs)
        self.assertEqual(daily, replay)
        self.assertEqual(daily.outcomes[0]["exit_reason"], "target")

    def test_completion_rejects_an_outcome_from_another_run(self):
        event, read, snapshot, calendar, receipt = self.forward_inputs()
        outcomes = produce_forward_outcomes(
            event,
            read,
            snapshot,
            calendar,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{calendar['as_of']}T22:02:00Z",
        )
        other = pending_receipt(
            event, read, snapshot, calendar, attempt="different-run-root"
        )
        with self.assertRaisesRegex(ContractError, "does not belong"):
            complete_baseline_run(
                other,
                "ForwardOutcome",
                outcomes,
                generated_at=f"{calendar['as_of']}T22:03:00Z",
                finished_at=f"{calendar['as_of']}T22:03:00Z",
            )

    def test_completion_rejects_foreign_event_even_with_rebound_run_id(self):
        event, _, _, calendar, receipt = self.forward_inputs()
        other = M10ForwardBaselineTests.other_event
        other_rows = adjusted_rows(
            other, M10ForwardBaselineTests.sessions, through=calendar["as_of"]
        )
        other_read, other_snapshot = market_evidence(
            other, other_rows, as_of=calendar["as_of"]
        )
        other_receipt = pending_receipt(
            other, other_read, other_snapshot, calendar, attempt="foreign-event"
        )
        foreign = produce_forward_outcomes(
            other,
            other_read,
            other_snapshot,
            calendar,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=other_receipt,
            generated_at=f"{calendar['as_of']}T22:02:00Z",
        )[0]
        rebound = plain(foreign)
        for field in (
            "forward_outcome_id", "forward_content_fingerprint",
            "input_fingerprint",
        ):
            rebound.pop(field)
        rebound["run_id"] = receipt["run_id"]
        rebound = finalize_result("ForwardOutcome", rebound)
        with self.assertRaises(ContractError):
            complete_baseline_run(
                receipt,
                "ForwardOutcome",
                (rebound,),
                generated_at=f"{calendar['as_of']}T22:03:00Z",
                finished_at=f"{calendar['as_of']}T22:03:00Z",
            )

    def test_completion_rejects_foreign_market_and_missing_windows(self):
        event, read, snapshot, calendar, receipt = self.forward_inputs()
        outcomes = produce_forward_outcomes(
            event,
            read,
            snapshot,
            calendar,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{calendar['as_of']}T22:02:00Z",
        )
        with self.assertRaises(ContractError):
            complete_baseline_run(
                receipt,
                "ForwardOutcome",
                outcomes[:1],
                generated_at=f"{calendar['as_of']}T22:03:00Z",
                finished_at=f"{calendar['as_of']}T22:03:00Z",
            )

        changed_rows = list(read.rows)
        changed_rows[-1] = {
            **changed_rows[-1],
            "close": changed_rows[-1]["close"] + 0.25,
            "high": max(
                changed_rows[-1]["high"], changed_rows[-1]["close"] + 0.25
            ),
        }
        foreign_read, foreign_snapshot = market_evidence(
            event, tuple(changed_rows), as_of=calendar["as_of"]
        )
        foreign_receipt = pending_receipt(
            event,
            foreign_read,
            foreign_snapshot,
            calendar,
            attempt="foreign-market",
        )
        foreign = produce_forward_outcomes(
            event,
            foreign_read,
            foreign_snapshot,
            calendar,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=foreign_receipt,
            generated_at=f"{calendar['as_of']}T22:02:00Z",
        )
        rebound = []
        for item in foreign:
            values = plain(item)
            for field in (
                "forward_outcome_id", "forward_content_fingerprint",
                "input_fingerprint",
            ):
                values.pop(field)
            values["run_id"] = receipt["run_id"]
            rebound.append(finalize_result("ForwardOutcome", values))
        with self.assertRaises(ContractError):
            complete_baseline_run(
                receipt,
                "ForwardOutcome",
                rebound,
                generated_at=f"{calendar['as_of']}T22:03:00Z",
                finished_at=f"{calendar['as_of']}T22:03:00Z",
            )

    def test_completion_rejects_changed_universe_calendar_and_extra_window(self):
        event, read, snapshot, calendar, receipt = self.forward_inputs()
        outcomes = list(produce_forward_outcomes(
            event,
            read,
            snapshot,
            calendar,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{calendar['as_of']}T22:02:00Z",
        ))
        attacks = (
            {
                "universe_id": "universe:sha256:" + "e" * 64,
                "universe_content_fingerprint": "sha256:" + "e" * 64,
            },
            {
                "session_calendar_id": "session-calendar:sha256:" + "e" * 64,
                "session_calendar_fingerprint": "sha256:" + "e" * 64,
            },
        )
        for changes in attacks:
            with self.subTest(changes=changes):
                values = plain(outcomes[0])
                for field in (
                    "forward_outcome_id", "forward_content_fingerprint",
                    "input_fingerprint",
                ):
                    values.pop(field)
                values.update(changes)
                attacked = finalize_result("ForwardOutcome", values)
                with self.assertRaises(ContractError):
                    complete_baseline_run(
                        receipt,
                        "ForwardOutcome",
                        (attacked, *outcomes[1:]),
                        generated_at=f"{calendar['as_of']}T22:03:00Z",
                        finished_at=f"{calendar['as_of']}T22:03:00Z",
                    )
        with self.assertRaises(ContractError):
            complete_baseline_run(
                receipt,
                "ForwardOutcome",
                (*outcomes, outcomes[0]),
                generated_at=f"{calendar['as_of']}T22:03:00Z",
                finished_at=f"{calendar['as_of']}T22:03:00Z",
            )

    def test_completion_binds_normalized_calendar_content_across_all_windows(self):
        event, read, snapshot, calendar, receipt = self.forward_inputs()
        outcomes = produce_forward_outcomes(
            event,
            read,
            snapshot,
            calendar,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{calendar['as_of']}T22:02:00Z",
        )
        other_calendar = build_session_calendar_evidence(
            calendar_name=calendar["calendar_name"],
            calendar_version=calendar["calendar_version"],
            signal_date=calendar["signal_date"],
            as_of=calendar["as_of"],
            sessions=calendar["sessions"],
            target_sessions=calendar["target_sessions"][:-1],
        )
        self.assertEqual(calendar["calendar_id"], other_calendar["calendar_id"])
        self.assertNotEqual(
            calendar["content_fingerprint"],
            other_calendar["content_fingerprint"],
        )

        def with_calendar_fingerprint(outcome, fingerprint):
            values = plain(outcome)
            for field in (
                "forward_outcome_id",
                "forward_content_fingerprint",
                "input_fingerprint",
            ):
                values.pop(field)
            values["session_calendar_fingerprint"] = fingerprint
            return finalize_result("ForwardOutcome", values)

        all_rebound = tuple(
            with_calendar_fingerprint(item, other_calendar["content_fingerprint"])
            for item in outcomes
        )
        with self.assertRaises(ContractError):
            complete_baseline_run(
                receipt,
                "ForwardOutcome",
                all_rebound,
                generated_at=f"{calendar['as_of']}T22:03:00Z",
                finished_at=f"{calendar['as_of']}T22:03:00Z",
            )

        one_rebound = (
            with_calendar_fingerprint(
                outcomes[0], other_calendar["content_fingerprint"]
            ),
            *outcomes[1:],
        )
        with self.assertRaises(ContractError):
            complete_baseline_run(
                receipt,
                "ForwardOutcome",
                one_rebound,
                generated_at=f"{calendar['as_of']}T22:03:00Z",
                finished_at=f"{calendar['as_of']}T22:03:00Z",
            )

        completed = complete_baseline_run(
            receipt,
            "ForwardOutcome",
            outcomes,
            generated_at=f"{calendar['as_of']}T22:03:00Z",
            finished_at=f"{calendar['as_of']}T22:03:00Z",
        )
        self.assertEqual("completed", completed["status"])

    def test_completion_rejects_wrong_target_date_or_adjacent_session_price(self):
        fixture = M10ForwardBaselineTests()
        outcomes, read, _, calendar, receipt = fixture.produce(elapsed=100)
        rows = {row["date"]: row for row in read.rows}
        wrong_indexes = {1: 1, 5: 3, 20: 18, 60: 58, 100: 98}

        def rebound(item, *, target_date=None, endpoint_price=None):
            values = plain(item)
            for field in (
                "forward_outcome_id",
                "forward_content_fingerprint",
                "input_fingerprint",
            ):
                values.pop(field)
            if target_date is not None:
                values["target_session_date"] = target_date
                values["endpoint"] = {
                    "date": target_date,
                    "price": rows[target_date]["close"],
                }
            if endpoint_price is not None:
                values["endpoint"] = {
                    **values["endpoint"],
                    "price": endpoint_price,
                }
            return finalize_result("ForwardOutcome", values)

        for window, wrong_index in wrong_indexes.items():
            with self.subTest(window=window):
                position = next(
                    index for index, item in enumerate(outcomes)
                    if item["window_sessions"] == window
                )
                attacked = list(outcomes)
                attacked[position] = rebound(
                    outcomes[position], target_date=fixture.sessions[wrong_index]
                )
                with self.assertRaises(ContractError):
                    complete_baseline_run(
                        receipt,
                        "ForwardOutcome",
                        attacked,
                        generated_at=f"{calendar['as_of']}T22:03:00Z",
                        finished_at=f"{calendar['as_of']}T22:03:00Z",
                    )

        five = next(item for item in outcomes if item["window_sessions"] == 5)
        self.assertEqual(five["target_session_date"], "2026-09-09")
        wrong_five = rebound(five, target_date="2026-09-08")
        with self.assertRaises(ContractError):
            complete_baseline_run(
                receipt,
                "ForwardOutcome",
                tuple(wrong_five if item is five else item for item in outcomes),
                generated_at=f"{calendar['as_of']}T22:03:00Z",
                finished_at=f"{calendar['as_of']}T22:03:00Z",
            )

        one = next(item for item in outcomes if item["window_sessions"] == 1)
        wrong_price = rebound(
            one, endpoint_price=rows[fixture.sessions[1]]["close"]
        )
        with self.assertRaises(ContractError):
            complete_baseline_run(
                receipt,
                "ForwardOutcome",
                tuple(wrong_price if item is one else item for item in outcomes),
                generated_at=f"{calendar['as_of']}T22:03:00Z",
                finished_at=f"{calendar['as_of']}T22:03:00Z",
            )

        completed = complete_baseline_run(
            receipt,
            "ForwardOutcome",
            outcomes,
            generated_at=f"{calendar['as_of']}T22:03:00Z",
            finished_at=f"{calendar['as_of']}T22:03:00Z",
        )
        self.assertEqual(completed["status"], "completed")

    def test_trade_completion_rejects_changed_plan_or_exit_state(self):
        fixture, state, read, snapshot, receipt, state_link = self.trade_inputs()
        outcome = produce_trade_outcome(
            fixture.event,
            fixture.plan_link,
            fixture.plan,
            (state,),
            state_link,
            read,
            snapshot,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{state['as_of']}T22:02:00Z",
        )
        attacks = (
            {
                "trade_plan_id": "plan:sha256:" + "e" * 64,
                "trade_plan_content_fingerprint": "sha256:" + "e" * 64,
            },
            {
                "exit_state_id": "exit-state:sha256:" + "e" * 64,
                "exit_state_content_fingerprint": "sha256:" + "e" * 64,
            },
        )
        for changes in attacks:
            with self.subTest(changes=changes):
                values = plain(outcome)
                for field in (
                    "trade_outcome_id", "trade_content_fingerprint",
                    "input_fingerprint",
                ):
                    values.pop(field)
                values.update(changes)
                attacked = finalize_result("TradeOutcome", values)
                with self.assertRaises(ContractError):
                    complete_baseline_run(
                        receipt,
                        "TradeOutcome",
                        (attacked,),
                        generated_at=f"{state['as_of']}T22:03:00Z",
                        finished_at=f"{state['as_of']}T22:03:00Z",
                    )

    def test_invalid_batch_does_not_write_or_replace_existing_files(self):
        event, read, snapshot, calendar, receipt = self.forward_inputs()
        valid = evaluate_forward_baseline(
            event,
            read,
            snapshot,
            calendar,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{calendar['as_of']}T22:02:00Z",
            finished_at=f"{calendar['as_of']}T22:03:00Z",
        )
        invalid = BaselineEvaluationBatch(
            result_contract="ForwardOutcome",
            pending_run_receipt=valid.pending_run_receipt,
            outcomes=valid.outcomes[:1],
            completed_run_receipt=valid.completed_run_receipt,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "m10-b"
            store = EvaluationShadowStore(root)
            with self.assertRaises(ContractError):
                store_baseline_evaluation_batch(store, invalid)
            self.assertFalse(root.exists())

        foreign_values = plain(valid.outcomes[0])
        for field in (
            "forward_outcome_id", "forward_content_fingerprint",
            "input_fingerprint",
        ):
            foreign_values.pop(field)
        foreign_values.update({
            "event_id": "opportunity:sha256:" + "e" * 64,
            "event_content_fingerprint": "sha256:" + "e" * 64,
            "instrument_id": "instrument:sha256:" + "e" * 64,
        })
        foreign = finalize_result("ForwardOutcome", foreign_values)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "m10-b"
            store = EvaluationShadowStore(root)
            store.write_result("ForwardOutcome", foreign)
            before = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*") if path.is_file()
            }
            with self.assertRaisesRegex(ContractError, "unregistered"):
                store_baseline_evaluation_batch(store, valid)
            after = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*") if path.is_file()
            }
            self.assertEqual(before, after)

        fixture, state, read, snapshot, receipt, state_link = self.trade_inputs()
        trade = produce_trade_outcome(
            fixture.event,
            fixture.plan_link,
            fixture.plan,
            (state,),
            state_link,
            read,
            snapshot,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{state['as_of']}T22:02:00Z",
        )
        trade_values = plain(trade)
        for field in (
            "trade_outcome_id", "trade_content_fingerprint",
            "input_fingerprint",
        ):
            trade_values.pop(field)
        trade_values["run_id"] = valid.pending_run_receipt["run_id"]
        cross_contract = finalize_result("TradeOutcome", trade_values)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "m10-b"
            store = EvaluationShadowStore(root)
            store.write_result("TradeOutcome", cross_contract)
            before = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*") if path.is_file()
            }
            with self.assertRaisesRegex(ContractError, "unregistered"):
                store_baseline_evaluation_batch(store, valid)
            after = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*") if path.is_file()
            }
            self.assertEqual(before, after)

    def test_shadow_store_persists_pending_results_then_completion(self):
        event, read, snapshot, calendar, receipt = self.forward_inputs()
        batch = evaluate_forward_baseline(
            event,
            read,
            snapshot,
            calendar,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{calendar['as_of']}T22:02:00Z",
            finished_at=f"{calendar['as_of']}T22:03:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationShadowStore(Path(directory) / "m10-b")
            paths = store_baseline_evaluation_batch(store, batch)
            self.assertEqual(len(paths), len(FORWARD_WINDOWS) + 2)
            self.assertTrue(all(path.exists() for path in paths))
            self.assertEqual(paths, store_baseline_evaluation_batch(store, batch))

            values = plain(batch.outcomes[0])
            for field in (
                "forward_outcome_id", "forward_content_fingerprint",
                "input_fingerprint",
            ):
                values.pop(field)
            values.update({
                "event_id": "opportunity:sha256:" + "e" * 64,
                "event_content_fingerprint": "sha256:" + "e" * 64,
                "instrument_id": "instrument:sha256:" + "e" * 64,
            })
            extra = finalize_result("ForwardOutcome", values)
            before = {
                path.relative_to(store.root): path.read_bytes()
                for path in store.root.rglob("*") if path.is_file()
            }
            with self.assertRaisesRegex(ContractError, "terminal"):
                store.write_result("ForwardOutcome", extra)
            after = {
                path.relative_to(store.root): path.read_bytes()
                for path in store.root.rglob("*") if path.is_file()
            }
            self.assertEqual(before, after)

    def test_completed_internal_run_requires_persisted_pending_root(self):
        event, read, snapshot, calendar, receipt = self.forward_inputs()
        batch = evaluate_forward_baseline(
            event,
            read,
            snapshot,
            calendar,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{calendar['as_of']}T22:02:00Z",
            finished_at=f"{calendar['as_of']}T22:03:00Z",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "m10-b"
            store = EvaluationShadowStore(root)
            for outcome in batch.outcomes:
                store.write_result("ForwardOutcome", outcome)

            rootless_values = plain(batch.completed_run_receipt)
            for field in (
                "run_id",
                "run_receipt_id",
                "run_content_fingerprint",
                "input_set_fingerprint",
                "result_set_fingerprint",
            ):
                rootless_values.pop(field)
            rootless_values["supersedes_run_receipt_id"] = None
            rootless = build_experiment_run_receipt(**rootless_values)
            before = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*") if path.is_file()
            }
            with self.assertRaises(ContractError):
                store.write_run_receipt(rootless)
            with self.assertRaises(ContractError):
                store.write_run_receipt(batch.completed_run_receipt)
            self.assertEqual(
                before,
                {
                    path.relative_to(root): path.read_bytes()
                    for path in root.rglob("*") if path.is_file()
                },
            )

            store.write_run_receipt(batch.pending_run_receipt)
            completed_path = store.write_run_receipt(batch.completed_run_receipt)
            self.assertEqual(
                completed_path,
                store.write_run_receipt(batch.completed_run_receipt),
            )

            pending_digest = batch.pending_run_receipt["run_receipt_id"].rsplit(
                ":", 1
            )[-1]
            (root / "runs" / f"{pending_digest}.json").unlink()
            remaining = {
                path.relative_to(root): path.read_bytes()
                for path in root.rglob("*") if path.is_file()
            }
            with self.assertRaises(ContractError):
                store.write_run_receipt(batch.completed_run_receipt)
            self.assertEqual(
                remaining,
                {
                    path.relative_to(root): path.read_bytes()
                    for path in root.rglob("*") if path.is_file()
                },
            )

    def test_concurrent_completed_receipts_preserve_one_immutable_leaf(self):
        event, read, snapshot, calendar, receipt = self.forward_inputs()
        batch = evaluate_forward_baseline(
            event,
            read,
            snapshot,
            calendar,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{calendar['as_of']}T22:02:00Z",
            finished_at=f"{calendar['as_of']}T22:03:00Z",
        )
        alternate_values = plain(batch.completed_run_receipt)
        for field in (
            "run_id",
            "run_receipt_id",
            "run_content_fingerprint",
            "input_set_fingerprint",
            "result_set_fingerprint",
        ):
            alternate_values.pop(field)
        alternate_values.update({
            "generated_at": f"{calendar['as_of']}T22:04:00Z",
            "finished_at": f"{calendar['as_of']}T22:04:00Z",
        })
        alternate = build_experiment_run_receipt(**alternate_values)
        self.assertEqual(
            batch.completed_run_receipt["run_receipt_id"],
            alternate["run_receipt_id"],
        )
        self.assertNotEqual(
            batch.completed_run_receipt["run_content_fingerprint"],
            alternate["run_content_fingerprint"],
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "m10-b"
            store = EvaluationShadowStore(root)
            store.write_run_receipt(batch.pending_run_receipt)
            for outcome in batch.outcomes:
                store.write_result("ForwardOutcome", outcome)

            def attempt(candidate):
                try:
                    store.write_run_receipt(candidate)
                    return "written"
                except ContractError:
                    return "rejected"

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(
                    attempt,
                    (batch.completed_run_receipt, alternate),
                ))
            self.assertEqual(["rejected", "written"], sorted(results))
            self.assertEqual(2, len(list((root / "runs").glob("*.json"))))

    def test_runner_does_not_mutate_m02_or_m09_inputs(self):
        event, read, snapshot, calendar, receipt = self.forward_inputs()
        before = plain({
            "event": event,
            "rows": read.rows,
            "snapshot": snapshot,
            "calendar": calendar,
            "receipt": receipt,
        })
        evaluate_forward_baseline(
            event,
            read,
            snapshot,
            calendar,
            universe_content_fingerprint=UNIVERSE_CONTENT,
            pending_run_receipt=receipt,
            generated_at=f"{calendar['as_of']}T22:02:00Z",
            finished_at=f"{calendar['as_of']}T22:03:00Z",
        )
        after = plain({
            "event": event,
            "rows": read.rows,
            "snapshot": snapshot,
            "calendar": calendar,
            "receipt": receipt,
        })
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
    complete_baseline_run,
    evaluate_forward_baseline,
    evaluate_trade_baseline,
