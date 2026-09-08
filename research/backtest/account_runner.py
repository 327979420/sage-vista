"""Parameterized legacy scenario: sole old exits -> VectorBT daily account.

Real runs require the explicitly approved Git scenario. Synthetic tests call
the pure account function without authorizing a production policy.
"""
from datetime import date
from functools import lru_cache
import json
import math
from pathlib import Path
from research.backtest.run_store import ROOT, POLICY, CANDIDATE_POLICY, trade_csv, encode, seal, sha256, validate_request

CONFIG = ROOT / 'research/backtest/account-scenario.json'
RANKINGS = ROOT / 'public/unified-v2-rankings.json'


def validate_scan_coverage(rankings, events, sessions):
    """Prove each requested session was scanned under this legacy policy.

    Version 1.1 lacks the execution-policy contract. Later saved 1.2/1.3/1.4
    records share it; this does not equate their signal-selection algorithms.
    """
    if rankings.get('future_data_used') is not False:
        raise ValueError('scan_future_data_safety_unproven')
    records = rankings.get('days', [])
    days = {d['date']: d for d in records}
    if len(days) != len(records):
        raise ValueError('duplicate_scan_date')
    supported = {'unified-v2-macd-trigger-1.2.0', 'unified-v2-macd-trigger-1.3.0', 'unified-v2-macd-trigger-1.4.0', 'cr056-policy-2.0.0-candidate'}
    for session in sessions:
        day = days.get(session)
        if day is None:
            raise ValueError('historical_scan_day_missing:' + session)
        if day.get('model_version') not in supported:
            raise ValueError('historical_scan_policy_unsupported:' + session)
        ranking = day.get('ranking')
        if (not isinstance(ranking, list) or type(day.get('candidate_count')) is not int
                or day['candidate_count'] < len(ranking)
                or (not ranking and day['candidate_count'] != 0)):
            raise ValueError('historical_scan_completeness_unproven:' + session)
        if any(r.get('execution_policy_version') != POLICY for r in ranking):
            raise ValueError('historical_scan_policy_unsupported:' + session)
        expected = {(r['symbol'], r['rank']) for r in ranking}
        actual_events = [e for e in events if e['signal_date'] == session]
        actual = {(e['symbol'], e['selection']['rank']) for e in actual_events}
        if (len(expected) != len(ranking) or len(actual) != len(actual_events) or actual != expected
                or any(e['selection'].get('model_version') != day['model_version']
                       or e['selection'].get('execution_policy_version') != POLICY for e in actual_events)):
            raise ValueError('ledger_does_not_match_historical_scan:' + session)
    return [days[d] for d in sessions]


def scenario_values(config):
    required = {'initial_cash', 'allocation_fraction', 'max_positions', 'cost_rate', 'fractional_shares'}
    if not isinstance(config, dict) or not required <= config.keys():
        raise ValueError('explicit_account_parameters_required')
    for key in ('initial_cash', 'allocation_fraction', 'cost_rate'):
        if type(config[key]) not in (int, float) or not math.isfinite(config[key]):
            raise ValueError('invalid_account_parameter')
    if config['initial_cash'] <= 0 or not 0 < config['allocation_fraction'] <= 1 or not 0 <= config['cost_rate'] < 1:
        raise ValueError('invalid_account_parameter')
    if type(config['max_positions']) is not int or config['max_positions'] < 1 or type(config['fractional_shares']) is not bool:
        raise ValueError('invalid_position_parameter')
    return {key: config[key] for key in sorted(required)}


def approved_scenario(path=CONFIG):
    if not Path(path).exists():
        raise ValueError('account_parameters_not_approved')
    config = json.loads(Path(path).read_bytes())
    if config.get('approved') is not True or not isinstance(config.get('approval_ref'), str) or not config['approval_ref'].strip():
        raise ValueError('account_parameters_not_approved')
    scenario_values(config)
    return config


@lru_cache(maxsize=1)
def order_callback():
    import numpy as np
    from numba import njit
    from vectorbt.portfolio import nb
    from vectorbt.portfolio.enums import Direction, NoOrder
    @njit
    def orders(c, enter, leave, entry_price, exit_price, symbol_ids, reasons, nominal, fee, max_positions, fractional):
        col = c.col
        if c.i == enter[col]:
            held = 0
            for other in range(len(enter)):
                if c.last_position[other] > 0:
                    held += 1
                    if symbol_ids[other] == symbol_ids[col]:
                        reasons[col] = 1
                        return NoOrder
            if held >= max_positions:
                reasons[col] = 2
                return NoOrder
            qty = nominal/entry_price[col]
            if not fractional:
                qty = np.floor(qty)
            if qty <= 0 or qty*entry_price[col]*(1+fee) > c.cash_now + 1e-9:
                reasons[col] = 3
                return NoOrder
            return nb.order_nb(size=qty, price=entry_price[col], fees=fee, direction=Direction.LongOnly, allow_partial=False, raise_reject=True)
        if c.i == leave[col] and c.position_now > 0:
            return nb.order_nb(size=-c.position_now, price=exit_price[col], fees=fee, direction=Direction.LongOnly, allow_partial=False, raise_reject=True)
        return NoOrder

    return orders


