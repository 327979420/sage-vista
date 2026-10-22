"""Notify from verified 3w-1.9 app projections; never scan or change strategy.

Reserve each identity durably BEFORE HTTP. An ambiguous delivery is held for
human reconciliation, never automatically retried (Discord has no atomic
transaction with our Git ledger). Preview is entirely read-only and offline.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from zoneinfo import ZoneInfo

from research.lab.app_data import next_session, ticket_name
from research.lab.run_queue import in_eod_window
from services.scanner.discord_daily_digest import post

STATE = 'automation/triangle-discord-state.json'
VERSION = '3w-1.9'
SIM_STATE = 'automation/triangle-discord-simulation-state.json'


def read(path):
    return json.loads(Path(path).read_text())


def latest_session(now):
    local = now.astimezone(ZoneInfo('America/New_York'))
    day = local.date()
    if local.hour < 16:
        day -= dt.timedelta(days=1)
    while next_session((day - dt.timedelta(days=1)).isoformat()) != day.isoformat():
        day -= dt.timedelta(days=1)
    return day.isoformat()


def money(value):
    # Preserve sub-cent levels while keeping whole-cent prices easy to scan.
    text = f'{value:.4f}'.rstrip('0').rstrip('.')
    whole, _, fraction = text.partition('.')
    return whole + '.' + fraction.ljust(2, '0')


def shares(equity, entry, stop):
    if not math.isfinite(equity) or equity <= 0:
        raise ValueError('invalid account equity')
    risk_limit, cap_limit = equity * .02 / (entry - stop), equity * .2 / entry
    count = math.floor(min(risk_limit, cap_limit))
    return count, count * (entry - stop), '风险2%' if risk_limit <= cap_limit else '仓位20%'


def share_line(label, equity, entry, stop):
    count, risk, bound = shares(equity, entry, stop)
    return f'{label}：{count} 股 · 风险 ${money(risk)} · {bound}限制'


def brief_payload(symbol, entry, stop, target, until, *, simulated=False, alert_id='A-TEST00', equity=None):
    label = '🧪 模拟 · 3W 挂单机会' if simulated else '3W 挂单机会'
    real = share_line('每 $10,000', 10000, entry, stop) if equity is None else share_line('实盘账户', equity, entry, stop)
    return {'allowed_mentions': {'parse': []}, 'content': (
        f'**{label} · {symbol} · {alert_id}**\n\n'
        f'限价入场　**${money(entry)}**\n'
        f'止损　　　**${money(stop)}**\n'
        f'止盈　　　**${money(target)}** · 3R\n\n'
        + share_line('$100,000 模拟', 100000, entry, stop) + '\n'
        + real + '\n开仓前确认：总风险 ≤ 10%、持仓 ≤ 10 只\n\n'
        + f'有效至约 **{until}** · 40 个交易日')}


EVENTS = {'filled': ('✅', '成交'), 'stopped': ('🛑', '止损'), 'target': ('🎯', '止盈'),
          'time': ('⏱️', '26周退出'), 'expired': ('⌛', '到期未成交'), 'cancelled': ('🚫', '撤单')}


CANCEL_WHY = {'stop before the fill': '成交前先碰到止损', 'target before the fill': '成交前先碰到止盈'}


def follow_payload(symbol, alert_id, event, date, price=None, net_r=None, simulated=False, reason=None):
    emoji, word = EVENTS[event]
    text = f'{emoji} {word} · {symbol} · {alert_id}'
    if simulated:
        text = '🧪 模拟 · ' + text
    date_label = '到期日' if event == 'expired' else '日期'
    text += f'\n{date_label}：{date}'
    if price is not None:
        price_label = '触发价' if event == 'cancelled' else '价格'
        text += f'\n{price_label}：${money(price)}'
    if net_r is not None:
        text += f'\n净 R：{net_r:+.4f}（每边成本0.1%）'
    if event == 'cancelled' and reason in CANCEL_WHY:
        text += f'\n原因：{CANCEL_WHY[reason]}'
    if event in ('cancelled', 'expired'):
        text += '\n如有挂单，请撤销'
    return {'allowed_mentions': {'parse': []}, 'content': text}


def alert_ids(snapshot, state):
    ids = {x['id'] for x in snapshot['signals']}
    prefix = VERSION + ':'
    for key in state['notifications']:
        if key.startswith(prefix):
            ids.add(key[len(prefix):].split(':')[0])
    assigned = {}
    for sid in sorted(ids):
        saved = state['notifications'].get(prefix + sid, {}).get('alert_id')
        assigned[sid] = saved or 'A-' + sid[:6]
    for sid in sorted(ids):
        if any(other != sid and other[:6] == sid[:6] for other in ids):
            if not state['notifications'].get(prefix + sid, {}).get('alert_id'):
                assigned[sid] = 'A-' + sid[:8]
    if len(set(assigned.values())) != len(assigned):
        raise ValueError('alert ID collision remains after eight characters')
    return assigned


def simulation_notices(state):
    base = 'simulation:3w-1.9:lifecycle-v1'
    notices = [dict(key=base, alert_id='A-TEST00', payload=brief_payload(
        'TEST', 98, 90, 122, '2026-12-14', simulated=True))]
    for event, price in [('filled',98), ('stopped',90), ('target',122), ('time',105), ('expired',None), ('cancelled',122)]:
        net = (price * .999 - 98 * 1.001) / 8 if event in ('stopped','target','time') else None
        notices.append(dict(key=base+':'+event, alert_id='A-TEST00', payload=follow_payload(
            'TEST', 'A-TEST00', event, '2026-12-14', price, net, True,
            reason='target before the fill' if event == 'cancelled' else None)))
    return [n for n in notices if n['key'] not in state['notifications']]


def follow_notices(signal, ticket, key, alert_id, as_of, state):
    o = ticket['outcome']
    if o.get('mismatch') or o['status'] == 'unverified':
        raise ValueError('unverified ticket outcome')
    if o['status'] == 'waiting':
        return []
    if o['status'] not in ('filled', 'closed', 'cancelled'):
        raise ValueError('unsupported ticket outcome')
    events = []
    if o['status'] in ('filled', 'closed'):
        events.append(('filled', o['fill_date'], o['fill_price'], None))
    if o['status'] == 'closed':
        event = {'loss':'stopped', 'win':'target', 'time':'time'}[o['source_status']]
        e, x, stop = o['fill_price'], o['exit'], ticket['order']['stop']
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in (e, x)):
            raise ValueError('invalid fill or exit price')
        if not 0 < stop < e:
            raise ValueError('invalid fill risk')
        events.append((event, o['exit_date'], x, (x*.999-e*1.001)/(e-stop)))
    if o['status'] == 'cancelled':
        why = o['cancel_reason']
        if why not in ('no fill in 8 weeks', 'stop before the fill', 'target before the fill'):
            raise ValueError('unknown cancellation reason')
        if not o.get('confirmed_date') or not o['cancel_date'] <= o['confirmed_date'] <= as_of:
            raise ValueError('unconfirmed cancellation')
        events.append(('expired' if why == 'no fill in 8 weeks' else 'cancelled', o['cancel_date'], o['cancel_price'], None))
    notices = []
    previous = signal['signal_day']
    for event, date, price, net in events:
        if not date or not previous <= date <= as_of:
            raise ValueError('invalid event date')
        previous = date
        if event != 'expired' and (isinstance(price, bool) or not isinstance(price, (int,float)) or not math.isfinite(price) or price <= 0):
            raise ValueError('invalid event price')
        if key+':'+event not in state['notifications']:
            notices.append(dict(key=key+':'+event, alert_id=alert_id,
                payload=follow_payload(signal['symbol'], alert_id, event, date, price, net,
                                       reason=ticket['outcome'].get('cancel_reason') if event == 'cancelled' else None)))
    return notices


def collect(root, state, now, equity=None):
    folder = Path(root) / 'public/app'
    snapshot = read(folder / 'signals.json')
    as_of = snapshot['as_of']
    if as_of != latest_session(now):
        raise ValueError('signal snapshot is not the latest completed regular NYSE session')
    if dt.datetime.fromisoformat(snapshot['generated_at'].replace('Z', '+00:00')) > now:
        raise ValueError('future snapshot timestamp')
    ids = alert_ids(snapshot, state)
    notices, seen = [], set()
    for signal in snapshot['signals']:
        key = f"{VERSION}:{signal['id']}"
        if key in seen:
            raise ValueError('duplicate signal identity')
        seen.add(key)
        alerted = key in state['notifications']
        if signal['version'] != VERSION or signal['order']['eligible'] is not True:
            continue
        if not alerted and signal['status'] != 'waiting':
            continue
        if signal['quote']['stale'] or signal['quote']['price_as_of'] != as_of:
            raise ValueError('stale opportunity quote')
        ticket = read(folder / ticket_name(signal['id']))
        if ticket.get('example') is not False:
            raise ValueError('example or unclassified ticket cannot be sent')
        for field in ('id', 'symbol', 'version', 'dataset', 'signal_day'):
            if ticket[field] != signal[field]:
                raise ValueError('ticket identity mismatch')
        order = ticket['order']
        if (not alerted and ticket['outcome']['status'] != 'waiting') or order['eligible'] is not True or signal['market']['ok'] is not True:
            raise ValueError('ticket outcome or eligibility mismatch')
        for field in ('limit', 'stop', 'target'):
            value = order[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('invalid order price')
            if value != signal['order'][field]:
                raise ValueError('ticket price mismatch')
        entry, stop, target = (order[k] for k in ('limit', 'stop', 'target'))
        if not 0 < stop < entry < target or not math.isclose(target, entry + 3 * (entry - stop), rel_tol=0, abs_tol=1e-8):
            raise ValueError('not a frozen 3R target')
        if order['wait_sessions'] != 40 or order['max_hold_sessions'] != 130 or order['R_multiple'] != 3:
            raise ValueError('frozen duration or target mismatch')
        until = signal['signal_day']
        for _ in range(40):
            until = next_session(until)
        if order['valid_until'] != until or order['valid_until_basis'] != 'regular_NYSE_sessions_estimate':
            raise ValueError('expiry mismatch')
        if signal['signal_day'] > as_of:
            raise ValueError('future signal')
        if alerted:
            notices.extend(follow_notices(signal, ticket, key, ids[signal['id']], as_of, state))
            continue
        if as_of >= until:
            continue  # Never invite a new order after its final session has closed.
        payload = brief_payload(signal['symbol'], entry, stop, target, until, alert_id=ids[signal['id']], equity=equity)
        notices.append({'key': key, 'alert_id': ids[signal['id']], 'payload': payload})
    return notices


def deliver(notices, state, persist, sender, now):
    """persist must synchronously confirm durable storage or raise before HTTP."""
    for notice in notices:
        key = notice['key']
        if key in state['notifications']:
            continue
        state['notifications'][key] = {'status': 'reserved', 'reserved_at': now.isoformat(), 'alert_id': notice.get('alert_id')}
        persist(state)
        try:
            sender(notice['payload'])
        except Exception:
            # Do not print urllib exceptions: they can contain the webhook URL.
            raise RuntimeError('Discord delivery unconfirmed; reservation retained; reconcile before retry') from None
        state['notifications'][key].update(status='sent', sent_at=now.isoformat())
        persist(state)


def publish_state(root, state, *, allow_eod_window=False, state_path=STATE):
    """CAS push on main with an isolated index; never commit other work."""
    if in_eod_window() and not allow_eod_window:
        raise RuntimeError('state publication blocked in EOD window')
    def git(*args, **kwargs):
        return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True, **kwargs).stdout
    git('fetch', 'origin', 'main')
    parent = git('rev-parse', 'origin/main').decode().strip()
    # Refuse a concurrent publisher or app-data change; next run can reconcile.
    for rel in (state_path, 'public/app/signals.json'):
        if rel == SIM_STATE and not (Path(root) / rel).exists():
            if git('ls-tree', '--name-only', parent, '--', rel).strip():
                raise RuntimeError('upstream simulation state changed')
            continue
        if git('show', f'{parent}:{rel}') != (Path(root) / rel).read_bytes():
            raise RuntimeError('upstream state or signal snapshot changed')
    for rel in git('ls-tree', '-r', '--name-only', parent, '--', 'public/app/tickets').decode().splitlines():
        if git('show', f'{parent}:{rel}') != (Path(root) / rel).read_bytes():
            raise RuntimeError('upstream ticket changed')
    data = (json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, 'GIT_INDEX_FILE': str(Path(tmp) / 'index')}
        git('read-tree', parent, env=env)
        oid = git('hash-object', '-w', '--stdin', input=data).decode().strip()
        git('update-index', '--add', '--cacheinfo', f'100644,{oid},{state_path}', env=env)
        tree = git('write-tree', env=env).decode().strip()
        commit = git('-c', 'user.name=sage-vista-bot', '-c', 'user.email=sage-vista-bot@users.noreply.github.com',
                     'commit-tree', tree, '-p', parent, '-m', 'state: 3W Discord delivery [skip ci]').decode().strip()
        if in_eod_window() and not allow_eod_window:
            raise RuntimeError('state publication blocked in EOD window')
        git('push', 'origin', f'{commit}:refs/heads/main')
    (Path(root) / state_path).write_bytes(data)


def run(root, send=False, now=None, simulate=False, allow_eod_window=False):
    if allow_eod_window and not simulate:
        raise ValueError('EOD exception is restricted to explicitly authorized simulations')
    now = now or dt.datetime.now(dt.timezone.utc)
    state_path = SIM_STATE if simulate else STATE
    path = Path(root) / state_path
    state = read(path) if path.exists() else {'schema_version': 1, 'notifications': {}}
    if not simulate and not path.exists():
        raise ValueError('missing production ledger')
    if state.get('schema_version') != 1 or not isinstance(state.get('notifications'), dict):
        raise ValueError('invalid notification ledger')
    equity = None
    if send and not simulate and os.environ.get('SV_ACCOUNT_EQUITY_USD'):
        try:
            equity = float(os.environ['SV_ACCOUNT_EQUITY_USD'])
            if not math.isfinite(equity) or equity <= 0:
                raise ValueError()
        except ValueError:
            raise ValueError('invalid account equity secret') from None
    notices = simulation_notices(state) if simulate else collect(root, state, now, equity)
    held = [key for key, value in state['notifications'].items() if value['status'] != 'sent']
    if not send:
        return {'result': 'preview', 'notices': notices, 'needs_reconciliation': held}
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise RuntimeError('sending is restricted to the main Actions workflow')
    webhook = os.environ.get('DISCORD_WEBHOOK_URL') or os.environ.get('DISCORD_OPPORTUNITY')
    if not webhook:
        raise RuntimeError('Discord webhook secret is not configured')
    deliver(notices, state, lambda s: publish_state(root, s, allow_eod_window=allow_eod_window, state_path=state_path), lambda p: post(webhook, p), now)
    if held:
        raise RuntimeError('previous deliveries require reconciliation; see notification ledger')
    return {'result': 'sent' if notices else 'no_new_opportunities', 'count': len(notices)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send', action='store_true')
    parser.add_argument('--simulate', action='store_true', help='fixed, clearly labeled synthetic sample; deduplicated separately')
    parser.add_argument('--allow-eod-window', action='store_true', help='explicit owner exception, simulation only')
    parser.add_argument('--root', type=Path, default=Path('.'))
    args = parser.parse_args()
    print(json.dumps(run(args.root, args.send, simulate=args.simulate, allow_eod_window=args.allow_eod_window), ensure_ascii=False, indent=2))
