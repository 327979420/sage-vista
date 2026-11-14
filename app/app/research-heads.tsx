'use client';
import {useEffect,useState} from 'react';
import {useLocale} from '../i18n/locale';
import {FACTS_EN} from '../forward/terminal';
import {sharedJson} from '../json-cache';

// Terminal openings for the reading pages: Archive (a grid of the original tools), About (what SV
// did today, from the published files) and Backtests (the verdict on each historical test).
function useJson<T>(url:string) {
 const [data,setData]=useState<T|null>(null);
 useEffect(()=>{let active=true;void sharedJson<T>(url).then(d=>{if(active)setData(d)});return()=>{active=false}},[url]);
 return data;
}
const Head = ({label,title,text}:{label:string;title:string;text:string}) => <section className="ovHead"><div><small>{label}</small><h1>{title}</h1><p>{text}</p></div></section>;

const ARCHIVE:[string,string,string,string,string][] = [
 ['/zh/watch/market','大盘','Market','原来的大盘页：参与度、机构仓位、融资余额，按日、周、月。','The original market page: participation, institutional positioning and margin, by day, week and month.'],
 ['/zh/watch/industry-radar','行业','Sectors','20 个主题和它们的 ETF：谁在领涨、谁在回调。','20 themes and their ETFs: which lead and which pull back.'],
 ['/zh/watch/resonance/rare-opportunities','多因子机会','Multi-factor opportunities','每天复评约 1,500 只股票，按月、周、日线打分排序。','About 1,500 stocks re-scored daily on monthly, weekly and daily charts.'],
 ['/zh/watch/resonance/favorite-pattern','我最喜欢形态','Daily setups','最活跃的 100 只股票里的三推回调和多底支撑。','Three-push pullbacks on multi-bottom support among the 100 most-traded stocks.'],
 ['/zh/backtest','回测','Backtests','历史研究的收益、亏损和还没被证明的结论。','Gains, losses and unproven conclusions from past research.'],
 ['/zh/watch/resonance/about','功能介绍与方法','About and method','SV 是什么、怎么运作、怎么用。','What SV is, how it works and how to use it.'],
];
export function ArchiveGrid() {
 const {locale}=useLocale(), en=locale==='en';
 return <div className="ovRoot">
  <Head label={en?'Research · Archive':'研究 · 研究档案'} title={en?'The original tools, one click away.':'原来的工具，一点就到。'} text={en?'Each keeps its original definitions. The live versions sit in the side menu.':'每个页面都保留原来的定义。新版在左边菜单里。'}/>
  <div className="rhGrid">{ARCHIVE.map(([href,zh,enL,dz,de],i)=><a key={href} href={href} className="rhCard" style={{animationDelay:`${i*70}ms`}}><small>{String(i+1).padStart(2,'0')}</small><b>{en?enL:zh}</b><span>{en?de:dz}</span><em>{href}</em></a>)}</div>
 </div>;
}

type Status = {source_latest_complete_date?:string; last_successful_update_at?:string};
type Today = {market?:{light?:string|null;breadth?:number|null}};
export function AboutHead() {
 const {locale}=useLocale(), en=locale==='en';
 const status=useJson<Status>('/update-status.json'), today=useJson<Today>('/app/today.json');
 const updated=status?.last_successful_update_at?new Date(status.last_successful_update_at).toLocaleString(en?'en-AU':'zh-CN',{timeZone:'Australia/Melbourne',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):null;
 return <div className="ovRoot">
  <Head label={en?'Research · About SV':'研究 · 关于 SV'} title={en?'A trend-pullback system that checks itself every day.':'一个每天自己检查一遍的顺势回调系统。'} text={en?'After each US close SV reviews about 1,500 stocks, scores them on three timeframes, and publishes only data whose dates check out.':'每个美股收盘后，SV 复评约 1,500 只股票，按三个周期打分，日期核对无误才发布。'}/>
  <div className="rhStats">
   <div className="ovPanel"><small>{en?'Latest close':'最新收盘'}</small><b>{status?.source_latest_complete_date??'—'}</b></div>
   <div className="ovPanel"><small>{en?'Published (Melbourne)':'发布时间（墨尔本）'}</small><b>{updated??'—'}</b></div>
   <div className="ovPanel"><small>{en?'Market gate':'市场闸门'}</small><b data-tone={today?.market?.light==='green'?'go':'wait'}>{today?.market?.light?(today.market.light==='green'?(en?'Green':'绿灯'):(en?'Amber':'黄灯')):'—'}</b></div>
   <div className="ovPanel"><small>{en?'3W pool above 200-day':'3W 股票池站上 200 日线'}</small><b>{today?.market?.breadth!=null?`${(today.market.breadth*100).toFixed(1)}%`:'—'}</b></div>
  </div>
 </div>;
}

type Fact = {id:string;label:string;period:string|null;trades?:number|null;p?:number|null;verdict:string|null;note:string;average_R?:number|null;win_rate?:number|null};
export function BacktestHead() {
 const {locale}=useLocale(), en=locale==='en';
 const record=useJson<{facts:Fact[]}>('/app/record.json');
 const facts=(record?.facts??[]).filter(f=>f.id!=='locked-exam-limits'&&f.id!=='forward-expectation');
 return <div className="ovRoot">
  <Head label={en?'Research · Backtests':'研究 · 回测'} title={en?'Hints in history, not yet proven.':'历史上有迹象，还没被证明。'} text={en?'Each tile is one test of the rule. Only the forward record, on signals after the freeze, can prove it.':'每一格是一次对规则的检验。真正能证明的，只有规则冻结之后的前向记录。'}/>
  <div className="rhVerdicts">{facts.map((f,i)=>{const tone=f.verdict==='FAIL'?'loss':f.verdict==='useful'?'go':'dim';return <div key={f.id} className="ovPanel" data-tone-border={tone} style={{animationDelay:`${i*80}ms`}}>
   <small>{(en&&f.period?f.period.replace(' 至 ','–'):f.period)??''}</small><b>{en?FACTS_EN[f.id]?.[0]??f.label:f.label}</b>
   <em data-tone={tone}>{f.verdict==='FAIL'?(en?'Not passed':'没通过'):f.verdict==='useful'?(en?'Useful':'有用'):(en?'Reference':'仅参考')}</em>
   <span>{[f.trades!=null?(en?`${f.trades} trades`:`${f.trades} 笔`):null,f.p!=null?`p ${f.p}`:null].filter(Boolean).join(' · ')}</span>
   <p>{en?FACTS_EN[f.id]?.[1]??f.note:f.note}</p></div>})}</div>
  <p className="mfListLabel">{en?'Research runs and saved results':'研究运行与保存的结果'}</p>
 </div>;
}
