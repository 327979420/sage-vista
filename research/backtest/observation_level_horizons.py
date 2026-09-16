"""Frozen classification candidates + reused horizons, no prices or scanner."""
import argparse
import copy
import html
import json
import os
from collections import Counter
from pathlib import Path
from research.backtest.observation_classification import classify, FRAMES
from research.backtest.observation_horizons import verify_parent, summarize, chart, PLAN, ROOT_URL
from research.backtest.selection_observation import LABELS
from research.backtest.run_store import encode, sha256, seal, trade_csv, validate_receipt

VERSION='opportunity-level-horizons-v1'
SOURCE='34938700564-1'
SOURCE_HASH='61aa16522ecbb1909bc197606f683028d318f3a28016b160dd4f47f2ad1db27a'
GAPS=(5,10,15)
PERIODS=((2005,2009),(2010,2014),(2015,2019),(2020,2025))


def study(events):
    comparisons=[]
    for gap in GAPS:
        classification={e['episode_id']:classify(e,gap) for e in events}
        selected=[e for e in events if classification[e['episode_id']]['research_label']]
        # Unique leader with its own ticket must agree with the old ticket-only leader.
        if any(classification[e['episode_id']]['research_label']!=e['timeframe'] for e in selected):
            raise ValueError('research_level_conflicts_with_frozen_parent')
        groups=summarize(selected)
        periods=[]
        for start,end in PERIODS:
            sample=[e for e in selected if start<=int(e['signal_date'][:4])<=end]
            periods.append({'period':f'{start}-{end}','groups':[g for g in summarize(sample) if g['cohort']=='common_planned']})
        comparisons.append({'minimum_gap':gap,'classification':classification,'selected_events':len(selected),
            'selected_symbols':len({e['symbol'] for e in selected}),'statuses':dict(Counter(c['reason'] for c in classification.values())),
            'groups':groups,'periods':periods})
    return {'version':VERSION,'source_id':SOURCE,'source_content_sha256':SOURCE_HASH,'main_gap':10,
            'comparisons':comparisons,'basis':'signal-time unweighted 0-100 scores; own original qualifying ticket required; unchanged parent events'}


def table(rows):
    pct=lambda v:'缺失' if v is None else f'{v*100:.2f}'
    fields=('mean_return','median_return','mean_excess','median_excess','win_rate','median_downside','mean_downside','p10_return')
    parts=['<div class="scroll"><table><tr><th>期限</th><th>事件/股票</th><th>平均涨跌%</th><th>中位涨跌%</th><th>平均SPY差</th><th>中位SPY差</th><th>上涨比例%</th><th>途中下行中位%</th><th>途中下行平均%</th><th>终点P10%</th></tr>']
    for r in rows:
        parts.append('<tr><td>'+html.escape(r['window'])+f'</td><td>{r["events"]}/{r["symbols"]}'+(' 小样本' if r['events']<30 else '')+'</td>'+''.join('<td>'+pct(r[k])+'</td>' for k in fields)+'</tr>')
    return ''.join(parts)+'</table></div>'


