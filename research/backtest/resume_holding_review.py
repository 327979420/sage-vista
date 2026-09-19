"""Resume paired holding research only after an accepted bounded V0 baseline."""
import json
from pathlib import Path
from statistics import median
from research.backtest.run_store import validate_receipt,sha256,encode
from research.backtest.price_identity import validate_baseline_receipt
from research.backtest.observation_classification import classify

ROOT=Path(__file__).resolve().parents[2]

def main():
    pointer=json.loads((ROOT/'research/backtest/v0-baseline.json').read_bytes())
    baseline=json.loads((ROOT/pointer['receipt']).read_bytes());validate_receipt(baseline);validate_baseline_receipt(baseline)
    if baseline['content_sha256']!=pointer['content_sha256']:raise ValueError('baseline_pointer_changed')
    source=json.loads((ROOT/'research/backtest/output/reusable-runs/35048162507-1/receipt.json').read_bytes());validate_receipt(source)
    if source['content_sha256']!='6d86df8d0cde21b1b5680facca1c7dce004870b0e8393729f0198e39ba9e25af':raise ValueError('holding_source_changed')
    prior=ROOT/'research/backtest/output/prior-high/35059821246-1'
    manifest=json.loads((prior/'manifest.json').read_bytes());raw=(prior/'analysis.json').read_bytes()
    if sha256(raw)!=manifest['files']['analysis.json']:raise ValueError('prior_high_source_changed')
    high=json.loads(raw)
    if high['source_hash']!=source['content_sha256']:raise ValueError('prior_high_parent_changed')
    pairs={'daily':[('20d','30d'),('20d','40d'),('20d','60d')], 'weekly_completed':[('5w','10w'),('5w','20w')], 'monthly_completed':[('3m','6m'),('3m','12m')]}
    rows=[]
    for tf,windows in pairs.items():
        events=[e for e in source['events'] if classify(e,10)['research_label']==tf]
        for a,b in windows:
            values=[]
            for event in events:
                outcomes={**event['outcomes'],**event.get('horizon_outcomes',{})}
                x,y=outcomes.get(a,{}),outcomes.get(b,{})
                if x.get('status')!='complete' or y.get('status')!='complete':continue
                gain=(1+y['return'])/(1+x['return'])-1
                spy=(1+y['spy_return'])/(1+x['spy_return'])-1
                values.append({'episode_id':event['episode_id'],'gain':gain,'excess':gain-spy})
            rows.append({'timeframe':tf,'from':a,'to':b,'n':len(values),'median_extra_return':median(v['gain'] for v in values),
                'median_extra_excess':median(v['excess'] for v in values),'positive_fraction':sum(v['gain']>0 for v in values)/len(values)})
    output=ROOT/'research/backtest/output/holding-resumed-v0';output.mkdir(parents=True,exist_ok=True)
    (output/'analysis.json').write_bytes(encode({'baseline':pointer,'observation_parent':source['content_sha256'],'prior_high_sha256':sha256(raw),'pairs':rows,'prior_high':high['comparisons']['10'],
        'role':'exploratory_existing_3_5_observations_not_new_V0_account_results','new_account_rules_applied':False}))
    names={'daily':'日线','weekly_completed':'周线','monthly_completed':'月线'}
    lines=['# 持仓研究已恢复：先看多等一段时间值不值','', '同源V0基准已经通过，以下复用既有3.5观察结果继续研究；不是把2.0小样本账户冒充3.5持仓回测，也未改动新V0的40日上限。','',
        '每一行比较同一批机会：从前一个检查点继续拿到后一个检查点，多赚或少赚多少。逐事件计算，再取中位数；不是直接相减两个窗口的中位数。','',
        '| 机会 | 继续等待 | 配对样本 | 多等期间涨跌中位数 | 相对SPY差中位数 |','|---|---|---|---|---|']
    for r in rows:lines.append(f"| {names[r['timeframe']]} | {r['from']} → {r['to']} | {r['n']} | {r['median_extra_return']:.2%} | {r['median_extra_excess']:.2%} |")
    lines+=['','简单读法：日线继续持有仍值得比较；周线5→10周的典型额外收益接近零；月线3→6个月虽然中位多赚1.99%，但同期相对SPY差的中位数为-3.61个百分点。不能只看涨幅就认定等待更好。','','## 能否等回本次下跌之前的前高？','','| 机会 | 观察窗口 | 摸到前高 | 全样本达到一半所需时间 |','|---|---|---|---|']
    for g in high['comparisons']['10']:
        last=g['windows'][-1];days=g['population_median_days']
        lines.append(f"| {names[g['timeframe']]} | {last['window']} | {last['hits']}/{last['n']}（{last['hits']/last['n']:.1%}） | {str(days)+'交易日' if days else '观察期内未达到一半'} |")
    lines+=['','前高表排除无可靠前高、信号当天已经触及及窗口不完整的记录，分母与上表不同。日/周/月的前高距离也不同，不能直接把命中率当策略强弱排名。','',
        '下一轮保留既有对照范围：日线30/40/60交易日；周线5/10周，20周作为较长对照；月线3/6/12月，保留9月负结果。这里没有决定到期必卖，也没有新增止损、止盈或trailing参数。下一步需要在同源候选上单独比较持仓规则，不能拿观察收益代替账户收益。']
    (output/'结论.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(rows,ensure_ascii=False))

if __name__=='__main__':main()
