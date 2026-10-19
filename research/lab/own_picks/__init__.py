"""Append-only, offline own-pick forward record (Task038). No cloud/network I/O."""
from __future__ import annotations
import argparse
import bisect
from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import uuid
from zoneinfo import ZoneInfo
from research.lab import forward_judge as J
from research.lab.app_data import next_session

ROOT = Path(__file__).resolve().parents[3]
FOLDER = Path(__file__).resolve().parent
NY = ZoneInfo('America/New_York')
UTC = dt.timezone.utc


def instant(value):
    t = dt.datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    if t.tzinfo is None:
        raise ValueError('时间必须有时区')
    return t.astimezone(UTC)


def session_open(day):
    return dt.datetime.combine(dt.date.fromisoformat(day), dt.time(9, 30), NY)


def registration_day(now):
    """Use regular close conservatively on early closes; refuse intraday orders."""
    local = instant(now).astimezone(NY)
    day = local.date()
    is_session = next_session((day-dt.timedelta(days=1)).isoformat()) == day.isoformat()
    if is_session and local.time() >= dt.time(16):
        return day.isoformat()
    day -= dt.timedelta(days=1)
    while next_session((day-dt.timedelta(days=1)).isoformat()) != day.isoformat():
        day -= dt.timedelta(days=1)
    return day.isoformat()


def validate_deadline(day, now):
    first = next_session(day)
    if instant(now) >= session_open(first):
        raise ValueError('首个可能成交交易日已开盘，拒绝迟到登记/撤单')
    return first


def clipped(series, day):
    end = bisect.bisect_right(series['date'], day)
    return {k: v[:end] for k, v in series.items() if isinstance(v, list)}


def reference(series, day):
    q = clipped(series, day)
    if not q['date'] or q['date'][-1] != day:
        raise ValueError('登记参考日缺价格，不使用陈旧收盘')
    w = J.BS.periods(q, 'week')
    # A Friday/holiday-shortened week is complete when the next session is in another ISO week.
    current_week = dt.date.fromisoformat(day).isocalendar()[:2]
    closed = dt.date.fromisoformat(next_session(day)).isocalendar()[:2] != current_week
    i = len(w['date'])-1 if closed else len(w['date'])-2
    if i < 20 or not w['atr'][i]:
        raise ValueError('登记时已完成周线/ATR不足')
    return {'ref': q['close'][-1], 'atr': w['atr'][i], 'atr_week': w['date'][i]}


def make_pick(px, dataset, symbol, stop, target, why, now, *, limit=None, weeks=26, wait=J.N.WAIT, rid=None):
    now = instant(now)
    day = registration_day(now)
    first = validate_deadline(day, now)
    if not why.strip() or type(weeks) is not int or weeks < 1 or type(wait) is not int or not 1 <= wait <= J.N.WAIT:
        raise ValueError('理由必填；weeks为正整数；wait只可缩短默认期限')
    if symbol not in px:
        raise ValueError('代码不在冻结美股数据源中')
    ref = reference(px[symbol], day)
    level = ref['ref'] if limit is None else limit
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in (stop, target, level)) or not 0 < stop < level < target:
        raise ValueError('必须0 < stop <参考入场价< target')
    if limit is not None and limit > ref['ref']:
        raise ValueError('限价须不高于登记参考收盘')
    rid = rid or uuid.uuid4().hex
    m = (level-stop)/ref['atr']
    r_target = (target-level)/(level-stop)
    pick = {'event': 'add', 'id': rid, 'symbol': symbol, 'dataset': dataset,
            'recorded_at': now.isoformat(), 'signal_day': day, 'first_session': first,
            'entry': {'type': 'market' if limit is None else 'limit', 'limit': limit},
            'stop': stop, 'target': target, 'weeks': weeks, 'hold': weeks*5, 'wait': wait, 'why': why,
            **ref, 'm': m, 'r_target': r_target, 'limit_ratio': level/ref['ref'],
            'calendar': 'regular_NYSE_holidays; early close conservatively treated as 16:00 NY'}
    return pick


def draw_twins(px, pick):
    """Compute-time frozen pool/draw; all order levels use registration-day data."""
    day = pick['signal_day']
    if not any(q['date'] and q['date'][-1] > day for q in px.values()):
        return []
    rules = {**J.N.POOL, 'exclude': J.selection.impossible_jumps(px) | J.N.FUNDS}
    pool = [s for s in J.selection.eligible_pool(px, day, rules) if s != pick['symbol']]
    seed = int(hashlib.sha256(pick['id'].encode()).hexdigest()[:8], 16)
    twins = []
    for sym in random.Random(seed).sample(pool, min(30, len(pool))):
        row = {'symbol': sym}
        try:
            ref_t = reference(px[sym], day)
            entry_t = ref_t['ref']*pick['limit_ratio']
            stop_t = entry_t-pick['m']*ref_t['atr']
            if stop_t <= 0 or (entry_t-stop_t)/entry_t > .4:
                raise ValueError('冻结孪生止损条件不满足')
            row.update(ref_t, entry={'type': pick['entry']['type'],
                                    'limit': entry_t if pick['entry']['type'] == 'limit' else None},
                       stop=stop_t, target=entry_t+pick['r_target']*(entry_t-stop_t))
        except ValueError as exc:
            row['skip'] = str(exc)
        twins.append(row)
    return twins


