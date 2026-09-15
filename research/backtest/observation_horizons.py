"""Derived horizon curves; reuse frozen events, prices and observer, never scan."""
import argparse
import copy
import json
import os
from collections import Counter
from pathlib import Path
from statistics import mean, median
from research.backtest import selection_observation as original
from research.backtest.run_store import encode, sha256, seal, trade_csv, validate_receipt
from services.scanner.cr056_inputs import normalized_comparison_rows

VERSION = 'horizon-curves-v1'
PARENT = '34766761296-2'
PARENT_HASH = '213761ec14fb849e0545afef1282c123e60bde318d65da2db256fd152b3f70ee'
PLAN = {**original.WINDOWS, 'daily': [(f'{n}d', n, 'd') for n in (5,10,15,20,30,40,60)]}
EXTRA = ('15d','30d','40d','60d')
ROOT_URL = 'https://raw.githubusercontent.com/327979420/sage-vista/main/research/backtest/output/reusable-runs/'


def verify_parent(parent):
    validate_receipt(parent)
    if parent['id'] != PARENT or parent['content_sha256'] != PARENT_HASH:
        raise ValueError('wrong_frozen_parent')


def outcomes(event):
    return {**event['outcomes'], **event.get('horizon_outcomes', {})}


def supplement(parent, cache, checkpoint=None):
    """A cache miss is explicit; a mismatched cache is never consumed."""
    events=copy.deepcopy(parent['events']); audit=Counter(); cache=Path(cache)
    sources={s['identity']['symbol']:s['identity'] for s in parent['observation']['sources']}
    spy_path=cache/'SPY.json'; spy=None
    if spy_path.exists():
        raw=json.loads(spy_path.read_bytes())
        if {s['spy'] for s in sources.values()} == {sha256(encode(raw))}:
            spy={r['date']:r for r in normalized_comparison_rows(raw,as_of=original.ASOF)}
    grouped={}
    for e in events:
        if e['timeframe']=='daily':grouped.setdefault(e['symbol'],[]).append(e)
    checkpoint=Path(checkpoint) if checkpoint else None
    if checkpoint:checkpoint.mkdir(parents=True,exist_ok=True)
    execution_hash=sha256(Path(__file__).read_bytes()+Path(original.__file__).read_bytes())
    saved_windows=original.WINDOWS
    try:
        original.WINDOWS={**saved_windows, 'extra':[(k,int(k[:-1]),'d') for k in EXTRA]}
        for symbol,items in grouped.items():
            path=cache/(symbol+'.json'); reason=None
            if spy is None:reason='original_spy_unavailable_or_hash_mismatch'
            elif not path.exists():reason='original_prices_unavailable'
            elif sha256(path.read_bytes())!=sources[symbol]['source']:reason='original_price_hash_mismatch'
            if reason:
                for e in items:e['horizon_outcomes']={k:{'status':'unavailable','reason':reason} for k in EXTRA}
                audit[reason]+=len(items);continue
            identity={'parent':PARENT_HASH,'source':sources[symbol],'execution':execution_hash,'events':[e['episode_id'] for e in items]}
            saved=checkpoint/(symbol+'.json') if checkpoint else None
            if saved and saved.exists():
                value=json.loads(saved.read_bytes())
                if value.get('identity')!=identity or value.get('sha256')!=sha256(encode(value.get('outcomes'))):
                    raise ValueError('horizon_checkpoint_identity_or_integrity_failed')
                for e in items:e['horizon_outcomes']=value['outcomes'][e['episode_id']]
                audit['events_exact_parity']+=len(items);audit['matched_daily_symbols']+=1
                audit['resumed_symbols']+=1
                continue
            rows=normalized_comparison_rows(json.loads(path.read_bytes()),as_of=original.ASOF)
            for e in items:
                reproduced=original.observe(e,rows,spy)
                if reproduced['signal_close']!=e['signal_close'] or any(reproduced['outcomes'][k]!=v for k,v in e['outcomes'].items()):
                    raise ValueError('saved_window_parity_failed:'+e['episode_id'])
                e['horizon_outcomes']={k:reproduced['outcomes'][k] for k in EXTRA}
                audit['events_exact_parity']+=1
            audit['matched_daily_symbols']+=1
            if saved:
                additions={e['episode_id']:e['horizon_outcomes'] for e in items}
                temp=saved.with_suffix('.tmp');temp.write_bytes(encode({'identity':identity,'outcomes':additions,'sha256':sha256(encode(additions))}));temp.replace(saved)
            if audit['matched_daily_symbols']%100==0:print(f"Verified {audit['matched_daily_symbols']} daily symbols",flush=True)
    finally:original.WINDOWS=saved_windows
    return events,dict(audit)


