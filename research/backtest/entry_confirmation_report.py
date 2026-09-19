"""Readable Chinese report from the sealed entry study; no recomputation of prices."""
import argparse
import html
import gzip
import json
from pathlib import Path

from research.backtest.entry_confirmation import NAMES, TF, METHODS
from research.backtest.run_store import sha256


def read_analysis(folder):
    folder=Path(folder); raw=folder/'analysis.json'
    return raw.read_bytes() if raw.exists() else gzip.decompress((folder/'analysis.json.gz').read_bytes())


def pct(v):return '—' if v is None else f'{v*100:+.2f}%'
def pp(v):return '—' if v is None else f'{v*100:+.2f}个百分点'
def number(v):return '—' if v is None else f'{v:.1f}'
def interval(v):return '不足以计算' if v is None else f'{pp(v[0])} ～ {pp(v[1])}'
def table(headers, rows):return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])


def render(data, delayed=None):
    stats=data['statistics'];main=[s for s in stats if s['period']=='all' and s['days']==20]
    out=['# 等日线确认，买进去以后会更好吗？',
         f"本轮复用原来的 **{data['raw_events']} 次机会、{data['stock_count']} 只股票**，合并重叠后比较 **{len(data['opportunities'])} 个机会**。四种方式用同一批机会。",
         '**先读法：**“途中最深跌幅”是买入后20个交易日内，相对买价曾经跌到多低；每组取中位数。“改善”是同一个机会等确认与直接买入的差值，再取中位数。正数表示改善。',
         '**这不是账户收益。**按次日开盘模拟买入，未计费用、仓位和现金约束。18股正式V0账户没有修改。']
    out+=['## 1．先看买成了多少，代价是什么',table(['机会','入场方式','机会数','买成','未确认仍等待','结构/跳空失效','资料不足','买成者等待中位'],[[TF[s['timeframe']],NAMES[s['method']],s['setups'],s['filled'],s['statuses'].get('waiting_censored',0),sum(s['statuses'].get(k,0) for k in ('invalidated','gap_invalidated')),sum(v for k,v in s['statuses'].items() if k.startswith('missing')),number(s['wait_median'])+'交易日'] for s in main]),
          '等待观察到：日线60交易日、周线20周、月线12个月。截止仍未确认，只表示“这段时间没等到”，不表示策略规定必须放弃。等待从机会出现到成交，直接买通常也需1个交易日。']
    out+=['## 2．买进去20天后，少跌了还是多赚了？',table(['机会','入场方式','完整结果数','收益中位','最深跌幅中位','最高涨幅中位','跑赢SPY中位','胜率'],[[TF[s['timeframe']],NAMES[s['method']],str(s['complete'])+('（样本少）' if s['sample_warning'] else ''),pct(s['return_median']),pct(s['mae_median']),pct(s['mfe_median']),pp(s['excess_median']),pct(s['win_rate'])] for s in main]),
          '这张表中的已成交样本不同，不能单靠它判断等待有效。下一张只比较同一个机会，才更接近“换买点有没有帮助”。',
          table(['机会','等待方式','配对次数','收益改善','跌幅改善','跌幅改善95%范围'],[[TF[s['timeframe']],NAMES[s['method']],s['paired_n'],pp(s['paired_return']),pp(s['paired_mae']),interval(s.get('paired_mae_ci95'))] for s in main if s['method']!='direct']),
          '范围横跨0：当前数据不能排除没有改善。范围按同一股票整体重抽样，仍未消除同一市场阶段的共同影响。配对只涵盖两种方式都成交者，必须连同未成交代价一起看。']
    out+=['## 3．有多少在等待时已经摸到前高？',table(['机会','方式','有可比前高的机会','买入前已摸到前高','其中最终没买成','等待期间最高涨幅中位'],[[TF[s['timeframe']],NAMES[s['method']],s['target_available'],s['missed_prior_high'],s['missed_no_fill'],pct(s['waiting_mfe_median'])] for s in main]),
          '前高沿用上一轮“这次下跌之前的波段高点”代理。无法确认目标、信号当天已经到达的，不放入该分母。“已经摸到”不等于全部上涨都错过了；最高价也不等于能够成交的价格。未买成者跟踪到共同等待截止，即使之前已失效。']
    out+=['## 4．历史换一段，改善还在吗？',table(['机会','方式','机会年份','配对次数','收益改善','跌幅改善'],[[TF[s['timeframe']],NAMES[s['method']],s['period'],str(s['paired_n'])+('（样本少）' if s['paired_n']<30 else ''),pp(s['paired_return']),pp(s['paired_mae'])] for s in stats if s['period']!='all' and s['days']==20 and s['method']!='direct'])]
    out+=['## 5．5、10、20、30天全部保留',table(['机会','方式','成交后天数','完整数','收益均值','收益中位','最深跌幅中位','配对收益改善','配对跌幅改善'],[[TF[s['timeframe']],NAMES[s['method']],s['days'],s['complete'],pct(s['return_mean']),pct(s['return_median']),pct(s['mae_median']),pp(s['paired_return']),pp(s['paired_mae'])] for s in stats if s['period']=='all'])]
    if delayed:
        subset=[g for g in delayed['groups'] if g['period']=='all' and g['days']==20]
        out+=['## 补充：确实延后买入的机会，结果如何？',
              '上面的主表保留信号日已满足确认的机会，因此一些配对差值恰好为0。下面把买入日期没有改变的机会分开。这是看完主结果后做的解释性拆分，不是新的预登记主检验。',
              table(['机会','方式','买点未变次数','确实延后次数','延后者收益变化','延后者跌幅改善'],[[TF[g['timeframe']],NAMES[g['method']],g['same_fill'],g['delayed_pairs'],pp(g['return']),pp(g['mae'])] for g in subset]),
              '日线等突破：在确实延后的208次中，20日收益典型少1.34个百分点、途中多跌0.63个百分点。这只描述两种方法都买成且实际延后的子组，不代表所有日线机会都变差。']
    out+=['## 6．这轮究竟比较什么',
         '- 直接买：机会出现后，下一可交易日开盘。\n- 等突破：现有日线三推结构突破。\n- 等支撑反转：现有日线底部支撑触及后反转，不是所有支撑回踩的统称。\n- 等动能恢复：现有突破后回踩支撑、负柱连续缩短的组合，不能解释成只看MACD。',
         '股票状态：发现机会 → 等日线确认 → 形成订单 → 下一交易日模拟成交 → 开始计算持有时间。来源周期分别记录；不会把月、周、日分数相加。EXPIRED状态预留，本轮没有擅自设定失效天数。',
         '**去重边界：**1041事件合并成977机会，64事件并入已有机会，其中57未在本轮机会终止前加入有效来源；它们仍保存在原始事件与合并清单，没有另造交易。为四种方法使用同一组机会，本轮按首次机会的固定等待观察区间加30交易日保守合并；后续来源只能从原信号日加入。提前失效或买完后又出现的机会，可能被保守合并而未独立研究。这不是可直接上线的持续机会管理器，重复机会利用率仍需下一轮验证。',
         '**哪些能确认：**可核对相同历史机会换买点的结果、等待覆盖和错失代价。\n\n**哪些不能确认：**未来仍有效、扣费后赚钱、$100k组合一定改善。样本有幸存者偏差、日期重叠、历史已被看过；小组低于30次仅作线索。',
         '**持有候选不变：**日线30/40d及60d；周线5w及20w；月线3m/6m/12m。以后接账户时从实际成交日起算。',
         '工程参考：[LEAN职责分离](https://www.quantconnect.com/docs/v1/algorithm-framework/overview)、[Backtrader次根开盘](https://www.backtrader.com/docu/order-creation-execution/order-creation-execution/)、[Nautilus成交与仓位](https://nautilustrader.io/docs/latest/concepts/positions/)。保留现有VectorBT账户。',
         f"数据来源：35048162507-1；源收据 `{data['parent_sha256']}`。研究代码 `{data['commit']}`。完整结果见 analysis.json 和 comparison.csv。"]
    return '\n\n'.join(out)+'\n'


