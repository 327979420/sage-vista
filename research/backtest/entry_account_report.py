"""Audit completed AB books and render plain Chinese tables; no strategy changes."""
import argparse
import gzip
import json
import math
from pathlib import Path
from statistics import median
from collections import Counter
from research.backtest.entry_account_validation import validate_comparison,write_csv
from research.backtest.account_ledger import ZH
REASONS={**ZH,"INVALIDATED":"结构失效","EXPIRED":"到期未确认","stop":"止损","stop_gap":"跳空止损","target":"2R止盈","time_40d":"持有满40交易日"}
def reason_zh(value):return REASONS.get(value,value)
from research.backtest.run_store import encode,sha256


def money(x):return '—' if x is None else f'${x:,.2f}'
def pct(x):return '—' if x is None else f'{x:.2%}'
def num(x):return '—' if x is None else f'{x:.2f}'
def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])


def read(folder):
    folder=Path(folder);manifest=json.loads((folder/'manifest.json').read_bytes())
    for name,expected in manifest['files'].items():
        if sha256((folder/name).read_bytes())!=expected:raise ValueError('artifact_hash_mismatch:'+name)
    data=json.loads(gzip.decompress((folder/'comparison.json.gz').read_bytes()))
    books={s:json.loads(gzip.decompress((folder/(s+'-book.json.gz')).read_bytes())) for s in ('A','B')}
    validate_comparison(data,books)
    return data,books


