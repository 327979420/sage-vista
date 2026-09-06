"""Frozen first-run configuration semantics; invoked only via validation.py.

Git blob pins are mechanically captured from the approved definition commit.
They freeze existing business sources; new M12 adapters are bound separately by
code_commit. Nothing here reads Git, files, tokens, or supplier data.
"""
from collections.abc import Mapping
import hashlib

from .validation import ContractError, _canonical, _m12_commit, _m12_exact, _m12_json

DEFINITION_COMMIT = "14fef535f67b7c4de035b4c84224e604850f1fed"
# Complete services tree at the approved baseline, except the two already
# approved M12 integration files (shared validation and provider transport).
# This is a source freeze, not a claim to parse/revalidate all old algorithms.
BASELINE_BLOBS = {
    'data/context/etf-registry-v1.json': ('100644', '439fb7c9362f638cb343351b1dc60cf33f83ff12'),
    'public/factor-registry.json': ('100644', 'a46c59fbe2d6c8e4510e96c8fd1b1ce01fa9640e'),
    'services/automation/eod_scheduler_worker.mjs': ('100644', 'a03aee897eb4867327449ba48a804486cbbdba91'),
    'services/context/__init__.py': ('100644', '8164d4372164d7c0fc9c1c2610dc9d53ed7d3904'),
    'services/context/producer.py': ('100644', 'b46a4b34dc1874372e72d73d99c6f3e6bd7c56a9'),
    'services/context/registry.py': ('100644', '264558177d2fdae8c4f39a2d3a15401e2384c707'),
    'services/contracts/__init__.py': ('100644', '062d90006e3b288f33bbdcf89e320bd6628ffc25'),
    'services/contracts/adapters.py': ('100644', '169d14951787d57c9bf5b1e75671dea5d8c67edd'),
    'services/contracts/manifest.py': ('100644', '395d8c27a977b7c212d24efa38dc1dadfbc8f06f'),
    'services/contracts/market_data.py': ('100644', '0f5c3ed9e23d9757b045560250e1a5380aa8a921'),
    'services/contracts/policies.py': ('100644', 'e253d2f73d3460c2b251017c91162e277bceadc6'),
    'services/evaluation/__init__.py': ('100644', '4d5359940e2650e3689c3543ed03639b8c84474d'),
    'services/evaluation/aggregate.py': ('100644', 'fa7928e84302309adb287eb07ee91ebd1c9f2430'),
    'services/evaluation/baseline.py': ('100644', 'c64a4298d5aaf45387ad6c3e30d03502cdf9ef3d'),
    'services/evaluation/checkpoint.py': ('100644', 'ffa8805809b27f89512e12b0d3c2203babe68bfe'),
    'services/evaluation/config.py': ('100644', 'a437f6760ef5f9570d990f1b0740db4e634ad485'),
    'services/evaluation/contracts.py': ('100644', 'a5cb39ec4e461430eae61c11c3e534fe0d12dc06'),
    'services/evaluation/export.py': ('100644', '66137ebbb7673b0b97625307c80be1eb431c7cbf'),
    'services/evaluation/metrics.py': ('100644', '1192872611a712d711946f83f46668ad069487f3'),
    'services/evaluation/ooxml.py': ('100644', '9fa76bdbb601be5997de4c768e9f550965b9a053'),
    'services/evaluation/orchestration.py': ('100644', 'b92f178f2dc7cf1f5355e972e1e6dcbccfa4828d'),
    'services/evaluation/policies.py': ('100644', 'b70db478ccda282649f20ce3bac7e4828697bf5b'),
    'services/evaluation/query.py': ('100644', 'b46f6f703867af288353dc45be2b8d9d56bc8e62'),
    'services/evaluation/runner.py': ('100644', 'ed1a4faec2e12cb3320c523e5d67d83d8e123b23'),
    'services/evaluation/storage.py': ('100644', 'f81052a82679d0a00fe30f6a6ae73137647a22a5'),
    'services/evaluation/xlsx_export.py': ('100644', 'cfa1c7beddedb0714bfaa7b48662194f64cb5987'),
    'services/execution/__init__.py': ('100644', '5bc24dc68a977ce2fbb6cb3615675cb8cb7a458f'),
    'services/execution/adapters.py': ('100644', 'c71e3e34a7168f310fc20d0d4f08e01d656dee52'),
    'services/execution/policies.py': ('100644', 'd6ad1a775c8aa275c14e794bd7e6c8bbaf3f04d4'),
    'services/execution/producer.py': ('100644', 'a47118449450a2ca60f9b1684b56ef944985ad14'),
    'services/execution/storage.py': ('100644', 'c8900857a79d88c9def723caf069ad5eb5b9845e'),
    'services/factors/__init__.py': ('100644', '35f38133be57ff4ecc804b748c238e943add4fc8'),
    'services/factors/adapters.py': ('100644', '43508cd5963c7b8e00394fdadc271f408803dcf8'),
    'services/factors/producer.py': ('100644', '747f85ad429809f3e9fa087829bc9d72f265c081'),
    'services/factors/support.py': ('100644', 'a019e55cefa85c3d925b191d494ded27aab0e06b'),
    'services/gates/__init__.py': ('100644', '07ae0c01b8fd9acc582e45f867efb80cffd407f3'),
    'services/gates/baseline.py': ('100644', 'e5279c3e4de53076b7955d9b81fec6135284da25'),
    'services/gates/local_structure.py': ('100644', 'dda70d036921195cc951e5cc63342f454003ef39'),
    'services/gates/long_term_state.py': ('100644', 'f1dab9bec5dcb08c64d24e2dbc8c5f695c80466e'),
    'services/gates/producer.py': ('100644', '6b2c6498f949c9ed617bfdc17789b01418201127'),
    'services/ledger/__init__.py': ('100644', '5a149d87d35ecda6ed263b110ab5763642b0e88a'),
    'services/ledger/adapters.py': ('100644', '97dc88c5099048da9e36f7e465b39ff556391d98'),
    'services/ledger/producer.py': ('100644', '4ca97def34472006c74648e255a7ba69881a1ee1'),
    'services/ledger/storage.py': ('100644', '6870d3a70cd6ac975982a06010911133c6cfe1f7'),
    'services/market_data/__init__.py': ('100644', '36bb3ee81dda093dd18bde466b48110a54794d3c'),
    'services/market_data/consumer.py': ('100644', '1041dbd2880a4d897d313424387617c9d9ee0eb2'),
    'services/market_data/legacy.py': ('100644', 'c729228a6d155308a51339785283a4d09d9e6e20'),
    'services/market_data/normalization.py': ('100644', '9657ede7c8e732d0fa5eff9456176c18f0350b18'),
    'services/market_data/repository.py': ('100644', 'ed22f065ce8c5943ba6359bae69031f970595f5c'),
    'services/market_data/storage.py': ('100644', '181c6d60821ca919ad5d7613e9d6169b2de36ac7'),
    'services/market_data/universe.py': ('100644', '2ba817871e04a28bab68275c59dfe0735773810b'),
    'services/playbook/__init__.py': ('100644', '62e9b6f7d6a6ce67c62b990f0c39a897c7a1a3ab'),
    'services/playbook/authority.py': ('100644', 'ee9d298897b56617929185671f77bac4da9774f5'),
    'services/playbook/contracts.py': ('100644', '9aeada510a8e6142ac9fbaa88596811e5bfb1749'),
    'services/playbook/evidence.py': ('100644', '2844aa60311b715d46cb34622070c67c91fce0e6'),
    'services/playbook/producer.py': ('100644', '3ec344250857a72719a7d50b6dca32d4c8c420fa'),
    'services/playbook/registry.py': ('100644', '2f6670922ec07a71f83a45fb3d3745b9202f37ec'),
    'services/playbook/storage.py': ('100644', 'd66632b6b15afdbbf1006328269f43704307ce56'),
    'services/ranking/__init__.py': ('100644', 'e1a02041d71cae91ba359c757f90008c4a59f7d6'),
    'services/ranking/adapters.py': ('100644', '35ba075a626b099b13c0d602bd573ab1ebb2aaa6'),
    'services/ranking/policies.py': ('100644', '846c6aab13e122a0300b664a404fdc976d8462ca'),
    'services/ranking/producer.py': ('100644', 'cc9af13aec59aadd5c05ba2e0b4d80faf54cc0c8'),
    'services/ranking/storage.py': ('100644', '5be63b3d31757cd9c401db35fa63536a1f41769a'),
    'services/scanner/__init__.py': ('100644', '804b07afad2a2a4edfa7d382bc6780d9dd79309c'),
    'services/scanner/audit_eodhd.py': ('100644', '9116c30ee1ba35254b0dc0b804ca657bd2281b8d'),
    'services/scanner/backtest_progress.py': ('100644', '709dd1427a8264de7769d5eba2663cfdbcb508f5'),
    'services/scanner/cache_theme_etfs.py': ('100644', '2b7881b5687e3211898ccb558bb94241d52ff1dd'),
    'services/scanner/confluence_rules.py': ('100644', 'c18e3bcd2707608632342c2ded9b235e481c1fdc'),
    'services/scanner/daily_tracker_update.py': ('100644', '530e23a2d7c120b5073194c2788c53e8374badef'),
    'services/scanner/date_partitions.py': ('100644', 'faa0c44cfe7f121c674170dbe7c3bfbdc7b6056c'),
    'services/scanner/decision_summary.py': ('100644', 'e88ce8ea85edf0c2bafb2b9e19457b6d4a0ecb3b'),
    'services/scanner/detectors.py': ('100644', 'fcb703fd2a8d9dd464d769027852aadcfe1be691'),
    'services/scanner/discord_daily_digest.py': ('100644', '4fc9feeba67803750a384abc8b575b58558bd2c3'),
    'services/scanner/eodhd_factor_pilot.py': ('100644', '7474dd93bb3e60ea54286ff4194ba6375d37a17f'),
    'services/scanner/eodhd_factor_validation.py': ('100644', '0fa3ef3e159fc775301eb15accb554950225a264'),
    'services/scanner/expand_tracker_universe.py': ('100644', '9a8d0ed1b7c384b860a3493f50277ba2864d5b7e'),
    'services/scanner/experiment_catalog.py': ('100644', '6de1e98bbae85ba0a85a27dcd4e11f83f493fb36'),
    'services/scanner/factor_detectors.py': ('100644', '33ab5c971a919ce1762476a34b4370f6820a794d'),
    'services/scanner/factor_effectiveness.py': ('100644', '41b4d51f19e0600ee7d2feb65dabadf339394c9b'),
    'services/scanner/factor_registry.py': ('100644', '9e760649f2cfcdb1f6ed6ec9760d7cc9a6a59b5a'),
    'services/scanner/factor_scoring.py': ('100644', '89ac71eb1aa0bcbfed4371b797efd728d2aafb26'),
    'services/scanner/factor_snapshot.py': ('100644', 'ef0cc3fe1d474248c0f7c6e2f79951afcc0e2b99'),
    'services/scanner/favorite_pattern_tracker.py': ('100644', '4962b2dd031e73064178c1232dfb8054f1dffc88'),
    'services/scanner/fetch_nasdaq.py': ('100644', '8942e2167c46ca723e47cf4b9332bcfecf881904'),
    'services/scanner/fetch_yahoo.py': ('100644', '75f67007290e522a392037242b0e056cc03378a6'),
    'services/scanner/freshness_monitor.py': ('100644', '14d1f35a0813f68d73864cb6ef30619502e105e9'),
    'services/scanner/industry_membership.py': ('100644', 'e5d3bd36fb0ccc02ac26440df93c994b585cb55d'),
    'services/scanner/industry_radar.py': ('100644', '24f77e093f5ddc63f0a3426b19dc7bf57ab51964'),
    'services/scanner/legacy_signal_recovery.py': ('100644', '67575924a1ea3be46d2a038dd4d161bad0e7de15'),
    'services/scanner/macd_factor_backtest.py': ('100644', '67497342d7e290729d3ef175c3f0cfb89bd9bb45'),
    'services/scanner/market_context_factor_test.py': ('100644', 'b63b0a7489738691c04a52342484808bbf57627c'),
    'services/scanner/market_etf_watch.py': ('100644', '89b79746c9f7256ad97f8c40b8383da6bf13e382'),
    'services/scanner/merge_unified_v2_reports.py': ('100644', 'ac76b9e85ae933b3d8e3f948b00f83c863f874b9'),
    'services/scanner/neutralization_test.py': ('100644', '491fb980acd9251348691093cfd97d4b5b010afc'),
    'services/scanner/open_source_industry.py': ('100644', 'c3cc15f4b8ed07885e56d140cc26878c4e6ab3bb'),
    'services/scanner/opportunity_ledger.py': ('100644', '0ae6a1265314d6f307b2669660bf00e2408eb263'),
    'services/scanner/project_status.py': ('100644', '64b01b1db8bd0d24e46065dad776e9e2b0dc26f4'),
    'services/scanner/quick_scan.py': ('100644', 'ea739c3a896334ca170e778c592584a602013b99'),
    'services/scanner/rare_opportunity_scanner.py': ('100644', 'a7cbed609168bd37305343510442d8393c832335'),
    'services/scanner/refresh_validation_analysis.py': ('100644', '141d890cd2e735b24f5db53e198b225014d23b15'),
    'services/scanner/rescore_candidate_pool.py': ('100644', 'fba49f0240374dc05a4881c9f67c0b4c26b2ef1a'),
    'services/scanner/research_pipeline.py': ('100644', 'a390fa823e14fa31b877c56fe50900960ebad259'),
    'services/scanner/research_schema.sql': ('100644', 'ece8772d6a06cbb73cfede8fb15eb4e96d57a1fe'),
    'services/scanner/resonance_tracker.py': ('100644', 'e6edaae123fdafb9ba0fc25a1b60c2c6bb1dc894'),
    'services/scanner/signal_history.py': ('100644', '6b89ec66dc21738b9618854b7c6cf9b4774722d7'),
    'services/scanner/support_risk.py': ('100644', '551bd3b7bee6e6a005c8b4c20f598b336bd63076'),
    'services/scanner/technical.py': ('100644', 'fcec45b0da130d4829c4325a6ecc701d9000412a'),
    'services/scanner/theme_etf_context.py': ('100644', '0bd62b3c649857fc28fe90a2d44d289f977984af'),
    'services/scanner/unified_v2_scan.py': ('100644', '68d0d4d52075ae1aa644056bca3a3df068a7f9e5'),
    'services/scanner/verify_live_deployment.py': ('100644', 'c331aea2fbe18b1cb4c938501078568534297a8a'),
    'services/selectors/__init__.py': ('100644', '1214885bc8d122029d535d083351ed6ed821f9f1'),
    'services/selectors/adapters.py': ('100644', '99c385c22035e35af768179b94e71c7886cbc63e'),
    'services/selectors/producer.py': ('100644', 'c7e242e99147e07bb0e9dd16f69124f521ccc96c'),
}

