"""Read existing verified EOD inputs and append immutable Market snapshots.

No downloads, shared-cache writes, candidate/score inputs or trading side effects.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean
import tempfile
from services.contracts.market_data import canonical_fingerprint, require_date
from services.market_data.normalization import adjusted_point_in_time_rows
from services.scanner.audit_eodhd import common
from services.scanner import market_internals as calc

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT/'data/market/config-v1.json'


def read(path):
    return json.loads(Path(path).read_bytes())


def canonical_bytes(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def atomic(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    content=canonical_bytes(value)
    if path.exists() and path.read_bytes()==content: return False
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
        f.write(content); name=f.name
    Path(name).replace(path)
    return True


def immutable(path,value):
    path=Path(path)
    if path.exists():
        if read(path)!=value: raise ValueError('immutable_market_artifact_conflict')
        return False
    return atomic(path,value)


def logic_fingerprint():
    return canonical_fingerprint({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                  (Path(__file__),Path(calc.__file__),ROOT/'services/market_data/normalization.py')})


def prepared(raw, as_of):
    # Limit this read-only consumer to the one-year chart plus 252-day warmup.
    rows=[r for r in raw if r.get('date','')<=as_of][-600:]
    adjusted=adjusted_point_in_time_rows(rows,as_of=as_of)
    raw_by_date={r['date']:r for r in rows}
    return {r['date']:{**r,'raw_close':raw_by_date[r['date']]['close']} for r in adjusted}


def load_inputs(cache_dir, index_path, common_path, etf_dir, as_of, members=None):
    index=read(index_path)
    if index['as_of']!=as_of: raise ValueError('market_cache_index_date_mismatch')
    listed={r['Code'] for r in common(read(common_path))}
    expected={r['symbol']:r['repaired_sha256'] for r in index['repaired']}
    if len(expected)!=len(index['repaired']): raise ValueError('duplicate_market_cache_manifest_symbol')
    stocks, excluded, hashes={}, {}, {}
    for symbol in sorted(members if members is not None else listed & expected.keys()):
        path=Path(cache_dir)/f'{symbol}.json'
        if symbol not in expected or not path.exists():
            excluded[symbol]='missing_verified_history';continue
        content=path.read_bytes(); digest=hashlib.sha256(content).hexdigest()
        if digest!=expected[symbol]:raise ValueError('market_input_hash_mismatch:'+symbol)
        try:
            stocks[symbol]=prepared(json.loads(content),as_of)
            hashes[symbol]=digest
        except (ValueError, TypeError, KeyError):
            excluded[symbol]='invalid_price_history'
    etfs={}
    for symbol in ('SPY','RSP'):
        path=Path(etf_dir)/f'{symbol}.json'
        if path.exists():
            content=path.read_bytes()
            hashes[symbol]=hashlib.sha256(content).hexdigest()
            try: etfs[symbol]=prepared(json.loads(content),as_of)
            except (ValueError,TypeError,KeyError): etfs[symbol]={}
        else: etfs[symbol]={}
    if as_of not in etfs['SPY']: raise ValueError('market_requires_same_day_SPY_calendar')
    sessions=sorted(etfs['SPY'])
    return stocks,etfs,sessions,{'provider':'EODHD','common_list_count':len(listed),
        'common_list_sha256':hashlib.sha256(Path(common_path).read_bytes()).hexdigest(),
        'cache_index_sha256':hashlib.sha256(Path(index_path).read_bytes()).hexdigest(),
        'source_files':hashes,'excluded':excluded}


def freeze_universe(stocks, sessions, as_of, config, source):
    policy=config['universe_policy'];members=[]; end=sessions.index(as_of)
    for ticker,series in sorted(stocks.items()):
        w=calc.window(series,sessions,end,21)
        if w and w[-1]['raw_close']>=policy['minimum_price'] and mean(r['raw_close']*r['volume'] for r in w[:-1])>=policy['minimum_average_dollar_volume']:
            members.append(ticker)
    if not members:raise ValueError('no_market_universe_members')
    result={'name':'缓存普通股固定样本','scope':policy['scope'],'members':members,
            'observed_at':as_of,'policy':policy,'common_list_count':source['common_list_count'],
            'membership_source':source['common_list_sha256'],
            'limitation':'来自现有扫描行情覆盖，不是全美股或历史指数成分；成员固定，不按候选和评分筛选。'}
    result['id']=canonical_fingerprint(result)
    return result


def validate_public(payload, expected=None):
    if payload['schema_version']!='market-internals-public-v1': raise ValueError('market_schema_mismatch')
    if expected and payload['as_of']!=expected:raise ValueError('market_public_date_mismatch')
    config=payload['config']; universe=payload['universe']; rows=payload['history']
    calc.validate_config(config)
    if canonical_fingerprint({k:v for k,v in universe.items() if k!='id'})!=universe['id']:raise ValueError('market_universe_hash_mismatch')
    if not rows or rows[-1]['date']!=payload['as_of']:raise ValueError('market_latest_missing')
    dates=[r['date'] for r in rows]
    if dates!=sorted(set(dates)):raise ValueError('market_history_order')
    for r in rows:
        require_date(r['date'],'market_snapshot_date')
        if r['fingerprint']!=canonical_fingerprint({k:v for k,v in r.items() if k!='fingerprint'}):raise ValueError('market_snapshot_hash_mismatch')
        if r['config_fingerprint']!=canonical_fingerprint(config) or r['universe_id']!=universe['id'] or r['identity']['logic_fingerprint']!=payload['logic_fingerprint']:
            raise ValueError('market_series_identity_mismatch')
        quality=r['quality']; score=r['temperature']['score']
        if quality['valid_ticker_count']+quality['missing_ticker_count']!=len(universe['members']):raise ValueError('market_coverage_count_mismatch')
        if score is not None:
            if quality['status']!='complete' or quality['coverage']<config['quality']['minimum_coverage'] or len(universe['members'])<config['quality']['minimum_members']:
                raise ValueError('market_incomplete_score')
            expected_score=round(sum(s['score']*config['subscores'][k]['weight'] for k,s in r['temperature']['subscores'].items()),1)
            if score!=expected_score or not 0<=score<=100:raise ValueError('market_score_mismatch')
            if r['temperature']['status']!=calc.band(score,config['temperature_bands']):raise ValueError('market_status_mismatch')
        elif r['temperature']['status']['tone']!='neutral':raise ValueError('market_missing_score_has_color')
    fingerprint=canonical_fingerprint({k:v for k,v in payload.items() if k!='content_fingerprint'})
    if payload.get('content_fingerprint')!=fingerprint:raise ValueError('market_public_hash_mismatch')
    return payload


def run(*, cache_dir, index_path, common_path, etf_dir, as_of, state_dir, out, config_path=CONFIG_PATH, bootstrap_sessions=126):
    require_date(as_of,'as_of'); config=read(config_path); calc.validate_config(config); logic=logic_fingerprint()
    if bootstrap_sessions<1 or bootstrap_sessions>126:raise ValueError('market_bootstrap_budget_exceeded')
    state=Path(state_dir)/config['series_id']; manifest_path=state/'manifest.json'
    expected={'calculation_version':calc.CALCULATION_VERSION,'config_fingerprint':canonical_fingerprint(config),'logic_fingerprint':logic}
    manifest=read(manifest_path) if manifest_path.exists() else None
    if manifest and any(manifest[k]!=v for k,v in expected.items()): raise ValueError('market_version_changed_start_new_series')
    universe=read(state/'universe.json') if manifest else None
    prior=[read(p) for p in sorted((state/'snapshots').glob('*.json'))] if manifest else []
    # Replays never re-price or overwrite a saved observation.
    current=next((p for p in prior if p['date']==as_of),None)
    if prior and as_of<prior[-1]['date']:raise ValueError('market_cannot_rewind_saved_series')
    if not current:
        stocks,etfs,sessions,source=load_inputs(cache_dir,index_path,common_path,etf_dir,as_of,universe['members'] if universe else None)
        if not universe:universe=freeze_universe(stocks,sessions,as_of,config,source)
        days=[d for d in sessions if d>prior[-1]['date']] if prior else sessions[-bootstrap_sessions:]
        if prior and days!=[as_of]:raise ValueError('market_missing_daily_snapshots_explicit_recovery_required')
        # Chain only the day's already-completed observations, never future bars.
        chain='market-price-prefix-v1'; price_versions={}
        for day in sessions:
            bars={s:rows[day] for s,rows in {**stocks,**etfs}.items() if day in rows}
            chain=canonical_fingerprint({'previous':chain,'date':day,'bars':bars})
            if day in days:price_versions[day]=chain
        generated=[]
        recorded_at=datetime.now(timezone.utc).isoformat()
        for day in days:
            raw=calc.facts(stocks,etfs,sessions,day,universe['members'])
            item=calc.snapshot(raw,day=day,sessions=sessions,universe=universe,config=config,prior=prior+generated,
                identity={'price_version':price_versions[day],'logic_fingerprint':logic,'provider':'EODHD',
                          'source_manifest_fingerprint':canonical_fingerprint(source)},
                observation_kind='observed_eod' if day==as_of else 'reconstructed_current_membership')
            item['recorded_at']=recorded_at
            item['fingerprint']=canonical_fingerprint({k:v for k,v in item.items() if k!='fingerprint'})
            generated.append(item)
        manifest=manifest or {**expected,'series_id':config['series_id'],'initialized_at':as_of,
                  'historical_membership':'current_membership_reconstruction','universe_id':universe['id']}
        # Validate all new observations before writing any official snapshot.
        candidate=make_public(prior+generated,universe,config,logic,as_of)
        validate_public(candidate,as_of)
        immutable(manifest_path,manifest);immutable(state/'universe.json',universe)
        for item in generated:immutable(state/'snapshots'/f"{item['date']}.json",item)
        immutable(state/'sources'/f'{as_of}.json',source)
        prior+=generated
    payload=make_public(prior,universe,config,logic,as_of)
    validate_public(payload,as_of)
    changed=atomic(out,payload)
    return {'result':'updated' if changed else 'already_current','changed':changed,'as_of':as_of,
            'quality':prior[-1]['quality'],'temperature':prior[-1]['temperature']['score'],
            'history_sessions':len(prior),'content_fingerprint':payload['content_fingerprint']}


def make_public(prior,universe,config,logic,as_of):
    # Last year is a small public projection; every daily source snapshot is kept in Git.
    payload={'schema_version':'market-internals-public-v1','as_of':as_of,'config':config,
             'universe':universe,'logic_fingerprint':logic,'history':prior[-252:]}
    payload['content_fingerprint']=canonical_fingerprint(payload)
    return payload


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--as-of',required=True);p.add_argument('--cache-dir',default='work/cr056-daily/cache/eodhd-cache')
    p.add_argument('--index-path',default='work/cr056-daily/cache/index.json')
    p.add_argument('--common-path',default='work/eodhd-active-common.json')
    p.add_argument('--etf-dir',default='work/eodhd-cache');p.add_argument('--state-dir',default='data/market')
    p.add_argument('--out',default='public/market-internals.json');p.add_argument('--bootstrap-sessions',type=int,default=126)
    print(json.dumps(run(**vars(p.parse_args())),ensure_ascii=False))


if __name__=='__main__':main()
