"""Pure frozen-signal continuation. No source attestation, store or task runner.

The eventual trusted inventory adapter must read the entire original signal and
execution history under its task lease. Sessions must come from verified M02
calendar/tradability evidence, never inferred from available bars. This function
alone cannot prove either source completeness or a durable checkpoint.
"""
from dataclasses import dataclass, replace
from typing import Any, Mapping

from services.contracts.configuration import _policy_objects
from services.contracts.market_data import canonical_fingerprint, require_date
from services.contracts.validation import ContractError
from services.execution import (
    TradePlanBatch, advance_exit_state, current_exit_state, produce_trade_plans, validate_trade_plan,
)
from services.factors import SupportEvidenceBatch, validate_support_evidence_batch
from services.ledger import (
    EventLedgerBatch, produce_exit_state_link, produce_trade_plan_links, validate_event_ledger_batch,
)
from services.ledger.producer import _freeze
from services.market_data import RepositoryRead
from services.market_data.normalization import validate_adjusted_rows
from services.ranking import validate_ranking_snapshot


@dataclass(frozen=True)
class FrozenExecutionSignal:
    ranking: Mapping[str, Any]
    support: SupportEvidenceBatch
    events: EventLedgerBatch


def freeze_execution_signal(ranking, support, events):
    """Detach original validated batches; no new formal contract or task ID."""
    validate_ranking_snapshot(ranking)
    validate_support_evidence_batch(support)
    validate_event_ledger_batch(events)
    policies = _policy_objects()
    for kind in ('score', 'ranking', 'authority'):
        if ranking[kind + '_policy_fingerprint'] != policies['M07.' + kind]['policy_fingerprint']:
            raise ContractError('frozen execution signal must use approved policies')
    # Original producers check cross-batch conservation and formal authority,
    # including the empty-event case, without inventing a second validator.
    plans = produce_trade_plans(ranking, support, entry_reads={}, generated_at=ranking['generated_at'])
    produce_trade_plan_links(events, plans, generated_at=ranking['generated_at'])
    return FrozenExecutionSignal(
        _freeze(ranking), replace(support, evidence=_freeze(support.evidence)),
        replace(events, events=_freeze(events.events)),
    )


@dataclass(frozen=True)
class ExecutionContinuation:
    # Persist in order: M08 object, corresponding M09 link. Only the future
    # transactional adapter may advance a checkpoint after both are registered.
    records: tuple[tuple[str, Mapping[str, Any]], ...]
    plan_batch: TradePlanBatch
    pending: Mapping[str, str]


