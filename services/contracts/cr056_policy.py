"""Frozen candidate settings for CR-056; not a production activation."""
from types import MappingProxyType
from services.contracts.market_data import canonical_fingerprint

# One template per algorithm; higher-period aliases retain source provenance.
from dataclasses import asdict
from services.scanner.factor_registry import FACTORS, FACTORS_BY_ID

FRAMES = ('monthly_completed', 'weekly_completed', 'daily')
ALIASES = {
    'support.weekly_ema_proximity': 'support.ema_proximity',
    'support.monthly_ema_proximity': 'support.ema_proximity',
    'macd.weekly_histogram_improving': 'direction.macd_state',
    'macd.monthly_bull_cross': 'direction.macd_state',
    'structure.weekly_bullish_engulfing': 'structure.period_bullish_engulfing',
    'structure.monthly_bullish_engulfing': 'structure.period_bullish_engulfing',
    'structure.weekly_double_bullish_engulfing': 'structure.period_double_bullish_engulfing',
    'structure.monthly_double_bullish_engulfing': 'structure.period_double_bullish_engulfing',
}
TEMPLATES = {f.id: f for f in FACTORS if f.timeframe == 'daily'}
TEMPLATES.update({
    'structure.period_bullish_engulfing': FACTORS_BY_ID['structure.monthly_bullish_engulfing'],
    'structure.period_double_bullish_engulfing': FACTORS_BY_ID['structure.monthly_double_bullish_engulfing'],
    'direction.macd_state': FACTORS_BY_ID['macd.weekly_histogram_improving'],
})

def mapped_id(timeframe, template):
    return timeframe + '::' + template

MAPPED_FACTORS = {}
for timeframe in FRAMES:
    for template, factor in TEMPLATES.items():
        source_ids = [f.id for f in FACTORS if ALIASES.get(f.id, f.id) == template]
        role = ('unimplemented' if factor.runtime_status == 'definition_required' else
                'qualification' if factor.factor_type == 'qualification' else
                'ticket' if template == 'macd.daily_bull_cross' else
                'risk' if factor.evidence_family == 'risk' else 'score')
        parents = tuple(mapped_id(timeframe, ALIASES.get(parent, parent)) for parent in factor.depends_on)
        if template == 'structure.period_double_bullish_engulfing':
            parents = (mapped_id(timeframe, 'structure.period_bullish_engulfing'),)
        group = 'macd_direction' if template == 'direction.macd_state' else factor.redundancy_group
        if template.startswith('structure.period_'): group = 'engulfing_reversal'
        MAPPED_FACTORS[mapped_id(timeframe, template)] = {
            'template': template, 'source_ids': source_ids, 'timeframe': timeframe,
            'name': factor.name_zh.replace('完整月线', '').replace('完整周线', '').replace('日线', '').replace('周线', ''),
            'family': factor.evidence_family, 'group': timeframe + '::' + group,
            'parents': parents, 'window': factor.observation_window_sessions,
            'role': role, 'research_status': factor.status, 'source_definition': asdict(factor),
        }
        if template == 'direction.macd_state':
            MAPPED_FACTORS[mapped_id(timeframe, template)].update(name='MACD方向质量', window=0)
# One zone detector backs all bottom evidence; aliases share one capped group.
for timeframe in FRAMES:
    for template in ('structure.double_bottom','structure.triple_bottom_pullback','structure.higher_low'):
        item=MAPPED_FACTORS[mapped_id(timeframe,template)]
        item.update(group=timeframe+'::bottom_structure',family='price_structure',parents=(),window=0,graded=True,
                    name={'structure.double_bottom':'支撑区多底','structure.triple_bottom_pullback':'三底及以上支撑区','structure.higher_low':'支撑区末底抬高'}[template])
        item['source_definition']=dict(item['source_definition'],version='candidate-3.5.0',factor_type='state',
            machine_rule='Current trendline-bounded continuous support zone; independent rallies separate older support; reject deep sweeps')
for timeframe in FRAMES:
    item=dict(MAPPED_FACTORS[mapped_id(timeframe,'support.ema_proximity')])
    item.update(template='support.historical_bottom_zone',source_ids=[],name='历史底部支撑参考',
        group=timeframe+'::historical_bottom_support',parents=(),window=0,graded=True,research_status='testing')
    item['source_definition']=dict(item['source_definition'],id='support.historical_bottom_zone',version='candidate-3.5.0',factor_type='state',
        machine_rule='Prior episode lows tested by current candle within 2 percent, close held; 0.25 credit, never entry anchors')
    MAPPED_FACTORS[mapped_id(timeframe,'support.historical_bottom_zone')]=item
