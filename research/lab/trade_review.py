"""Read-only Task042 post-mortems; offline caches, no trading decisions or writes to inputs."""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
from pathlib import Path

from research.lab import forward_judge as J, own_picks as P

MISSING = '缺数据'
REASONS = {'loss': 'stop', 'win': 'target', 'time': 'time', 'manual': 'manual',
           'stop': 'stop', 'target': 'target'}
LABELS = {'stop': '止损', 'target': '止盈', 'time': '到期', 'manual': '手动'}
GROUPS = ['3W前向', '自选股'] + [f'{a}/{s}' for a in ('paper', 'real') for s in ('3W', 'core', 'manual')]


def number(x):
    return type(x) in (float, int) and math.isfinite(x)


def day(value):
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def pnl(entry, exit_price):
    return exit_price * (1 - J.COST) - entry * (1 + J.COST) if all(number(x) for x in (entry, exit_price)) else None


def net_r(entry, exit_price, stop):
    return J.net_r(entry, exit_price, stop) if all(number(x) for x in (entry, exit_price, stop)) and entry > stop else None


def impact(actual, alert, skipped=False):
    """Both P&Ls in dollars/share; one denominator, the replayed alert's initial risk."""
    if not alert or not alert.get('verified'):
        return None
    e, st = alert.get('entry'), alert.get('stop')
    ref = pnl(e, alert.get('exit'))
    actual_pnl = 0. if skipped else pnl(actual.get('entry'), actual.get('exit'))
    if ref is None or actual_pnl is None or not number(st) or e <= st:
        return None
    return (actual_pnl - ref) / (e - st)


def period_data(series, opened, closed, as_of):
    """Do not pad missing sessions or extrapolate the requested 60/20 chart window."""
    result = {'holding_days': None, 'bars': [], 'before': 0, 'after': 0, 'complete_hold': False}
    if not series or not day(opened) or not day(closed) or opened > closed:
        return result
    dates = series.get('date', [])
    if opened not in dates or closed not in dates or closed > as_of:
        return result
    a, b = dates.index(opened), dates.index(closed)
    if a > b:
        return result
    hold_dates = dates[a:b+1]
    complete = all(P.next_session(x) == y for x, y in zip(hold_dates, hold_dates[1:]))
    result.update(holding_days=b-a+1 if complete else None, complete_hold=complete)
    for i in range(max(0, a-60), min(len(dates), b+21)):
        if dates[i] > as_of:
            break
        bar = {'date': dates[i]}
        for k in ('open', 'high', 'low', 'close'):
            values = series.get(k, [])
            bar[k] = values[i] if i < len(values) and number(values[i]) else None
        result['bars'].append(bar)
    result['before'] = sum(x['date'] < opened for x in result['bars'])
    result['after'] = sum(x['date'] > closed for x in result['bars'])
    return result


def market_context(card, series, spy, as_of):
    info = period_data(series, card.get('opened'), card.get('closed'), as_of)
    card.update(info, mfe_R=None, mae_R=None, spy_return=None)
    e, st = card.get('entry'), card.get('stop')
    held = [b for b in info['bars'] if card['opened'] <= b['date'] <= card['closed']]
    if info['complete_hold'] and held and all(number(b[k]) for b in held for k in ('high', 'low')) and number(e) and number(st) and e > st:
        card['mfe_R'] = max(0., (max(b['high'] for b in held)-e)/(e-st))
        card['mae_R'] = min(0., (min(b['low'] for b in held)-e)/(e-st))
    if spy and card.get('opened') in spy.get('date', []) and card.get('closed') in spy['date']:
        a, b = (spy['date'].index(card[k]) for k in ('opened', 'closed'))
        closes = spy.get('close', [])
        if a <= b < len(closes) and number(closes[a]) and number(closes[b]) and closes[a] > 0:
            card['spy_return'] = closes[b]/closes[a]-1


