"""Bounded legacy engineering comparison, never a signal or exit producer.

VectorBT consumes frozen fills. Optional cache replay calls the existing legacy
execution function; neither leg independently validates that execution policy.
Only compact derived facts leave this module; raw OHLC is never exported.
"""
import argparse
from collections import Counter
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / 'research/backtest/vectorbt-order-input-v1.json'
POLICY = 'support-5pct-cap-10pct-2r-v1'
EXPECTED_INPUT_SHA256 = '72fa4eb9699a8042ae4d1a2d301e52cf12f08289810364e9c0fb7c4467cb1d95'
CACHE_KEYS = ('eodhd-history-v1-33293559230', 'eodhd-history-v1-34184997473')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def check(field, expected, actual, places=None, origin='frozen_evidence'):
    delta = None
    match = expected == actual
    if isinstance(expected, (int, float)) and not isinstance(expected, bool) and isinstance(actual, (int, float)):
        delta = float(Decimal(str(actual))-Decimal(str(expected)))
        if places is not None:
            quantum = Decimal(1).scaleb(-places)
            match = Decimal(str(actual)).quantize(quantum, rounding=ROUND_HALF_EVEN) == Decimal(str(expected)).quantize(quantum, rounding=ROUND_HALF_EVEN)
    return {'field': field, 'expected': expected, 'actual': actual, 'delta': delta,
            'source_decimal_places': places, 'status': 'match' if match else 'difference', 'origin': origin}


def frozen_input(path=INPUT):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_INPUT_SHA256:raise ValueError('frozen_input_fingerprint_mismatch')
    data = json.loads(raw)
    events = data['events']
    if data['selection']['count'] != 20 or len(events) != 20 or data['selection']['sort_keys'] != ['signal_date', 'event_id']:
        raise ValueError('fixed_sample_contract_mismatch')
    if data['assumptions'] != {'quantity_per_trade':1,'fees':0,'slippage':0,'actual_quantity_available':False,'actual_fees_available':False,'capital_allocation':'independent_unit_trade_not_portfolio'}:
        raise ValueError('comparison_assumptions_changed')
    if len({x['event_id'] for x in events}) != 20 or events != sorted(events,key=lambda x:(x['signal_date'],x['event_id'])):
        raise ValueError('fixed_sample_order_or_duplicate')
    if any(x['policy_version'] != POLICY for x in events): raise ValueError('unsupported_execution_policy')
    return data, hashlib.sha256(raw).hexdigest()


def vectorbt_orders(event, vbt, pd):
    base = event.get('baseline') or {}
    required = (event.get('entry_date'), event.get('entry_price'), base.get('exit_date'), base.get('exit_price'), base.get('stop'), base.get('return'))
    if base.get('status') != 'resolved' or any(x is None for x in required):
        return {'status':'unavailable','reason':'closed_frozen_fill_fields_missing','checks':[]}
    entry, exit_price = float(event['entry_price']), float(base['exit_price'])
    if not 0 < base['stop'] < entry or not event['signal_date'] < event['entry_date'] <= base['exit_date']:
        return {'status':'unavailable','reason':'invalid_frozen_dates_or_risk','checks':[]}
    # Two ordered fill slots, not invented intraday timestamps or an OHLC path.
    pf = vbt.Portfolio.from_orders(pd.Series([entry, exit_price]), size=[1., -1.],
         price=[entry, exit_price], fees=0., fixed_fees=0., slippage=0., init_cash=entry*2,
         allow_partial=False, raise_reject=True)
    trades = pf.trades.records.to_dict('records'); orders = pf.orders.records.to_dict('records')
    if len(trades) != 1 or len(orders) != 2:
        return {'status':'difference','reason':'unexpected_trade_or_order_count','checks':[]}
    t = trades[0]; risk = entry-float(base['stop'])
    checks = [check('entry_price',entry,t['entry_price'],6),check('exit_price',exit_price,t['exit_price'],6),
              check('entry_slot',0,t['entry_idx']),check('exit_slot',1,t['exit_idx']),check('closed_status',1,t['status']),
              check('quantity',1.,t['size'],origin='unit_trade_assumption'),
              check('entry_order_side',0,orders[0]['side']),check('exit_order_side',1,orders[1]['side']),
              check('gross_return',base['return'],t['return'],8),
              check('fees',0.,t['entry_fees']+t['exit_fees'],origin='zero_cost_assumption'),
              check('net_return_zero_cost_scenario',base['return'],t['return'],8,origin='zero_cost_assumption'),
              check('unit_pnl',exit_price-entry,t['pnl'],6,origin='derived_from_frozen_fills'),
              check('r_multiple',base['r_multiple'],t['pnl']/risk,6,origin='sage_derived_using_frozen_risk_not_vectorbt_metric')]
    return {'status':'match' if all(c['status']=='match' for c in checks) else 'difference',
            'checks':checks,'engine_trade':t,'engine_orders':orders,'actual_fees':None,'actual_quantity':None,
            'actual_net_return':None,'mfe':None,'mae':None,'path_validation':'not_performed_by_vectorbt'}


