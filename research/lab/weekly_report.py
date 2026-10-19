"""Offline, read-only Chinese paper-account report.

CLI: --cockpit export.json --date YYYY-MM-DD [--history daily_exports/]
History files use the cockpit shape plus as_of (valuation session). Saturday
snapshots alone are not daily history. No interpolation or backfilled trades.
"""
import argparse
import calendar
from collections import Counter, defaultdict
import datetime as dt
from html import escape
import json
import math
from pathlib import Path

from research.lab import app_data, calendars


def rows(value):
    return list(value.values()) if isinstance(value, dict) else value


def number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('non-finite account number')
    return value


def valuation(export, day):
    account = export['accounts']['paper']
    cash, start = number(account['cash']), number(account['start_cash'])
    sleeves = defaultdict(lambda: dict(value=0., realized=0., unrealized=0.))
    issues = []
    for p in rows(export.get('positions', [])):
        if p['account'] != 'paper':
            continue
        if p['opened'][:10] > day:
            issues.append(f"{p['symbol']} 开仓日期晚于估值日")
            continue
        sleeve = sleeves[p['source']]
        qty, entry = number(p['qty']), number(p['entry'])
        if p['status'] == 'closed':
            if not p.get('closed') or p['closed'][:10] > day or p.get('exit') is None:
                issues.append(f"{p['symbol']} 平仓记录不完整或晚于估值日")
                continue
            sleeve['realized'] += qty * (number(p['exit']) - entry)
        elif p['status'] == 'open':
            q = export.get('prices', {}).get(p['symbol'])
            if not q or q.get('date') != day:
                issues.append(f"{p['symbol']} 缺少 {day} 收盘价")
                continue
            value = qty * number(q['close'])
            sleeve['value'] += value
            sleeve['unrealized'] += value - qty * entry
        else:
            issues.append(f"{p['symbol']} 未识别状态 {p['status']}")
    equity = cash + sum(s['value'] for s in sleeves.values()) if not issues else None
    return dict(cash=cash, start=start, equity=equity, sleeves=dict(sleeves), issues=issues)


def history_metrics(exports, sector_prices, end):
    import pandas as pd
    import quantstats as qs

    dated = {}
    for export in exports:
        day = export['as_of']
        if day > end:
            continue
        if day in dated:
            raise ValueError(f'duplicate history session: {day}')
        if not calendars.is_session('XNYS', day):
            raise ValueError(f'history date is not a session: {day}')
        dated[day] = valuation(export, day)
    days = sorted(dated)
    # Twenty returns need twenty-one closing valuations, not twenty snapshots.
    if len(days) < 21:
        return None, f'每日净值历史不足 20 个交易日收益（现有 {len(days)} 个收盘快照）；暂不生成 QuantStats。'
    if days[-1] != end or any(calendars.next_session('XNYS', a) != b for a, b in zip(days, days[1:])):
        return None, '每日净值历史不连续或未到报告估值日；不补齐、不计算 QuantStats。'
    if any(v['equity'] is None or v['equity'] <= 0 for v in dated.values()):
        return None, '历史净值存在缺价或非正值；不计算 QuantStats。'
    # A full position ledger must reconcile to cash; unexplained deposits/fees
    # cannot be treated as investment returns.
    for v in dated.values():
        pnl = sum(s['realized'] + s['unrealized'] for s in v['sleeves'].values())
        if abs(v['equity'] - v['start'] - pnl) > .01:
            return None, '历史现金与持仓损益不一致（可能有费用或资金进出）；不计算未经调整的收益。'
    if len({v['start'] for v in dated.values()}) != 1:
        return None, '历史起始资金发生变化；不计算未经调整的收益。'
    spy = dict(zip(sector_prices['SPY']['date'], sector_prices['SPY']['close']))
    if any(day not in spy or spy[day] <= 0 for day in days):
        return None, 'SPY 同期行情缺失；不使用未来价格或联网补价。'
    index = pd.to_datetime(days)
    equity = pd.Series([dated[d]['equity'] for d in days], index=index)
    benchmark = pd.Series([spy[d] for d in days], index=index)
    returns = equity.pct_change().iloc[1:]
    benchmark_returns = benchmark.pct_change().iloc[1:]
    # Include the observed starting valuation for drawdown from the first loss.
    with_origin = pd.concat([pd.Series([0.], index=index[:1]), returns])
    monthly = qs.stats.monthly_returns(returns, eoy=False)
    observed = {(d.year, d.month) for d in returns.index}
    for year in monthly.index:
        for month in range(1, 13):
            column = calendar.month_abbr[month].upper()
            if column in monthly.columns and (int(year), month) not in observed:
                monthly.loc[year, column] = float('nan')
    return dict(days=days, equity=(equity / equity.iloc[0]).tolist(),
                spy=(benchmark / benchmark.iloc[0]).tolist(),
                drawdown=qs.stats.to_drawdown_series(with_origin).tolist(),
                monthly=monthly,
                total=float(qs.stats.comp(returns)), benchmark=float(qs.stats.comp(benchmark_returns))), ''