def quantile(values, q):
    values=sorted(values); pos=(len(values)-1)*q; lo=int(pos); hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(pos-lo)


def summarize(events):
    result=[]
    for tf,windows in PLAN.items():
        items=[e for e in events if e['timeframe']==tf]
        names=[w[0] for w in windows]
        available=[k for k in names if any(outcomes(e).get(k,{}).get('status')=='complete' for e in items)]
        for cohort,required in [('per_window',[]),('common_available',available),('common_planned',names)]:
            selected=[e for e in items if all(outcomes(e).get(k,{}).get('status')=='complete' for k in required)]
            for k in names:
                full=[e for e in selected if outcomes(e).get(k,{}).get('status')=='complete']
                obs=[outcomes(e)[k] for e in full]
                row={'timeframe':tf,'cohort':cohort,'window':k,'total_events':len(items),'cohort_events':len(selected),'events':len(full),'symbols':len({e['symbol'] for e in full}),'required_windows':required,
                     'statuses':dict(Counter(outcomes(e).get(k,{}).get('status','unavailable') for e in items))}
                for metric in ('return','excess','spy_return'):
                    for label,fn in [('mean',mean),('median',median)]:row[label+'_'+metric]=fn(o[metric] for o in obs) if obs else None
                row.update(win_rate=mean(o['return']>0 for o in obs) if obs else None,
                    median_downside=median(min(0,o['mae']) for o in obs) if obs else None,
                    mean_downside=mean(min(0,o['mae']) for o in obs) if obs else None,
                    p10_return=quantile([o['return'] for o in obs],.1) if obs else None)
                result.append(row)
    return result


def chart(rows, metrics):
    colors=['#2563eb','#0f766e','#c026d3','#dc2626']; width=760; height=260
    values=[r[k]*100 for r in rows for k,_ in metrics if r[k] is not None]+[0]
    low,high=min(values),max(values); pad=max((high-low)*.15,.5);low-=pad;high+=pad
    positions=[int(r['window'][:-1]) for r in rows]
    xs=[65+(n-min(positions))*625/max(1,max(positions)-min(positions)) for n in positions]
    y=lambda v:210-(v-low)/(high-low)*165
    svg=['<svg viewBox="0 0 760 290" role="img" aria-label="各期限收益与相对SPY曲线，圆点为实际窗口，缺失处不连线">']
    for i in range(5):
        v=low+(high-low)*i/4
        svg.append(f'<line x1="65" x2="705" y1="{y(v)}" y2="{y(v)}" stroke="#ddd"/><text x="5" y="{y(v)+4}">{v:.1f}%</text>')
    for x,r in zip(xs,rows):svg.append(f'<text x="{x}" y="235" text-anchor="middle">{r["window"]}</text>')
    for j,(key,label) in enumerate(metrics):
        last=None
        for x,r in zip(xs,rows):
            if r[key] is None:last=None;continue
            yy=y(r[key]*100)
            if last:svg.append(f'<line x1="{last[0]}" y1="{last[1]}" x2="{x}" y2="{yy}" stroke="{colors[j]}" stroke-width="2"/>')
            svg.append(f'<circle cx="{x}" cy="{yy}" r="4" fill="{colors[j]}"><title>{r["window"]}: {r[key]*100:.2f}% · {r["events"]}事件</title></circle>');last=(x,yy)
        svg.append(f'<text x="{65+j*170}" y="275" fill="{colors[j]}">{label}</text>')
    return ''.join(svg)+'</svg>'


