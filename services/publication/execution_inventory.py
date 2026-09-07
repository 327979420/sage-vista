"""Task inventory derived from registered source bytes and complete execution history.

This is an internal resolver, not a supplied graph validator or an acquisition
attestation. The fixed coordinator must read the authoritative task under lease.
It cannot be used as an inventory of all daily/publication tasks.
"""
import base64
import json

from services.contracts.market_data import canonical_fingerprint, select_universe_snapshot
from services.contracts.validation import ContractError, verify_publication_configuration
from services.market_data import RepositoryRead
from services.publication.configuration import read_configuration_sources
from services.publication.daily_chain import produce_daily_chain
from services.publication.execution_continuation import freeze_execution_signal
from services.publication.execution_history import (
    _decode, _plain, _read, encode, restore_execution_history,
)
from services.publication.inventory import build_source_inventory


def _unbase64(value):
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ContractError('execution source bytes encoding is invalid') from exc


def _replay(sources):
    if not isinstance(sources, dict) or set(sources) != {'configuration_bytes', 'daily_input_bytes'}:
        raise ContractError('execution source envelope is incomplete')
    config_raw = _unbase64(sources['configuration_bytes'])
    try:
        config = json.loads(config_raw)
        evidence = read_configuration_sources(config['code_commit'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError('execution source configuration is invalid') from exc
    config_ref = verify_publication_configuration(config_raw, evidence)
    values = _decode(_unbase64(sources['daily_input_bytes']))
    expected = {'as_of', 'stock_snapshots', 'etf_snapshots', 'stock_reads', 'etf_reads',
                'data_source', 'membership_registry', 'activation', 'generated_at', 'scan_batch_id'}
    if not isinstance(values, dict) or set(values) != expected:
        raise ContractError('execution original daily input is incomplete')
    if (values['data_source'].get('provider') != config['membership']['provider'] or
            values['data_source'].get('market') != config['membership']['market']):
        raise ContractError('execution source provider differs from frozen configuration')
    def reader(records):
        def read(instrument_id, *, as_of):
            try:
                value = RepositoryRead(**records[instrument_id])
                if value.instrument_id != instrument_id or value.as_of != as_of:
                    raise ValueError('read identity')
                return value
            except (KeyError, TypeError, ValueError) as exc:
                raise ContractError('execution original M02 read is missing or mismatched') from exc
        return read
    kwargs = {key: value for key, value in values.items() if key not in {'stock_reads', 'etf_reads'}}
    result = produce_daily_chain(**kwargs, stock_reader=reader(values['stock_reads']),
        etf_reader=reader(values['etf_reads']), etf_registry=config['etf_registry'])
    required_etfs = {item['symbol'] for item in config['etf_registry']['etfs']}
    if set(result.etf.symbol_rows) != required_etfs:
        raise ContractError('execution source does not contain the configured ETF set')
    # Reject unconsumed read maps; the inventory is not inferred from a subset.
    for name, prepared in (('stock', result.stock), ('etf', result.etf)):
        ids = {row['instrument_id'] for row in prepared.market_snapshot['symbols']}
        if set(values[name + '_reads']) != ids:
            raise ContractError('execution source read map differs from consumed M02 inputs')
    return result, values, config_ref


def encode_execution_source_root(configuration_bytes, daily_input_bytes):
    """Freeze the actual default-producer signal together with its source bytes.

    Neither a supplied signal nor substituted detectors/policies are accepted.
    Creation alone is not authoritative registration or permission to run.
    """
    sources = {'configuration_bytes': base64.b64encode(configuration_bytes).decode(),
               'daily_input_bytes': base64.b64encode(daily_input_bytes).decode()}
    daily, _, _ = _replay(sources)
    signal = freeze_execution_signal(daily.ranking.snapshot, daily.support, daily.events)
    return encode({'format': 'm12-execution-signal/2', 'signal': signal, 'sources': sources})


def build_execution_source_inventory(snapshot, objects, *, generated_at):
    """Resolve this task's registered root, sources and ALL paired artifacts.

    Roots/dependencies are derived here; there is no caller roots/nodes argument.
    The existing SourceInventory producer/validator alone verifies the closure.
    """
    restored = restore_execution_history(snapshot, objects)
    root_raw = _read(snapshot['root']['root'], objects)
    root = _decode(root_raw)
    if root.get('format') != 'm12-execution-signal/2':
        raise ContractError('execution root has no complete registered source bundle')
    daily, inputs, config_ref = _replay(root['sources'])
    signal = freeze_execution_signal(daily.ranking.snapshot, daily.support, daily.events)
    if encode(signal) != encode(restored.signal):
        raise ContractError('registered signal differs from original source replay')
    nodes = {}
    def add(stable_id, fingerprint, dependencies=()):
        ref = {'id': stable_id, 'content_fingerprint': fingerprint}
        deps = {item['id']: item for item in dependencies}
        node = {'ref': ref, 'dependencies': [deps[key] for key in sorted(deps)]}
        if stable_id in nodes and nodes[stable_id] != node:
            raise ContractError('execution inventory contains conflicting resolved originals')
        nodes[stable_id] = node
        return ref
    add(config_ref['id'], config_ref['content_fingerprint'])
    # Byte originals are leaves. Their logical contracts below carry actual
    # business dependencies; no embedded reference is used to assert authority.
    raw_refs = [add('execution-archive:' + ref['sha256'], ref['sha256']) for ref in
                [snapshot['root']['root'], *[row[key] for row in snapshot['history'] for key in ('input', 'object', 'link')]]]
    markets = []
    for name, prepared in (('stock', daily.stock), ('etf', daily.etf)):
        universe = select_universe_snapshot(inputs[name + '_snapshots'], as_of=daily.stock.as_of)
        universe_ref = add(universe['universe_id'], canonical_fingerprint(universe), [config_ref])
        reads = []
        for original in inputs[name + '_reads'].values():
            digest = canonical_fingerprint(original)
            reads.append(add('repository-read:' + digest, digest, [universe_ref]))
        markets.append(add(prepared.market_snapshot_id, canonical_fingerprint(_plain(prepared.market_snapshot)), [universe_ref, *reads]))
    parents = [config_ref, *markets]
    def records(items, id_key, fingerprint_key, dependencies):
        return [add(item[id_key], item.get(fingerprint_key) if fingerprint_key in item else canonical_fingerprint(_plain(item)), dependencies)
                for item in items]
    gates = records(daily.gates.events, 'gate_event_id', 'event_content_fingerprint', parents)
    technical = records(daily.technical.evidence, 'evidence_id', 'evidence_content_fingerprint', [*parents, *gates])
    technical_batch = add(daily.technical.batch_id, daily.technical.batch_id.split(':', 1)[1], [*parents, *technical])
    support = records(daily.support.evidence, 'support_evidence_id', 'support_content_fingerprint', [technical_batch, *gates])
    support_batch = add(daily.support.batch_id, daily.support.batch_id.split(':', 1)[1], [technical_batch, *support])
    models = records(daily.models.assessments, 'assessment_id', 'assessment_content_fingerprint', [technical_batch, *gates])
    model_batch = add(daily.models.batch_id, daily.models.batch_id.split(':', 1)[1], [technical_batch, *models])
    etf_states = records(daily.context.etf_states, 'state_id', 'state_content_fingerprint', parents)
    contexts = records(daily.context.contexts, 'context_id', 'context_content_fingerprint', [model_batch, technical_batch, *etf_states])
    context_batch = add(daily.context.batch_id, daily.context.batch_id.split(':', 1)[1], [*contexts, *etf_states, model_batch])
    scores = records(daily.ranking.snapshot['score_results'], 'score_result_id', 'score_content_fingerprint', [technical_batch, model_batch, context_batch])
    ranking = add(signal.ranking['ranking_snapshot_id'], signal.ranking['ranking_content_fingerprint'], [*scores, context_batch, technical_batch, model_batch])
    events = records(signal.events.events, 'event_id', 'event_content_fingerprint', [ranking, support_batch])
    event_batch = add(signal.events.batch_id, signal.events.batch_id.split(':', 1)[1], [ranking, *events])
    execution_parents = [ranking, support_batch, event_batch]
    input_refs, plan_input, state_input = {}, {}, {}
    for row in snapshot['history']:
        input_ref = nodes['execution-archive:' + row['input']['sha256']]['ref']
        value = _decode(_read(row['object'], objects))
        input_refs[row['step_id']] = input_ref
        if value['kind'] == 'plans':
            for plan in value['batch']['plans']:
                plan_input.setdefault(plan['plan_id'], input_ref)
        else:
            state_input[value['state']['exit_state_id']] = input_ref
    plan_refs = {plan['plan_id']: add(plan['plan_id'], plan['plan_content_fingerprint'],
        [ranking, support_batch, plan_input[plan['plan_id']]]) for plan in restored.plans}
    state_refs = {}
    for state in restored.states:
        prior = state['previous_exit_state_id']
        dependencies = [plan_refs[state['plan_id']], state_input[state['exit_state_id']]]
        if prior is not None:
            dependencies.append(state_refs[prior])
        state_refs[state['exit_state_id']] = add(state['exit_state_id'], state['exit_state_content_fingerprint'], dependencies)
    links, batch_refs = [], {}
    as_of = daily.stock.as_of
    for row in snapshot['history']:
        value = _decode(_read(row['object'], objects))
        if value['kind'] == 'plans':
            batch = value['batch']
            batch_refs[batch['batch_id']] = add(batch['batch_id'], batch['batch_id'].split(':', 1)[1],
                [ranking, support_batch, input_refs[row['step_id']], *[plan_refs[plan['plan_id']] for plan in batch['plans']]])
        linked = _decode(_read(row['link'], objects))
        links.extend(linked if isinstance(linked, list) else [linked])
        as_of = max(as_of, _decode(_read(row['input'], objects))['as_of'])
    link_refs = []
    for link in links:
        source = link['source_reference']
        parent = batch_refs[source['trade_plan_batch_id']] if link['link_type'] == 'trade_plan_decision' else state_refs[source['exit_state_id']]
        link_refs.append(add(link['link_id'], link['link_content_fingerprint'], [event_batch, parent]))
    plans, states, batches = list(plan_refs.values()), list(state_refs.values()), list(batch_refs.values())
    digest = canonical_fingerprint(snapshot)
    # The root comes from the entire registered task snapshot, never a selected
    # result list. Include no-gate audits and source bundle even for zero events.
    task_root = add('execution-inventory-root:' + digest, digest,
                    [*execution_parents, context_batch, *raw_refs, *plans, *states, *batches, *link_refs])
    evidence = {'as_of': as_of, 'config_ref': config_ref, 'roots': [task_root],
                'nodes': [nodes[key] for key in sorted(nodes)]}
    return build_source_inventory(evidence, generated_at=generated_at)
