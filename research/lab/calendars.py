"""Verified, offline exchange sessions; no third-party runtime dependencies.

Next/previous are strictly after/before the supplied ISO date. Unknown dates
outside the exported coverage raise rather than silently assuming weekdays.
"""
import bisect
import datetime as dt
from functools import lru_cache
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / 'data/calendars'
ALIASES = {'US': 'XNYS', 'NYSE': 'XNYS', 'HK': 'XHKG', 'HKEX': 'XHKG'}


@lru_cache(maxsize=2)
def _load(market):
    if market not in ('XNYS', 'XHKG'):
        raise ValueError(f'unknown market: {market}')
    data = json.loads((ROOT / f'{market.lower()}-2005-2030.json').read_text())
    payload = {k: data[k] for k in ('sessions', 'early_closes')}
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    if hashlib.sha256(raw).hexdigest() != data['header']['sha256']:
        raise ValueError('calendar hash mismatch')
    if data['sessions'] != sorted(set(data['sessions'])):
        raise ValueError('calendar sessions not sorted and unique')
    return data


def _checked(market, day):
    day = dt.date.fromisoformat(str(day)).isoformat()
    data = _load(ALIASES.get(market.upper(), market.upper()))
    if not data['header']['start'] <= day <= data['header']['end']:
        raise ValueError(f'calendar date out of bounds: {day}')
    return data['sessions'], day


def is_session(market, day):
    sessions, day = _checked(market, day)
    i = bisect.bisect_left(sessions, day)
    return i < len(sessions) and sessions[i] == day


def next_session(market, day):
    sessions, day = _checked(market, day)
    i = bisect.bisect_right(sessions, day)
    if i == len(sessions):
        raise ValueError('next session outside calendar coverage')
    return sessions[i]


def previous_session(market, day):
    sessions, day = _checked(market, day)
    i = bisect.bisect_left(sessions, day) - 1
    if i < 0:
        raise ValueError('previous session outside calendar coverage')
    return sessions[i]


def last_session_of_month(market, day):
    sessions, day = _checked(market, day)
    i = bisect.bisect_right(sessions, day[:7] + '-31') - 1
    if i < 0 or sessions[i][:7] != day[:7]:
        raise ValueError('month outside calendar coverage')
    return sessions[i]
