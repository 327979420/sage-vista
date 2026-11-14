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
 return <div className="ovRoot">
  <Head label={en?'Research · Backtests':'研究 · 回测'} title={en?'Hints in history, not yet proven.':'历史上有迹象，还没被证明。'} text={en?'Each bar is one test of the rule. Only the forward record, on signals after the freeze, can prove it.':'每一条是一次对规则的检验。真正能证明的，只有规则冻结之后的前向记录。'}/>
 </div>;
}

// About: how about 1,500 stocks narrow to a short list today. Each step counts the stocks whose
// first failed check belongs to it (from the published review reasons); click a step to read it.
const STEPS:{id:string;zh:string;en:string;codes:RegExp;dz:string;de:string}[] = [
 {id:'data',zh:'数据检查',en:'Data check',codes:/^(empty_invalid_or_old_cache|daily_history_below_420|recent_session_missing|completed_months_below_61|adjustment_anchor_missing|local_structure_unavailable|raw OHLC|open must)/,dz:'行情太短、缺最近交易日或价格不合理的，先排除；不拿坏数据打分。',de:'Too little history, a missing recent session or impossible prices: left out first, so nothing is scored on bad data.'},
 {id:'monthly',zh:'月线：方向',en:'Monthly: direction',codes:/^(monthly_|near_observed_history_high|no_available_background)/,dz:'第一层滤网。月线要确认长期上升，且不在历史高位附近；方向不对，后面都不看。',de:'Screen one. The monthly chart must confirm a long uptrend away from its high; with the wrong direction nothing else is checked.'},
 {id:'weekly',zh:'周线：趋势',en:'Weekly: trend',codes:/^weekly_/,dz:'第二层滤网。周线趋势要确认，不能接近死叉。',de:'Screen two. The weekly trend must be confirmed and not close to a bearish cross.'},
 {id:'shape',zh:'形态与位置',en:'Shape and position',codes:/^(structure_broken|no_pullback_60d)/,dz:'要有一段回调，且结构没被破坏：在上升趋势里回到支撑。',de:'There must be a pullback with the structure intact: back to support inside an uptrend.'},
 {id:'daily',zh:'日线：入场',en:'Daily: entry',codes:/^(daily_tradability_not_met|no_confirmed_reversal_entry)/,dz:'第三层滤网。成交够活跃，并且日线出现确认的反转入场。',de:'Screen three. Enough daily trading, and a confirmed reversal entry on the daily chart.'},
];
type Review = {rank:number|null; reason_codes?:string[]};
export function AboutFlow() {
 const {locale}=useLocale(), en=locale==='en';
 const data=useJson<{as_of:string;reviews:Review[];selected_symbols:string[]}>('/cr056-ranking.json');
 const [step,setStep]=useState(1);
 if(!data?.reviews?.length)return null;
 const out=data.reviews.filter(r=>r.rank===null), ranked=data.reviews.length-out.length;
 const cut=STEPS.map(s=>out.filter(r=>s.codes.test(r.reason_codes?.[0]??'')).length);
 const other=out.length-cut.reduce((a,b)=>a+b,0);
 const remain=cut.map((_,i)=>data.reviews.length-cut.slice(0,i+1).reduce((x,y)=>x+y,0));
 const s=STEPS[step];
 return <section className="ovPanel abFlow" aria-label={en?'How SV narrows the list':'SV 怎么筛'}>
  <header><small>{en?`How SV works, with today’s numbers · ${data.as_of} · click a step`:`SV 怎么运作，用今天的真实数字 · ${data.as_of} · 点任意一步`}</small></header>
  <ol className="abSteps">
   <li><b>{data.reviews.length.toLocaleString()}</b><span>{en?'reviewed':'只复评'}</span></li>
   {STEPS.map((x,i)=><li key={x.id}><button type="button" aria-pressed={i===step} onClick={()=>setStep(i)} onMouseEnter={()=>setStep(i)}>
    <small>{en?x.en:x.zh}</small><b>{remain[i].toLocaleString()}</b><em>−{cut[i]}</em>
    <i style={{width:`${remain[i]/data.reviews.length*100}%`}}/></button></li>)}
   <li><b>{ranked}</b><span>{en?'ranked':'进入排名'}</span></li>
   <li data-end><b>{data.selected_symbols.length}</b><span>{en?'to look at first':'先看'}</span></li>
  </ol>
  <div className="abExplain"><b>{en?s.en:s.zh}</b><p>{en?s.de:s.dz}</p><span>{en?`${cut[step]} stocks stopped here today (their first failed check).`:`今天有 ${cut[step]} 只停在这一步（它们第一个没通过的检查）。`}</span></div>
  {other>0&&<p className="roHint">{en?`${other} more stopped on other checks.`:`另有 ${other} 只停在其他检查。`}</p>}
 </section>;
}

