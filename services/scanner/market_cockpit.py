"""Dated display observations, isolated from selection/account price caches.

Downloaded histories describe today's known revisions, NOT point-in-time signals.
"""
from __future__ import annotations
import argparse
import calendar
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
from html.parser import HTMLParser
import io
import json
import math
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from services.contracts.market_data import canonical_fingerprint, require_date
from services.scanner.market_internals_daily import atomic, immutable

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 'market-cockpit-v1'
FINRA = 'https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics'
ICI = 'https://www.ici.org/research/stats/combined_flows'
CFTC = 'https://publicreporting.cftc.gov/resource/gpe5-46if.json'
OCC = 'https://marketdata.theocc.com/onn-volume-download'
CODES = {'13874A': '标普500 E-mini', '209742': '纳斯达克 Mini'}
SECTORS = {'XLK':'科技', 'XLF':'金融', 'XLV':'医疗', 'XLY':'可选消费', 'XLP':'必需消费', 'XLC':'通信', 'XLI':'工业', 'XLE':'能源', 'XLB':'原材料', 'XLRE':'房地产', 'XLU':'公用事业'}
SYMBOLS = ['SPY', 'RSP', 'IWM', *SECTORS]
FREQUENCIES = {'flows':'weekly', 'positions':'weekly', 'margin':'monthly', 'options':'daily', 'quotes':'daily'}


def finite(value, *, nonnegative=False):
    number = float(str(value).replace(',', '').strip())
    if not math.isfinite(number) or (nonnegative and number < 0):
        raise ValueError('invalid_number')
    return number


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables=[]; self.table=None; self.row=None; self.cell=None
    def handle_starttag(self, tag, attrs):
        if tag == 'table': self.table=[]
        elif tag == 'tr' and self.table is not None: self.row=[]
        elif tag in ('td','th') and self.row is not None: self.cell=[]
    def handle_data(self, value):
        if self.cell is not None: self.cell.append(value)
    def handle_endtag(self, tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split())); self.cell=None
        elif tag == 'tr' and self.row is not None:
            self.table.append(self.row); self.row=None
        elif tag == 'table' and self.table is not None:
            self.tables.append(self.table); self.table=None


def tables(content):
    parser=Tables(); parser.feed(content.decode('utf-8-sig')); return parser.tables


def ordered(rows, as_of):
    rows=sorted((r for r in rows if r['date'] <= as_of), key=lambda r:r['date'])
    if not rows or len({r['date'] for r in rows}) != len(rows): raise ValueError('empty_or_duplicate_dates')
    for r in rows: require_date(r['date'], 'observation_date')
    return rows


def parse_margin(content, as_of):
    candidates=[t for t in tables(content) if any("Debit Balances in Customers' Securities Margin Accounts" in c for row in t for c in row)]
    if len(candidates)!=1: raise ValueError('finra_table_schema')
    table=candidates[0]; header=next(r for r in table if any('Debit Balances' in c for c in r))
    col=next(i for i,c in enumerate(header) if "Debit Balances in Customers' Securities Margin Accounts" in c)
    if 'millions' not in content.decode().lower(): raise ValueError('finra_units')
    rows=[]
    for r in table:
        if r and re.fullmatch(r'[A-Z][a-z]{2}-\d{2}',r[0]):
            month=datetime.strptime(r[0],'%b-%y').date(); day=month.replace(day=calendar.monthrange(month.year,month.month)[1])
            rows.append({'date':day.isoformat(),'value':finite(r[col],nonnegative=True)/1000})
    rows=ordered(rows,as_of); last=rows[-1]; previous=rows[-2] if len(rows)>1 else None
    contiguous=previous and (date.fromisoformat(last['date']).replace(day=1)-timedelta(days=1)).isoformat()==previous['date']
    year_ago=next((r for r in rows if r['date'][:7]==f"{int(last['date'][:4])-1}{last['date'][4:7]}"),None)
    return {'history':rows,'value':last['value'],'observation_date':last['date'],'unit':'USD billion',
            'change_pct':(last['value']/previous['value']-1)*100 if contiguous and previous['value'] else None,
            'change_yoy_pct':(last['value']/year_ago['value']-1)*100 if year_ago and year_ago['value'] else None}


