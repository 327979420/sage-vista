"""Descriptive continuation study using frozen observation windows only."""
import argparse
import hashlib
import html
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from research.backtest.observation_horizons import outcomes, quantile
from research.backtest.run_store import validate_receipt

SOURCE_HASH = '6d86df8d0cde21b1b5680facca1c7dce004870b0e8393729f0198e39ba9e25af'
PAIRS = {'daily': [('20d', '30d'), ('20d', '40d'), ('20d', '60d')],
         'weekly_completed': [('5w', '10w'), ('5w', '20w')],
         'monthly_completed': [('3m', '6m'), ('3m', '9m'), ('3m', '12m'), ('6m', '12m')]}
NAMES = {'daily': '日线', 'weekly_completed': '周线', 'monthly_completed': '月线'}
STATES = ('全部', '下跌', '横盘', '上涨')


def state(value):
    return '下跌' if value < -.05 else '上涨' if value > .05 else '横盘'


def paired(event, start, end):
    data = outcomes(event)
    a, b = data.get(start, {}), data.get(end, {})
    if a.get('status') != 'complete' or b.get('status') != 'complete':
        return None
    if a['return'] <= -1 or a['spy_return'] <= -1:
        return None
    ret = (1 + b['return']) / (1 + a['return']) - 1
    spy = (1 + b['spy_return']) / (1 + a['spy_return']) - 1
    return {'episode_id': event['episode_id'], 'symbol': event['symbol'],
            'signal_date': event['signal_date'], 'start': start, 'end': end,
            'checkpoint_return': a['return'], 'state': state(a['return']),
            'return': ret, 'excess': ret - spy,
            'checkpoint_date': a['target_date'], 'end_date': b['target_date']}


def interval(rows, grouping):
    """Descriptive sensitivity bounds; no claim of joint dependency correction."""
    groups = defaultdict(list)
    for row in rows:
        key = row['symbol'] if grouping == 'symbol' else (int(row['signal_date'][:4]) - 2005) // 2
        groups[key].append(row['excess'])
    if len(groups) < 4:
        return None
    blocks = list(groups.values())
    rng = random.Random(20260916)
    draws = [median([v for block in rng.choices(blocks, k=len(blocks)) for v in block]) for _ in range(1000)]
    return {'low': quantile(draws, .025), 'high': quantile(draws, .975), 'clusters': len(blocks)}


def stats(rows, uncertainty=False):
    if not rows:
        return {'n': 0, 'symbols': 0}
    returns = [r['return'] for r in rows]
    result = {'n': len(rows), 'symbols': len({r['symbol'] for r in rows}),
              'mean': mean(returns), 'median': median(returns),
              'median_excess': median(r['excess'] for r in rows),
              'positive': mean(v > 0 for v in returns), 'p10': quantile(returns, .1)}
    if uncertainty:
        result.update(time_interval=interval(rows, 'time'), symbol_interval=interval(rows, 'symbol'))
    return result


def study(receipt):
    validate_receipt(receipt)
    if receipt['content_sha256'] != SOURCE_HASH or receipt['id'] != '35048162507-1':
        raise ValueError('wrong_frozen_source')
    result = {'source_id': receipt['id'], 'source_hash': SOURCE_HASH,
              'version': 'continuation-descriptive-v1', 'rows': [], 'details': [], 'targets': [], 'concentration': []}
    for comp in receipt['level_study']['comparisons']:
        gap = comp['minimum_gap']
        for tf, pairs in PAIRS.items():
            events = [e for e in receipt['events'] if comp['classification'][e['episode_id']]['research_label'] == tf]
            for start, end in pairs:
                rows = [p for e in events if (p := paired(e, start, end)) is not None]
                for status in STATES:
                    sample = rows if status == '全部' else [r for r in rows if r['state'] == status]
                    result['rows'].append({'gap': gap, 'timeframe': tf, 'start': start, 'end': end,
                                           'state': status, 'missing': len(events) - len(rows),
                                           **stats(sample, gap == 10),
                                           'periods': [{'period': f'{a}—{b}', **stats([r for r in sample if a <= int(r['signal_date'][:4]) <= b])}
                                                       for a, b in ((2005, 2009), (2010, 2014), (2015, 2019), (2020, 2025))]})
                if gap == 10:
                    result['details'].extend({'timeframe': tf, **r} for r in rows)
            if gap != 10:
                continue
            windows = list(dict.fromkeys(w for pair in pairs for w in pair))
            for window in windows:
                available = [outcomes(e)[window] for e in events if outcomes(e).get(window, {}).get('status') == 'complete']
                hits = [o['days_to_10pct'] for o in available if o['days_to_10pct'] is not None]
                result['targets'].append({'timeframe': tf, 'window': window, 'n': len(available),
                    'missing': len(events)-len(available), 'hits': len(hits), 'not_hit': len(available)-len(hits),
                    'hit_rate': len(hits)/len(available) if available else None,
                    'hit_days_median': median(hits) if hits else None,
                    'cumulative_downside_median': median(min(0, o['mae']) for o in available) if available else None})
                ordered = sorted(o['return'] for o in available)
                result['concentration'].append({'timeframe': tf, 'window': window, 'n': len(ordered),
                    'mean': mean(ordered) if ordered else None, 'median': median(ordered) if ordered else None,
                    'mean_without_top5': mean(ordered[:-5]) if len(ordered)>5 else None})
    return result