POLICY_PINS = {
    'M07.score': '3c9f4b0906aca617943a863f1c3dd47dcbb9fcfc6c66a0a7eab496df3ed8ccda',
    'M07.ranking': '11637db181b6806db901c281c521e6ae2cdeb4d58be0f9af4822e505573d38e6',
    'M07.authority': 'c9fe70a2d2dab9651961dd882cb003d2bbccc18e6b2b066614693d422e75908e',
    'M08.plan': '73cdde85b287393799741a12c3649127c70e485dd6e7140f10ec3a4653da9346',
    'M08.exit': 'b3a41ac261d995224fab7d88a33a945ce0282d66ef1f8d827168a2f2c2019d39',
    'M10.evaluation': 'ef5be58fb95cdd7221cdbe0a9696098abbb1f2e5da1c89d87af7bcff5f3a47e1',
    'M10.forward_window': '88b05882c1e78f76a47fc582b55ab5851fb0a1b7f938d9c3c708e6ec0ffa58bc',
    'M10.partition': '9ad6f6cbb9ff2889db8832ce68e081d2482f9d9a872be61d6b0bc2e1b2cd0fd2',
    'M10.aggregation': '9bbdaf7ee1a785e38e854bc1a5acd2283afdb9d584a7622b3f960d00cb90d782',
}