def replay(series, pick, cancel_at=None):
    """Daily mechanical fills. Invalid actual risk is counted but never fabricated."""
    day = pick['signal_day']
    if day not in series['date']:
        raise ValueError('参考交易日缺行情')
    i0 = series['date'].index(day)
    cancel_day = None
    if cancel_at is not None:
        cancel_at = instant(cancel_at)
        cancel_day = next_session(registration_day(cancel_at))
        validate_deadline(registration_day(cancel_at), cancel_at)
    q = series
    # Missing sessions may not silently lengthen WAIT/HOLD. Refuse rather than pad prices.
    dates = q['date'][i0:]
    for a, b in zip(dates, dates[1:]):
        if next_session(a) != b:
            raise ValueError(f'行情交易日缺口 {a} -> {b}；STOP，不补价格')
    st, target, hold = pick['stop'], pick['target'], pick['hold']
    fill = None
    if pick['entry']['type'] == 'limit':
        # Let the frozen function own the exact order cancellation/expiry semantics.
        active = q
        if cancel_day is not None:
            end = bisect.bisect_left(q['date'], cancel_day)
            active = {k: v[:end] for k, v in q.items() if isinstance(v, list)}
        g = J.N.trade(active, i0, pick['entry']['limit'], st, target, hold=hold, wait=pick['wait'])
        if 'fill_day' not in g:
            if cancel_day and q['date'][-1] >= cancel_day and g['status'] == 'waiting':
                g = {'status': 'cancelled', 'why': 'owner cancellation', 'cancel_effective': cancel_day}
            return g
        # Cancellation applies to a pending order only; an earlier fill continues to exit mechanically.
        g = J.N.trade(q, i0, pick['entry']['limit'], st, target, hold=hold, wait=pick['wait'])
        result = {**g, 'stop': st, 'fill_date': q['date'][g['fill_day']], 'net_R': None}
        if g['status'] in J.DONE:
            result.update(exit_date=q['date'][g['exit_day']], net_R=J.net_r(g['entry'], g['exit'], st))
        return result
    else:
        i = i0+1
        if i >= len(q['date']):
            return {'status': 'waiting'}
        if cancel_day and q['date'][i] >= cancel_day:
            return {'status': 'cancelled', 'why': 'owner cancellation', 'cancel_effective': cancel_day}
        fill = (i, q['open'][i])
    i, e = fill
    base = {'fill_day': i, 'entry': e, 'fill_date': q['date'][i], 'stop': st}
    if e <= st:
        # Market gap at entry: actual e-stop cannot define a positive R unit.
        return {**base, 'status': 'loss', 'exit_day': i, 'exit_date': q['date'][i], 'exit': e,
                'R': None, 'net_R': None, 'why': '开盘已越止损，开盘即退出；实际风险非正，R不可计分'}
    for k in range(i, min(i+hold, len(q['date']))):
        o, lo, hi = q['open'][k], q['low'][k], q['high'][k]
        # Stop takes priority on a bar touching both boundaries; gaps execute at open.
        if o <= st:
            x, status = o, 'loss'
        elif lo <= st:
            x, status = st, 'loss'
        elif hi >= target:
            x, status = max(o, target), 'win'
        elif k == i+hold-1:
            x, status = q['close'][k], 'time'
        else:
            continue
        return {**base, 'status': status, 'exit_day': k, 'exit_date': q['date'][k], 'exit': x,
                'R': (x-e)/(e-st), 'net_R': J.net_r(e, x, st)}
    return {**base, 'status': 'open', 'net_R': None}


def checkpoint(done, paper):
    scored = [r for r in done if r['scored']]
    avg, t = J.paired_stats(scored)
    pause = (len(done)-len(scored))/len(done) > .1
    alarm = bool(not pause and avg is not None and avg < 0 and t is not None and t <= -2)
    return {'k': len(done), 'scored': len(scored), 'unscorable': len(done)-len(scored),
            'mean_d': avg, 't': t, 'alarm1': alarm,
            'verdict': '暂停判断（对照不足）' if pause else '提醒owner' if alarm else
            '有效' if len(done) >= 100 and t is not None and t >= 2 else '继续记录，未证明'}


