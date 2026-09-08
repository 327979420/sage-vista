"""QuantStats presentation of a caller's daily account, never trade returns.

The caller must supply VectorBT's end-of-session account values and returns.
Reconciliation includes the first session against initial cash. No strategy,
cash allocation, price downloads, benchmark fetching, or signal logic lives here.
"""
import html
import math
import re
from pathlib import Path


def checked_daily_returns(equity, returns, initial_cash):
    import pandas as pd
    if not isinstance(equity, pd.Series) or not isinstance(returns, pd.Series):
        raise ValueError('daily_series_required')
    if not isinstance(equity.index, pd.DatetimeIndex) or not equity.index.equals(returns.index):
        raise ValueError('matching_session_dates_required')
    if len(equity) < 2 or not equity.index.is_unique or not equity.index.is_monotonic_increasing:
        raise ValueError('ordered_unique_daily_account_required')
    if not equity.index.equals(equity.index.normalize()):
        raise ValueError('intraday_slots_are_not_daily_account_returns')
    if not math.isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError('positive_initial_cash_required')
    previous = initial_cash
    for value, change in zip(equity, returns):
        if not math.isfinite(value) or value <= 0 or not math.isfinite(change):
            raise ValueError('account_values_missing_or_invalid')
        if not math.isclose(change, value / previous - 1, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError('daily_return_does_not_reconcile_to_account')
        previous = value
    return returns.copy()


def render_daily_report(equity, returns, initial_cash, out, *, title, synthetic=False):
    import quantstats as qs
    if qs.__version__ != '0.0.81':
        raise ValueError('unapproved_quantstats_version')
    daily = checked_daily_returns(equity, returns, initial_cash)
    path = Path(out)
    root = Path(__file__).resolve().parents[2]
    if root / 'public' in path.resolve().parents:
        raise ValueError('report_adapter_cannot_write_public_assets')
    if synthetic and root / 'research/backtest/output' in path.resolve().parents:
        raise ValueError('synthetic_test_cannot_publish_research_results')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Passing a numeric Series and no benchmark prevents the library's ticker
    # convenience path from fetching prices. Never call extend_pandas/download.
    qs.reports.html(daily, benchmark=None, rf=0, compounded=True,
                    periods_per_year=252, match_dates=False,
                    title=html.escape(title), output=str(path), figfmt='svg')
    marker = 'SYNTHETIC ADAPTER TEST — NOT STRATEGY PERFORMANCE' if synthetic else 'LEGACY RESEARCH SCENARIO — NOT FORMAL POLICY'
    note = ('<aside style="padding:16px;border:2px solid #a66"><b>' + marker + '</b>'
            '<p>Account daily returns, including cash and costs from the same run. '
            'Win-rate and profit-factor metrics below are DAILY statistics, not per-trade statistics. '
            'Annualization assumes 252 trading sessions and zero risk-free rate; no benchmark downloaded.</p></aside>')
    raw = path.read_text()
    if not re.search(r'<body\b[^>]*>', raw):
        raise ValueError('quantstats_report_body_missing')
    path.write_text(re.sub(r'<body\b[^>]*>', lambda _: '<body>' + note, raw, count=1))
    return {'total_return': float(qs.stats.comp(daily)),
            'max_drawdown': float(qs.stats.max_drawdown(daily)),
            'daily_sessions': len(daily), 'initial_cash': initial_cash,
            'ending_equity': float(equity.iloc[-1]),
            'quantstats_version': qs.__version__}