def report(data,books):
    a,b=data['metrics']['A'],data['metrics']['B'];e=data['entry_confirmation']
    skip_counts=Counter((r['challenger_decision'] or {}).get('reason',r['skip_reason']) for r in data['attribution'] if r['timeframe']=='monthly_completed' and r['challenger_skipped'])
    metrics=[('最后账户价值','ending_portfolio_value',money),('总收益','total_return',pct),('年化收益（CAGR）','cagr',pct),
             ('已实现盈亏','realised_pnl',money),('未实现盈亏','unrealised_pnl',money),('最大回撤','max_drawdown',pct),
             ('年化波动','annualised_volatility',pct),('Sharpe','sharpe',num),('Sortino','sortino',num),
             ('买入笔数','entered_trades',str),('已平仓笔数','closed_trades',str),('仍持有笔数','open_trades',str),
             ('已平仓胜率','win_rate',pct),('平均盈利单','average_winner_dollars',money),('平均亏损单','average_loser_dollars',money),
             ('盈利总额/亏损总额','profit_factor',num),('每笔平均盈亏','expectancy_dollars',money),('平均持有交易日','average_closed_holding_sessions',num),
             ('累计双边换手倍数','gross_turnover',num),('平均资金投入股票比例','average_capital_utilisation',pct),('平均现金余额','average_cash_balance',money),
             ('完全空仓交易日','completely_idle_cash_sessions',str),('完全空仓时间比例','completely_idle_cash_fraction',pct),('平均持仓只数','average_open_positions',num),
             ('达到10仓交易日','max_positions_sessions',str),('单股最高占账户比例','maximum_single_stock_account_weight',pct)]
    out=['# 两个10万美元账户：完整对照',
         f"期间：{data['period']['start']}—{data['period']['end']}，{data['period']['sessions']}个交易日。用上一轮977个机会，其中100个月线机会。A全部按原买点；B只让月线等日线支撑反转。",
         '**共同规则：**每笔初始资金的10%、最多10仓、整股、单边0.1%成本；原支撑位、支撑下5%/最多10%风险、2R止盈、最多40交易日全部保持。持有时间从各自实际成交日开始。',
         '## 1．账户结果',table(['指标','A：直接入场','B：月线等支撑反转'],[[name,fmt(a.get(key)),fmt(b.get(key))] for name,key,fmt in metrics]),
         '年化使用原工具的252交易日约定，无风险利率和现金利息为0。胜率、盈亏比和期望按已平仓交易计算；换手为累计买卖金额之和/平均账户净值，未年化、未除以2。Sharpe/Sortino衡量收益相对波动或下跌的表现，这里越高越好，不是收益百分比。平均现金可超过初始10万，因为已平仓利润留在现金，单笔买入仍固定约1万。',
         '## 2．月线等待过程中发生了什么',
         table(['项目','次数/天数'],[['月线机会',e['monthly_setups']],['A实际买入',e['direct_entries_A']],['B出现确认',e['triggered_B']],['B实际买入',e['filled_B']],['没有确认到期',e['expired']],['等待结构失效',e['invalidated']],['确认等待：均值 / 中位',num(e['confirmation_wait_mean'])+' / '+num(e['confirmation_wait_median'])+'交易日'],['买成者从setup到fill：均值 / 中位',num(e['actual_fill_wait_mean'])+' / '+num(e['actual_fill_wait_median'])+'交易日'],['确认前已摸到前高',str(e['prior_high_touched_before_confirmation'])+' / '+str(e['prior_high_available'])],['B没买成、但A盈利',e['missed_baseline_results'].get('profit',0)],['B没买成、且A亏损',e['missed_baseline_results'].get('loss',0)],['日周因容量差异新增买入',e['later_nonmonthly_fills_enabled_by_capacity']]]),
         '“出现确认”不等于“买成”：还有原止损可执行性、现金和持仓名额检查。支撑在setup时冻结，不在B确认日另选更低的支撑；如果新开盘价已经不满足旧止损计划，原引擎会拒绝买入。',
         'B月线未成交原因：'+'；'.join(str(reason_zh(k))+' '+str(v)+'次' for k,v in skip_counts.items())+'。逐笔具体决定在月线CSV中。',
         '## 3．账户差额来自哪里']
    names={'monthly_both':'月线：两边都买了','monthly_A_only':'月线：只有A买了','monthly_B_only':'月线：只有B买了','monthly_neither':'月线：都没买',
           'daily_weekly_both':'日周：两边都买了','daily_weekly_A_only':'日周：只有A买了','daily_weekly_B_only':'日周：只有B买了','daily_weekly_neither':'日周：都没买'}
    out.append(table(['来源','B减A的盈亏贡献'],[[names[k],money(v)] for k,v in data['attribution_categories'].items()]+[['合计',money(b['ending_portfolio_value']-a['ending_portfolio_value'])]]))
    out.append('合计已与两账户期末净值差逐分核对。日周入场规则没有变；它们的新增/缺失交易来自现金、名额或同股占用变化。正贡献不一定来自更好的月线买价。')
    changed=sorted((r for r in data['attribution'] if abs(r['pnl_difference'])>1e-6),key=lambda r:abs(r['pnl_difference']),reverse=True)
    out+=['### 对差额影响最大的10笔',table(['股票','机会日期','类别','A盈亏','B盈亏','B减A'],[[r['ticker'],r['original_setup_date'],names[r['category']],money(r['baseline_pnl']),money(r['challenger_pnl']),money(r['pnl_difference'])] for r in changed[:10]])]
    out+=['### 现金/名额释放后新增的日周交易',table(['股票','买入日','A没有买的原因','B盈亏','当时重叠的月线等待数量'],[[r['symbol'],r['entry_date'],reason_zh(r['A_decision']['reason']),money(r['pnl_B']),len(r['overlapping_monthly_waits'])] for r in data['capacity_effects']]),
         '逐笔保存A/B决定时的现金和持仓数。若有多个月线同时等待，它们是可能共同释放容量的来源，不能把新增交易的全部盈利分别算到每一个月线上。']
    immediate=sum(bool(x['overlapping_monthly_waits']) for x in data['capacity_effects'])
    out.append(f'其中{immediate}笔在当时可找到重叠的月线等待，余下{len(data["capacity_effects"])-immediate}笔没有这种直接重叠证据，属于两账户此前资金路径差异的后续影响；不把20笔全部说成当时某一笔月线直接释放的现金。')
    out+=['## 4．等待时已经涨走了哪些？',
         '不另设“涨10%就算大涨”的门槛。以下按确认前最高涨幅列前10个，参照setup后首个交易日开盘；确认当日收盘前的最高价也包括在内。没触发的跟踪到等待窗口结束。这是未持仓期间的价格路径，不是可成交收益。']
    monthly=[r for r in data['attribution'] if r['timeframe']=='monthly_completed']
    ranked=sorted((r for r in monthly if r['preconfirmation_mfe'] is not None),key=lambda r:r['preconfirmation_mfe'],reverse=True)
    out.append(table(['股票','机会日期','确认前最高涨幅','已摸到前高','B实际买入日','A盈亏'],[[r['ticker'],r['original_setup_date'],pct(r['preconfirmation_mfe']),'无法确认' if r['touched_prior_high_before_confirmation'] is None else '是' if r['touched_prior_high_before_confirmation'] else '否',r['challenger_fill_date'] or '没有买成',money(r['baseline_pnl'])] for r in ranked[:10]]))
    out+=['## 5．不同历史时期是否一致',table(['期间','A盈亏','B盈亏','B减A','A区间回撤','B区间回撤'],[[r['start']+'—'+r['end'],money(r['A']['pnl']),money(r['B']['pnl']),money(r['pnl_difference']),pct(r['A']['drawdown_within_period']),pct(r['B']['drawdown_within_period'])] for r in data['stability']]),
         '这是同两条连续账户路径的分段，没有每段重新充值。2025-09-11后不再增加新候选，2026段主要是处理之前留下的等待与持仓。',
         '## 6．可信度与边界',
         '- **账务事实：**两组使用同一引擎、行情、候选、排序和参数；每日现金、股数、净值相互对账，盈亏归因合计对上。\n- **这份样本的结果：**这977个保存机会在当前固定支撑及40日退出规则下的差异。\n- **还不够的策略证据：**完整历史榜单未保存、样本来自存续股票、64个重叠事件按上一轮方式保守合并、历史已经看过，没有独立留样。不能据此直接上线。',
         '排序复用现有函数，但只在原收据保存的同日提名池中排序；没有重新评分或伪造完整历史榜单。单笔固定$10000，不随净值复利扩仓，这会影响长样本的资金利用率。',
         '支撑计划两边相同；入场价变化后，原公式产生不同stop/target是入场时机变化的结果，没有调整止损止盈参数。',
         f"价格版本：`{data['price_manifest']['price_version']}`。运行 `{data['run']}`；计算提交 `{data['commit']}`。旧正式V0仍为35415051176-1。"]
    return '\n\n'.join(out)+'\n'