// Backtests: each test as a bar across the years it covered, coloured by its verdict.
const yearsOf=(p:string|null)=>{const ys=(p??'').match(/\d{4}(?:-\d{2})?/g);if(!ys)return null;const v=(s:string)=>+s.slice(0,4)+(s.length>4?(+s.slice(5)-1)/12:0);return [v(ys[0]),v(ys[ys.length-1])+(ys[ys.length-1].length>4?1/12:1)] as const};
export function BacktestTimeline() {
 const {locale}=useLocale(), en=locale==='en';
 const record=useJson<{facts:Fact[]}>('/app/record.json');
 const [pick,setPick]=useState<string|null>(null);
 const facts=(record?.facts??[]).filter(f=>f.id!=='locked-exam-limits'&&yearsOf(f.period));
 if(!facts.length)return null;
 const lo=1994, hi=2027, X=(y:number)=>(y-lo)/(hi-lo)*100;
 const f=facts.find(x=>x.id===pick)??facts[0], span=yearsOf(f.period)!;
 const tone=(x:Fact)=>x.verdict==='FAIL'?'loss':x.verdict==='useful'?'go':'dim';
 const label=(x:Fact)=>en?FACTS_EN[x.id]?.[0]??x.label:x.label;
 return <section className="ovPanel btLine" aria-label={en?'Test timeline':'检验时间线'}>
  <header><small>{en?'Every test on one timeline · point at a bar':'所有检验放在一条时间线上 · 指向任意一条'}</small>
   <span className="btLegend"><i data-tone="loss"/>{en?'not passed':'没通过'}<i data-tone="go"/>{en?'useful':'有用'}<i data-tone="dim"/>{en?'reference':'仅参考'}</span></header>
  <div className="btTrack" style={{height:`${44+facts.length*30}px`}}>
   {[1995,2000,2005,2010,2015,2020,2025].map(y=><span key={y} className="btYear" style={{left:`${X(y)}%`}}>{y}</span>)}
   <span className="btLocked" style={{left:0,width:`${X(2005)}%`}}>{en?'locked exam data':'锁定的考试数据'}</span>
   {facts.map((x,i)=>{const [a,b]=yearsOf(x.period)!;return <button key={x.id} type="button" className="btBar" data-tone={tone(x)} data-on={x.id===f.id||undefined} style={{left:`${X(a)}%`,width:`${X(b)-X(a)}%`,top:`${34+i*30}px`}}
    onMouseEnter={()=>setPick(x.id)} onFocus={()=>setPick(x.id)} onClick={()=>setPick(x.id)} aria-label={`${label(x)} ${x.period}`}><span>{label(x)}</span></button>})}
  </div>
  <div className="btPick">
   <b>{label(f)}</b><em data-tone={tone(f)}>{f.verdict==='FAIL'?(en?'Not passed':'没通过'):f.verdict==='useful'?(en?'Useful':'有用'):(en?'Reference':'仅参考')}</em>
   <span>{en&&f.period?f.period.replace(' 至 ','–'):f.period} · {Math.round(span[1]-span[0])} {en?'years':'年'}</span>
   {f.trades!=null&&<span>{en?`${f.trades} trades`:`${f.trades} 笔`}</span>}
   {f.p!=null&&<span className="btP">p {f.p}<i><em style={{left:`${Math.min(f.p,1)*100}%`}}/><u style={{left:'5%'}}/></i><small>{en?'needs below 0.05':'要低于 0.05'}</small></span>}
   {f.average_R!=null&&<span>{en?`average ${f.average_R}R`:`平均 ${f.average_R}R`}{f.win_rate!=null?` · ${en?'win rate':'胜率'} ${Math.round(f.win_rate*100)}%`:''}</span>}
   <p>{en?FACTS_EN[f.id]?.[1]??f.note:f.note}</p>
  </div>
 </section>;
}