def slippage(card):
    e, plan, st = card.get('entry'), card.get('planned_entry'), card.get('planned_stop')
    card['slippage_pct'] = (e/plan-1)*100 if number(e) and number(plan) and plan > 0 else None
    card['slippage_R'] = (e-plan)/(plan-st) if all(number(x) for x in (e, plan, st)) and plan > st else None


def mechanical(card, alert=None):
    if card['group'] not in ('3W前向', 'paper/3W'):
        return {'核对': '不适用'}
    if not alert or not alert.get('verified'):
        return dict.fromkeys(('限价', '止损', '3R目标', '26周退出'), MISSING)
    same = lambda a, b: all(number(x) for x in (a, b)) and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    e, level = card.get('entry'), alert.get('planned_entry')
    limit = MISSING if not number(e) or not number(level) or not card.get('opened') else (
        '一致' if e <= level and same(e, alert.get('entry')) and card['opened'] == alert.get('opened') else '不同')
    st = card.get('stop')
    stop = MISSING if not number(st) else ('一致' if same(st, alert['stop']) else '不同')
    if card.get('stop_changed'):
        stop = '不同'
    target = card.get('target')
    target_check = MISSING if not number(target) else ('一致' if same(target, alert['target']) else '不同')
    # Compare both actual endpoint and date with the frozen replay, including gap executions.
    exit_check = MISSING if not card.get('closed') else ('一致' if card['closed'] == alert.get('closed') and same(card.get('exit'), alert.get('exit')) else '不同')
    return {'限价': limit, '止损': stop, '3R目标': target_check, '26周退出': exit_check}


def replay_cards(prices, records, outcomes, config, events, as_of):
    cards, alerts = [], {}
    for ds in sorted({r['dataset'] for r in records}):
        recs = [r for r in records if r['dataset'] == ds]
        rows = J.recompute(prices.get(ds, {}), recs, outcomes, config)
        by = {r['id']: r for r in recs}
        for row in rows:
            rec = by[row['id']]
            if not row['eligible']:
                continue
            g, plan = row.get('trade') or {}, rec['plan']
            q = prices.get(ds, {}).get(rec['symbol'])
            def date_at(key):
                i = g.get(key)
                return q['date'][i] if q and type(i) is int and 0 <= i < len(q['date']) else None
            c = {'id': rec['id'], 'symbol': rec['symbol'], 'group': '3W前向',
                 'opened': date_at('fill_day'), 'closed': row.get('exit_date'),
                 'entry': g.get('entry'), 'exit': g.get('exit') if g.get('status') in J.DONE else None,
                 'stop': plan['stop'], 'target': plan['level']+3*(plan['level']-plan['stop']),
                 'planned_entry': plan['level'], 'planned_stop': plan['stop'],
                 'planned_target': plan['level']+3*(plan['level']-plan['stop']),
                 'reason': REASONS.get(g.get('status')), 'net_R': g.get('net_R'),
                 'twin_net_R': row['net_twin_mean'] if row['check'] != '对照不一致' else None,
                 'check': row['check'], 'verified': row['completed'] and row['check'] != '对照不一致'}
            if not c['verified']:
                c.update(net_R=None, exit=None)
            alerts[c['id']] = c.copy()
            if row['completed']:
                c['checks'] = mechanical(c, alerts[c['id']])
                slippage(c)
                market_context(c, q, prices.get(ds, {}).get('SPY'), as_of)
                cards.append(c)
    if events:
        picks, _ = P.validate_events(events)
        ready = {rid for rid, p in picks.items() if p['symbol'] in prices.get(p['dataset'], {})
                 and p['signal_day'] in prices[p['dataset']][p['symbol']].get('date', [])}
        report = {'rows': []}
        missing = set(picks)-ready
        for rid in sorted(ready):
            try:
                report['rows'].extend(P.compute(prices, [e for e in events if e['id'] == rid])['rows'])
            except ValueError as exc:
                if '行情交易日缺口' not in str(exc) and '参考交易日缺行情' not in str(exc):
                    raise
                missing.add(rid)
        # Missing inputs cannot establish closure. Keep an explicitly undated card for inspection.
        for rid in sorted(missing):
            p = picks[rid]
            c = {'id': rid, 'symbol': p['symbol'], 'group': '自选股', 'opened': None, 'closed': None,
                 'entry': None, 'exit': None, 'stop': p['stop'], 'target': p['target'],
                 'planned_entry': p['entry'].get('limit'), 'planned_stop': p['stop'],
                 'planned_target': p['target'], 'reason': None, 'net_R': None, 'twin_net_R': None,
                 'check': '缺数据（无法确定是否结束）', 'checks': {'核对': MISSING}}
            slippage(c)
            market_context(c, None, None, as_of)
            cards.append(c)
        for row in report['rows']:
            if not row['completed']:
                continue
            p, g = picks[row['id']], row['trade']
            plan_entry = p['entry'].get('limit') if p['entry']['type'] == 'limit' else None
            c = {'id': p['id'], 'symbol': p['symbol'], 'group': '自选股', 'opened': g.get('fill_date'),
                 'closed': g.get('exit_date'), 'entry': g.get('entry'), 'exit': g.get('exit'),
                 'stop': p['stop'], 'target': p['target'], 'planned_entry': plan_entry,
                 'planned_stop': p['stop'], 'planned_target': p['target'], 'reason': REASONS.get(g['status']),
                 'net_R': g.get('net_R'), 'twin_net_R': row['net_twin_mean'], 'check': row['check'],
                 'checks': {'核对': '不适用（自选登记）'}}
            slippage(c)
            market_context(c, prices[p['dataset']].get(p['symbol']), prices[p['dataset']].get('SPY'), as_of)
            cards.append(c)
    return cards, alerts