def main():
    p=argparse.ArgumentParser();p.add_argument('folder');args=p.parse_args();folder=Path(args.folder)
    data,books=read(folder)
    # An independent fill-holding-clock check, beyond the existing ledger reconciliation.
    calendar=[d['date'] for d in books['A']['ledger']['days']];index={d:i for i,d in enumerate(calendar)}
    fills=0
    for side in ('A','B'):
        for t in books[side]['trades']:
            if t['status']=='closed':
                assert index[t['execution']['exit_date']]-index[t['entry_date']]+1==t['execution']['holding_sessions']
                fills+=1
    attribution=sum(r['pnl_difference'] for r in data['attribution'])
    difference=data['metrics']['B']['ending_portfolio_value']-data['metrics']['A']['ending_portfolio_value']
    assert math.isclose(attribution,difference,abs_tol=1e-6)
    for side in ('A','B'):
        m=data['metrics'][side]
        assert math.isclose(m['realised_pnl']+m['unrealised_pnl'],m['ending_portfolio_value']-100000,abs_tol=1e-6)
    first_monthly=min(s['setup_date'] for s in data['monthly_states'].values())
    for a,b in zip(books['A']['daily_account'],books['B']['daily_account']):
        if a['date']<=first_monthly:assert math.isclose(a['equity'],b['equity'],abs_tol=1e-6)
    (folder/'完整报表.md').write_text(report(data,books))
    monthly=[r for r in data['attribution'] if r['timeframe']=='monthly_completed']
    labels={r['event_id']:r['ticker']+' '+r['original_setup_date'] for r in data['attribution']}
    write_csv(folder/'月线逐笔.csv',[{'股票':r['ticker'],'机会日期':r['original_setup_date'],'固定排名':r['rank'],
        'A买入日':r['baseline_entry_date'],'B确认日':r['challenger_trigger_date'],'B买入日':r['challenger_fill_date'],
        '等待成交交易日':r['waiting_days'],'A买价':r['baseline_entry_price'],'B买价':r['challenger_entry_price'],
        'A卖出日':(r['baseline_exit'] or {}).get('exit_date'),'A卖出原因':reason_zh((r['baseline_exit'] or {}).get('exit_reason')),
        'B卖出日':(r['challenger_exit'] or {}).get('exit_date'),'B卖出原因':reason_zh((r['challenger_exit'] or {}).get('exit_reason')),
        'A盈亏':r['baseline_pnl'],'B盈亏':r['challenger_pnl'],'B减A盈亏':r['pnl_difference'],
        'B没买原因':reason_zh((r['challenger_decision'] or {}).get('reason') if r['challenger_skipped'] and r['challenger_decision'] else r['skip_reason']),
        '确认前最大涨幅':r['preconfirmation_mfe'],'确认前碰到前高':r['touched_prior_high_before_confirmation'],
        '可能释放资金关联交易':[labels[eid] for eid in r['released_capital_trade_ids']]} for r in monthly])
    verification={'status':'passed','run':data['run'],'closed_trades_fill_clock_checked':fills,'pnl_difference':difference,
                  'price_version':data['price_manifest']['price_version'],'checks':['cloud artifact hashes','strict AB inputs','signal/support/execution/account bindings','actual daily ledger and fees','fill-relative holding count','P&L attribution sum','identical path before first monthly divergence']}
    from research.backtest.entry_confirmation_report import read_analysis
    from research.backtest.entry_account_validation import ENTRY_FOLDER,ENTRY_HASH
    entry_raw=read_analysis(ENTRY_FOLDER)
    if sha256(entry_raw)!=ENTRY_HASH:raise ValueError('lifecycle_source_mismatch')
    old={o['episode_id']:o for o in json.loads(entry_raw)['opportunities']}
    lifecycle=[];trades={s:{t['event_id']:t for t in books[s]['trades']} for s in ('A','B')}
    for row in monthly:
        eid=row['event_id'];state=data['monthly_states'][eid];timeline=[]
        def add(label,day,reason=None):
            if timeline and day<timeline[-1]['date']:raise ValueError('lifecycle_time_reversal')
            timeline.append({'state':label,'date':day,'reason':reason})
        for label in ('DETECTED','ACTIVE_SETUP','WAITING_FOR_DAILY_CONFIRMATION'):add(label,state['setup_date'])
        trigger=state['trigger_date'];t=trades['B'].get(eid)
        if trigger:
            add('ENTRY_READY',trigger);add('ORDER_PENDING',trigger)
            if t and t['status'] in ('open','closed'):
                add('OPEN_POSITION',t['entry_date'])
                if t['status']=='closed':
                    add('EXIT_READY',t['execution']['exit_date'],t['execution']['exit_reason'])
                    add('CLOSED',t['execution']['exit_date'])
            elif t and t['status']=='skipped':
                add('ORDER_REJECTED',t['entry_date'],(row['challenger_decision'] or {}).get('reason',t.get('reason')))
        elif state['state']=='EXPIRED':add('EXPIRED',state['wait_end'])
        else:
            invalid=next(x['date'] for x in old[eid]['methods']['support']['states'] if x['state']=='INVALIDATED')
            add('INVALIDATED',invalid)
        lifecycle.append({'event_id':eid,'ticker':row['ticker'],'terminal_state':timeline[-1]['state'],'events':timeline})
    (folder/'monthly-lifecycle.json').write_bytes(encode(lifecycle))
    verification['monthly_terminal_states']=dict(Counter(x['terminal_state'] for x in lifecycle))
    (folder/'verification.json').write_bytes(encode(verification));print(json.dumps(verification,ensure_ascii=False))

if __name__=='__main__':main()
