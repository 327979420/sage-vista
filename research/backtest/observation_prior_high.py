"""Reuse frozen events and exact prices to study recovery of pre-decline highs."""
import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from research.backtest.run_store import encode, sha256, validate_receipt
from research.backtest.selection_observation import ASOF, observe, target_day
from research.backtest.observation_continuation import SOURCE_HASH, NAMES, table, pct
from services.scanner.cr056_inputs import normalized_comparison_rows
from services.scanner.macd_factor_backtest import completed_groups

VERSION='prior-high-v1'
WINDOWS={'daily':[(f'{n}d',n,'d') for n in (5,10,20,30,40,60)],
 'weekly_completed':[(f'{n}w',n,'w') for n in (5,10,20)],
 'monthly_completed':[(f'{n}m',n,'m') for n in (1,2,3,6,9,12)]}


def prior_high(event, rows):
    tf=event['timeframe'];evidence=event['entry_gate']['evidence'][tf]
    cutoff=evidence.get('completed_through')
    if not cutoff or cutoff>event['signal_date']:return {'status':'invalid_completed_cutoff'}
    history=[r for r in rows if r['date']<=cutoff]
    bars=history if tf=='daily' else [r for _,r in completed_groups(history,'weekly' if tf=='weekly_completed' else 'monthly')]
    highs=[i for i in range(2,len(bars)-2) if bars[i]['high']>max(bars[j]['high'] for j in (i-2,i-1,i+1,i+2))]
    zone=evidence.get('support_zone',{})
    if zone.get('start_source')=='three_push_anchor':
        candidates=[i for i in highs if bars[i]['date']==zone.get('structure_start')]
        method='frozen_declining_trend_first_high'
    else:
        bottoms=zone.get('anchors') or evidence.get('bottoms') or []
        dates=[b['date'] for b in bottoms if b.get('date')]
        if not dates:return {'status':'no_frozen_bottom_anchor'}
        boundary=min(dates)
        candidates=[i for i in highs if bars[i]['date']<boundary]
        method='last_confirmed_high_before_first_bottom'
    if not candidates:return {'status':'no_matching_confirmed_high'}
    i=candidates[-1];price=bars[i]['high']
    current=next((r for r in rows if r['date']==event['signal_date']),None)
    if current is None:return {'status':'missing_signal_price'}
    return {'status':'already_touched_on_signal' if current['high']>=price else 'target_available',
      'price':price,'date':bars[i]['date'],'confirmed_at':bars[i+2]['date'],'method':method,
      'distance':price/event['signal_close']-1}


def evaluate(event, rows, sessions):
    target=prior_high(event,rows)
    output={'episode_id':event['episode_id'],'symbol':event['symbol'],'signal_date':event['signal_date'],
      'timeframe':event['timeframe'],'target':target,'status':target['status']}
    if target['status']!='target_available':return output
    prices={r['date']:r for r in rows};base=event['signal_close'];windows=WINDOWS[event['timeframe']]
    ends={w:target_day(event['signal_date'],n,u,sessions) for w,n,u in windows}
    end=ends[windows[-1][0]]
    if end is None:return {**output,'status':'immature'}
    dates=[d for d in sessions if event['signal_date']<d<=end]
    if not dates or any(d not in prices for d in dates):return {**output,'status':'missing_followup_prices'}
    path=[prices[d] for d in dates];hit=next((i for i,r in enumerate(path) if r['high']>=target['price']),None)
    closehit=next((i for i,r in enumerate(path) if r['close']>=target['price']),None)
    def downside(rs,ref=base):return min([0]+[r['low']/ref-1 for r in rs])
    output.update(status='complete',hit_day=None if hit is None else hit+1,
      hit_date=None if hit is None else dates[hit],close_hit_date=None if closehit is None else dates[closehit],
      downside_before_hit=None if hit is None else downside(path[:hit]),
      downside_including_hit=None if hit is None else downside(path[:hit+1]),
      downside_full=downside(path),windows=[],wait=[])
    for w,n,u in windows:
        day=ends[w]
        output['windows'].append({'window':w,'date':day,'hit':hit is not None and dates[hit]<=day,
          'close_hit':closehit is not None and dates[closehit]<=day})
    for a,b in zip(output['windows'],output['windows'][1:]):
        if a['hit']:continue
        sub=[r for r in path if a['date']<r['date']<=b['date']]
        output['wait'].append({'start':a['window'],'end':b['window'],'hit':b['hit'],
          'downside':downside(sub,prices[a['date']]['close'])})
    return output