def cockpit_cards(cockpit, alerts, px, as_of):
    cards, deviations = [], []
    if cockpit is None:
        return cards, deviations
    positions = cockpit.get('positions', [])
    skips = cockpit.get('skips', [])
    if not isinstance(positions, list) or not isinstance(skips, list):
        raise ValueError('cockpit positions/skips 必须为数组')
    for i, pos in enumerate(positions + skips):
        alert = alerts.get(pos.get('alert_id'))
        if alert and alert.get('closed') and alert['closed'] > as_of:
            alert = {**alert, 'verified': False, 'net_R': None, 'exit': None, 'closed': None, 'twin_net_R': None}
        if pos.get('skipped') is True:
            deviations.append({'id': pos.get('alert_id'), 'symbol': alert.get('symbol') if alert else None,
                               'date': day(pos.get('date')), 'kind': '跳过', 'note': pos.get('note'),
                               'comparison_date': alert.get('closed') if alert and alert.get('verified') else None,
                               'actual_net_R': None, 'alert_net_R': alert.get('net_R') if alert else None,
                               'impact_R': impact({}, alert, skipped=True)})
            continue
        if pos.get('status') not in ('closed', 'win', 'loss', 'time', 'manual', 'stop', 'target'):
            continue
        if pos.get('account') not in ('paper', 'real') or pos.get('source') not in ('3W', 'core', 'manual'):
            raise ValueError('cockpit 已结束交易的 account/source 不在合同内')
        if alert and alert['symbol'] != pos.get('symbol'):
            raise ValueError('alert_id 与持仓代码不一致')
        opened, closed = day(pos.get('opened')), day(pos.get('closed'))
        if opened and closed and closed < opened:
            raise ValueError('退出日期早于入场日期')
        history = pos.get('stop_history')
        valid_history = isinstance(history, list) and bool(history) and all(day(h.get('date')) and number(h.get('stop')) for h in history)
        hist = sorted(history, key=lambda h: h['date']) if valid_history else []
        initial = [h for h in hist if opened and h['date'] <= opened]
        # A lone current stop cannot prove the original stop. Preserve missing provenance.
        original_stop = initial[0]['stop'] if initial else None
        stop_changed = original_stop is not None and closed and any(
            opened <= h['date'] <= closed and h['stop'] != original_stop for h in hist)
        c = {'id': str(pos.get('id', f'cockpit-{i}')), 'symbol': pos.get('symbol'),
             'group': f"{pos['account']}/{pos['source']}", 'opened': opened, 'closed': closed,
             'entry': pos.get('entry'), 'exit': pos.get('exit_price'), 'stop': original_stop,
             'target': pos.get('target'), 'planned_entry': alert.get('planned_entry') if alert else None,
             'planned_stop': alert.get('planned_stop') if alert else None,
             'planned_target': alert.get('planned_target') if alert else None,
             'reason': REASONS.get(pos.get('exit_reason')), 'net_R': net_r(pos.get('entry'), pos.get('exit_price'), original_stop),
             'twin_net_R': alert.get('twin_net_R') if alert else None,
             'check': '提醒已匹配' if alert else MISSING, 'alert_id': pos.get('alert_id'),
             'stop_changed': bool(stop_changed),
             'alert_net_R': alert.get('net_R') if alert else None, 'impact_R': impact({'entry': pos.get('entry'), 'exit': pos.get('exit_price')}, alert)}
        c['checks'] = mechanical(c, alert)
        slippage(c)
        market_context(c, px.get(pos.get('symbol')), px.get('SPY'), as_of)
        if pos['account'] == 'real':
            detected = []
            if alert and number(c['entry']) and number(alert.get('entry')) and not math.isclose(c['entry'], alert['entry'], rel_tol=1e-9):
                detected.append('成交价格不同')
            if stop_changed:
                detected.append('移动止损')
            if alert and original_stop is not None and original_stop != alert.get('stop'):
                detected.append('原始止损不同')
            if alert and closed and alert.get('closed') and closed < alert['closed']:
                detected.append('提前退出')
            c['deviation_checks'] = {
                '成交价格': '已核对' if alert and number(alert.get('entry')) and number(c['entry']) else MISSING,
                '止损历史': '已提供' if original_stop is not None else MISSING,
                '退出日期': '已核对' if closed and alert and alert.get('closed') else MISSING}
            # One impact per trade, not one impact per label: never sum causal attributions.
            if detected:
                deviations.append({'id': c['id'], 'symbol': c['symbol'], 'date': closed, 'kind': '、'.join(detected),
                                   'comparison_date': max(closed, alert['closed']) if closed and alert and alert.get('verified') and alert.get('closed') else None,
                                   'note': None, 'actual_net_R': c['net_R'], 'alert_net_R': c['alert_net_R'], 'impact_R': c['impact_R']})
            c['deviations'] = detected
        cards.append(c)
    return cards, deviations