def continue_execution_signal(
    signal, *, as_of, sessions_by_instrument, entry_reads, completed_reads,
    existing_plans=(), existing_states=(), generated_at,
):
    """Backfill original entry, then one original exit transition per session.

    Supplied existing plans/states are the full frozen inventory, not a caller
    selected subset. This pure seam is intentionally not reachable by RPC.
    """
    signal = freeze_execution_signal(signal.ranking, signal.support, signal.events)
    require_date(as_of, 'execution.as_of')
    if as_of < signal.ranking['as_of']:
        raise ContractError('execution cannot predate the original signal')
    calendars = {}
    for instrument, values in sessions_by_instrument.items():
        dates = tuple(require_date(day, 'execution.session') for day in values)
        if dates != tuple(sorted(set(dates))) or any(
            day <= signal.ranking['as_of'] or day > as_of for day in dates
        ):
            raise ContractError('execution sessions must be ordered within the original signal window')
        calendars[instrument] = dates
    for instrument, read in entry_reads.items():
        dates = calendars.get(instrument, ())
        if not isinstance(read, RepositoryRead) or not dates or read.as_of != dates[0]:
            raise ContractError('entry must use the first original tradable session')
    batch = produce_trade_plans(signal.ranking, signal.support,
                               entry_reads=entry_reads, generated_at=generated_at)
    candidates = {plan['plan_id']: plan for plan in batch.plans}
    seen = set()
    for plan in existing_plans:
        validate_trade_plan(plan)
        candidate = candidates.get(plan['plan_id'])
        if (plan['plan_id'] in seen or candidate is None or
                candidate['plan_content_fingerprint'] != plan['plan_content_fingerprint']):
            raise ContractError('stored plan conflicts with frozen entry evidence')
        seen.add(plan['plan_id'])
        candidates[plan['plan_id']] = _freeze(plan)  # Keep original generated_at too.
    batch = replace(batch, plans=tuple(candidates[plan['plan_id']] for plan in batch.plans))
    links = produce_trade_plan_links(signal.events, batch, generated_at=generated_at)
    events = {event['event_id']: event for event in signal.events.events}
    grouped = {plan_id: [] for plan_id in candidates}
    for state in existing_states:
        if state['plan_id'] not in grouped:
            raise ContractError('stored exit state belongs to another frozen signal')
        grouped[state['plan_id']].append(state)
    records, pending = [], {}
    for link in links:
        plan_id = link['source_reference']['plan_id']
        if plan_id is None:
            records.append(('link', link))
            if link['status'] == 'unavailable':
                pending[link['instrument_id']] = link['reason']
            continue
        plan = candidates[plan_id]
        records.extend((('plan', plan), ('link', link)))
        history = grouped[plan_id]
        previous = current_exit_state(history) if history else None
        # Restore every missing historical association before new transitions.
        for state in sorted(history, key=lambda item: (item['holding_sessions'], item['as_of'])):
            if state['plan']['plan_content_fingerprint'] != plan['plan_content_fingerprint']:
                raise ContractError('stored exit state changes the frozen plan')
            records.extend((('exit', _freeze(state)), ('link', produce_exit_state_link(
                events[link['event_id']], link, state, generated_at=generated_at))))
        if previous is not None and previous['as_of'] > as_of:
            raise ContractError('stored exit state is newer than this execution attempt')
        instrument = plan['instrument_id']
        read = completed_reads.get(instrument)
        if read is None:
            if previous is None or previous['state'] == 'active':
                pending[instrument] = 'completed_prices_unavailable'
            continue  # A terminal chain can repair associations without new bars.
        if not isinstance(read, RepositoryRead) or read.instrument_id != instrument or read.as_of > as_of:
            raise ContractError('completed read identity/date does not match execution')
        rows = validate_adjusted_rows(read.rows)
        if (not rows or rows[-1]['date'] != read.as_of or
                read.point_in_time_fingerprint != canonical_fingerprint(list(rows))):
            raise ContractError('completed read fingerprint or cutoff is invalid')
        path = tuple(row for row in rows if row['date'] >= plan['entry_date'])
        dates = calendars.get(instrument, ())
        if any(row['date'] not in dates for row in path):
            raise ContractError('completed prices contain a non-session date')
        by_date = {row['date']: row for row in path}
        prefix = []
        for day in dates:
            if day not in by_date:
                pending[instrument] = 'completed_session_unavailable:' + day
                break
            prefix.append(by_date[day])
        if prefix and prefix[0] != dict(entry_reads[instrument].rows[-1]):
            raise ContractError('completed entry bar changes frozen entry evidence')
        held = int(previous['holding_sessions']) if previous else 0
        if previous:
            # Original M08 rejects short or rewritten already-observed prefixes.
            advance_exit_state(plan, completed_bars=prefix[:held],
                               previous_state=previous, generated_at=generated_at)
        if previous is not None and previous['state'] != 'active':
            pending.pop(instrument, None)
            continue
        for count in range(held + 1, len(prefix) + 1):
            state = advance_exit_state(plan, completed_bars=prefix[:count],
                                       previous_state=previous, generated_at=generated_at)
            records.extend((('exit', state), ('link', produce_exit_state_link(
                events[link['event_id']], link, state, generated_at=generated_at))))
            previous = state
            if state['state'] != 'active':
                pending.pop(instrument, None)
                break
    return ExecutionContinuation(tuple(records), batch, _freeze(pending))