def pct(v):
    return '—' if v is None else f'{v*100:+.2f}%'


def table(rows, columns):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(label)+'</th>' for label, _ in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(fn(r)))+'</td>' for _, fn in columns)+'</tr>' for r in rows)+'</tbody></table></div>'


def render(s):
    cols = [('多拿多久', lambda r:r['start']+' → '+r['end']), ('次数 / 股票', lambda r:f"{r['n']} / {r['symbols']}"),
            ('平均涨跌', lambda r:pct(r.get('mean'))), ('中位涨跌', lambda r:pct(r.get('median'))), ('比大盘多赚', lambda r:pct(r.get('median_excess')).replace('%','个百分点')),
            ('赚钱比例', lambda r:f"{r['positive']:.0%}" if r['n'] else '—'), ('较差10%的终点', lambda r:pct(r.get('p10')))]
    parts = ['''<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>继续拿，还值不值？</title><style>
body{margin:0;background:#f1f5f9;color:#172033;font:16px/1.7 system-ui,-apple-system,sans-serif}main{max-width:1100px;margin:auto;padding:30px 22px}h1{font-size:36px;line-height:1.2}h2{font-size:24px}h3{font-size:19px}section,.hero{padding:24px;background:white;border-radius:16px;margin:20px 0}.hero{background:#153c45;color:white}small,.muted{color:#526174}.hero small{color:#d0e5e8}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px 10px;border-bottom:1px solid #dfe6ed;text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}th{background:#edf4f5}summary{cursor:pointer;font-weight:650;padding:12px 0}.note{background:#fff5d9;padding:14px;border-radius:8px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.card{border-left:4px solid #348884;padding:12px;background:#edf6f5}a{color:#08776e}.bar{display:flex;align-items:center;gap:10px;margin:10px 0}.track{width:55%;height:18px;background:#e4eaed;border-radius:8px;overflow:hidden}.fill{background:#348884;height:100%}@media(max-width:700px){.cards{grid-template-columns:1fr}main{padding:14px}h1{font-size:28px}section{padding:16px}}@media print{details{display:block}section{break-inside:avoid}body{background:white}}</style></head><body><main>
<div class="hero"><small>SAGE VISTA · 持仓期限补充研究 · 2026-09-16</small><h1>继续拿，还值不值？</h1><p>先看多等能赚多少，再看这个答案靠不靠谱。</p><p>日线、周线、月线分开算。这一轮仍从门票当天观察，还没有模拟实际买卖。</p></div>
<section><h2>先读这三句话</h2><div class="cards"><div class="card"><b>可以用：设定比较范围</b><p>给下一轮入场实验安排短、中、长三种持有对照。</p></div><div class="card"><b>还不能用：到期一律卖</b><p>继续持有的优势会随年份和分组改变，尚未找到稳定期限。</p></div><div class="card"><b>优先补：新的下跌风险</b><p>从检查点起会再跌多深，需要原始逐日行情；本表没有假装已经知道。</p></div></div></section>
<section><h2>怎么看数字？</h2><p>假设第3个月你有100元：“3m → 6m，中位＋1.99%”表示再等3个月，典型结果约变成101.99元。中位数是一半样本在它上面、一半在下面。</p><p>“比大盘多赚”为每次机会与同期SPY的差，再取中位数。负数表示跑输。“较差10%的终点”是亏损尾部参考，<b>不是中途最大跌幅，也不是最坏结果</b>。</p><p class="muted">d＝交易日；w＝日历周；m＝日历月。主表要求机会分数领先另两个周期至少10分，并有对应门票。10分只是研究标准。</p></section>''']
    for tf in PAIRS:
        main = [r for r in s['rows'] if r['gap']==10 and r['timeframe']==tf and r['state']=='全部']
        parts.append('<section><h2>'+NAMES[tf]+'机会：多等一段时间</h2>'+table(main,cols))
        conclusions = {
            'daily': '日线：20日以后再拿到40/60日，中位大盘差分别为＋0.61/＋1.07个百分点，值得优先做入场对照。但持有越久，较差一批的终点损失也更深；这还不是采用理由。',
            'weekly_completed': '周线：从5周多拿到10周，中位涨跌约为0，且跑输大盘；多拿到20周也没有稳定优势。暂时保留不同期限比较。',
            'monthly_completed': '月线：3→6月中位赚1.99%，但跑输大盘3.61个百分点；6→12月中位赚9.47%，但优势范围仍跨过0。现在不能定“到6个月必须卖”。102次中有69次在3个月内曾涨到10%，这提示后续值得研究利润回吐；不能把曾经涨到当成实际赚到。'}
        parts.append('<p class="note">'+conclusions[tf]+'</p><p class="muted">本组各延长窗口缺失数：'+ '；'.join(r['start']+'→'+r['end']+'：'+str(r['missing']) for r in main)+'。未分入明确机会组的事件不计为零收益。</p>')
        targets=[r for r in s['targets'] if r['timeframe']==tf]
        parts.append('<h3>等到涨10%，有多常见？</h3><p class="muted">相对门票当天收盘，曾有一天收盘达到＋10%就算。可能后来又跌回去；不是止盈收益。</p>')
        for r in targets:
            parts.append(f'<div class="bar"><span>{r["window"]}</span><div class="track"><div class="fill" style="width:{100*r["hit_rate"]:.3f}%"></div></div><span>{r["hits"]}/{r["n"]}（{r["hit_rate"]:.0%}）</span></div>')
        parts.append('<details><summary>当时已经涨了、横盘、跌了，后面有什么不同？</summary><p>检查点下跌超过5%＝下跌；−5%至＋5%＝横盘；上涨超过5%＝上涨。少于30次只看线索，不能定规则。</p>')
        states=[r for r in s['rows'] if r['gap']==10 and r['timeframe']==tf and r['state']!='全部']
        parts.append(table(states,[('当时状态',lambda r:r['state']+(' · 小样本' if r['n']<30 else ''))]+cols))
        parts.append('</details><details><summary>换年份、换分组，结果可靠吗？</summary><p>这些历史已经看过，是复核，不是新数据验证。不同窗口之间先逐次配对，不相减两个中位数。</p>')
        for r in main:
            parts.append('<h3>'+r['start']+' → '+r['end']+'</h3>'+table(r['periods'],[('信号年份',lambda v:v['period'])]+cols[1:]))
            for key,label in [('time_interval','按两年一组重抽'),('symbol_interval','按股票整组重抽')]:
                ci=r.get(key)
                parts.append('<p>'+label+'：中位大盘差95%描述性范围 '+(f'{pct(ci["low"])} ～ {pct(ci["high"])}，{ci["clusters"]}组' if ci else '样本组不足')+'。</p>')
        sensitivity=[r for r in s['rows'] if r['gap']!=10 and r['timeframe']==tf and r['state']=='全部']
        parts.append(table(sensitivity,[('领先分数',lambda r:r['gap'])]+cols)+'<p class="muted">上面两种重抽分别考虑年份聚集和同股重复，不能完全消除两者共同影响。范围跨过0，说明正负方向不够确定；本轮不做多重比较显著性宣称。</p></details>')
        first_start,first_end=PAIRS[tf][0]
        cases=sorted([r for r in s['details'] if r['timeframe']==tf and r['start']==first_start and r['end']==first_end],key=lambda r:(r['return'],r['episode_id']))
        chosen=[dict(cases[i],role=role) for role,i in [('最低',0),('中间',len(cases)//2),('最高',len(cases)-1)]]
        parts.append('<details><summary>看三个具体例子</summary><p>固定取本组第一个延长窗口中收益最低、中间和最高的事件，仅帮助理解；不是统计证明，也没有完整逐日路径或模拟成交。</p>'+table(chosen,[('例子',lambda r:r['role']),('股票',lambda r:r['symbol']),('门票日',lambda r:r['signal_date']),('检查点',lambda r:r['checkpoint_date']),('结束',lambda r:r['end_date']),('继续持有涨跌',lambda r:pct(r['return']))])+'</details></section>')
    parts.append('<section><h2>平均收益有没有被少数大涨拉高？</h2><p>暂时去掉最高5次只是检查依赖程度，完整结果仍保留。不能据此事后删掉赢家，也不能提前知道谁是赢家。</p>'+table(s['concentration'],[('机会',lambda r:NAMES[r['timeframe']]),('期限',lambda r:r['window']),('次数',lambda r:r['n']),('平均',lambda r:pct(r['mean'])),('中位',lambda r:pct(r['median'])),('去最高5次后的平均',lambda r:pct(r['mean_without_top5']))])+'</section>')
    parts.append('<section><h2>已经知道的下跌风险</h2><p>以下是从门票当天开始，一直到期限结束，途中最低价格相对门票价格的跌幅中位数。<b>不是从中途检查点开始的新增跌幅。</b></p>'+table(s['targets'],[('机会',lambda r:NAMES[r['timeframe']]),('期限',lambda r:r['window']),('累计途中下跌中位',lambda r:pct(r['cumulative_downside_median'])),('未达到＋10%的次数',lambda r:r['not_hit']),('达到者耗时中位 / 交易日',lambda r:r['hit_days_median'] if r['hit_days_median'] is not None else '—')])+'<p class="note">新增途中下行尚缺：需要恢复原20年逐日价格并验证指纹。累计跌幅不能相减。达到者耗时只计算已经达到的机会，不代表所有机会等这么久就能赚10%。</p></section>')
    parts.append('''<section><h2>离“能直接用”还差哪一步？</h2><ol><li><b>现在可写入实验：</b>日线30/40/60交易日，周线5/10/20周，月线3/6/9/12月保留对照，含表现差的窗口。</li><li><b>下一步优先：</b>恢复原逐日行情，量出检查点之后的新下跌；同一批机会比较立即入场与既定日线确认，记录等不到、错过上涨。</li><li><b>之后再决定：</b>有实际买点后重新计时，比较收益、下跌和资金占用，才能判断时间退出与状态退出。月线机会使用日线确认，仍然是月线持仓模型。</li></ol><p>状态差异是候选假设，不能直接变成“卖赢家、留输家”。当前无成交成本、止损、持仓上限或现金限制，不是账户收益或可执行交易建议。</p></section>''')
    parts.append('<section><details><summary>数据来源、计算与边界</summary><p>冻结收据 '+s['source_id']+'；信号2005-09-12至2025-09-11；观察截至2026-09-11。原始3115次机会，主组日693/周246/月102次。配对收益＝(1＋结束累计收益)/(1＋检查点累计收益)−1。</p><p>观察样本可能来自相同股票或重叠日期；当前股票池存在幸存者与覆盖限制。所有收益为已保存复权价格口径。研究没有重新识别形态、改变原标签或生产评分。</p><p>复现：'+s['version']+'；固定随机种子20260916，重抽1000次。源指纹：<small>'+s['source_hash']+'</small>。</p><p><a href="analysis.json">下载本轮完整统计与逐次配对数据</a> · <a href="https://vectorbt.dev/api/portfolio/trades/">参考：VectorBT逐笔交易统计</a> · <a href="https://quantopian.github.io/pyfolio/notebooks/round_trip_tear_sheet_example/">参考：pyfolio持仓时长与盈利分析</a></p></details></section></main></body></html>')
    return ''.join(parts)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=study(json.loads(Path(args.source).read_bytes()))
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    (out/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (out/'report.html').write_text(render(result))
    manifest={'source_hash':SOURCE_HASH,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'analysis.json',out/'report.html')}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'groups':len(result['rows']),'pairs':len(result['details']),'output':str(out)}))


if __name__=='__main__':
    main()