def totals(cards):
    rs = [c['net_R'] for c in cards if number(c.get('net_R'))]
    pairs = [c for c in cards if number(c.get('net_R')) and number(c.get('twin_net_R'))]
    wins, losses = [x for x in rs if x > 0], [x for x in rs if x < 0]
    return {'count': len(cards), 'net_count': len(rs), 'win_rate': len(wins)/len(rs) if rs else None,
            'payoff': J.mean(wins)/-J.mean(losses) if wins and losses else None,
            'profit_factor': sum(wins)/-sum(losses) if losses else None, 'mean_net_R': J.mean(rs),
            'paired_count': len(pairs), 'vs_twins': J.mean([c['net_R']-c['twin_net_R'] for c in pairs])}


def digest(cards, deviations, as_of, cockpit_status, synthetic=False):
    end = dt.date.fromisoformat(as_of)
    start = (end-dt.timedelta(days=end.weekday())).isoformat()
    available = [c for c in cards if c.get('closed') and c['closed'] <= as_of]
    undated = [c for c in cards if not c.get('closed')]
    return {'as_of': as_of, 'week_start': start, 'synthetic': synthetic, 'cockpit_status': cockpit_status,
            'cards': [c for c in available if c['closed'] >= start], 'undated': undated,
            'totals': {g: totals([c for c in available if c['group'] == g]) for g in GROUPS},
            'deviations': [d for d in deviations if d.get('date') and (
                start <= d['date'] <= as_of or d['date'] <= as_of and d.get('comparison_date') and start <= d['comparison_date'] <= as_of)],
            'undated_deviations': [d for d in deviations if not d.get('date')],
            'future_excluded': sum(bool(c.get('closed') and c['closed'] > as_of) for c in cards)}