def _plain(value):
    if isinstance(value, Mapping): return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [_plain(item) for item in value]
    return value


def _policy_objects():
    from services.ranking import policies as ranking
    from services.execution import policies as execution
    from services.evaluation import policies as evaluation
    objects = {}
    for prefix, module, names in [('M07', ranking, ('SCORE_POLICY', 'RANKING_POLICY', 'AUTHORITY_POLICY')),
                                  ('M08', execution, ('PLAN_POLICY', 'EXIT_POLICY')),
                                  ('M10', evaluation, ('EVALUATION_POLICY', 'FORWARD_WINDOW_POLICY', 'PARTITION_POLICY', 'AGGREGATION_POLICY'))]:
        for name in names:
            policy = getattr(module, name)
            kind = name.removesuffix('_POLICY').lower()
            module.validate_policy(policy, expected_kind=kind)
            key = prefix + '.' + kind
            if policy['policy_fingerprint'] != 'sha256:' + POLICY_PINS[key]:
                raise ContractError('M12 approved policy content drift')
            objects[key] = _plain(policy)
    return dict(sorted(objects.items()))


# C2a behavior-preserving extraction only; original definition inventory stays intact.
RUNTIME_SOURCE_ALTERNATIVES = {
    'services/gates/baseline.py': ('100644', '1f69d4339b77af789621d4bb90e0586893be7446'),
}


