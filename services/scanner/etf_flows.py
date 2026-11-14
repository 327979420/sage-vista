"""Daily ETF creations/redemptions from issuer-published shares outstanding.

flow(day) = (shares outstanding on day - shares on the previous trading day) x NAV on day.
Issuers book creations on their own schedule (often one day after the trade), so a day's
figure is the issuer's reported change, not an intraday buying estimate. Display only.

Sources (all public, no key):
- State Street SPDR: navhist xlsx, full daily history of NAV and shares outstanding.
- Invesco: navs JSON, full daily history of NAV and total net assets (shares = TNA / NAV).
- iShares: product page, today's NAV and shares outstanding only; the previous day's shares
  come from the last successful panel, so iShares flows start on the second collected day.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import zipfile

# ticker, issuer, Chinese label, English label, group, iShares product page (iShares only)
FUNDS = [
    ('SPY', 'SSGA', '标普500', 'S&P 500', 'equity', None),
    ('IVV', 'iShares', '标普500', 'S&P 500', 'equity', 'https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf'),
    ('QQQ', 'Invesco', '纳指100', 'Nasdaq-100', 'equity', None),
    ('DIA', 'SSGA', '道指', 'Dow Jones', 'equity', None),
    ('MDY', 'SSGA', '中盘400', 'Mid-cap 400', 'equity', None),
    ('IWM', 'iShares', '小盘2000', 'Small-cap 2000', 'equity', 'https://www.ishares.com/us/products/239710/ishares-russell-2000-etf'),
    ('RSP', 'Invesco', '等权标普', 'Equal-weight S&P', 'equity', None),
    ('IWF', 'iShares', '大盘成长', 'Large growth', 'style', 'https://www.ishares.com/us/products/239706/ishares-russell-1000-growth-etf'),
    ('IWD', 'iShares', '大盘价值', 'Large value', 'style', 'https://www.ishares.com/us/products/239708/ishares-russell-1000-value-etf'),
    ('MTUM', 'iShares', '动量', 'Momentum', 'style', 'https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf'),
    ('QUAL', 'iShares', '质量', 'Quality', 'style', 'https://www.ishares.com/us/products/256101/ishares-msci-usa-quality-factor-etf'),
    ('USMV', 'iShares', '低波动', 'Min volatility', 'style', 'https://www.ishares.com/us/products/239695/ishares-msci-usa-min-vol-factor-etf'),
    ('TLT', 'iShares', '20年+美债', '20y+ Treasuries', 'bonds', 'https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf'),
    ('LQD', 'iShares', '投资级公司债', 'Investment-grade corporates', 'bonds', 'https://www.ishares.com/us/products/239566/ishares-iboxx-investment-grade-corporate-bond-etf'),
    ('HYG', 'iShares', '高收益债', 'High-yield corporates', 'bonds', 'https://www.ishares.com/us/products/239565/ishares-iboxx-high-yield-corporate-bond-etf'),
    ('UUP', 'Invesco', '美元', 'US dollar', 'dollar', None),
]
TICKERS = [f[0] for f in FUNDS]
META = [{'ticker': t, 'issuer': i, 'label': zh, 'label_en': en, 'group': g} for t, i, zh, en, g, _ in FUNDS]
SSGA = 'https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/navhist-us-en-{t}.xlsx'
INVESCO = 'https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/{t}/navs?idType=ticker&productType=ETF'
KEEP = 126          # trading days of history kept on the panel
MAX_LAG_DAYS = 4    # a fund further behind the freshest fund is reported missing, not averaged in
SNAPSHOTS = 10      # iShares share-count snapshots kept to difference consecutive sessions


def _number(value):
    number = float(str(value).replace(',', '').strip())
    if not math.isfinite(number) or number <= 0: raise ValueError('etf_flow_number')
    return number


def _series(rows, as_of):
    """[(date, shares, nav)] -> sorted, deduplicated, not after as_of."""
    out = {}
    for day, shares, nav in rows:
        date.fromisoformat(day)
        if day <= as_of: out[day] = (_number(shares), _number(nav))
    if not out: raise ValueError('etf_flow_empty')
    return sorted((d, s, n) for d, (s, n) in out.items())


def parse_ssga(content, ticker, as_of):
    z = zipfile.ZipFile(io.BytesIO(content))
    strings = [''.join(re.findall(r'<t[^>]*>([^<]*)</t>', s)) for s in re.findall(r'<si>(.*?)</si>', z.read('xl/sharedStrings.xml').decode(), re.S)]
    cells = []
    for row in re.findall(r'<row [^>]*>(.*?)</row>', z.read('xl/worksheets/sheet1.xml').decode(), re.S):
        values = []
        for kind, value in re.findall(r'<c r="[A-Z]+\d+"(?: t="(\w+)")?[^>]*?(?:/>|>(?:<f>[^<]*</f>)?<v>([^<]*)</v></c>)', row):
            values.append(strings[int(value)] if kind == 's' and value else value)
        cells.append(values)
    if not any(r[:2] == ['Ticker Symbol:', ticker] for r in cells): raise ValueError('ssga_ticker')
    header = next((i for i, r in enumerate(cells) if r[:4] == ['Date', 'NAV', 'Shares Outstanding', 'Total Net Assets']), None)
    if header is None: raise ValueError('ssga_columns')
    rows = []
    for r in cells[header + 1:]:
        if len(r) < 3 or not re.fullmatch(r'\d{2}-[A-Z][a-z]{2}-\d{4}', r[0] or ''): continue
        if not all(re.fullmatch(r'[\d.E+-]+', v or '') and v != '-' for v in r[1:3]): continue  # '-' marks a day without a NAV
        rows.append((datetime.strptime(r[0], '%d-%b-%Y').date().isoformat(), r[2], r[1]))
    return _series(rows, as_of)


def parse_invesco(content, ticker, as_of):
    raw = json.loads(content)
    if not isinstance(raw, list): raise ValueError('invesco_schema')
    rows = [(r['effectiveDate'][:10], round(r['totalNetAssets'] / r['netAssetValue']), r['netAssetValue'])
            for r in raw if r.get('netAssetValue') and r.get('totalNetAssets') and r.get('currencyCode') == 'USD']
    return _series(rows, as_of)


def parse_ishares(content, ticker, as_of):
    text = content.decode('utf-8', 'replace').replace('&quot;', '"')
    nav = re.search(r'"name":"NAV as of","value":"([\d,.]+)","unitText":"USD","valueReference":\{"@type":"PropertyValue","name":"As of Dates","value":"([A-Z][a-z]{2} \d{1,2}, \d{4})"', text)
    shares = re.search(r'"label":"Shares Outstanding","formattedValue":"([\d,]+)"[^{}]*?"formattedAsOfDate":"([A-Z][a-z]{2} \d{1,2}, \d{4})"', text)
    if not nav or not shares: raise ValueError('ishares_fields')
    if f'({ticker})' not in text and f'"tickerSymbol":"{ticker}"' not in text and f'"ticker":"{ticker}"' not in text: raise ValueError('ishares_ticker')
    days = {datetime.strptime(m, '%b %d, %Y').date().isoformat() for m in (nav[2], shares[2])}
    if len(days) != 1: raise ValueError('ishares_dates_disagree')
    return _series([(days.pop(), shares[1], nav[1])], as_of)


def _request(ticker, issuer, page):
    if issuer == 'SSGA': return SSGA.format(t=ticker.lower()), parse_ssga
    if issuer == 'Invesco': return INVESCO.format(t=ticker), parse_invesco
    return page, parse_ishares


def _store(state, digest, extract):
    path = Path(state) / 'raw' / f'{digest}.extract.json.gz'
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(json.dumps(extract, sort_keys=True).encode(), mtime=0))


def read_fund(fund, as_of, now, state, getter):
    ticker, issuer, *_, page = fund
    url, parser = _request(ticker, issuer, page)
    content = getter(url)
    rows = parser(content, ticker, as_of)
    digest = hashlib.sha256(content).hexdigest()
    # Issuer files are large (pages ~3 MB, full histories); keep only the rows used, named by the source hash.
    _store(state, digest, {'ticker': ticker, 'rows': rows[-KEEP - 1:]})
    return ticker, rows, {'provider': issuer, 'url': url, 'fetched_at': now, 'sha256': digest, 'stored': 'extract'}


def _previous(state):
    saved = Path(state) / 'last-success' / 'flows.json'
    if not saved.exists(): return None
    panel = json.loads(saved.read_bytes())['panel']
    return panel if panel.get('frequency') == 'daily_lag' and panel.get('status') != 'unavailable' else None


def build(series, as_of, previous=None):
    """series: {ticker: [(date, shares, nav)]} for funds read today. Pure; returns panel data."""
    previous = previous or {}
    old_rows = {r['date']: r for r in previous.get('history', [])}
    history_funds = {t for t, rows in series.items() if len(rows) > 1}
    if not history_funds: raise ValueError('etf_flow_no_calendar')
    calendar = sorted({d for t in history_funds for d, _, _ in series[t]} | set(old_rows))
    newest = max(rows[-1][0] for rows in series.values())
    lag = lambda day: (date.fromisoformat(newest) - date.fromisoformat(day)).days
    current = {t: rows for t, rows in series.items() if lag(rows[-1][0]) <= MAX_LAG_DAYS}
    observation = min(rows[-1][0] for rows in current.values())
    prior = {d: calendar[i - 1] for i, d in enumerate(calendar) if i}
    flows = {}
    for ticker, rows in current.items():
        if ticker in history_funds:
            for (d0, s0, _), (d1, s1, nav) in zip(rows, rows[1:]):
                if prior.get(d1) == d0: flows[(d1, ticker)] = (s1 - s0) * nav / 1e9
    # iShares publish one snapshot a day: keep the last few (shares and NAV) and difference
    # consecutive sessions, so a day held back by a lagging fund is still computed next run.
    snapshots = {t: {r['date']: (r['value'], r['nav']) for r in v} for t, v in previous.get('shares', {}).items() if t in TICKERS}
    for ticker, rows in current.items():
        if ticker not in history_funds:
            day, shares, nav = rows[-1]; snapshots.setdefault(ticker, {})[day] = (shares, nav)
    for ticker, by_day in snapshots.items():
        days = sorted(by_day)
        for d0, d1 in zip(days, days[1:]):
            if prior.get(d1) == d0: flows[(d1, ticker)] = (by_day[d1][0] - by_day[d0][0]) * by_day[d1][1] / 1e9
    shares = {t: [{'date': d, 'value': v, 'nav': n} for d, (v, n) in sorted(by_day.items())[-SNAPSHOTS:]] for t, by_day in snapshots.items()}
    history = []
    for day in [d for d in calendar if d <= observation][-KEEP:]:
        row = {t: v for t, v in old_rows.get(day, {}).items() if t in TICKERS}
        row.update({t: v for (d, t), v in flows.items() if d == day})
        row = {t: round(row[t], 4) for t in TICKERS if t in row}
        if row: history.append({'date': day, 'value': round(sum(row.values()), 4), 'funds': len(row), **row})
    if not history or history[-1]['date'] != observation: raise ValueError('etf_flow_no_latest_row')
    return {'history': history, 'value': history[-1]['value'], 'observation_date': observation, 'unit': 'USD billion',
            'funds_meta': META, 'shares': shares, 'missing': sorted(set(TICKERS) - set(current))}


def collect(as_of, now, state, getter):
    errors = {}
    def attempt(fund):
        try: return read_fund(fund, as_of, now, state, getter)
        except (OSError, ValueError, KeyError, TypeError, IndexError, zipfile.BadZipFile, json.JSONDecodeError) as error:
            errors[fund[0]] = type(error).__name__; return None
    with ThreadPoolExecutor(max_workers=4) as pool: results = [r for r in pool.map(attempt, FUNDS) if r]
    if not results: raise ValueError('etf_flow_all_sources_failed')
    data = build({t: rows for t, rows, _ in results}, as_of, _previous(state))
    data['sources'] = [s for _, _, s in results]
    return data


def check(panel, as_of):
    """Structural checks used by market_cockpit.validate for the flows panel."""
    if [m['ticker'] for m in panel['funds_meta']] != TICKERS: raise ValueError('cockpit_flow_funds')
    for row in panel['history']:
        funds = [t for t in row if t not in ('date', 'value', 'funds')]
        if not set(funds) <= set(TICKERS) or row['funds'] != len(funds) or not funds: raise ValueError('cockpit_flow_row')
        if abs(row['value'] - sum(row[t] for t in funds)) > 1e-3: raise ValueError('cockpit_flow_total')
    if not set(panel['missing']) <= set(TICKERS): raise ValueError('cockpit_flow_missing')
    for ticker, snaps in panel['shares'].items():
        days = [r['date'] for r in snaps]
        if ticker not in TICKERS or not snaps or days != sorted(set(days)) or days[-1] > as_of or len(snaps) > SNAPSHOTS: raise ValueError('cockpit_flow_shares')
        if any(isinstance(r[k], bool) or not isinstance(r[k], (int, float)) or not r[k] > 0 for r in snaps for k in ('value', 'nav')): raise ValueError('cockpit_flow_shares')