def show(value, suffix=''):
    if value is None:
        return MISSING
    return f'{value:.4f}{suffix}' if isinstance(value, float) else str(value)+suffix


def esc(value):
    return html.escape(show(value), quote=True)


def chart(card):
    bars = [b for b in card.get('bars', []) if all(number(b[k]) for k in ('open', 'high', 'low', 'close'))]
    if not bars:
        return '<p>日线图：缺数据</p>'
    levels = [('入场', card.get('entry')), ('止损', card.get('stop')), ('目标', card.get('target')), ('退出', card.get('exit'))]
    values = [b[k] for b in bars for k in ('low', 'high')] + [v for _, v in levels if number(v)]
    lo, hi = min(values), max(values)
    pad = (hi-lo)*.1 or 1
    lo, hi = lo-pad, hi+pad
    x = lambda i: 20 + i*690/max(1, len(bars)-1)
    y = lambda v: 240-(v-lo)/(hi-lo)*210
    parts = ['<div class="chart"><svg viewBox="0 0 850 290" role="img" aria-label="交易日线与成交标记">']
    width = min(6, 420/max(1, len(bars)))
    for i, b in enumerate(bars):
        color = '#177c65' if b['close'] >= b['open'] else '#b94e53'
        parts.append(f'<path d="M{x(i):.2f} {y(b["high"]):.2f}V{y(b["low"]):.2f}" stroke="{color}"/>')
        parts.append(f'<rect x="{x(i)-width/2:.2f}" y="{min(y(b["open"]),y(b["close"])):.2f}" width="{width:.2f}" height="{max(1,abs(y(b["open"])-y(b["close"]))):.2f}" fill="{color}"/>')
    # Separate right-hand labels prevent identical levels from overlapping.
    for n, (label, value) in enumerate(levels):
        if not number(value):
            continue
        yy, label_y = y(value), 35+n*48
        parts.append(f'<path d="M15 {yy:.2f}H720L740 {label_y}" fill="none" stroke="#7c8c9a" stroke-dasharray="4 4"/><text x="746" y="{label_y+4}">{label} {value:.2f}</text>')
    for label, date in [('入', card.get('opened')), ('出', card.get('closed'))]:
        indices = [i for i,b in enumerate(bars) if b['date'] == date]
        if indices:
            xx = x(indices[0])
            parts.append(f'<path d="M{xx:.2f} 18V245" stroke="#405db1" stroke-dasharray="2 4"/><text x="{xx:.2f}" y="{12 if label == "入" else 260}">{label}</text>')
    parts.append(f'<text x="20" y="282">{esc(bars[0]["date"])}</text><text x="630" y="282">{esc(bars[-1]["date"])}</text></svg></div>')
    parts.append(f'<p class="muted">请求入场前60 / 退出后20个交易日；已提供 {card["before"]} / {card["after"]}。不足部分：'+('缺数据' if card['before'] < 60 or card['after'] < 20 else '无')+'。</p>')
    return ''.join(parts)