def configuration_source_allowed(path, mode, blob, *, runtime):
    expected = BASELINE_BLOBS.get(path)
    return expected is not None and ((mode, blob) == expected or (
        runtime and (mode, blob) == RUNTIME_SOURCE_ALTERNATIVES.get(path)))


def _configuration_body(evidence):
    _m12_exact(evidence, {'definition_commit', 'code_commit', 'definition_sources', 'runtime_sources'}, 'configuration source evidence')
    if evidence['definition_commit'] != DEFINITION_COMMIT:
        raise ContractError('M12 configuration definition commit differs')
    _m12_commit(evidence['code_commit'])
    sources = []
    overrides = []
    for group in ('definition_sources', 'runtime_sources'):
        _m12_exact(evidence[group], set(BASELINE_BLOBS), group)
        for path, (mode, blob) in BASELINE_BLOBS.items():
            item = evidence[group][path]
            _m12_exact(item, {'mode', 'blob', 'bytes'}, 'configuration source object')
            data = item['bytes']
            if type(data) is not bytes or len(data) > 1024 * 1024:
                raise ContractError('configuration source bytes invalid')
            actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if actual != item['blob'] or not configuration_source_allowed(
                    path, item['mode'], item['blob'], runtime=group == 'runtime_sources'):
                raise ContractError('configuration business source drift or corrupt blob')
            if group == 'definition_sources':
                sources.append({'path': path, 'mode': mode, 'source_blob': blob,
                                'sha256': 'sha256:' + hashlib.sha256(data).hexdigest(), 'size_bytes': len(data)})
            elif item['blob'] != blob:
                overrides.append({'path': path, 'mode': mode, 'definition_blob': blob,
                                  'source_blob': actual, 'sha256': 'sha256:' + hashlib.sha256(data).hexdigest(),
                                  'size_bytes': len(data)})
    # Read values from original module definitions; all persisted objects and
    # imported versions are pinned, never reconstructed scoring/execution rules.
    from services.contracts.policies import ADJUSTMENT_POLICY
    from services.gates.baseline import MIN_HISTORY_SESSIONS, MIN_CLOSE, MIN_DOLLAR_VOLUME
    from services.gates.producer import GATE_POLICY_VERSION
    from services.factors.producer import DETECTOR_POLICY_VERSION
    from services.selectors.producer import MODEL_VERSIONS, SELECTOR_POLICY_VERSION
    from services.context.producer import CONTEXT_POLICY_VERSION, ETF_STATE_POLICY_VERSION
    from services.context.registry import validate_etf_registry
    from services.scanner.factor_registry import REGISTRY_VERSION
    from services.scanner.audit_eodhd import PRIMARY
    from services.playbook.contracts import SCHEMA_VERSION
    versions = {'M03': GATE_POLICY_VERSION, 'M04': DETECTOR_POLICY_VERSION, 'M05': SELECTOR_POLICY_VERSION,
                'M05_models': dict(MODEL_VERSIONS), 'M06': CONTEXT_POLICY_VERSION, 'M06_etf': ETF_STATE_POLICY_VERSION,
                'M11_schema': SCHEMA_VERSION, 'factor_registry': REGISTRY_VERSION}
    expected = {'M03': 'm03-shadow-1.0.0', 'M04': 'm04-factor-evidence-1.0.0', 'M05': 'm05-selector-assessment-1.0.0',
                'M05_models': {'complex_multifactor': '1.0.0', 'favorite_pattern': '3.0.0'},
                'M06': 'm06-market-industry-context-1.0.0', 'M06_etf': 'm06-etf-state-1.0.0',
                'M11_schema': '2.2.0', 'factor_registry': '0.10.0'}
    if _canonical(versions) != _canonical(expected) or (MIN_HISTORY_SESSIONS, MIN_CLOSE, MIN_DOLLAR_VOLUME) != (420, 5.0, 10000000.0):
        raise ContractError('configuration approved versions or qualification thresholds drift')
    if ADJUSTMENT_POLICY != {'version': 'eodhd-adjusted-ratio-1.0.0', 'formula': 'ratio=adjusted_close/close; adjusted_ohlc=raw_ohlc*ratio'}:
        raise ContractError('configuration adjustment policy drift')
    if sorted(PRIMARY) != ['AMEX', 'NASDAQ', 'NYSE', 'NYSE ARCA', 'NYSE MKT']:
        raise ContractError('configuration membership range drift')
    registry = _m12_json(evidence['definition_sources']['public/factor-registry.json']['bytes'])
    etfs = _m12_json(evidence['definition_sources']['data/context/etf-registry-v1.json']['bytes'])
    validate_etf_registry(etfs)
    if sorted(item['symbol'] for item in etfs['etfs']) != ['BOTZ', 'IWM', 'QQQ', 'SOXX', 'SPY', 'XLE']:
        raise ContractError('configuration ETF set drift')
    return {
        'protocol': 'm12-research-configuration/1', 'definition_commit': DEFINITION_COMMIT,
        'code_commit': evidence['code_commit'], 'publication_mode': 'research_only', 'scope': 'complex_multifactor_main',
        'versions': versions, 'policies': _policy_objects(), 'definition_sources': sources,
        **({'runtime_source_overrides': overrides} if overrides else {}),
        'membership': {'provider': 'EODHD', 'market': 'US', 'request_url': 'https://eodhd.com/api/exchange-symbol-list/US?delisted=0&fmt=json',
                       'instrument_type': 'Common Stock', 'exchanges': sorted(PRIMARY), 'observation_timezone': 'America/New_York',
                       'identity': 'observed_instrument_id', 'historical_membership_backfill': False},
        'qualification': {'version': 'm12-eodhd-primary-common-1.0.0', 'min_history_sessions': MIN_HISTORY_SESSIONS,
                          'min_close': MIN_CLOSE, 'min_dollar_volume': MIN_DOLLAR_VOLUME, 'unknown_member': 'fail_whole_formal_day'},
        'adjustment_policy': dict(ADJUSTMENT_POLICY), 'factor_registry': registry, 'etf_registry': etfs,
        'boundaries': {'active_strategies': [], 'context_ranking_effect': 'none', 'formal_net_return': 'unavailable_without_approved_cost',
                       'portfolio': 'unavailable', 'favorite_non_gate': 'observation_only_no_formal_trade_outcomes',
                       'equity_etf_membership': 'unavailable_without_dated_identity_evidence'},
    }