def render(receipt):
    h=receipt['horizon_analysis'];p=lambda x:'缺失' if x is None else f'{100*x:.2f}%'
    parts=['<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>分周期收益期限曲线</title><style>body{font:15px system-ui;color:#172033;max-width:1100px;margin:auto;padding:24px;background:#f8fafc}section{background:white;padding:20px;margin:20px 0;border-radius:12px}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:right}svg{width:100%;max-width:850px}small{color:#526070}.scroll{overflow:auto}</style><h1>选股后：多久表现较稳定？</h1>',
       '<p>2005-09-12—2025-09-11候选，观察截至2026-09-11。3115次事件、1223只股票。按当时有门票周期中未加权得分最高者分类，同分月优先。这是算法代理，未按后来收益重贴标签。</p>',
       '<p>从候选收盘起观察，不是确认买点或交易账户收益。图线只连接实际计算的窗口，不表示中间每日走势。日=d交易日，周=w日历周，月=m日历月；周/月到期取当日或随后首个SPY交易日。</p>',
       '<p>典型表现看中位数，同时保留均值和负结果；超额=每个事件与同期限SPY涨跌之差。样本未按股票等权，重复股票与重叠时期不独立；当前股票池有幸存者/覆盖及复权修订限制，已看过的20年仅作探索。</p>',
       f'<p>父收据 <a href="{ROOT_URL+PARENT}/receipt.json">{PARENT}</a> · 执行 {VERSION} · 选股 {receipt["observation"]["policy"]}</p>',
       f'<p>原行情复用核对：{json.dumps(h["cache_audit"],ensure_ascii=False)}。缺失不计零，不推荐事后收益最高的窗口作为卖点。</p>']
    labels={'per_window':'逐窗可用样本','common_available':'已有窗口共同满期样本','common_planned':'全部计划窗口共同满期样本'}
    for tf in PLAN:
        parts.append(f'<section><h2>{original.LABELS[tf]}机会</h2>')
        for cohort,label in labels.items():
            rows=[r for r in h['groups'] if r['timeframe']==tf and r['cohort']==cohort]
            parts.append(f'<h3>{label}</h3><p>共同窗口：{", ".join(rows[0]["required_windows"]) or "各期限独立筛选"}。共同可用事件 {rows[0]["cohort_events"]}。</p>')
            parts.append(chart(rows,[('mean_return','平均涨跌'),('median_return','中位涨跌'),('mean_excess','平均SPY差'),('median_excess','中位SPY差')]))
            parts.append('<div class="scroll"><table><tr><th>期限</th><th>事件/股票</th><th>平均涨跌</th><th>中位涨跌</th><th>平均SPY差*</th><th>中位SPY差*</th><th>上涨比例</th><th>途中下行中位</th><th>途中下行平均</th><th>终点P10</th></tr>')
            for r in rows:
                parts.append('<tr><td>'+r['window']+f'</td><td>{r["events"]}/{r["symbols"]}</td>'+''.join('<td>'+p(r[k])+'</td>' for k in ('mean_return','median_return','mean_excess','median_excess','win_rate','median_downside','mean_downside','p10_return'))+'</tr>')
            parts.append('</table></div>')
        parts.append('<p><small>*SPY差单位为百分点。途中下行=min(0, 窗口最低价/候选收盘−1)，不是账户回撤；P10为终点收益第10百分位。各行缺失数与原因、共同样本定义保存在衍生收据。</small></p></section>')
    parts.append(f'<p>数据版本：父收据content_sha256 {PARENT_HASH}；逐股原行情hash沿父收据保留。执行代码 {receipt["code_commit"]}；选股代码 {h["selection_code"]}。</p></html>')
    return ''.join(parts).encode()


def build(parent,cache,runid,code,checkpoint=None):
    verify_parent(parent);events,audit=supplement(parent,cache,checkpoint)
    receipt={k:copy.deepcopy(v) for k,v in parent.items() if k not in ('content_sha256','downloads','report')}
    receipt.update(id=runid,code_commit=code,events=events)
    receipt['horizon_analysis']={'version':VERSION,'parent_id':PARENT,'parent_content_sha256':PARENT_HASH,'selection_code':parent['code_commit'],'cache_audit':audit,'groups':summarize(events),'planned_windows':{tf:[w[0] for w in ws] for tf,ws in PLAN.items()}}
    report=render(receipt);receipt['report']={'path':runid+'/report.html','sha256':sha256(report)}
    receipt['downloads']={'trades_csv':{'path':runid+'/trades.csv','sha256':sha256(trade_csv(receipt))}}
    return seal(receipt),report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--parent',required=True);parser.add_argument('--cache',default='work/eodhd-cache');parser.add_argument('--output',default='work/horizon-attempt');args=parser.parse_args()
    receipt,report=build(json.loads(Path(args.parent).read_bytes()),args.cache,os.environ['GITHUB_RUN_ID']+'-'+os.environ.get('GITHUB_RUN_ATTEMPT','1'),os.environ['GITHUB_SHA'],'work/horizon-checkpoints')
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    (out/'receipt.json').write_bytes(encode(receipt));(out/'report.html').write_bytes(report);(out/'trades.csv').write_bytes(trade_csv(receipt))
    print(json.dumps(receipt['horizon_analysis']['cache_audit']))