def table(headers, rows):
    return '<div class="scroll"><table><thead><tr>'+''.join(f'<th>{esc(h)}</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{esc(v)}</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def render_card(c):
    fields = [('计划入场', c.get('planned_entry')), ('计划止损', c.get('planned_stop')), ('计划目标', c.get('planned_target')),
              ('实际入场', c.get('entry')), ('实际退出', c.get('exit')), ('原始止损', c.get('stop')),
              ('入场日期', c.get('opened')), ('退出日期', c.get('closed')), ('退出原因', LABELS.get(c.get('reason'))),
              ('入场滑点%', c.get('slippage_pct')), ('入场滑点R（计划风险）', c.get('slippage_R')),
              ('净R（实际风险）', c.get('net_R')), ('持有交易日（含首尾）', c.get('holding_days')),
              ('MFE R（日线范围）', c.get('mfe_R')), ('MAE R（日线范围，负值）', c.get('mae_R')),
              ('同日孪生平均净R', c.get('twin_net_R')), ('SPY同期收盘收益%', c.get('spy_return')*100 if number(c.get('spy_return')) else None),
              ('数据核对', c.get('check'))]
    if 'alert_id' in c:
        fields += [('提醒ID', c.get('alert_id')), ('提醒净R（提醒风险）', c.get('alert_net_R')), ('偏差影响R（提醒风险）', c.get('impact_R'))]
    body = f'<article><h3>{esc(c["symbol"])} · {esc(c["group"])}</h3><p class="muted">{esc(c["id"])}</p><dl>'+''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k,v in fields)+'</dl>'
    body += '<h4>机械核对</h4>'+table(['项目','记录'], c.get('checks', {}).items())
    if 'deviation_checks' in c:
        body += '<h4>真实账户记录</h4>'+table(['项目','资料'], c['deviation_checks'].items())
        body += '<p>已记录偏差：'+esc('、'.join(c['deviations']) or '未记录；资料状态见上表')+'</p>'
    return body+chart(c)+'</article>'