def summarize(events,comp):
    groups=[]
    for tf in WINDOWS:
        selected=[e for e in events if comp['classification'][e['episode_id']]['research_label']==tf]
        valid=[e for e in selected if e['status']=='complete'];n=len(valid)
        hits=[e for e in valid if e['hit_day'] is not None];times=sorted(e['hit_day'] for e in hits)
        group={'timeframe':tf,'selected':len(selected),'statuses':dict(Counter(e['status'] for e in selected)),
          'n':n,'symbols':len({e['symbol'] for e in valid}),'hit_n':len(hits),
          'population_median_days':times[(n+1)//2-1] if n and len(times)>=(n+1)//2 else None,
          'hit_only_median_days':median(times) if times else None,
          'hit_downside_before':median(e['downside_before_hit'] for e in hits) if hits else None,
          'hit_downside_including':median(e['downside_including_hit'] for e in hits) if hits else None,
          'nonhit_downside':median(e['downside_full'] for e in valid if e['hit_day'] is None) if n>len(hits) else None,
          'target_distance_median':median(e['target']['distance'] for e in valid) if valid else None,'windows':[],'wait':[],'periods':[]}
        for w,_,_ in WINDOWS[tf]:
            ws=[next(x for x in e['windows'] if x['window']==w) for e in valid]
            group['windows'].append({'window':w,'n':n,'hits':sum(x['hit'] for x in ws),'close_hits':sum(x['close_hit'] for x in ws)})
        for a,b in zip(WINDOWS[tf],WINDOWS[tf][1:]):
            ws=[x for e in valid for x in e['wait'] if x['start']==a[0] and x['end']==b[0]]
            group['wait'].append({'start':a[0],'end':b[0],'n':len(ws),'hits':sum(x['hit'] for x in ws),
              'downside_median':median(x['downside'] for x in ws) if ws else None})
        for a,b in ((2005,2009),(2010,2014),(2015,2019),(2020,2025)):
            sample=[e for e in valid if a<=int(e['signal_date'][:4])<=b]
            group['periods'].append({'period':f'{a}—{b}','n':len(sample),'hits':sum(e['hit_day'] is not None for e in sample)})
        groups.append(group)
    return groups


def render(result):
    parts=['<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>多久能回到下跌前的高点？</title><style>body{font:17px/1.8 system-ui;background:#f2f5f7;color:#192d38;max-width:1050px;margin:auto;padding:24px}section{background:white;border-radius:14px;padding:24px;margin:20px 0}h1{font-size:30px}h2{font-size:24px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:15px}th,td{padding:10px;border-bottom:1px solid #ddd;text-align:right;white-space:nowrap}td:first-child,th:first-child{text-align:left}.note{background:#fff2ce;padding:14px}summary{cursor:pointer;font-weight:bold}small{color:#52616a}</style><h1>多久能回到下跌前的高点？</h1><p>比如从100跌下来，出现门票时是60。我们看它能不能回到原来的100，等多久，途中先跌多少。</p><p>这是原20年候选的补充研究，没有重新选股。“摸到”指当天最高价碰到前高，不代表能按该价格成交。</p>']
    for g in result['comparisons']['10']:
        n=g['n'];tf=g['timeframe'];h=g['hit_n'];med=g['population_median_days']
        parts.append('<section><h2>'+NAMES[tf]+'机会</h2>')
        if not n:parts.append('<p>没有可完整计算的样本，不能给结论。</p></section>');continue
        parts.append(f'<p><b>① 能回去多少？</b>可计算的{n}次中，在{WINDOWS[tf][-1][0]}内，{h}次摸到前高（{h/n:.0%}），{n-h}次没摸到。</p>')
        parts.append('<p><b>② 一般要等多久？</b>'+ (f'等到第{med}个交易日，才累计有一半机会摸到前高。' if med is not None else '观察到最后，仍不到一半摸到；不能说“通常等这么久就能回去”。')+'</p>')
        parts.append(f'<p><b>③ 回去前会先跌多少？</b>在最终摸到的{h}次中，触及前最低跌幅的中位约为{pct(g["hit_downside_before"])}至{pct(g["hit_downside_including"])}（相对门票收盘）。这个范围来自触及当天先涨还是先跌无法确定。</p>')
        parts.append(f'<p>没有摸到的{n-h}次，整个观察期途中最低跌幅中位是{pct(g["nonhit_downside"])}。这是原价下跌，不是账户回撤。</p>')
        parts.append('<h3>每等一段时间，有多少回去了？</h3>'+table(g['windows'],[('等到',lambda r:r['window']),('曾摸到 / 全部',lambda r:f"{r['hits']} / {r['n']}"),('比例',lambda r:f"{r['hits']/r['n']:.0%}"),('收盘也到过',lambda r:f"{r['close_hits']} / {r['n']}")]))
        parts.append('<h3>还没回去的，再等有没有用？</h3><p>每行只看当时还没摸到的机会。下跌从该检查点收盘重新算，观察至下一检查点；即使中间摸到，也继续观察这段下跌。</p>'+table(g['wait'],[('继续等',lambda r:r['start']+' → '+r['end']),('还没到的次数',lambda r:r['n']),('后来摸到的次数',lambda r:r['hits']),('后来摸到比例',lambda r:f"{r['hits']/r['n']:.0%}" if r['n'] else '—'),('期间下跌中位',lambda r:pct(r['downside_median']))]))
        parts.append('<p class="note">怎么用：命中机会增加得少、等待下跌却大时，值得测试缩短等待；不是直接规定卖出。这轮还没有比较买点、止损或资金占用。</p>')
        parts.append('<details><summary>哪些没算进来？结果稳不稳？</summary><p>原明确研究组'+str(g['selected'])+'次，可计算'+str(n)+'次。原因：'+str(g['statuses'])+'。目标在信号当天已摸到的，不混入未来等待。</p><p>前高离信号收盘的距离中位：'+pct(g['target_distance_median'])+'。已摸到者的耗时中位：'+str(g['hit_only_median_days'])+'交易日；这只描述成功者，不能代替全部机会。</p>'+table(g['periods'],[('信号年份',lambda r:r['period']),('次数',lambda r:str(r['n'])+(' · 样本少' if r['n']<30 else '')),('最大窗口内摸到',lambda r:f"{r['hits']}/{r['n']}")]))
        for gap in ('5','15'):
            v=next(x for x in result['comparisons'][gap] if x['timeframe']==tf)
            parts.append(f'<p>领先{gap}分对照：可计算{v["n"]}次，摸到{v["hit_n"]}次；一半样本所需交易日{v["population_median_days"] if v["population_median_days"] is not None else "未达到"}。</p>')
        parts.append('</details></section>')
    parts.append('<section><h2>这次结论的边界</h2><p>日、周、月使用各自结构的下跌前高。机器用冻结下降趋势第一高点，或首底之前最近确认高点来对应；它是可复核的代理，不保证每个案例都等于人眼判断。找不到就单列，不用一年最高价顶替。</p><p>d是交易日，w是周，m是月。少于30次仅作线索。历史年份已经看过；同股重复、行情重叠、股票池幸存者偏差尚存在，比例不是未来保证。等待长短结论需要结合实际入场实验。</p><p>来源35048162507-1，指纹'+SOURCE_HASH+'。计算版本'+VERSION+'。原行情只读复用；逐文件身份核验且原窗口复现。<a href="analysis.json">完整统计和逐事件前高/日期</a></p></section></html>')
    return ''.join(parts)


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',default='research/backtest/output/reusable-runs/35048162507-1/receipt.json');p.add_argument('--cache',default='work/eodhd-cache');p.add_argument('--output',default='work/prior-high-attempt');a=p.parse_args()
    receipt=json.loads(Path(a.source).read_bytes());validate_receipt(receipt)
    if receipt['content_sha256']!=SOURCE_HASH:raise ValueError('wrong_source')
    sources={s['identity']['symbol']:s['identity'] for s in receipt['observation']['sources']}
    cache=Path(a.cache);raw=json.loads((cache/'SPY.json').read_bytes())
    if {s['spy'] for s in sources.values()}!={sha256(encode(raw))}:raise ValueError('spy_identity_mismatch')
    spy={r['date']:r for r in normalized_comparison_rows(raw,as_of=ASOF)};sessions=sorted(spy)
    comp5=next(c for c in receipt['level_study']['comparisons'] if c['minimum_gap']==5)
    groups=defaultdict(list)
    for e in receipt['events']:
        if comp5['classification'][e['episode_id']]['research_label']:groups[e['symbol']].append(e)
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True);checks=Path('work/prior-high-checkpoints');checks.mkdir(parents=True,exist_ok=True)
    code=sha256(Path(__file__).read_bytes());events=[]
    for count,(symbol,items) in enumerate(sorted(groups.items()),1):
        path=cache/(symbol+'.json')
        if not path.exists() or sha256(path.read_bytes())!=sources[symbol]['source']:raise ValueError('original_price_unavailable_or_mismatch:'+symbol)
        identity={'source':SOURCE_HASH,'price':sources[symbol]['source'],'code':code,'commit':os.environ.get('GITHUB_SHA'),'events':[e['episode_id'] for e in items]}
        saved=checks/(symbol+'.json')
        if saved.exists():
            value=json.loads(saved.read_bytes())
            if value.get('identity')!=identity or value.get('hash')!=sha256(encode(value['events'])):raise ValueError('checkpoint_mismatch')
            events.extend(value['events']);continue
        rows=normalized_comparison_rows(json.loads(path.read_bytes()),as_of=ASOF);batch=[]
        for e in items:
            parity=observe(e,rows,spy)
            if parity['signal_close']!=e['signal_close'] or parity['outcomes']!=e['outcomes']:raise ValueError('original_outcome_parity_failed:'+e['episode_id'])
            batch.append(evaluate(e,rows,sessions))
        saved.write_bytes(encode({'identity':identity,'events':batch,'hash':sha256(encode(batch))}));events.extend(batch)
        if count%50==0:print(f'Verified and reused {count}/{len(groups)} stocks',flush=True)
    result={'version':VERSION,'source_hash':SOURCE_HASH,'code':os.environ.get('GITHUB_SHA'),'verified_symbols':len(groups),'events':events,
       'comparisons':{str(c['minimum_gap']):summarize(events,c) for c in receipt['level_study']['comparisons']}}
    (out/'analysis.json').write_bytes(encode(result));(out/'report.html').write_text(render(result))
    (out/'manifest.json').write_bytes(encode({'source':SOURCE_HASH,'script':code,'code':result['code'],'files':{f.name:sha256(f.read_bytes()) for f in (out/'analysis.json',out/'report.html')}}))
    print(json.dumps(result['comparisons']['10'],ensure_ascii=False),flush=True)

if __name__=='__main__':main()