def render(receipt):
    s=receipt['level_study'];main=next(c for c in s['comparisons'] if c['minimum_gap']==10)
    reasons={'classified':'明确研究组','tied_scores':'分数并列','lead_too_small':'领先不足10分','leader_without_matching_ticket':'最高分周期缺匹配门票','scores_unavailable':'分数资料不足'}
    parts=['<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>分清机会级别，再看拿多久</title><style>body{font:15px system-ui;color:#172033;max-width:1120px;margin:auto;padding:24px;background:#f8fafc}section{background:white;border-radius:12px;padding:20px;margin:20px 0}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:right}svg{width:100%;max-width:850px}.scroll{overflow:auto}details{margin:18px 0}small{color:#526070}h1{font-size:28px}</style><h1>先分清机会，再看拿多久</h1>',
      '<p>本轮只研究持有期限，没有模拟买卖。用发出门票当天的分数分组，不看后来谁涨得好。</p>',
      '<p><b>主试验标准：</b>比较日、周、月三个未加权百分制分数；第一名至少领先第二名10分，而且第一名有原始门票和有效结构底。比如月80、周65、日60，并有月线门票，才进入本轮月线研究组。10分是暂定研究标准，不是已经证明最好的标准。</p>',
      f'<p>原样本{len(receipt["events"])}次，进入明确研究组{main["selected_events"]}次、{main["selected_symbols"]}只股票；其余样本保留，没有记成零收益。'+ '；'.join(f'{reasons[k]}：{v}' for k,v in main['statuses'].items())+'。</p>',
      '<p>同一批股票等得更久：收益有没有增加，下跌是否也加深？先看每组的“共同满期样本”，再看不同分差与年份。图上的点才是实际观察期限，中间连线不是逐日走势。</p>',
      '<p>日=d交易日；周=w日历周；月=m日历月。周/月目标日取当天或随后首个SPY交易日。SPY差单位为百分点。途中下行是相对候选收盘的最低跌幅，不是账户回撤。候选日期不是实际买点。</p>']
    parts.append('<section><h2>这轮先得到什么？</h2><ul><li><b>日线：</b>30、40、60交易日可留作下一轮持有对照。三种分差下总体中位SPY差均为正，但2015—2019段转负，不能称跨时期稳定。</li><li><b>周线：</b>先保留5周和10周对照，不因20周终点涨幅更高就延长持有；分差和年份改变后，优势不一致。</li><li><b>月线：</b>现在不能定“6个月最合理”。10分主组6个月的中位收益低于3个月，期间下跌更深；5/15分对照也没有给出一致的最佳期限。下一轮保留3/6/12月作为对照，不把9月负结果删掉。</li></ul><p>这些只是下一轮比较范围，不是到期必卖的规则。CSV的timeframe仍是原标签，research_level_5/10/15是本轮研究分组；空白表示未进入明确组。</p></section>')
    for tf in FRAMES:
        rows=[g for g in main['groups'] if g['timeframe']==tf and g['cohort']=='common_planned']
        parts.append(f'<section><h2>{LABELS[tf]}机会：领先至少10分</h2><p>全部计划窗口都完整的共同样本：{rows[0]["events"]}事件/{rows[0]["symbols"]}只股票。研究窗口：'+', '.join(r['window'] for r in rows)+'。</p>')
        parts.append(chart(rows,[('mean_return','平均涨跌'),('median_return','中位涨跌'),('mean_excess','平均SPY差'),('median_excess','中位SPY差')]))
        parts.append(chart(rows,[('median_downside','途中下行中位'),('p10_return','较差10%终点')]))
        parts.append(table(rows))
        parts.append('<details><summary>逐窗可用样本与缺失情况</summary>'+table([g for g in main['groups'] if g['timeframe']==tf and g['cohort']=='per_window']))
        for g in main['groups']:
            if g['timeframe']==tf and g['cohort']=='per_window':parts.append('<p>'+g['window']+'：'+html.escape(json.dumps(g['statuses'],ensure_ascii=False))+'</p>')
        parts.append('</details><details><summary>领先5分、10分、15分，结论是否容易变化？</summary><p>分差变大，股票会变少。这是不同样本的对照，不把赚钱最多的分差选为正式规则。</p>')
        for candidate in s['comparisons']:
            parts.append(f'<h3>至少领先{candidate["minimum_gap"]}分</h3>'+table([g for g in candidate['groups'] if g['timeframe']==tf and g['cohort']=='common_planned']))
        parts.append('</details><details><summary>不同年份是否一致？</summary><p>按候选出现年份分段，持有路径可能跨段。样本少于30单独标记；这些年份已看过，不是独立验证。</p>')
        for period in main['periods']:
            parts.append('<h3>'+period['period']+'</h3>'+table([g for g in period['groups'] if g['timeframe']==tf]))
        parts.append('</details></section>')
    parts.append('<section><h2>这份报告能做什么？</h2><p>帮助缩小下一轮值得比较的持有区间。不能根据终点涨幅最高就指定那天卖出，也不能保证等确认以后收益一定更高。入场方案确定后，要从实际成交重新计算持有时间和下行。</p><p>当前股票池有幸存者、覆盖与复权修订限制；同一股票多次出现、事件时间重叠，样本不独立。本轮只检查分数领先和门票，不冒充完整人工形态分类。生产评分和买卖规则没有改变。</p>')
    parts.append(f'<details><summary>来源与版本</summary><p>原20年收据：<a href="{ROOT_URL}34766761296-2/receipt.json">34766761296-2</a>；期限补算父收据：<a href="{ROOT_URL}{SOURCE}/receipt.json">{SOURCE}</a>。</p><p>父收据指纹 {SOURCE_HASH}；选股代码 ddb129c9ca847e83e1356ed995907e12428cb3c5；分组执行代码 {receipt["code_commit"]}；研究定义 {VERSION}。</p></details></section></html>')
    return ''.join(parts).encode()


def build(parent,source,runid,code):
    verify_parent(parent);validate_receipt(source)
    if source['id']!=SOURCE or source['content_sha256']!=SOURCE_HASH:raise ValueError('wrong_horizon_source')
    if [{k:v for k,v in e.items() if k!='horizon_outcomes'} for e in source['events']]!=parent['events']:
        raise ValueError('parent_events_changed')
    receipt={k:copy.deepcopy(v) for k,v in source.items() if k not in ('content_sha256','downloads','report')}
    receipt.update(id=runid,code_commit=code,level_study=study(source['events']))
    report=render(receipt);receipt['report']={'path':runid+'/report.html','sha256':sha256(report)}
    receipt['downloads']={'trades_csv':{'path':runid+'/trades.csv','sha256':sha256(trade_csv(receipt))}}
    return seal(receipt),report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--parent',default='research/backtest/output/reusable-runs/34766761296-2/receipt.json');parser.add_argument('--source',default='research/backtest/output/reusable-runs/'+SOURCE+'/receipt.json');parser.add_argument('--output',default='work/horizon-attempt');args=parser.parse_args()
    receipt,report=build(json.loads(Path(args.parent).read_bytes()),json.loads(Path(args.source).read_bytes()),os.environ['GITHUB_RUN_ID']+'-'+os.environ.get('GITHUB_RUN_ATTEMPT','1'),os.environ['GITHUB_SHA'])
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    (out/'receipt.json').write_bytes(encode(receipt));(out/'report.html').write_bytes(report);(out/'trades.csv').write_bytes(trade_csv(receipt))
    print(json.dumps({c['minimum_gap']:c['statuses'] for c in receipt['level_study']['comparisons']}))