def render(report):
    rows = [[g, *[t[k] for k in ('count','net_count','win_rate','payoff','profit_factor','mean_net_R','paired_count','vs_twins')]] for g,t in report['totals'].items()]
    body = f'<header><p class="eyebrow">SAGE VISTA · 交易复盘</p><h1>{"合成样例 · " if report["synthetic"] else ""}每周交易记录</h1><p>{esc(report["week_start"])} — {esc(report["as_of"])}</p><p>本周已结束 {len(report["cards"])} 笔 · cockpit：{esc(report["cockpit_status"])}</p></header>'
    body += '<section><h2>累计记录（截至报告日）</h2>'+table(['来源','笔数','净R可用','胜率（比例）','盈亏比','Profit factor','平均净R','孪生配对数','平均净R差'],rows)
    body += '<p class="muted">按来源分别累计，不合并可能重叠的前向与账户记录。胜率、盈亏比和Profit factor按可用净R计算；无分母显示缺数据。孪生差只取可配对交易。</p></section>'
    body += '<section><h2>本周复盘卡</h2>' + (''.join(render_card(c) for c in report['cards']) or '<p>本周无已结束交易。</p>')+'</section>'
    def deviations(rows):
        return table(['记录','代码','记录日期','对照完成日期','偏差','实际净R','提醒净R','影响R（提醒风险）','备注'], [[d.get(k) for k in ('id','symbol','date','comparison_date','kind','actual_net_R','alert_net_R','impact_R','note')] for d in rows]) if rows else '<p>无已记录偏差。</p>'
    body += '<section><h2>本周真实账户偏差</h2><p class="muted">列本周记录或本周完成提醒对照的偏差；提醒尚未结束时影响为缺数据。</p>'+deviations(report['deviations'])+'</section>'
    body += '<section><h2>日期缺失记录</h2><p>退出日期或结束状态无法确定 '+str(len(report['undated']))+' 笔，未纳入本周或累计；偏差日期缺失 '+str(len(report['undated_deviations']))+' 条。</p>'+''.join(render_card(c) for c in report['undated'])+deviations(report['undated_deviations'])+'</section>'
    body += '<footer><p>每边成本0.1%。实际净R分母＝实际入场−原始止损；提醒净R分母＝提醒成交价−提醒原始止损。偏差影响＝（实际每股净盈亏−提醒每股净盈亏）÷提醒风险；明确跳过的实际盈亏为0。同笔多个偏差只列一个合计影响，不作原因分摊。</p><p>滑点为实际入场减计划入场，正值表示买入价更高。MFE/MAE采用持有日期首尾日完整OHLC范围，不能区分首尾日成交前后，可能高估实际持仓内波动；盘中精确MFE/MAE：缺数据。SPY为相同日期收盘至收盘收益。</p><p>日线图仅使用截至报告日的离线价格。缺价格不补齐；缺提醒关联、原始止损历史或退出信息不推断。后续20个交易日不足时随缓存更新补齐。报告日之后的交易排除 '+str(report['future_excluded'])+' 笔。</p></footer>'
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>每周交易复盘</title><style>
:root{font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:#263843;background:#f4f6f6;font-variant-numeric:tabular-nums}*{box-sizing:border-box}body{margin:0}main{max-width:1220px;margin:auto;padding:32px 24px}header{padding:24px 0}h1{font-size:32px}h2{font-size:21px}h3{font-size:19px}h4{font-size:15px}p{line-height:1.75}section,article{background:white;border:1px solid #dce4e6;border-radius:12px;padding:24px;margin:20px 0}article{background:#fafcfc}.eyebrow,.muted,dt,footer{color:#647680;font-size:13px}dl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}dl div{min-width:0}dd{margin:6px 0 0;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}th,td{text-align:left;padding:12px;border-bottom:1px solid #e2e8e9}th{color:#647680;font-weight:500}.scroll{overflow-x:auto}.chart{overflow-x:auto;margin-top:24px}svg{display:block;width:100%;min-width:680px}svg text{font-size:11px;fill:#526773}footer{padding:12px}@media(max-width:600px){main{padding:16px}section,article{padding:16px}h1{font-size:26px}dl{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}section article{margin-left:0;margin-right:0}}
</style></head><body><main>'''+body+'</main></body></html>\n'


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def load_inputs(as_of, cockpit):
    config = json.loads(J.F.CONFIG.read_text())
    frozen = json.loads((J.F.ROOT/J.F.FOLDER/'outcomes.json').read_text())
    records = J.F.load_records()
    events = read_jsonl(P.FOLDER/'picks.jsonl')
    selected = {r['dataset'] for r in records} | {e['dataset'] for e in events if e['event'] == 'add'}
    if cockpit and cockpit.get('positions'):
        selected.update(config['datasets'])
    if selected - set(config['datasets']):
        raise ValueError('未知数据集，拒绝漏计')
    # No future prices even when rebuilding an older report from a newer cache.
    cutoff = min(as_of, frozen['computed_at'][:10])
    prices = {}
    for ds in config['datasets']:
        if ds not in selected:
            continue
        try:
            prices[ds] = {s: P.clipped(q, cutoff) for s,q in J.cached_prices(ds, config, cutoff).items()}
        except FileNotFoundError:
            prices[ds] = {}
    return prices, records, frozen['outcomes'], config, events


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cockpit', type=Path)
    p.add_argument('--as-of', default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    p.add_argument('--out', type=Path, default=J.F.ROOT/'work/trade-review')
    a = p.parse_args(argv)
    if not day(a.as_of):
        p.error('--as-of 必须为YYYY-MM-DD')
    cockpit = json.loads(a.cockpit.read_text()) if a.cockpit and a.cockpit.exists() else None
    prices, records, outcomes, config, events = load_inputs(a.as_of, cockpit)
    cards, alerts = replay_cards(prices, records, outcomes, config, events, a.as_of)
    # Same first-dataset precedence as forward registration, never overwrite with another dataset.
    px = {}
    for ds in config['datasets']:
        for sym, q in prices.get(ds, {}).items():
            px.setdefault(sym, q)
    cc, deviations = cockpit_cards(cockpit, alerts, px, a.as_of)
    report = digest(cards+cc, deviations, a.as_of, '已提供' if cockpit is not None else '未提供')
    a.out.mkdir(parents=True, exist_ok=True)
    path = a.out/f'weekly-{a.as_of}.html'
    path.write_text(render(report), encoding='utf-8')
    path.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(f'{path}；本周已结束 {len(report["cards"])} 笔；cockpit {report["cockpit_status"]}')


if __name__ == '__main__':
    main()