def main():
    p=argparse.ArgumentParser();p.add_argument('folder');a=p.parse_args();folder=Path(a.folder)
    manifest=json.loads((folder/'manifest.json').read_bytes())
    if sha256(read_analysis(folder))!=manifest['files']['analysis.json']:raise ValueError('analysis_hash_mismatch')
    data=json.loads(read_analysis(folder));delayed=json.loads((folder/'delayed-only.json').read_bytes()) if (folder/'delayed-only.json').exists() else None
    if delayed and delayed['parent_sha256']!=manifest['files']['analysis.json']:raise ValueError('delayed_parent_mismatch')
    text=render(data,delayed)
    (folder/'详细数据.md').write_text(text)
    # Markdown itself is the authoritative, copyable report. HTML shows tables without extra dependencies.
    lead=(folder/'结论.md').read_text() if (folder/'结论.md').exists() else ''
    parts=[];lines=(lead+'\n\n'+text).splitlines();i=0
    while i<len(lines):
        line=lines[i]
        if line.startswith('| '):
            group=[]
            while i<len(lines) and lines[i].startswith('| '):group.append(lines[i]);i+=1
            parts.append('<div class="scroll"><table>')
            for j,row in enumerate(group):
                if j==1:continue
                tag='th' if j==0 else 'td'
                parts.append('<tr>'+''.join(f'<{tag}>{html.escape(c.strip())}</{tag}>' for c in row.strip('|').split('|'))+'</tr>')
            parts.append('</table></div>');continue
        elif line.startswith('# '):parts.append('<h1>'+html.escape(line[2:])+'</h1>')
        elif line.startswith('## '):parts.append('<h2>'+html.escape(line[3:])+'</h2>')
        elif line:parts.append('<p>'+html.escape(line).replace('**','')+'</p>')
        i+=1
    (folder/'report.html').write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>入场确认研究</title><style>body{font:16px/1.7 system-ui;max-width:1180px;margin:auto;padding:24px;color:#18303b}h2{margin-top:40px}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid #ddd;padding:8px;text-align:right;white-space:nowrap}th{background:#edf4f7}p{max-width:900px}</style>'+''.join(parts)+'</html>')

if __name__=='__main__':main()