def cache_replay(event, cache_dir):
    if cache_dir is None:return {'status':'unavailable','reason':'cache_not_restored_locally','checks':[]}
    from services.scanner.cr056_inputs import normalized_comparison_rows
    from services.scanner.support_risk import simulate_execution
    path=Path(cache_dir)/(event['symbol']+'.json'); calendar=Path(cache_dir)/'SPY.json'
    if not path.exists() or not calendar.exists():return {'status':'unavailable','reason':'symbol_or_reference_calendar_missing','checks':[]}
    try:
        raw_bytes=path.read_bytes(); raw=json.loads(raw_bytes)
        raw_window=[r for r in raw if event['signal_date'] <= r['date'] <= '2026-09-04']
        rows=normalized_comparison_rows(raw_window,as_of='2026-09-04')
        if not rows or rows[0]['date'] != event['signal_date']:raise ValueError('signal_bar_missing')
        future=rows[1:41]
        if not future:raise ValueError('entry_bar_missing')
        base=event['baseline']; end=base['exit_date']
        expected=[r['date'] for r in json.loads(calendar.read_text()) if event['signal_date']<r['date']<=end]
        actual=[r['date'] for r in future if r['date']<=end]
        if not expected or actual!=expected:raise ValueError('exit_path_sessions_missing_or_misaligned')
        support={'level':base['support_level'],'source':base['support_source']}
        replay=simulate_execution(future[0]['open'],support,future)
        fields=('entry','stop','target','exit_price','exit_date','exit_reason','holding_sessions','return','r_multiple','status')
        checks=[check('entry_date',event['entry_date'],future[0]['date'])]
        for field in fields:
            places=8 if field=='return' else 6 if field in ('entry','stop','target','exit_price','r_multiple') else None
            checks.append(check(field,base.get(field),replay.get(field),places))
        used=[r for r in raw_window if r['date']<=future[-1]['date']]
        ratios=[{'date':r['date'],'ratio':r['adjusted_close']/r['close']} for r in used]
        return {'status':'match' if all(c['status']=='match' for c in checks) else 'difference','checks':checks,
                'source_file_sha256':hashlib.sha256(raw_bytes).hexdigest(),'window_sha256':digest(used),
                'adjustment_fingerprint':digest(ratios),'signal_adjustment_ratio':ratios[0]['ratio'],
                'window_start':rows[0]['date'],'window_end':future[-1]['date'],'path_sessions':len(future),
                'source_first_date':raw[0]['date'],'source_last_date':raw[-1]['date'],
                'replay':replay,'historical_revision_proven':False,
                'note':'Saved fills lack original raw-source fingerprint; matching fills cannot prove identical historical revision.'}
    except (ValueError,KeyError,TypeError,ZeroDivisionError) as exc:
        return {'status':'unavailable','reason':str(exc),'checks':[]}


def run(input_path=INPUT, cache_dir=None, cache_key=None):
    data,input_hash=frozen_input(input_path)
    if cache_dir is not None and cache_key not in CACHE_KEYS:raise ValueError('unapproved_cache_key')
    import vectorbt as vbt
    import pandas as pd
    if vbt.__version__!='1.1.0':raise ValueError('unapproved_vectorbt_version')
    results=[]
    for event in data['events']:
        try:accounting=vectorbt_orders(event,vbt,pd)
        except Exception as exc:accounting={'status':'unavailable','reason':type(exc).__name__,'checks':[]}
        results.append({**event,'accounting':accounting,'cache_replay':cache_replay(event,cache_dir)})
    report={'schema_version':'1.0.0','result_role':'comparison','data_path':'legacy','scope':'frozen_order_accounting_and_optional_old_policy_replay',
            'source':data['source'],'input_sha256':input_hash,'selection':data['selection'],'assumptions':data['assumptions'],
            'engine':{'name':'vectorbt','version':vbt.__version__,'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            'cache_key':cache_key,'events':results,
            'summary':{name:dict(Counter(r[name]['status'] for r in results)) for name in ('accounting','cache_replay')},
            'sample_audit':{'frozen_status_counts':dict(Counter((e.get('baseline') or {}).get('status','missing') for e in data['events'])),
                            'omitted_after_selection':0,'source_fields_unavailable':sum(r['accounting']['status']=='unavailable' for r in results)},
            'limitations':['engineering_comparison_not_strategy_validation','frozen_exits_not_independently_decided_by_vectorbt',
                           'actual_quantity_fees_net_return_unavailable','r_is_sage_derived_from_frozen_risk',
                           'mfe_mae_unavailable','original_raw_revision_not_proven','zero_cost_is_only_an_assumption']}
    report['content_fingerprint']='sha256:'+digest(report)
    return report


def bundle_reports(paths):
    reports=[]
    for path in paths:
        report=json.loads(Path(path).read_bytes())
        fingerprint=report.pop('content_fingerprint',None)
        if fingerprint!='sha256:'+digest(report) or report.get('input_sha256')!=EXPECTED_INPUT_SHA256:
            raise ValueError('comparison_report_fingerprint_mismatch')
        report['content_fingerprint']=fingerprint;reports.append(report)
    if not reports:raise ValueError('comparison_reports_missing')
    return {'schema_version':'1.0.0','reports':reports,'scope':'engineering_comparison_not_full_backtest'}


def save(report,out):
    path=Path(out).resolve()
    if ROOT/'public' in path.parents:raise ValueError('engine_cannot_write_public_assets')
    raw=(json.dumps(report,indent=2,allow_nan=False)+'\n').encode()
    if path.exists() and path.read_bytes()!=raw:raise FileExistsError('comparison_output_is_immutable')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',nargs='+');parser.add_argument('--input',default=str(INPUT));parser.add_argument('--cache-dir');parser.add_argument('--cache-key');parser.add_argument('--out',required=True)
    args=parser.parse_args();result=bundle_reports(args.bundle) if args.bundle else run(args.input,args.cache_dir,args.cache_key);save(result,args.out)
    print(json.dumps({'summary':result.get('summary'),'fingerprint':result.get('content_fingerprint'),'report_count':len(result.get('reports',[]))}))
