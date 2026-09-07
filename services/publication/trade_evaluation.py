"""Compose registered execution evidence with the original M10 baseline.

Internal computation only: snapshot/objects must come from the task archive's
full locked readback. Market/universe arguments are already acquired evidence,
not supplier authorization. No IO, exit advancement, or alternative evaluator.
The returned dependency bytes must be persisted and bound by the coordinator.
"""
from dataclasses import dataclass

from services.contracts.market_data import canonical_fingerprint, validate_universe_snapshot
from services.contracts.validation import ContractError
from services.evaluation.baseline import (
    BASELINE_ADAPTER_VERSION, BASELINE_ENGINE_NAME, BASELINE_ENGINE_VERSION,
    BASELINE_SOURCE_VERSION, baseline_run_scope_fingerprint, trade_result_scope_keys,
)
from services.evaluation.contracts import build_experiment_run_receipt
from services.evaluation.orchestration import _actual_trade_refs, _expected_policies
from services.evaluation.policies import EVALUATION_POLICY
from services.evaluation.runner import BaselineEvaluationBatch, evaluate_trade_baseline
from services.execution import current_exit_state
from services.publication.execution_history import (
    _decode, _plain, _read, encode, restore_execution_history,
)


@dataclass(frozen=True)
class RegisteredTradeEvaluation:
    task_id: str
    state: str
    reason: str | None
    dependency_bytes: bytes
    batch: BaselineEvaluationBatch | None


def evaluate_registered_trade(snapshot, objects, *, event_id, market_read,
                              market_snapshot, universe_snapshot, code_commit,
                              generated_at, finished_at, previous_outcomes=()):
    """Read only paired facts; M10 alone computes outcome status and metrics.

    A completed *run* containing a pending/unavailable outcome remains queued.
    Missing plan/exit dependencies produce no invented M10 receipt. This local
    adapter does not claim an attempt or register a production completion.
    """
    history = restore_execution_history(snapshot, objects)
    events = [event for event in history.signal.events.events if event['event_id'] == event_id]
    if len(events) != 1:
        raise ContractError('trade evaluation requires one registered original event')
    event = events[0]
    policy = EVALUATION_POLICY
    task_id = 'evaluation-task:' + canonical_fingerprint({
        'event_ref': {'id': event_id, 'content_fingerprint': event['event_content_fingerprint']},
        'result_contract': 'TradeOutcome', 'window_sessions': None,
        'evaluation_policy_ref': {'id': 'evaluation-policy:' + policy['policy_version'],
                                  'content_fingerprint': policy['policy_fingerprint']},
        'candidate_or_baseline': 'baseline', 'partition_role': 'forward',
    })
    links = []
    for row in snapshot['history']:
        value = _decode(_read(row['link'], objects))
        links.extend(value if isinstance(value, list) else [value])
    decisions = [link for link in links if link['event_id'] == event_id
                 and link['link_type'] == 'trade_plan_decision']
    dependencies = {'format': 'm12-trade-dependencies/1', 'task_id': task_id,
                    'execution_snapshot': snapshot, 'event': event}
    def waiting(reason):
        return RegisteredTradeEvaluation(task_id, 'queued', reason, encode(dependencies), None)
    if not decisions:
        return waiting('trade_plan_link_unavailable')
    # Append order comes from the complete authoritative execution history.
    # A later created decision supersedes an earlier unavailable observation.
    link = decisions[-1]
    plan, states, state, state_link = None, (), None, None
    if link['status'] == 'created':
        plans = [item for item in history.plans if item['plan_id'] == link['source_reference']['plan_id']]
        if len(plans) != 1:
            raise ContractError('registered trade decision has no unique plan')
        plan = plans[0]
        states = tuple(item for item in history.states if item['plan_id'] == plan['plan_id'])
        if not states:
            return waiting('exit_state_link_unavailable')
        state = current_exit_state(states)
        state_links = [item for item in links if item['event_id'] == event_id
                       and item['link_type'] == 'exit_state'
                       and item['source_reference']['exit_state_id'] == state['exit_state_id']]
        if len(state_links) != 1:
            raise ContractError('registered trade state has no unique paired M09 link')
        state_link = state_links[0]
    validate_universe_snapshot(universe_snapshot)
    if universe_snapshot['universe_id'] != event['input_identity']['universe_id']:
        raise ContractError('trade evaluation changes the frozen universe')
    universe_fingerprint = canonical_fingerprint(_plain(universe_snapshot))
    arguments = dict(event=event, trade_plan_link=link, trade_plan=plan,
                     exit_states=states, exit_state_link=state_link,
                     market_read=market_read, market_snapshot=market_snapshot,
                     universe_content_fingerprint=universe_fingerprint)
    refs = _actual_trade_refs(arguments)
    policies = _expected_policies('trade_evaluation')
    as_of = state['as_of'] if state is not None else event['signal_date']
    scope = baseline_run_scope_fingerprint(
        'TradeOutcome', input_refs=refs, policy_refs=policies, path_status='formal',
        result_role='authoritative', partition_role='forward', instrument_id=event['instrument_id'],
        signal_date=event['signal_date'], market_data_fingerprint=market_read.point_in_time_fingerprint,
        expected_result_keys=trade_result_scope_keys(event, link, plan, state,
                                                    market_snapshot, universe_fingerprint))
    previous = tuple(previous_outcomes)
    dependencies.update(arguments=_plain(arguments), universe_snapshot=universe_snapshot,
                        previous_outcomes=previous, code_commit=code_commit)
    dependency_bytes = encode(dependencies)
    attempt_id = 'm12-trade:' + canonical_fingerprint(_plain(dependencies))
    pending = build_experiment_run_receipt(
        as_of=as_of, generated_at=generated_at,
        source_version={'evaluation_contracts': BASELINE_SOURCE_VERSION},
        attempt_id=attempt_id, experiment_id=task_id, status='pending',
        evidence_window={'start': event['signal_date'], 'end': as_of, 'evidence_as_of': as_of},
        path_status='formal', result_role='authoritative', partition_role='forward', bias_labels=[],
        code_commit=code_commit, config_ref={'config_id': 'm12-trade-baseline-scope',
            'config_version': '1.0.0', 'content_fingerprint': scope},
        engine={'name': BASELINE_ENGINE_NAME, 'version': BASELINE_ENGINE_VERSION,
                'adapter_version': BASELINE_ADAPTER_VERSION},
        policy_refs=policies, input_refs=refs, result_refs=[], started_at=generated_at,
        finished_at=None, parent_run_id=None, checkpoint_ref=None, error=None)
    batch = evaluate_trade_baseline(**arguments, pending_run_receipt=pending,
        generated_at=generated_at, finished_at=finished_at, previous_outcomes=previous)
    outcome = batch.outcomes[0]
    complete = outcome['status'] in {'completed', 'no_trade'}
    return RegisteredTradeEvaluation(task_id, 'completed' if complete else 'queued',
        None if complete else outcome['status_reason'], dependency_bytes, batch)