def compute(prices, events):
    picks, cancels = validate_events(events)
    rows = []
    for pick in picks.values():
        px = prices[pick['dataset']]
        g = replay(px[pick['symbol']], pick, cancels.get(pick['id']))
        awaiting = not any(q['date'] and q['date'][-1] > pick['signal_day'] for q in px.values())
        if awaiting:
            g['why'] = '等待次日行情'
        twins = []
        for t in draw_twins(px, pick):
            if 'skip' in t:
                twins.append(t)
            else:
                twins.append({**t, 'trade': replay(px[t['symbol']], {**pick, **t}, cancels.get(pick['id']))})
        rs = [t['trade']['net_R'] for t in twins if t.get('trade', {}).get('status') in J.DONE
              and t['trade'].get('net_R') is not None]
        mean_t = J.mean(rs)
        done = g['status'] in J.DONE
        scored = done and g.get('net_R') is not None and mean_t is not None
        rows.append({'id': pick['id'], 'symbol': pick['symbol'], 'eligible': True, 'completed': done,
                     'exit_date': g.get('exit_date'), 'trade': g, 'twins': twins, 'scored': scored,
                     'net_twin_mean': mean_t, 'd': g['net_R']-mean_t if scored else None,
                     'check': '自选股无冻结核对', 'frozen': {}, 'gross_difference': None})
    # forward_judge's gross check expects numeric entries only for scored rows.
    for r in rows:
        if r['scored']:
            gross = [t['trade']['R'] for t in r['twins'] if t.get('trade', {}).get('status') in J.DONE and t['trade'].get('R') is not None]
            r['gross_difference'] = r['trade']['R']-J.mean(gross)
    report = J.score(rows, checkpoint_judge=checkpoint)
    # Descriptive trade metrics include all computable own trades, even without a twin.
    rs = [r['trade']['net_R'] for r in rows if r['completed'] and r['trade'].get('net_R') is not None]
    wins, losses = [r for r in rs if r > 0], [r for r in rs if r < 0]
    report['all_trades'] = {'completed': sum(r['completed'] for r in rows), 'net_R_available': len(rs),
        'win_rate': len(wins)/len(rs) if rs else None, 'mean_net_R': J.mean(rs),
        'payoff_ratio': J.mean(wins)/-J.mean(losses) if wins and losses else None,
        'profit_factor': sum(wins)/-sum(losses) if losses else None}
    report['registered'] = len(picks)
    report['cancel_events'] = len(cancels)
    report['status_counts'] = {s: sum(r['trade']['status'] == s for r in rows) for s in ('waiting', 'cancelled', 'open', 'win', 'loss', 'time')}
    return report


def validate_events(events):
    picks, cancels = {}, {}
    previous = None
    for e in events:
        at = instant(e['recorded_at'])
        if previous is not None and at < previous:
            raise ValueError('日志时间倒退')
        previous = at
        rid = e['id']
        if e['event'] == 'add':
            if rid in picks:
                raise ValueError('重复登记id，禁止覆盖')
            validate_deadline(e['signal_day'], at)
            picks[rid] = e
        elif e['event'] == 'cancel':
            if rid not in picks or rid in cancels:
                raise ValueError('未知或重复撤单')
            validate_deadline(registration_day(at), at)
            cancels[rid] = e['recorded_at']
        else:
            raise ValueError('只允许add/cancel，不允许编辑或删除')
    return picks, cancels