def chart(lines, percent=False):
    values = [v for _, line in lines for v in line]
    low, high = min(values), max(values)
    span = high - low or 1
    paths = []
    for color, line in lines:
        points = ' '.join(f'{20 + i * 660 / max(1, len(line)-1):.2f},{170-(v-low)*140/span:.2f}' for i, v in enumerate(line))
        paths.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{points}"/>')
    fmt = (lambda x: f'{x:.1%}') if percent else (lambda x: f'{x:.3f}')
    return f'<svg viewBox="0 0 740 195" role="img" aria-label="净值或回撤走势"><text x="685" y="30">{fmt(high)}</text><text x="685" y="170">{fmt(low)}</text>{"".join(paths)}</svg>'


def render(export, outcomes, sectors, report_date, *, history=(), signals=None):
    report_day = dt.date.fromisoformat(report_date)
    day = report_date if calendars.is_session('XNYS', report_date) else calendars.previous_session('XNYS', report_date)
    if export.get('as_of', day) != day:
        raise ValueError('cockpit as_of does not match report valuation session')
    book = valuation(export, day)
    money = lambda x: '不可用' if x is None else f'{x:,.2f}'
    sections = []
    def card(title, body):
        sections.append(f'<section><h2>{title}</h2>{body}</section>')
    card('模拟账户', f'<p>估值日 {day} · 现金 {money(book["cash"])} · 总资产 {money(book["equity"])} · 相对起始资金变动 {money(book["equity"]-book["start"] if book["equity"] is not None else None)}</p>'
         + '<p>金额按导出账户币种；策略组损益为持仓毛损益，未分配费用或现金。资金进出会影响总资产变动。</p>'
         + '<ul>' + ''.join(f'<li>{escape(i)}</li>' for i in book['issues']) + '</ul>'
         + '<table><tr><th>策略组</th><th>持仓市值</th><th>已实现损益</th><th>未实现损益</th></tr>'
         + ''.join(f'<tr><td>{escape(k)}</td><td>{money(v["value"]) if not book["issues"] else "不完整"}</td><td>{money(v["realized"])}</td><td>{money(v["unrealized"]) if not book["issues"] else "不完整"}</td></tr>' for k,v in sorted(book['sleeves'].items())) + '</table>')
    start = (report_day - dt.timedelta(days=report_day.weekday())).isoformat()
    if signals is None:
        signal_text = '<p>信号明细未提供，不能把缺失记录当作零信号。</p>'
    else:
        week = [s for s in signals if s.get('version') == app_data.VERSION and start <= s['signal_day'] <= day]
        signal_text = f'<p>本周 {len(week)} 个记录（不等于成交或买入建议）。</p><ul>' + ''.join(f'<li>{escape(s["symbol"])} · {escape(s["signal_day"])}</li>' for s in week) + '</ul>'
    card('本周信号', signal_text)
    journal = [j for j in rows(export.get('journal', [])) if start <= j['at'][:10] <= report_date]
    card('本周日志', '<ul>' + ''.join(f'<li>{escape(j["at"])} · {escape(j["text"])}</li>' for j in journal) + '</ul>')
    portfolio = app_data.portfolio(sectors, day)
    changes = [s['symbol'] for s in portfolio['sleeves'] if s['would_switch']]
    stale = [s['symbol'] for s in portfolio['sleeves'] if s['stale'] or s['month_end']['stale'] or s['today']['hold'] is None]
    card('月底再平衡', f'<p>最近月底判断：{portfolio["month_end_signal_as_of"]}；当前是否到期：{"是" if portfolio["rebalance_due"] else "否"}；下一交易日：{portfolio["next_session"]}。</p><p>与月底相比的候选变化：{escape("、".join(changes) or "无")}。行情不足或过期：{escape("、".join(stale) or "无")}。这里只展示状态，不生成交易。</p>')
    computed = outcomes.get('computed_at', '')
    if not computed or computed[:10] > report_date:
        forward = '前向记录日期缺失或晚于报告日，不能用于本期报告。'
    else:
        statuses = Counter(o.get('r19', {}).get('status', o.get('status', 'unknown')) for o in outcomes.get('outcomes', []))
        forward = f'来源日期 {computed}；版本 {outcomes.get("version", "未注明")}；记录 {len(outcomes.get("outcomes", []))}；状态 {dict(statuses)}。尚不能据此证明策略有效。'
    card('前向记录', f'<p>{escape(forward)}</p>')
    snapshots = list(history)
    for snapshot in snapshots:
        if snapshot.get('as_of') == day and valuation(snapshot, day) != book:
            raise ValueError('current export conflicts with history valuation')
    if not any(x.get('as_of') == day for x in snapshots):
        snapshots.append(dict(export, as_of=day))
    metrics, reason = history_metrics(snapshots, sectors, day)
    if metrics is None:
        card('QuantStats', f'<p>{reason}</p>')
    else:
        card('QuantStats', f'<p>{metrics["days"][0]} — {day}；区间收益 {metrics["total"]:.2%}，SPY {metrics["benchmark"]:.2%}。蓝色：账户；绿色：SPY。首个净值归一为 1。</p>'
             + chart([('#2563eb', metrics['equity']), ('#059669', metrics['spy'])]))
        card('回撤', chart([('#dc2626', metrics['drawdown'])], percent=True))
        monthly = metrics['monthly']
        card('月度收益（首尾月可能不完整）', monthly.to_html(float_format=lambda x: f'{x:.2%}', border=0, na_rep='—'))
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sage Vista 周报</title><style>body{margin:0;background:#eef2f6;color:#17243b;font:16px system-ui}header{background:#10213b;color:white;padding:28px}main{max-width:1040px;margin:auto;padding:18px}section{background:white;border-radius:12px;padding:20px;margin:16px 0;overflow:auto}h2{font-size:20px}table{border-collapse:collapse;width:100%}td,th{padding:8px;text-align:right;border-bottom:1px solid #e2e8f0}svg{width:100%;min-width:320px}svg text{font-size:11px}</style><header><h1>Sage Vista 周报 · ' + report_date + ('（合成夹具示例）' if export.get('fixture') else '') + '</h1><p>记录本周事实；历史不足时不展示绩效结论。</p></header><main>' + ''.join(sections) + '</main></html>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cockpit', type=Path, required=True)
    parser.add_argument('--date', required=True)
    parser.add_argument('--history', type=Path, help='Directory of daily cockpit JSON exports, each with as_of')
    parser.add_argument('--outcomes', type=Path, default=app_data.ROOT / app_data.FORWARD / 'outcomes.json')
    parser.add_argument('--signals', type=Path, help='Defaults to signals.jsonl beside outcomes')
    parser.add_argument('--output-dir', type=Path, default=app_data.ROOT / 'work/reports/weekly')
    args = parser.parse_args()
    read = lambda p: json.loads(p.read_text())
    signals_path = args.signals or args.outcomes.with_name('signals.jsonl')
    signals = [json.loads(line) for line in signals_path.read_text().splitlines() if line.strip()] if signals_path.exists() else None
    history = [read(p) for p in sorted(args.history.glob('*.json'))] if args.history else []
    html = render(read(args.cockpit), read(args.outcomes), app_data.frozen_prices(app_data.SECTOR), args.date, history=history, signals=signals)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f'{args.date}.html'
    path.write_text(html, encoding='utf-8')
    print(path)


if __name__ == '__main__':
    main()