def account(events, rows_by_symbol, sessions, config):
    """Pure deterministic scenario over normalized bars; no files or downloads."""
    import numpy as np
    import pandas as pd
    import vectorbt as vbt
    from services.scanner.support_risk import simulate_execution
    if vbt.__version__ != '1.1.0':
        raise ValueError('unapproved_vectorbt_version')
    params = scenario_values(config)
    if len(sessions) < 2 or sessions != sorted(set(sessions)):
        raise ValueError('complete_reference_sessions_required')
    if any(date.fromisoformat(d).isoformat() != d for d in sessions):
        raise ValueError('canonical_sessions_required')
    events = sorted(events, key=lambda e: (e['signal_date'], e['selection']['rank'], e['event_id']))
    if len({e['event_id'] for e in events}) != len(events):
        raise ValueError('unique_signal_set_required')
    trades, pending = [], []
    for event in events:
        if event['selection'].get('execution_policy_version') != POLICY:
            raise ValueError('mixed_execution_policy')
        if event['signal_date'] not in sessions:
            raise ValueError('signal_session_missing')
        future = sessions[sessions.index(event['signal_date'])+1:]
        if not future:
            pending.append({'event_id':event['event_id'], 'symbol':event['symbol'], 'signal_date':event['signal_date'], 'status':'pending_next_session'})
            continue
        rows = rows_by_symbol[event['symbol']]
        by_date = {r['date']:r for r in rows}
        if len(by_date) != len(rows):
            raise ValueError('duplicate_asset_session:' + event['symbol'])
        path = []
        for d in future:
            if d not in by_date:
                break
            path.append(by_date[d])
        if not path:
            raise ValueError('entry_session_missing:' + event['symbol'])
        execution = simulate_execution(path[0]['open'], event['selection']['support_plan'], path)
        if len(path) < len(future) and execution.get('status') not in ('resolved','skipped'):
            raise ValueError('held_asset_session_missing:' + event['symbol'])
        trades.append({'event_id':event['event_id'], 'symbol':event['symbol'], 'signal_date':event['signal_date'],
                       'rank':event['selection']['rank'], 'entry_date':future[0], 'entry_price':path[0]['open'], 'execution':execution})
    # One column per original signal. Multiple signals for the same symbol are
    # denied by the allocator while a prior column still holds that symbol.
    # VectorBT needs a column for the account even without any asset orders.
    # Keep one inert all-NaN book slot: no asset price, signal, or trade is invented.
    n = max(1, len(trades))
    close = np.full((len(sessions)*3, n), np.nan)
    enter = np.full(n, -1, dtype=np.int64); leave = enter.copy()
    entry_price = np.zeros(n); exit_price = np.zeros(n)
    symbols = sorted({t['symbol'] for t in trades})
    symbol_ids = np.array([symbols.index(t['symbol']) for t in trades] or [-1], dtype=np.int64)
    for col,t in enumerate(trades):
        rows = {r['date']:r for r in rows_by_symbol[t['symbol']]}
        for i,d in enumerate(sessions):
            # Missing prices before this signal has any position are inert NaN,
            # never fabricated market prices or a held-asset forward fill.
            close[i*3: i*3+3,col] = [rows[d]['open'], rows[d]['close'], rows[d]['close']] if d in rows else np.nan
        ex = t['execution']
        if ex.get('executable'):
            enter[col] = sessions.index(t['entry_date'])*3
            entry_price[col] = t['entry_price']
            if ex['status'] == 'resolved':
                leave[col] = sessions.index(ex['exit_date'])*3+1
                exit_price[col] = ex['exit_price']
    reasons = np.zeros(n,dtype=np.int64)
    nominal = params['initial_cash']*params['allocation_fraction']
    fee = params['cost_rate']; max_positions = params['max_positions']; fractional = params['fractional_shares']

    pf = vbt.Portfolio.from_order_func(pd.DataFrame(close), order_callback(), enter, leave, entry_price, exit_price, symbol_ids, reasons, nominal, fee, max_positions, fractional, init_cash=params['initial_cash'],
                                     cash_sharing=True, group_by=True, ffill_val_price=False)
    # Only the final phase is a daily account observation. Intraday phases must
    # never be fed into QuantStats as daily returns.
    values = pf.value().iloc[2::3].to_numpy()
    equity = pd.Series(values,index=pd.to_datetime(sessions),name='Account')
    daily = equity.pct_change(fill_method=None)
    daily.iloc[0] = equity.iloc[0]/params['initial_cash']-1
    records = {int(r['col']):r for r in pf.trades.records.to_dict('records')}
    labels = {1:'same_stock_held',2:'position_limit',3:'cash_or_whole_share_insufficient'}
    for col,t in enumerate(trades):
        r = records.get(col)
        if r is None:
            t.update(status='skipped', reason=labels.get(int(reasons[col]),'original_plan_not_executable'))
        else:
            t.update(status='closed' if int(r['status']) == 1 else 'open', quantity=float(r['size']),
                     net_pnl=float(r['pnl']), net_return=float(r['return']),
                     entry_fees=float(r['entry_fees']), exit_fees=float(r['exit_fees']))
    return equity, daily, trades+pending