@contextmanager
def locked_log(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            events = [json.loads(line) for line in f if line.strip()]
            validate_events(events)
            yield f, events
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def append_event(handle, events, event):
    validate_events(events+[event])
    handle.seek(0, os.SEEK_END)
    handle.write(json.dumps(event, ensure_ascii=False, allow_nan=False)+'\n')
    handle.flush()
    os.fsync(handle.fileno())


def load_prices(config, as_of, datasets=None):
    return {ds: J.cached_prices(ds, config, as_of) for ds in (datasets or config['datasets'])}


def markdown(report):
    from research.lab.eye_judge import show
    r = report['all_trades']
    lines = [report['verdict'], '', '状态：本地实现；尚未接入Actions正式计分。',
             f"已登记 {report['registered']}；已结束 {r['completed']}；可比孪生 {report['scored']}；下一检查点 {report['next_checkpoint']}。",
             f"胜率 {show(r['win_rate'])}；盈亏比 {show(r['payoff_ratio'])}；profit factor {show(r['profit_factor'])}；平均净R {show(r['mean_net_R'])}。",
             f"净R对照差 {show(report['mean_d'])}；t {show(report['t'])}（全样本仅描述）。",
             f"状态计数：{report['status_counts']}", '', '| 检查点 | 已计分 | 净R差 | t | 结论 |', '|---|---|---|---|---|']
    for c in report['checkpoints']:
        lines.append('| '+' | '.join(show(c[k]) for k in ('k', 'scored', 'mean_d', 't', 'verdict'))+' |')
    f = report.get('triangle', {})
    lines += ['', f"同期旁列3W：已结束 {f.get('completed', '未提供')}；平均净R {show(f.get('mean_net_R'))}；对随机 {show(f.get('mean_d'))}；{f.get('verdict', '未提供')}。",
              '3W与自选股各自累计起点不同，旁列不构成两组配对检验。',
              'Concerns：小样本；owner可能先看到3W信号；只登记部分自选股会造成选择偏差；重复检查和交易相关性会增加误报。',
              '离线日历只含常规休市，未知临时停市无法预知；缺行情直接停止，不补价。',
              '登记日志只提供追加接口；不宣称能防止操作者在文件系统外部篡改。缺对照超过10%暂停检查点判断。']
    return '\n'.join(lines)+'\n'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--log', type=Path, default=FOLDER/'picks.jsonl')
    sub = p.add_subparsers(dest='command', required=True)
    add = sub.add_parser('add')
    add.add_argument('symbol')
    for flag in ('stop', 'target'):
        add.add_argument('--'+flag, type=float, required=True)
    add.add_argument('--limit', type=float)
    add.add_argument('--weeks', type=int, default=26)
    add.add_argument('--wait', type=int, default=J.N.WAIT)
    add.add_argument('--why', required=True)
    cancel = sub.add_parser('cancel')
    cancel.add_argument('id')
    calc = sub.add_parser('compute')
    calc.add_argument('--out', type=Path, default=FOLDER/'outcomes.json')
    a = p.parse_args(argv)
    now = dt.datetime.now(UTC)
    config = json.loads(J.F.CONFIG.read_text())
    if a.command == 'add':
        day = registration_day(now)
        validate_deadline(day, now)
        # Fixed config order, same first-dataset precedence as frozen forward signal registration.
        pick = None
        for ds in config['datasets']:
            px = J.cached_prices(ds, config, day)
            if a.symbol.upper() in px:
                pick = make_pick(px, ds, a.symbol.upper(), a.stop, a.target, a.why, now,
                                 limit=a.limit, weeks=a.weeks, wait=a.wait)
                break
        if pick is None:
            raise ValueError('代码不在五个冻结美股数据源内')
        with locked_log(a.log) as (f, events):
            # Check deadline again after loading a potentially large cache.
            validate_deadline(day, dt.datetime.now(UTC))
            pick['recorded_at'] = dt.datetime.now(UTC).isoformat()
            append_event(f, events, pick)
        print(pick['id'])
    elif a.command == 'cancel':
        day = registration_day(now)
        validate_deadline(day, now)
        with locked_log(a.log) as (f, events):
            picks, cancels = validate_events(events)
            if a.id not in picks or a.id in cancels:
                raise ValueError('未知或已撤订单')
            pick = picks[a.id]
            px = J.cached_prices(pick['dataset'], config, day)
            if px[pick['symbol']]['date'][-1] != day:
                raise ValueError('撤单前行情未更新，不猜测是否已成交')
            if replay(px[pick['symbol']], pick)['status'] != 'waiting':
                raise ValueError('只允许撤销尚未成交的等待订单')
            now = dt.datetime.now(UTC)
            validate_deadline(day, now)
            append_event(f, events, {'event': 'cancel', 'id': a.id, 'recorded_at': now.isoformat()})
        print('已追加撤单，原登记保留')
    else:
        with locked_log(a.log) as (handle, events):
            events = list(events)
            handle.seek(0)
            log_digest = hashlib.sha256(handle.read().encode()).hexdigest()
        picks, _ = validate_events(events)
        frozen_path = ROOT/'research/lab/forward/triangle/outcomes.json'
        frozen = json.loads(frozen_path.read_text())
        as_of = frozen['computed_at'][:10]
        selected = sorted({r['dataset'] for r in picks.values()})
        px = load_prices(config, as_of, selected) if selected else {}
        if any(r['signal_day'] > as_of for r in picks.values()):
            raise ValueError('前向运行早于最新自选股登记，等待同次缓存更新')
        report = compute(px, events)
        from research.lab.eye_judge import forward_rows
        report['triangle'] = J.score(forward_rows(frozen_path, frozen_path.with_name('judgements.jsonl'))[0])
        report['computed_at'] = now.isoformat()
        report['price_as_of'] = as_of
        report['log_sha256'] = log_digest
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
        a.out.with_suffix('.md').write_text(markdown(report))
        print(markdown(report))