for timeframe in FRAMES:
    item=MAPPED_FACTORS[mapped_id(timeframe,'support.ema_proximity')]
    item['name']='EMA20/50/100/200支撑'
    item['source_definition']=dict(item['source_definition'],version='candidate-3.3.0',
        machine_rule='Native EMA20/50/100/200, each requires matching history, 2 percent current proximity; historical tests are evidence only')
    if timeframe!='daily':
        for template in ('structure.trendline_three_push',):
            item=MAPPED_FACTORS[mapped_id(timeframe,template)]
            item['source_definition']=dict(item['source_definition'],version='candidate-3.3.0',factor_type='state',
                machine_rule='Confirmed native-period structural state retained until frozen support invalidation within 120-bar discovery window')
MAPPED_FACTORS = MappingProxyType(MAPPED_FACTORS)
WHITE_LIST = MappingProxyType({tf: tuple(fid for fid, m in MAPPED_FACTORS.items()
                                       if m['timeframe'] == tf and m['role'] == 'score') for tf in FRAMES})
SETTINGS = MappingProxyType({
    'pullback_bear_body_atr': 1.0, 'pullback_bear_wick_fraction': 0.10,
    'minimum_daily_rows': 420, 'minimum_completed_months': 61,
    'period_double_engulfing_window': 12,
    'monthly_negative_improvements': 1, 'weekly_negative_improvements': 2,
    'monthly_percentile_history': 60, 'high_percentile': 0.90,
    'near_history_high_fraction': 0.95, 'monthly_ema_extension': 0.20,
    'weekly_positive_peak_window': 13, 'weekly_near_cross_fraction': 0.10,
    'weekly_shrinking_multiplier': 0.75, 'pullback_window': 60, 'pullback_fraction': 0.95,
    'base_months': 12, 'prior_base_months': 24, 'base_prior_drawdown': 0.30,
    'base_max_width': 0.50, 'base_touch_tolerance': 0.05, 'base_touch_gap': 3,
    'base_min_low_ratio': 0.98, 'family_cap': 2.0, 'story_cap': 1.5,
    'child_confirmation': 0.25, 'confirmation_cap': 0.5, 'recent_strength': 0.5,
    'minimum_score_coverage': 0.8, 'high_score': 60.0, 'alert_family_minimum': 2,
    'alert_cooldown_sessions': 5,
})
WEIGHTS = MappingProxyType({'daily': 1, 'weekly_completed': 2, 'monthly_completed': 3})
def _frame_cap(tf):
    families = {}
    ids = WHITE_LIST[tf]
    for group in {MAPPED_FACTORS[fid]['group'] for fid in ids}:
        members = [MAPPED_FACTORS[fid] for fid in ids if MAPPED_FACTORS[fid]['group'] == group]
        confirmation = min(SETTINGS['confirmation_cap'], sum(SETTINGS['child_confirmation'] for m in members if m['parents']))
        value = min(SETTINGS['story_cap'], 1 + confirmation)
        family = members[0]['family']
        families[family] = min(SETTINGS['family_cap'], families.get(family, 0) + value)
    return sum(families.values())
CAPS = MappingProxyType({tf: _frame_cap(tf) for tf in FRAMES})
# Include shared geometry settings so a detector parameter change invalidates caches.
from services.scanner.detectors import load_config
ENTRY_SETTINGS = load_config()
# Parameter AND implementation identity: even a same-version bug fix must
# invalidate daily snapshots rather than silently reuse yesterday's rules.
from hashlib import sha256
from pathlib import Path
_RULE_ROOT = Path(__file__).resolve().parents[2]
RULE_IMPLEMENTATION = {name: sha256((_RULE_ROOT/name).read_bytes()).hexdigest() for name in (
    'services/factors/cr056.py', 'services/selectors/cr056.py', 'services/ranking/cr056.py',
    'services/scanner/factor_detectors.py', 'services/scanner/detectors.py',
    'services/scanner/technical.py', 'services/scanner/macd_factor_backtest.py',
    'services/gates/baseline.py', 'services/gates/local_structure.py',
    'services/gates/long_term_state.py', 'services/ledger/cr056.py')}
POLICY_VERSION = 'cr056-policy-3.5.0-candidate'
POLICY_FINGERPRINT = canonical_fingerprint({'version': POLICY_VERSION, 'entry_settings': ENTRY_SETTINGS, 'implementation': RULE_IMPLEMENTATION, 'settings': dict(SETTINGS),
    'white_list': {k: list(v) for k, v in WHITE_LIST.items()}, 'weights': dict(WEIGHTS), 'caps': dict(CAPS), 'mapped_factors': dict(MAPPED_FACTORS)})