def parse_flows(content, as_of):
    text=content.decode('utf-8-sig')
    if 'Combined Estimated' not in text or 'Millions of dollars' not in text: raise ValueError('ici_scope_or_units')
    candidates=[t for t in tables(content) if any(r and r[0]=='Domestic' for r in t)]
    if len(candidates)!=1: raise ValueError('ici_table_schema')
    table=candidates[0]; dates=next((r[1:] for r in table if len(r)>1 and all(re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',c) for c in r[1:])),None)
    values=next(r[1:] for r in table if r and r[0]=='Domestic')
    if not dates or len(dates)!=len(values): raise ValueError('ici_dates')
    rows=ordered([{'date':datetime.strptime(d,'%m/%d/%Y').date().isoformat(),'value':finite(v)/1000} for d,v in zip(dates,values)],as_of)
    four=rows[-4:]; contiguous=len(four)==4 and all((date.fromisoformat(b['date'])-date.fromisoformat(a['date'])).days==7 for a,b in zip(four,four[1:]))
    return {'history':rows,'value':rows[-1]['value'],'observation_date':rows[-1]['date'],'unit':'USD billion', 'sum_4w':sum(r['value'] for r in four) if contiguous else None}


def parse_positions(content, as_of):
    raw=json.loads(content); contracts=[]
    for code,label in CODES.items():
        rows=[]
        for r in raw:
            if r['cftc_contract_market_code']!=code: continue
            day=r['report_date_as_yyyy_mm_dd'][:10]
            oi=finite(r['open_interest_all'],nonnegative=True)
            if oi<=0: raise ValueError('cftc_open_interest')
            row={'date':day,'open_interest':oi}
            for key,field in [('leveraged','lev_money_positions'),('asset','asset_mgr_positions')]:
                long=finite(r[field+'_long'],nonnegative=True); short=finite(r[field+'_short'],nonnegative=True)
                if max(long,short)>oi: raise ValueError('cftc_positions_exceed_oi')
                row[key+'_net']=long-short; row[key]=(long-short)/oi*100
            rows.append(row)
        rows=ordered(rows,as_of)[-157:]; last=rows[-1]; previous=rows[-157:-1]
        percentiles={key:(100*sum(r[key]<=last[key] for r in previous)/len(previous) if len(previous)>=52 else None) for key in ('leveraged','asset')}
        contracts.append({'code':code,'label':label,'history':rows,'percentiles':percentiles,'percentile_weeks':len(previous)})
    days={c['history'][-1]['date'] for c in contracts}
    if len(days)!=1: raise ValueError('cftc_contract_dates')
    return {'contracts':contracts,'observation_date':days.pop(),'unit':'net / open interest %'}


def parse_options(content, as_of):
    text=content.decode('utf-8-sig')
    match=re.search(r'From (\d{2}-\d{2}-\d{4}) To (\d{2}-\d{2}-\d{4})',text)
    if not match or match[1]!=match[2]: raise ValueError('occ_daily_date')
    day=datetime.strptime(match[1],'%m-%d-%Y').date().isoformat()
    if day!=as_of: raise ValueError('occ_wrong_date')
    lines=list(csv.reader(io.StringIO(text),delimiter='\t'))
    expected=['Group','Symbol','Ex.','Customer','Firm','Customer/Firm Totals','Mkt Maker','Total']
    if expected not in lines: raise ValueError('occ_columns')
    # Sum exchange detail rows once; never add Symbol/Group subtotal rows.
    total=[0.,0.,0.]; group_totals=[0.,0.,0.]; count=0
    for r in lines[lines.index(expected)+1:]:
        if not r or not any(r): continue
        if len(r)!=8: raise ValueError('occ_truncated_or_schema')
        c,f,cf,m,t=[finite(v,nonnegative=True) for v in r[3:]]
        if any(v!=int(v) for v in (c,f,cf,m,t)) or c+f!=cf or cf+m!=t: raise ValueError('occ_inconsistent_totals')
        if r[0]=='Group' and r[1]=='Total': group_totals=[a+b for a,b in zip(group_totals,(c,f,m))]
        elif r[0]=='Symbol' and r[1]=='Total': pass
        elif re.fullmatch('[A-Z]',r[2]):
            total=[a+b for a,b in zip(total,(c,f,m))]; count+=1
        else: raise ValueError('occ_unknown_record')
    if not count or total!=group_totals or sum(total)<=0: raise ValueError('occ_missing_or_truncated_groups')
    c,f,m=total; row={'date':day,'value':c/sum(total)*100,'customer':c,'firm':f,'market_maker':m,'total':sum(total)}
    return {'history':[row],'value':row['value'],'observation_date':day,'unit':'share of reported volume %'}


def parse_yahoo(content, as_of, symbol):
    data=json.loads(content)['chart']; results=data.get('result')
    if data.get('error') or not results: raise ValueError('quote_error')
    r=results[0]
    if r['meta']['symbol']!=symbol or r['meta']['currency']!='USD': raise ValueError('quote_identity')
    stamps=r['timestamp']; values=r['indicators']['adjclose'][0]['adjclose']
    if len(stamps)!=len(values): raise ValueError('quote_length')
    rows=[]
    for ts,v in zip(stamps,values):
        if v is None: continue
        day=datetime.fromtimestamp(ts,ZoneInfo('America/New_York')).date().isoformat(); value=finite(v,nonnegative=True)
        if value<=0: raise ValueError('quote_nonpositive')
        rows.append({'date':day,'value':value})
    return ordered(rows,as_of)


def quote_metrics(histories, as_of):
    if set(histories)!=set(SYMBOLS): raise ValueError('quote_universe')
    dates=[r['date'] for r in ordered(histories['SPY'],as_of)][-126:]
    if any(not set(dates)<=set(r['date'] for r in rows) for rows in histories.values()): raise ValueError('quote_missing_session')
    if len(dates)<21 or dates[-1]!=as_of: raise ValueError('quote_alignment_or_stale')
    dates=dates[-126:]; funds=[]
    for symbol in SYMBOLS:
        lookup={r['date']:r['value'] for r in histories[symbol]}; values=[lookup[d] for d in dates]
        funds.append({'ticker':symbol,'label':SECTORS.get(symbol,{'SPY':'标普500','RSP':'等权标普','IWM':'小盘股'}.get(symbol)),
                      'history':[{'date':d,'value':v} for d,v in zip(dates,values)],
                      'returns':{str(n):(values[-1]/values[-n-1]-1)*100 for n in (1,5,20)}})
    return {'funds':funds,'observation_date':as_of,'unit':'adjusted close USD'}


def fetch(url, limit=5_000_000):
    with urlopen(Request(url,headers={'User-Agent':'SageVista-MarketOverview/1.0'}),timeout=20) as response:
        content=response.read(limit+1)
    if len(content)>limit: raise ValueError('response_too_large')
    return content


def source_record(provider, url, content, now, state):
    digest=hashlib.sha256(content).hexdigest(); raw=Path(state)/'raw'/f'{digest}.gz'
    if not raw.exists():
        raw.parent.mkdir(parents=True,exist_ok=True); raw.write_bytes(gzip.compress(content,mtime=0))
    return {'provider':provider,'url':url,'fetched_at':now,'sha256':digest}


def collect(key, as_of, now, state, getter=fetch):
    sources=[]
    if key=='quotes':
        from services.scanner import eodhd
        try: eodhd.token(); provider='EODHD'
        except RuntimeError: provider='Yahoo Finance'
        def get_symbol(symbol):
            if provider=='EODHD':
                start=(date.fromisoformat(as_of)-timedelta(days=210)).isoformat()
                raw=eodhd.get(f'eod/{symbol}.US',**{'from':start,'to':as_of,'period':'d','_timeout':20})
                content=json.dumps(raw,sort_keys=True).encode(); url=f'https://eodhd.com/api/eod/{symbol}.US'
                rows=ordered([{'date':r['date'],'value':finite(r['adjusted_close'],nonnegative=True)} for r in raw],as_of)
                if any(r['value']<=0 for r in rows): raise ValueError('quote_nonpositive')
            else:
                url=f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=6mo&interval=1d'
                content=getter(url); rows=parse_yahoo(content,as_of,symbol)
            return symbol,rows,source_record(provider,url,content,now,state)
        with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(get_symbol,SYMBOLS))
        sources=[r[2] for r in results]; data=quote_metrics({r[0]:r[1] for r in results},as_of)
    else:
        specs={
            'margin':('FINRA',FINRA,parse_margin), 'flows':('ICI',ICI,parse_flows),
            'positions':('CFTC',CFTC+'?'+urlencode({'$where':"cftc_contract_market_code in('13874A','209742')",'$order':'report_date_as_yyyy_mm_dd DESC','$limit':340}),parse_positions),
            'options':('OCC',OCC+'?'+urlencode({'productKind':'options','reportType':'D','reportDate':as_of.replace('-',''),'reportFormat':'volume','issues':'all','reportView':'totals'}),parse_options)}
        provider,url,parser=specs[key]; content=getter(url)
        sources=[source_record(provider,url,content,now,state)]; data=parser(content,as_of)
    age=(date.fromisoformat(as_of)-date.fromisoformat(data['observation_date'])).days
    limit={'daily':0,'weekly':14,'monthly':70}[FREQUENCIES[key]]
    return {'id':key,'frequency':FREQUENCIES[key],'status':'available' if age<=limit else 'stale','sources':sources,**data}


def validate(payload, expected=None):
    if payload.get('schema_version')!=SCHEMA: raise ValueError('cockpit_schema')
    as_of=payload['as_of']; require_date(as_of,'as_of')
    if expected is not None and as_of!=expected: raise ValueError('cockpit_target_date')
    if payload.get('point_in_time_backtest_eligible') is not False: raise ValueError('cockpit_not_strategy_history')
    if set(payload['panels'])!=set(FREQUENCIES): raise ValueError('cockpit_panels')
    for key,p in payload['panels'].items():
        if p['id']!=key or p['frequency']!=FREQUENCIES[key]: raise ValueError('cockpit_identity')
        if p['status']=='unavailable':
            if p.get('observation_date') is not None or set(p)-{'id','frequency','status','sources','observation_date','error_type'}: raise ValueError('unavailable_with_data')
            continue
        require_date(p['observation_date'],'observation_date')
        if p['observation_date']>as_of: raise ValueError('cockpit_future')
        age=(date.fromisoformat(as_of)-date.fromisoformat(p['observation_date'])).days
        limit={'daily':0,'weekly':14,'monthly':70}[p['frequency']]
        if p['status']!=('available' if age<=limit else 'stale'): raise ValueError('cockpit_freshness')
        if not p['sources']: raise ValueError('cockpit_no_provenance')
        for s in p['sources']:
            if not re.fullmatch('[a-f0-9]{64}',s['sha256']): raise ValueError('cockpit_hash')
        groups=p.get('contracts',p.get('funds',[p]))
        for g in groups:
            rows=g['history']; clean=ordered(rows,as_of)
            if rows!=clean or rows[-1]['date']!=p['observation_date']: raise ValueError('cockpit_history_dates')
            for row in rows:
                for field,v in row.items():
                    if field!='date' and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)): raise ValueError('cockpit_bad_value')
        if key in ('margin','flows','options') and p['value']!=p['history'][-1]['value']: raise ValueError('cockpit_latest')
        if key=='options':
            for r in p['history']:
                total=r['customer']+r['firm']+r['market_maker']
                if total<=0 or total!=r['total'] or min(r['customer'],r['firm'],r['market_maker'])<0 or abs(r['value']-r['customer']/total*100)>1e-8: raise ValueError('cockpit_share')
        if key=='positions':
            if {c['code'] for c in p['contracts']}!=set(CODES) or len(p['contracts'])!=2: raise ValueError('cockpit_contracts')
            for c in p['contracts']:
                previous=c['history'][-157:-1]; last=c['history'][-1]
                if c['percentile_weeks']!=len(previous): raise ValueError('cockpit_percentile_window')
                for field in ('asset','leveraged'):
                    expected_pct=100*sum(r[field]<=last[field] for r in previous)/len(previous) if len(previous)>=52 else None
                    if c['percentiles'][field]!=expected_pct: raise ValueError('cockpit_percentile')
                    for r in c['history']:
                        if r['open_interest']<=0 or abs(r[field]-r[field+'_net']/r['open_interest']*100)>1e-8: raise ValueError('cockpit_net_position')
        if key=='flows':
            four=p['history'][-4:]; continuous=len(four)==4 and all((date.fromisoformat(b['date'])-date.fromisoformat(a['date'])).days==7 for a,b in zip(four,four[1:]))
            if p['sum_4w']!=(sum(r['value'] for r in four) if continuous else None): raise ValueError('cockpit_flow_window')
        if key=='margin' and any(r['value']<0 for r in p['history']): raise ValueError('cockpit_negative_balance')
        if key=='quotes':
            if len({s['provider'] for s in p['sources']})!=1: raise ValueError('cockpit_mixed_quotes')
            derived=quote_metrics({f['ticker']:f['history'] for f in p['funds']},as_of)
            if derived['funds']!=p['funds']: raise ValueError('cockpit_quote_metrics')
    if payload['content_fingerprint']!=canonical_fingerprint({k:v for k,v in payload.items() if k!='content_fingerprint'}): raise ValueError('cockpit_fingerprint')
    return payload