def attach_signal_audit(trades, events):
    """Copy selection-time facts only; never read later evaluation or scores."""
    by_id = {e['event_id']: e for e in events}
    if len(by_id) != len(events):
        raise ValueError('duplicate_signal_audit_identity')
    for trade in trades:
        event = by_id.get(trade['event_id'])
        if (event is None or event['symbol'] != trade['symbol']
                or event['signal_date'] != trade['signal_date']
                or ('rank' in trade and event['selection']['rank'] != trade['rank'])):
            raise ValueError('trade_signal_audit_identity_mismatch')
        snapshot = {'as_of': event['signal_date'], 'basis': 'signal_close_before_next_open',
                    'selection': json.loads(encode(event['selection']))}
        trade['signal_snapshot'] = snapshot
        trade['signal_snapshot_sha256'] = sha256(encode(snapshot))
        trade['exit_score'] = {'status': 'unavailable', 'reason': 'not_recorded_at_exit'}
    return trades


def execute(request, config, cache_dir, ledger_path, *, out, run_id, attempt, code_commit, cache_key, synthetic=False, rankings_path=RANKINGS):
    from services.scanner.cr056_inputs import normalized_comparison_rows
    from research.backtest.quantstats_report import render_daily_report
    validate_request(request)
    if not synthetic and (config.get('approved') is not True or not config.get('approval_ref')):
        raise ValueError('account_parameters_not_approved')
    raw = Path(ledger_path).read_bytes(); ledger = json.loads(raw)
    if request['start'] < ledger['coverage']['first'] or request['end'] > ledger['coverage']['last']:
        raise ValueError('requested_signal_history_not_covered')
    cache = Path(cache_dir)
    calendar = json.loads((cache/'SPY.json').read_bytes())
    if not calendar or calendar[0]['date'] > request['start'] or calendar[-1]['date'] < request['end']:
        raise ValueError('requested_reference_calendar_not_covered')
    reference = normalized_comparison_rows([r for r in calendar if request['start'] <= r['date'] <= request['end']],as_of=request['end'])
    sessions = [r['date'] for r in reference]
    window_events = [e for e in ledger['events'] if request['start'] <= e['signal_date'] <= request['end']]
    scan_bytes = Path(rankings_path).read_bytes()
    scan_doc=json.loads(scan_bytes)
    scan_days = validate_scan_coverage(scan_doc, window_events, sessions)
    new_model='cr056-policy-2.0.0-candidate'
    if any((d['model_version']==new_model)!=(request['strategy']==CANDIDATE_POLICY) for d in scan_days):
        raise ValueError('research_request_selection_model_mismatch')
    events = [e for e in window_events if e['selection'].get('execution_policy_version') == POLICY]
    rows, sources = {}, {}
    for symbol in sorted({e['symbol'] for e in events}):
        if not symbol.replace('-','').replace('.','').isalnum():
            raise ValueError('invalid_symbol')
        window = [r for r in json.loads((cache/(symbol+'.json')).read_bytes()) if request['start'] <= r['date'] <= request['end']]
        rows[symbol] = normalized_comparison_rows(window,as_of=request['end'])
        if any(r['date'] not in sessions for r in rows[symbol]):
            raise ValueError('asset_date_missing_from_reference_calendar')
        sources[symbol] = sha256(encode(window))
    equity,daily,trades = account(events,rows,sessions,config)
    attach_signal_audit(trades, events)
    versions = sorted({e["selection"]["model_version"] for e in events})
    implementation = {name: sha256((ROOT/name).read_bytes()) for name in ("research/backtest/account_runner.py", "services/scanner/support_risk.py", "research/backtest/quantstats_report.py", "research/backtest/dependencies/vectorbt-requirements.lock", "research/backtest/dependencies/quantstats-requirements.lock")}
    experiment = {"request":request,"account_parameters":scenario_values(config),"selection_versions":versions,"implementation":implementation,"scan_days_sha256":sha256(encode(scan_days)),"signal_snapshots_sha256":sha256(encode([t["signal_snapshot"] for t in trades])),"price_windows_sha256":sources,"reference_sha256":sha256(encode(reference))}
    audit = {"version":"trade-signal-audit-v1", "account_algorithm":"legacy-shared-cash-v1", "selection_versions":versions, "execution_policy":POLICY, "experiment_key":sha256(encode(experiment)), "experiment_identity":experiment}
    output = Path(out); output.mkdir(parents=True,exist_ok=True)
    report_path = output/'report.html'
    summary = render_daily_report(equity,daily,config['initial_cash'],report_path,title='CR056 new nominations / legacy exits' if request['strategy']==CANDIDATE_POLICY else 'Legacy account research',synthetic=synthetic)
    closed = [t for t in trades if t['status'] == 'closed']
    summary['win_rate'] = sum(t['net_pnl']>0 for t in closed)/len(closed) if closed else None
    win_text = f"{summary['win_rate']:.1%}" if summary['win_rate'] is not None else '不可用（无已平仓交易）'
    intro = (f"<section><h2>账户净收益 {summary['total_return']:.2%} · 最大回撤 {summary['max_drawdown']:.2%}</h2>"
             f"<p>{request['start']} 至 {request['end']} · 实际入场 {sum(t['status'] in ('open','closed') for t in trades)} 笔 · 已平仓胜率 {win_text} · 期末未平仓 {sum(t['status']=='open' for t in trades)} 笔</p>"
             f"<p>研究资金 {config['initial_cash']:,.2f}；每笔初始资金的 {config['allocation_fraction']:.1%}；最多 {config['max_positions']} 只；单边综合成本 {config['cost_rate']:.2%}；碎股 {'允许' if config['fractional_shares'] else '不允许'}。</p>"
             f"<p>仅旧支撑5%／入场10%上限止损、2R目标、最长40交易日。窗口原信号 {len(window_events)} 条，其中旧政策 {len(events)} 条；其余政策不混入本回测。每窗口从初始现金开始，不带入起始日前持仓。</p>"
             "<p>保守记账约定：原排名新入场先于当日退出，不用当日卖出款资助新买入；不代表真实盘中现金顺序。只做多，无杠杆，无部分成交；未平仓收益按窗口末有效收盘估值。</p></section>")
    if request['strategy']==CANDIDATE_POLICY:
        intro=intro.replace('窗口原信号', '新版首次合格金叉信号').replace('其余政策不混入本回测。','选股CR0562.0，年度/窗口开始观察池为空；不是完整历史市场，使用现有缓存观测股票，存在幸存者偏差。')
    report_path.write_text(report_path.read_text().replace('<body>','<body>'+intro,1))
    receipt = seal({'schema_version':'legacy-research-run-v1','id':f'{run_id}-{attempt}','result_role':'legacy/research',
                    'status':'completed','request':request,'summary':summary,'code_commit':code_commit,
                    'scenario':config,'selection':{'window_events':len(window_events),'eligible_policy_events':len(events),'excluded_other_policy':len(window_events)-len(events),'entered_trades':sum(t['status'] in ('open','closed') for t in trades)},'source':{'ledger_sha256':sha256(raw),'cache_key':cache_key,'windows_sha256':sources,'reference_sessions_sha256':sha256(encode(sessions)),'scan_file_sha256':sha256(scan_bytes),'scan_days_sha256':sha256(encode(scan_days)),'historical_raw_revision_proven':False},
                    'daily_account':[{'date':d,'equity':float(v),'return':float(r)} for d,v,r in zip(sessions,equity,daily)],
                    'trades':trades,'synthetic':synthetic,'audit':audit,
                    'report':{'path':f'{run_id}-{attempt}/report.html','sha256':sha256(report_path.read_bytes())}})
    csv_bytes=trade_csv(receipt)
    receipt=seal({**receipt,'research_input':{'role':scan_doc.get('history_role','legacy_saved_signals'),'excluded_source_count':len(scan_doc.get('excluded_sources',{})),'incomplete_source_days':sum(bool(d.get('missing_session_symbols') or d.get('unavailable')) for d in scan_days),'coverage_note':'observed cached universe; not complete historical market; latest adjusted history revision'},'downloads':{'trades_csv':{'path':f'{run_id}-{attempt}/trades.csv','sha256':sha256(csv_bytes)}}})
    (output/'trades.csv').write_bytes(csv_bytes)
    (output/'receipt.json').write_bytes(encode(receipt))
    return receipt
