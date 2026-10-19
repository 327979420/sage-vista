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


def brief_payload(symbol, entry, stop, target, until, *, simulated=False):
    label = '🧪 模拟｜3W' if simulated else '3W 挂单机会'
    suffix = ' · 非真实机会' if simulated else ' · 日终模拟账户'
    return {'allowed_mentions': {'parse': []}, 'embeds': [{
        'title': f'{label} · {symbol}',
        'description': (
            f'入场 ${money(entry)}｜止损 ${money(stop)}｜止盈 ${money(target)}（3R）\n'
            f'挂单有效至约 {until}（40交易日）\n'
            f'规则 {VERSION}{suffix}'
        ),
        'color': 14197855 if simulated else 5763719,
    }]}


def simulation_notices(state):
    # Fixed synthetic sample, never read or write strategy/price records.
    key = 'simulation:3w-1.9:brief-v1'
    if key in state['notifications']:
        return []
    return [{'key': key, 'payload': brief_payload(
        'TEST', 98, 90, 122, '2026-12-14', simulated=True)}]


def collect(root, state, now):
    folder = Path(root) / 'public/app'
    snapshot = read(folder / 'signals.json')
    as_of = snapshot['as_of']
    if as_of != latest_session(now):
        raise ValueError('signal snapshot is not the latest completed regular NYSE session')
    if dt.datetime.fromisoformat(snapshot['generated_at'].replace('Z', '+00:00')) > now:
        raise ValueError('future snapshot timestamp')
    notices, seen = [], set()
    for signal in snapshot['signals']:
        key = f"{VERSION}:{signal['id']}"
        if key in seen:
            raise ValueError('duplicate signal identity')
        seen.add(key)
        if signal['version'] != VERSION or signal['status'] != 'waiting' or signal['order']['eligible'] is not True:
            continue
        if key in state['notifications']:
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
        if ticket['outcome']['status'] != 'waiting' or order['eligible'] is not True or signal['market']['ok'] is not True:
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
        if as_of >= until:
            continue  # Never invite a new order after its final session has closed.
        payload = brief_payload(signal['symbol'], entry, stop, target, until)
        notices.append({'key': key, 'payload': payload})
    return notices


def deliver(notices, state, persist, sender, now):
    """persist must synchronously confirm durable storage or raise before HTTP."""
    for notice in notices:
        key = notice['key']
        if key in state['notifications']:
            continue
        state['notifications'][key] = {'status': 'reserved', 'reserved_at': now.isoformat()}
        persist(state)
        try:
            sender(notice['payload'])
        except Exception:
            # Do not print urllib exceptions: they can contain the webhook URL.
            raise RuntimeError('Discord delivery unconfirmed; reservation retained; reconcile before retry') from None
        state['notifications'][key].update(status='sent', sent_at=now.isoformat())
        persist(state)


def publish_state(root, state):
    """CAS push on main with an isolated index; never commit other work."""
    if in_eod_window():
        raise RuntimeError('state publication blocked in EOD window')
    def git(*args, **kwargs):
        return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True, **kwargs).stdout
    git('fetch', 'origin', 'main')
    parent = git('rev-parse', 'origin/main').decode().strip()
    # Refuse a concurrent publisher or app-data change; next run can reconcile.
    for rel in (STATE, 'public/app/signals.json'):
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
        git('update-index', '--add', '--cacheinfo', f'100644,{oid},{STATE}', env=env)
        tree = git('write-tree', env=env).decode().strip()
        commit = git('-c', 'user.name=sage-vista-bot', '-c', 'user.email=sage-vista-bot@users.noreply.github.com',
                     'commit-tree', tree, '-p', parent, '-m', 'state: 3W Discord delivery [skip ci]').decode().strip()
        if in_eod_window():
            raise RuntimeError('state publication blocked in EOD window')
        git('push', 'origin', f'{commit}:refs/heads/main')
    (Path(root) / STATE).write_bytes(data)


def run(root, send=False, now=None, simulate=False):
    now = now or dt.datetime.now(dt.timezone.utc)
    state = read(Path(root) / STATE)
    if state.get('schema_version') != 1 or not isinstance(state.get('notifications'), dict):
        raise ValueError('invalid notification ledger')
    notices = simulation_notices(state) if simulate else collect(root, state, now)
    held = [key for key, value in state['notifications'].items() if value['status'] != 'sent']
    if not send:
        return {'result': 'preview', 'notices': notices, 'needs_reconciliation': held}
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise RuntimeError('sending is restricted to the main Actions workflow')
    webhook = os.environ.get('DISCORD_WEBHOOK_URL') or os.environ.get('DISCORD_OPPORTUNITY')
    if not webhook:
        raise RuntimeError('Discord webhook secret is not configured')
    deliver(notices, state, lambda s: publish_state(root, s), lambda p: post(webhook, p), now)
    if held:
        raise RuntimeError('previous deliveries require reconciliation; see notification ledger')
    return {'result': 'sent' if notices else 'no_new_opportunities', 'count': len(notices)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send', action='store_true')
    parser.add_argument('--simulate', action='store_true', help='fixed, clearly labeled synthetic sample; deduplicated separately')
    parser.add_argument('--root', type=Path, default=Path('.'))
    args = parser.parse_args()
    print(json.dumps(run(args.root, args.send, simulate=args.simulate), ensure_ascii=False, indent=2))
