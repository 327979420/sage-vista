"""Freeze the existing 19-file price world and rebuild only ELV dependencies."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from research.backtest.price_identity import freeze_manifest, bind, digest, require_consistent_baseline
from research.backtest.run_store import encode, sha256, validate_receipt
from services.scanner.cr056_inputs import normalized_comparison_rows
from research.backtest.account_runner import account

ROOT = Path(__file__).resolve().parents[2]
LEGACY = '8532d13a8bf7bcb0fc9a6b7bd60b3ccacce0c160'


def main():
    cache = ROOT / 'work/eodhd-cache'
    out = ROOT / 'work/elv-alignment'; out.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((ROOT / 'research/backtest/output/reusable-runs/34240123213-1/receipt.json').read_bytes())
    validate_receipt(receipt)
    audit = json.loads((ROOT / 'research/backtest/output/price-comparison/35067648499-1/price-world-audit.json').read_bytes())
    expected = {r['symbol']: r['current_source_hash'] for r in audit['records']}
    symbols = sorted(set(expected) | {'SPY'})
    frozen = out / 'prices'; frozen.mkdir(exist_ok=True)
    files = {}; raw = {}; normalized = {}
    for symbol in symbols:
        content = (cache / (symbol + '.json')).read_bytes()
        if symbol in expected and sha256(content) != expected[symbol]:
            raise ValueError('not_the_audited_price_vintage:' + symbol)
        values = json.loads(content)
        rows = normalized_comparison_rows(values, as_of=values[-1]['date'])
        files[symbol] = {'raw_sha256': sha256(content), 'normalized_sha256': digest(rows),
                         'first': rows[0]['date'], 'last': rows[-1]['date'], 'rows': len(rows)}
        target = frozen / (symbol + '.json')
        if target.exists() and target.read_bytes() != content: raise ValueError('immutable_price_conflict')
        target.write_bytes(content)
        raw[symbol] = values; normalized[symbol] = rows
    manifest = freeze_manifest(files, source={'cache_key': 'observation-history-v1-34766761296-1',
        'account_run': '35064720576-1', 'audit_run': '35067648499-1',
        'scope': '18_account_symbols_plus_SPY', 'historical_as_published_vintage_proven': False})
    (out / 'price-manifest.json').write_bytes(encode(manifest))
    legacy = ROOT / 'work/elv-legacy-code'; legacy.mkdir(parents=True, exist_ok=True)
    archive = subprocess.check_output(['git', 'archive', LEGACY, 'services', 'research'])
    subprocess.run(['tar', '-x', '-C', str(legacy)], input=archive, check=True)
    env = {**os.environ, 'PYTHONPATH': str(legacy)}
    subprocess.run([sys.executable, str(ROOT/'research/backtest/elv_legacy_probe.py'), str(frozen), str(out)], cwd=legacy, env=env, check=True)
    probe = json.loads((out/'legacy-elv-probe.json').read_bytes())
    old_elv = next(t for t in receipt['trades'] if t['symbol'] == 'ELV')
    old_selection = old_elv['signal_snapshot']['selection']
    if probe['fingerprint'] != old_selection['policy_fingerprint']: raise ValueError('legacy_policy_mismatch')
    eligible = [r for r in probe['days'] if r['new_nomination']]
    selected = eligible[0] if eligible else None
    on_original = next(r for r in probe['days'] if r['as_of'] == old_elv['signal_date'])
    events = [{'event_id': t['event_id'], 'symbol': t['symbol'], 'signal_date': t['signal_date'],
               'selection': copy.deepcopy(t['signal_snapshot']['selection'])} for t in receipt['trades']]
    regenerated = [copy.deepcopy(e) for e in events if e['symbol'] != 'ELV']
    new_selection = None
    if selected:
        score = selected['score']
        new_selection = {**old_selection, 'technical_score': score['total_score'],
            'score_fingerprint': score['score_fingerprint'], 'reasons': selected['reason_codes'],
            'timeframe_scores': {k: 100*v['normalized'] for k,v in score['timeframes'].items()},
            'support_plan': selected['support_plan']}
        regenerated.append({'event_id': 'CR056-ELV-'+selected['as_of'], 'symbol': 'ELV', 'signal_date': selected['as_of'], 'selection': new_selection})
    touched = {old_elv['signal_date']} | ({selected['as_of']} if selected else set())
    for day in touched:
        peers = sorted([e for e in regenerated if e['signal_date'] == day], key=lambda e: (
            -e['selection']['technical_score'], -e['selection']['timeframe_scores']['monthly_completed'],
            -e['selection']['timeframe_scores']['weekly_completed'], 'legacy-observed:'+e['symbol']))
        for rank, event in enumerate(peers, 1): event['selection']['rank'] = rank
    start, end = receipt['request']['start'], receipt['request']['end']
    rows = {s: [r for r in values if start <= r['date'] <= end] for s,values in normalized.items() if s != 'SPY'}
    sessions = [r['date'] for r in normalized['SPY'] if start <= r['date'] <= end]
    if sha256(encode(sessions)) != receipt['source']['reference_sessions_sha256']: raise ValueError('calendar_changed')
    mixed = account(events, rows, sessions, receipt['scenario'], with_ledger=True)
    rebuilt = account(regenerated, rows, sessions, receipt['scenario'], with_ledger=True)
    contract = {'manifest': manifest,
        'signal': bind(regenerated, manifest, symbols=list(rows), verified=False),
        'support': bind({e['symbol']: e['selection']['support_plan'] for e in regenerated}, manifest, symbols=list(rows), verified=False),
        'account': bind(rebuilt[3], manifest, symbols=list(rows), verified=True)}
    # Retained old signals do not acquire verified provenance merely by attaching today's ID.
    contract['signal']['unverified_symbols'] = sorted(set(rows)-{'ELV'})
    contract['support']['unverified_symbols'] = sorted(set(rows)-{'ELV'})
    try:
        require_consistent_baseline(contract)
    except ValueError as exc:
        blocked = str(exc)
    else:
        raise AssertionError('retained_unknown_provenance_must_block_baseline')
    (out/'price-consistency.json').write_bytes(encode(contract))
    (out/'elv-signal.json').write_bytes(encode(bind({'days':probe['days'], 'selected':new_selection}, manifest, symbols=['ELV'], verified=True)))
    (out/'elv-support.json').write_bytes(encode(bind(selected['support_plan'] if selected else None, manifest, symbols=['ELV'], verified=True)))
    (out/'regenerated-account.json').write_bytes(encode({'baseline_eligible':False,'blocked_reason':blocked,'price_version':manifest['price_version'],'trades':rebuilt[2],'book':rebuilt[3]}))
    trades = {t['symbol']: t for t in rebuilt[2]}; before = {t['symbol']: t for t in mixed[2]}
    fields = ('status','quantity','entry_price','net_pnl','entry_fees','exit_fees','execution','reason')
    comparisons=[]
    for symbol in sorted(rows):
        a={k:before[symbol].get(k) for k in fields}; b={k:trades.get(symbol,{}).get(k) for k in fields}
        comparisons.append({'ticker':symbol, 'price_difference':sha256(encode([r for r in raw[symbol] if start<=r['date']<=end])) != receipt['source']['windows_sha256'][symbol],
            'signal_affected': (selected is None or selected['as_of'] != old_elv['signal_date'] or new_selection['technical_score'] != old_selection['technical_score']) if symbol=='ELV' else 'retained_not_revalidated',
            'support_affected':selected['support_plan'] != old_selection['support_plan'] if symbol=='ELV' and selected else ('not_eligible' if symbol=='ELV' else 'previous_audit_equal'),
            'prior_high_affected':'not_used_by_this_account','trade_affected':a!=b,'pnl_impact':(b.get('net_pnl') or 0)-(a.get('net_pnl') or 0),'before':a,'after':b,'decision':'diagnostic_only'})
    summary={'price_version':manifest['price_version'],'legacy_code':LEGACY,'baseline_eligible':False,'blocked_reason':blocked,
        'old_signal_date':old_elv['signal_date'],'new_signal_date':selected['as_of'] if selected else None,
        'eligibility_on_old_date':on_original['new_nomination'], 'old_selection':old_selection,'new_selection':new_selection,
        'rank_scope':'frozen_same_day_cohort_only; other_tickers_not_rescanned',
        'mixed_final_equity':float(mixed[0].iloc[-1]),'regenerated_final_equity':float(rebuilt[0].iloc[-1]),'comparison':comparisons,
        'limits':['17 retained historical signals lack proven full-history input identities; unchanged account windows alone do not prove signal provenance.', 'No reconstruction of the missing original provider vintage.', 'Prior-high is not consumed by this account.']}
    (out/'comparison.json').write_bytes(encode(summary))
    lines=['# ELV 行情版本修复核验','',f"冻结版本：`{manifest['price_version']}`",'',
        '| Ticker | Price difference | Signal affected | Support affected | Prior-high affected | Trade affected | P&L impact | Decision |','|---|---|---|---|---|---|---|---|']
    for r in comparisons:
        lines.append('| '+' | '.join(str(r[k]) for k in ('ticker','price_difference','signal_affected','support_affected','prior_high_affected','trade_affected','pnl_impact','decision'))+' |')
    lines += ['',f"ELV资格：{on_original['new_nomination']}；原日期 {old_elv['signal_date']}，重算首次日期 {summary['new_signal_date']}。",f"分数：{old_selection['technical_score']} → {new_selection['technical_score'] if new_selection else None}；原候选内排名：{old_selection['rank']} → {new_selection['rank'] if new_selection else None}。",f"账户期末：混合版本 {summary['mixed_final_equity']:.2f} → 修复诊断 {summary['regenerated_final_equity']:.2f}。",'', '尚不能称正式基准：另17只旧信号缺少完整历史行情版本证明。本次仅重算ELV，没有将旧结果伪装成已重验。']
    (out/'comparison.md').write_text('\n'.join(lines)+'\n')
    shutil.rmtree(out/'stage')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('comparison','old_selection','new_selection')},ensure_ascii=False))

if __name__ == '__main__': main()