def run(as_of, *, out=ROOT/'public/market-cockpit.json', state=ROOT/'data/market/cockpit-v1', refresh=False, collector=collect):
    require_date(as_of,'as_of'); now=datetime.now(timezone.utc).isoformat()
    if as_of>now[:10]: raise ValueError('future_target')
    previous=validate(json.loads(Path(out).read_bytes())) if Path(out).exists() else None
    if previous:
        for key in ('options','flows'):
            saved=Path(state)/'last-success'/f'{key}.json'; old=previous['panels'][key]
            if old['status']!='unavailable' and not saved.exists(): atomic(saved,{'panel':old,'fingerprint':canonical_fingerprint(old)})
    same_check=bool(previous and previous['as_of']==as_of and previous['checked_at'][:10]==now[:10] and not refresh)
    if same_check and all(p['status']=='available' for p in previous['panels'].values()):
        return {'result':'already_checked','as_of':as_of,'changed':False,'source_status':{k:v['status'] for k,v in previous['panels'].items()}}
    def attempt(key):
        if same_check and previous['panels'][key]['status']=='available': return key,previous['panels'][key]
        try: return key,collector(key,as_of,now,state)
        except (OSError,ValueError,KeyError,TypeError,IndexError,RuntimeError,csv.Error) as error:
            return key,{'id':key,'frequency':FREQUENCIES[key],'status':'unavailable','observation_date':None,'sources':[],'error_type':type(error).__name__}
    with ThreadPoolExecutor(max_workers=3) as pool: panels=dict(pool.map(attempt,FREQUENCIES))
    # Only accumulate observed options/flow records. Revisions replace same dates;
    # the old immutable snapshot and source hash remain available for audit.
    for key in ('options','flows'):
        current=panels[key]; old=previous['panels'][key] if previous else None
        saved=Path(state)/'last-success'/f'{key}.json'
        if saved.exists():
            successful=json.loads(saved.read_bytes())
            if successful['fingerprint']!=canonical_fingerprint(successful['panel']): raise ValueError('cockpit_saved_history_hash')
            old=successful['panel']
        if current['status']!='unavailable' and old and old['status']!='unavailable':
            merged={r['date']:r for r in old['history'] if r['date']<=as_of}
            merged.update({r['date']:r for r in current['history']}); current['history']=sorted(merged.values(),key=lambda r:r['date'])[-126:]
            sources={s['sha256']:s for s in [*old['sources'],*current['sources']]}; current['sources']=list(sources.values())
            if key=='flows':
                four=current['history'][-4:]
                current['sum_4w']=sum(r['value'] for r in four) if len(four)==4 and all((date.fromisoformat(b['date'])-date.fromisoformat(a['date'])).days==7 for a,b in zip(four,four[1:])) else None
    if same_check and panels==previous['panels']:
        return {'result':'already_checked','as_of':as_of,'changed':False,'source_status':{k:v['status'] for k,v in panels.items()}}
    payload={'schema_version':SCHEMA,'as_of':as_of,'checked_at':now,'point_in_time_backtest_eligible':False,'panels':panels}
    payload['content_fingerprint']=canonical_fingerprint(payload); validate(payload,as_of)
    immutable(Path(state)/f"{as_of}-{payload['content_fingerprint'].split(':')[-1]}.json",payload)
    for key in ('options','flows'):
        if panels[key]['status']!='unavailable':
            atomic(Path(state)/'last-success'/f'{key}.json',{'panel':panels[key],'fingerprint':canonical_fingerprint(panels[key])})
    changed=atomic(out,payload)
    return {'result':'updated','as_of':as_of,'changed':changed,'source_status':{k:v['status'] for k,v in panels.items()},'content_fingerprint':payload['content_fingerprint']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--as-of',required=True); parser.add_argument('--refresh',action='store_true'); args=parser.parse_args()
    print(json.dumps(run(args.as_of,refresh=args.refresh)))
