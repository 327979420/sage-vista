"""Frozen candidate settings for CR-056; not a production activation."""
from types import MappingProxyType
from services.contracts.market_data import canonical_fingerprint

WHITE_LIST = MappingProxyType({
    'daily': ('support.ema_proximity', 'support.fibonacci_618',
              'structure.trendline_three_push', 'structure.trendline_three_push_retest',
              'structure.bullish_fvg_support', 'structure.bottom_bullish_engulfing',
              'structure.support_bullish_engulfing', 'volume.bottom_expansion'),
    'weekly_completed': ('macd.weekly_histogram_improving', 'support.weekly_ema_proximity'),
    'monthly_completed': ('direction.macd_state.monthly', 'support.monthly_ema_proximity',
                          'structure.monthly_bullish_engulfing', 'structure.monthly_double_bullish_engulfing'),
})
SETTINGS = MappingProxyType({
    'minimum_daily_rows': 420, 'minimum_completed_months': 61,
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
CAPS = MappingProxyType({'daily': 5.0, 'weekly_completed': 2.0, 'monthly_completed': 3.25})
POLICY_VERSION = 'cr056-policy-1.1.0-candidate'
POLICY_FINGERPRINT = canonical_fingerprint({'version': POLICY_VERSION, 'settings': dict(SETTINGS),
    'white_list': {k: list(v) for k, v in WHITE_LIST.items()}, 'weights': dict(WEIGHTS), 'caps': dict(CAPS)})
