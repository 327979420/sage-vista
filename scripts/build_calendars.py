"""Offline calendar export. Run with work/vectorbt-env/bin/python."""
import hashlib
import importlib.metadata
import json
from pathlib import Path

import exchange_calendars

ROOT = Path(__file__).resolve().parents[1]
START, END = '2005-01-03', '2030-12-31'


def export(code):
    calendar = exchange_calendars.get_calendar(code, start=START, end=END)
    payload = dict(sessions=[d.date().isoformat() for d in calendar.sessions],
                   early_closes={d.date().isoformat(): calendar.schedule.loc[d, 'close'].isoformat()
                                 for d in calendar.early_closes})
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    return dict(header=dict(market=code, start=START, end=END, source='exchange_calendars',
                            version=exchange_calendars.__version__, sha256=hashlib.sha256(raw).hexdigest(),
                            hash_basis='canonical JSON of sessions and early_closes; sorted keys, compact separators'),
                **payload)


def main():
    folder = ROOT / 'data/calendars'
    folder.mkdir(parents=True, exist_ok=True)
    for code in ('XNYS', 'XHKG'):
        result = export(code)
        (folder / f'{code.lower()}-2005-2030.json').write_text(json.dumps(result, indent=2) + '\n')
        print(code, len(result['sessions']), 'sessions', len(result['early_closes']), 'early closes')
    dist = importlib.metadata.distribution('exchange_calendars')
    licence = next(f for f in dist.files if str(f).endswith('/licenses/LICENSE'))
    blob = dist.locate_file(licence).read_bytes()
    folder = ROOT / 'research/backtest/dependencies'
    (folder / f'LICENSE.exchange_calendars-{dist.version}.txt').write_bytes(blob)
    evidence = dict(package='exchange_calendars', version=dist.version,
                    source=f'https://pypi.org/project/exchange-calendars/{dist.version}/',
                    license='Apache-2.0', license_sha256=hashlib.sha256(blob).hexdigest(),
                    license_bytes=len(blob), evidence_basis='installed distribution metadata; offline')
    (folder / f'exchange_calendars-{dist.version}.evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    main()
