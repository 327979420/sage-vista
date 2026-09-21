"use client";
import {useEffect,useRef,useState,type ReactNode} from 'react';
import {TrackerShell} from '../resonance/tracker-ui';
import {useDailyData} from './daily-data';

import {complete,participation,breakouts,leadership,sectorReading,positionReading,marginReading,unavailable,type Reading,type Panel,type CockpitReport,type SampleReport} from './interpretation';
export type {CockpitReport} from './interpretation';
type Line={label:string;color:string;values:(number|null)[]};
const PATHS=['/update-status.json','/market-cockpit.json','/market-internals.json'] as const;
const BLUE='#4979d1',TEAL='#148979',PURPLE='#8b68b4',RED='#bd6264';
const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v);
const num=(v:number|null|undefined,d=1)=>finite(v)?v.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
const sign=(v:number|null|undefined,d=1)=>finite(v)?`${Math.abs(v)<.5*10**(-d)?'':v>0?'+':''}${num(Math.abs(v)<.5*10**(-d)?0:v,d)}`:'—';
const pct=(v:number|null|undefined)=>finite(v)?`${sign(v)}%`:'—';

function Icon({kind}:{kind:string}){
 const paths:Record<string,string>={flows:'M4 7h15m-4-4 4 4-4 4M20 17H5m4-4-4 4 4 4',positions:'M4 20V9h4v11m4 0V4h4v16m4 0v-7',margin:'M4 17 9 12l4 3 7-10m-6 0h6v6',options:'M5 4v16m7-16v16m7-16v16M2 9h6m1 6h6m1-8h6',breadth:'M4 20V12m5 8V4m6 16v-6m5 6V8',highs:'m3 9 5-5 5 5M8 4v16m6-5 5 5 4-5m-4 5V4',relative:'M3 18 8 12l5 3 8-10M3 9l6 2 6-6 6 3',sectors:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z'};
 return <svg viewBox="0 0 24 24" aria-hidden="true" className="cockpitIcon"><path d={paths[kind]} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>
}

export function Chart({dates,lines,unit='',bars=false,zero=false}:{dates:string[];lines:Line[];unit?:string;bars?:boolean;zero?:boolean}){
 const [hover,setHover]=useState<number|null>(null); const all=lines.flatMap(l=>l.values).filter(finite);
 if(!all.length)return <div className="cockpitEmpty">暂无可验证数据</div>;
 const index=hover!==null&&hover<dates.length?hover:dates.length-1;
 let low=Math.min(...all,...(zero?[0]:[])),high=Math.max(...all,...(zero?[0]:[]));
 const pad=(high-low)*.13||1;low=all.every(v=>v>=0)&&!zero?Math.max(0,low-pad):low-pad;high+=pad;
 const left=49,right=490,top=16,bottom=145;
 const x=(i:number)=>left+(i+(bars?.5:0))*(right-left)/Math.max(dates.length-(bars?0:1),1),y=(v:number)=>bottom-(v-low)/(high-low)*(bottom-top);
 return <div className="cockpitChart">
  <div className="cockpitLegend">{lines.map(l=><span key={l.label}><i style={{background:l.color}}/>{l.label} <b>{num(l.values[index])}{unit}</b></span>)}<time>{dates[index]}</time></div>
  <svg viewBox="0 0 510 178" role="img" aria-label={`${lines.map(l=>l.label).join('、')}，${dates[0]}至${dates.at(-1)}，单位${unit||'数值'}`} onMouseLeave={()=>setHover(null)}>
   {[low,(low+high)/2,high].map(v=><g key={v}><line x1={left} x2={right} y1={y(v)} y2={y(v)} stroke="#e9edf1"/><text x={left-9} y={y(v)+4} textAnchor="end">{num(v,Math.abs(v)<10?1:0)}</text></g>)}
   {low<0&&high>0&&<line x1={left} x2={right} y1={y(0)} y2={y(0)} stroke="#adb7c3" strokeDasharray="3 3"/>}
   {lines.map(l=>{let d='',gap=true;l.values.forEach((v,i)=>{if(!finite(v)){gap=true;return}d+=`${gap?'M':'L'}${x(i)},${y(v)} `;gap=false});return <g key={l.label}>
    {bars?l.values.map((v,i)=>finite(v)?<rect key={i} x={x(i)-(right-left)/dates.length*.31} y={Math.min(y(v),y(0))} width={(right-left)/dates.length*.62} height={Math.max(Math.abs(y(v)-y(0)),1)} rx="2" fill={v>=0?TEAL:RED}/>:null):<><path d={d} fill="none" stroke={l.color} strokeWidth="2.6" strokeLinejoin="round"/>{l.values.map((v,i)=>finite(v)&&(i===index||dates.length===1)?<circle key={i} cx={x(i)} cy={y(v)} r="3.5" fill={l.color}/>:null)}</>}
   </g>})}
   {dates.map((d,i)=><rect key={d} x={x(i)-Math.max((right-left)/dates.length,8)/2} y={top} width={Math.max((right-left)/dates.length,8)} height={bottom-top} fill="transparent" onMouseEnter={()=>setHover(i)}><title>{`${d}\n${lines.map(l=>`${l.label}: ${num(l.values[i])}${unit}`).join('\n')}`}</title></rect>)}
   <text x={left} y="172">{dates[0]}</text><text x={right} y="172" textAnchor="end">{dates.at(-1)}</text>
  </svg>
 </div>
}

function Drawer({title,children,onClose}:{title:string;children:ReactNode;onClose:()=>void}){
 const ref=useRef<HTMLDialogElement>(null);
 useEffect(()=>{const previous=document.activeElement as HTMLElement|null;const dialog=ref.current;const dismiss=(e:MouseEvent)=>{if(e.target===dialog&&dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)onClose()}};dialog?.addEventListener('click',dismiss);dialog?.showModal();const overflow=document.body.style.overflow;document.body.style.overflow='hidden';return()=>{dialog?.removeEventListener('click',dismiss);dialog?.close();document.body.style.overflow=overflow;previous?.focus()}},[onClose]);
 return <dialog ref={ref} className="cockpitDrawer" aria-labelledby="cockpit-detail-title" onCancel={onClose}>
  <header><div><span className="cockpitEyebrow">详细观察</span><h2 id="cockpit-detail-title">{title}</h2></div><button aria-label="关闭详情" onClick={onClose}>×</button></header>{children}
 </dialog>
}
function DataTable({dates,lines,unit}:{dates:string[];lines:Line[];unit:string}){
 return <div className="cockpitTableWrap"><table><caption>最近记录 · {unit}</caption><thead><tr><th>日期</th>{lines.map(l=><th key={l.label}>{l.label}</th>)}</tr></thead><tbody>{dates.map((d,i)=>({d,i})).reverse().slice(0,26).map(({d,i})=><tr key={d}><td>{d}</td>{lines.map(l=><td key={l.label}>{num(l.values[i])}</td>)}</tr>)}</tbody></table></div>
}
function Missing({panel}:{panel?:Panel|null}){return <div className="cockpitEmpty"><b>这项数据暂未取得</b><span>本次更新未通过核对，恢复后自动补充。</span>{panel?.observation_date&&<span>上次观察 {panel.observation_date}</span>}</div>}
function Card({id,title,subtitle,date:day,frequency,status,children,onOpen,button='查看详情'}:{id:string;title:string;subtitle:string;date?:string|null;frequency:string;status?:string;children:ReactNode;onOpen:()=>void;button?:string}){
 return <section className="cockpitCard" aria-labelledby={`card-${id}`}><header><div className="cockpitTitle"><Icon kind={id}/><div><h2 id={`card-${id}`}>{title}</h2><p>{subtitle}</p></div></div><span className="cockpitFrequency">{frequency} · {day?day.slice(5).replace('-','/'):'待更新'}{status==='stale'?' · 延迟':''}</span></header><div className="cockpitBody">{children}</div><footer><span>{status==='stale'?'数据更新滞后，暂不判断当前状态':''}</span><button onClick={onOpen} aria-label={`查看${title}详情`}>{button} <span aria-hidden="true">↗</span></button></footer></section>
}
function Conclusion({reading}:{reading:Reading}){
 return <><div className="marketConclusion" data-level={reading.tone}><i/>{reading.level}</div><p className="marketConclusionExplain">{reading.explanation}</p>{reading.evidence.length>0&&<div className="marketEvidence">{reading.evidence.map(e=><div key={e.label}><span>{e.label}</span><strong>{e.value}</strong></div>)}</div>}<div className="marketDirection"><b>{reading.direction.arrow} {reading.direction.label}</b><span>{reading.direction.detail}</span></div></>
}
function GroupHeading({id,title,subtitle}:{id:string;title:string;subtitle:string}){return <header className="marketFrequencyHeading"><h2 id={id}>{title}</h2><p>{subtitle}</p></header>}

export function MarketView({cockpit,sample,targetDate}:{cockpit:CockpitReport|null;sample:SampleReport|null;targetDate:string}){
 const [detail,setDetail]=useState<string|null>(null),[contractIndex,setContractIndex]=useState(0),[window,setWindow]=useState(63);
 const valid=cockpit?.schema_version==='market-cockpit-v1'&&cockpit.as_of===targetDate;
 const panel=(key:string)=>{const p=valid?cockpit.panels[key]:null;return p&&(!p.observation_date||p.observation_date<=targetDate)?p:null};
 const usable=(p:Panel|null)=>!!p&&p.status!=='unavailable'&&!!p.observation_date;
 const current=(p:Panel|null)=>usable(p)&&p?.status==='available';
 const flows=panel('flows'),margin=panel('margin'),options=panel('options'),positions=panel('positions'),quotes=panel('quotes');
 const contract=usable(positions)?positions?.contracts?.[contractIndex]:null;
 const pos=contract?.history.at(-1),priorPos=contract?.history.at(-2),posHistory=contract?.history.slice(-52)??[];
 const savedHistory=sample?.as_of===targetDate?sample.history.filter(s=>s.date<=targetDate):[];
 const latest=savedHistory.at(-1)?.date===targetDate?savedHistory.at(-1):null;
 const previous=savedHistory.at(-6),history=savedHistory.slice(-window);
 const breadth=history.map(s=>complete(s)&&s.indicators.ad_line?.reliable?s.indicators.ad_line.value:null);
 const base=breadth.find(finite),breadthLine={label:'累计上涨家数减下跌家数',color:BLUE,values:breadth.map(v=>finite(v)&&finite(base)?v-base:null)};
 const upLine={label:'上涨股票占比',color:BLUE,values:history.map(s=>complete(s)?s.counts.advances/s.quality.valid_ticker_count*100:null)};
 const highLines=[{label:'新高',color:TEAL,values:history.map(s=>complete(s)&&s.indicators.new_high_low?.reliable?s.counts.new_highs:null)},{label:'新低',color:RED,values:history.map(s=>complete(s)&&s.indicators.new_high_low?.reliable?s.counts.new_lows:null)}];
 const funds=current(quotes)?quotes?.funds??[]:[],spy=funds.find(f=>f.ticker==='SPY');
 const relativeDates=spy?.history.slice(-window).map(r=>r.date)??[];
 const relativeLines=['RSP','IWM'].map((id,i)=>{const fund=funds.find(f=>f.ticker===id),rows=fund?.history.slice(-window)??[],benchmark=spy?.history.slice(-window)??[];const baseRatio=rows[0]&&benchmark[0]?rows[0].value/benchmark[0].value:null;return {label:i?'小盘 / 标普':'等权 / 标普',color:i?PURPLE:BLUE,values:rows.map((r,n)=>baseRatio&&benchmark[n]?.date===r.date?r.value/benchmark[n].value/baseRatio*100:null)}});
 const sectors=funds.filter(f=>!['SPY','RSP','IWM'].includes(f.ticker));
 const strongest=[...sectors].sort((a,b)=>b.returns['5']-a.returns['5']).slice(0,3),weakest=[...sectors].sort((a,b)=>a.returns['5']-b.returns['5']).slice(0,3);
 const optionLast=current(options)?options?.history?.at(-1):null;
 const reading:Record<string,Reading>={breadth:participation(latest,previous),highs:breakouts(latest,previous),relative:leadership(funds),sectors:sectorReading(funds),positions:current(positions)?positionReading(contract):unavailable('仓位数据缺失或发布延迟，暂不判断当前方向。'),margin:current(margin)?marginReading(margin):unavailable('融资数据缺失或发布延迟，暂不判断当前方向。')};
 const titles:Record<string,string>={flows:'资金流向',positions:'机构仓位',margin:'市场融资',options:'期权成交结构',breadth:'市场参与',highs:'市场突破',relative:'市场领导力',sectors:'行业扩散'};
 const descriptions:Record<string,string>={
  flows:'美国国内股票基金与 ETF 的周度净流入估计。正数为净流入，负数为净流出；不是整个股市的买卖资金总量。近4周仅在四周连续时合计。',
  positions:'杠杆基金与资产管理机构分开观察；期货可能用于对冲，不能代表机构全部股票仓位。历史位置比较此前最多156周，至少需要52周；80%表示高于此前约80%的记录，不是上涨概率。',
  margin:'客户融资余额按月发布，通常滞后到次月第三周。包含个人与机构客户，不能识别纯散户仓位。图中单位为十亿美元，主卡T表示万亿美元。',
  options:'Customer包含个人和机构账户，不代表散户。这里是客户、券商自营、做市商的分类成交占比，不是净买入、成交金额或持仓；不据此判断看涨或看跌。历史从真实日度记录积累。',
  breadth:'固定样本来自现有行情缓存，不代表整个美股市场。早期历史为当前成员回看，有存续和覆盖偏差。累计线起点设为0，只看参与方向。',
  highs:'新高、新低按过去252个交易日高低点比较；两组并非互斥。固定样本不代表整个美股市场。',
  relative:'等权标普和小盘 ETF 分别除以标普500 ETF，历史图共同起点设为100。线往上表示相对标普更强。使用同源、同日的复权价格。',
  sectors:'11个基本行业 ETF 与行业页的主题 ETF 范围不同。涨跌幅和相对收益都从保存的同源复权价格计算；颜色表示正负，不是买卖信号。'};
 const open=(id:string)=>()=>setDetail(id);
 const series=(p:Panel|null,label:string,color=BLUE):Line[]=>[{label,color,values:usable(p)?p?.history?.map(r=>r.value)??[]:[]}];
 const periodButtons=<div className="cockpitTabs" role="group" aria-label="参与趋势区间">{[[21,'1个月'],[63,'3个月'],[126,'6个月']].map(([n,label])=><button key={n} aria-pressed={window===n} onClick={()=>setWindow(Number(n))}>{label}</button>)}</div>;
 const detailData=detail==='flows'?{dates:flows?.history?.map(r=>r.date)??[],lines:series(flows,'周净流入'),unit:'十亿美元'}:detail==='margin'?{dates:margin?.history?.map(r=>r.date)??[],lines:series(margin,'融资余额'),unit:'十亿美元'}:detail==='options'?{dates:options?.history?.map(r=>r.date)??[],lines:series(options,'客户成交占比'),unit:'%'}:detail==='positions'?{dates:posHistory.map(r=>r.date),lines:[{label:'杠杆基金',color:BLUE,values:posHistory.map(r=>r.leveraged)},{label:'资产管理',color:TEAL,values:posHistory.map(r=>r.asset)}],unit:'%'}:detail==='breadth'?{dates:history.map(r=>r.date),lines:[upLine],unit:'%'}:detail==='highs'?{dates:history.map(r=>r.date),lines:highLines,unit:'家'}:detail==='relative'?{dates:relativeDates,lines:relativeLines,unit:'起点100'}:null;
 const sourcePanel=detail==='relative'||detail==='sectors'?quotes:detail?panel(detail):null;
 const flowCard=<Card id="flows" title={titles.flows} subtitle="美国股票基金 + ETF" frequency="每周" date={flows?.observation_date} status={flows?.status} onOpen={open('flows')}>
  {current(flows)?<><div className="marketConclusion" data-level="neutral">{(flows?.value??0)>0?'本周净流入':(flows?.value??0)<0?'本周净流出':'本周净流量为零'}</div><div className="marketEvidence"><div><span>本周 · 十亿美元</span><strong>{sign(flows?.value)}</strong></div><div><span>连续4周 · 十亿美元</span><strong>{sign(flows?.sum_4w)}</strong></div></div></>:<Missing panel={flows}/>}
 </Card>;
 const heatmap=<div className="cockpitHeatmap" role="table" aria-label="行业ETF涨跌幅"><div role="row"><span role="columnheader">行业</span>{['1日','5日','20日'].map(t=><span role="columnheader" key={t}>{t}</span>)}</div>{sectors.map(f=><div role="row" key={f.ticker}><span role="rowheader">{f.label}<small>{f.ticker}</small></span>{['1','5','20'].map(n=><span role="cell" key={n} data-sign={f.returns[n]>0?'positive':f.returns[n]<0?'negative':'flat'}>{pct(f.returns[n])}</span>)}</div>)}</div>;
 const marketRead=[
  {date:targetDate,frequency:'每日',text:['breadth','relative','highs','sectors'].filter(id=>reading[id].available).map(id=>`${titles[id]}：${reading[id].level}`).join('；')},
  {date:positions?.observation_date,frequency:'每周',text:reading.positions.available?`${contract?.label}：${reading.positions.explanation}`:''},
  {date:margin?.observation_date,frequency:'每月',text:reading.margin.available?`${reading.margin.level}。${reading.margin.explanation}`:''},
 ].filter(r=>r.text);
 return <div className="marketDashboard cockpit marketSummaryPage">
  <div className="cockpitToolbar"><span>收盘日 <b>{targetDate}</b><small>各模块按自己的发布频率更新</small></span><span className="marketReadingOrder">每日 → 每周 → 每月</span></div>
  <section aria-labelledby="daily-market"><GroupHeading id="daily-market" title="每日 · 市场内部" subtitle="先看当前状态，再看最近变化"/><div className="cockpitGrid">
   <Card id="breadth" title={titles.breadth} subtitle={`SV Fixed Universe · ${num(latest?.quality.universe_size,0)} stocks`} frequency="每日" date={latest?.date} onOpen={open('breadth')}><Conclusion reading={reading.breadth}/><p className="cockpitNote">固定样本，不代表整个美股市场</p></Card>
   <Card id="relative" title={titles.relative} subtitle="等权、小盘与标普比较" frequency="每日" date={quotes?.observation_date} onOpen={open('relative')}><Conclusion reading={reading.relative}/></Card>
   <Card id="highs" title={titles.highs} subtitle={`52周可比样本 · ${num(latest?.indicators.new_high_low?.valid_count,0)}只`} frequency="每日" date={latest?.date} onOpen={open('highs')}><Conclusion reading={reading.highs}/></Card>
   <Card id="sectors" title={titles.sectors} subtitle="11个基本行业 ETF" frequency="每日" date={quotes?.observation_date} onOpen={open('sectors')} button="查看全部"><Conclusion reading={reading.sectors}/>{reading.sectors.available&&<div className="marketSectorShortlist">{[['最强3个',strongest],['最弱3个',weakest]].map(([label,items])=><div key={String(label)}><h3>{String(label)}<span>近5日</span></h3>{(items as typeof sectors).map(f=><p key={f.ticker}><span>{f.label}</span><b data-positive={f.returns['5']>0}>{pct(f.returns['5'])}</b></p>)}</div>)}</div>}</Card>
  </div></section>
  <section className="marketRead" aria-label="市场概况"><h2>市场概况</h2>{marketRead.length?marketRead.map(r=><p key={r.frequency}><span>{r.frequency} · {r.date}</span>{r.text}</p>):<p>有效数据不足，暂不生成市场判断。</p>}<small>状态描述已有事实；颜色与箭头不代表买卖信号。</small></section>
  <details className="marketSecondary"><summary><span>每日辅助 · 期权成交结构</span><small>账户类别成交占比 · {options?.observation_date??'待更新'}</small></summary><Card id="options" title={titles.options} subtitle="辅助观察，不参与核心市场结论" frequency="每日" date={options?.observation_date} status={options?.status} onOpen={open('options')}>
   {optionLast?<div className="cockpitAccountMix" aria-label="客户、券商自营、做市商成交占比">{[['客户 Customer',optionLast.customer,BLUE],['自营 Firm',optionLast.firm,PURPLE],['做市商 Market Maker',optionLast.market_maker,'#aab8ca']].map(([label,v,color])=><div key={String(label)}><span>{label}</span><div><i style={{width:`${Number(v)/(optionLast.total||1)*100}%`,background:String(color)}}/></div><b>{num(Number(v)/(optionLast.total||1)*100)}%</b></div>)}</div>:<Missing panel={options}/>}<p className="cockpitNote">Customer包含个人和机构账户，不代表散户；成交量不等于仓位。</p>{optionLast&&(options?.history?.length??0)<2&&<p className="cockpitNote">已有1个交易日记录，历史逐日积累。</p>}</Card></details>
  <section aria-labelledby="weekly-market"><GroupHeading id="weekly-market" title="每周 · 机构仓位" subtitle="报告日期与日度行情不同，分开观察"/><div className="cockpitGrid marketSlowerGrid">
   <Card id="positions" title={titles.positions} subtitle="股指期货净敞口" frequency="每周" date={positions?.observation_date} status={positions?.status} onOpen={open('positions')}>
    {positions?.contracts&&<div className="cockpitTabs" role="group" aria-label="期货合约">{positions.contracts.map((c,i)=><button key={c.code} aria-pressed={contractIndex===i} onClick={()=>setContractIndex(i)}>{c.label}</button>)}</div>}<Conclusion reading={reading.positions}/>{reading.positions.available&&pos&&<p className="marketAuxiliary">资产管理：{pos.asset>0?'净多':pos.asset<0?'净空':'净仓为零'} {pct(pos.asset)}{priorPos&&reading.positions.direction.label!=='待比较'?` · 较上周 ${sign(pos.asset-priorPos.asset)}个百分点`:''}</p>}
   </Card>{current(flows)&&flowCard}
  </div></section>
  <section aria-labelledby="monthly-market"><GroupHeading id="monthly-market" title="每月 · 融资背景" subtitle="更新较慢，用来观察融资规模"/><div className="cockpitGrid marketSlowerGrid"><Card id="margin" title={titles.margin} subtitle="客户证券融资账户" frequency="每月" date={margin?.observation_date} status={margin?.status} onOpen={open('margin')}><Conclusion reading={reading.margin}/><p className="cockpitNote">FINRA customer margin accounts · 不代表纯散户</p></Card></div></section>
  <details className="marketTrendSection"><summary>趋势与详情 <span>需要时再展开</span></summary><div className="marketTrendToolbar"><p>日度趋势统一区间；周度保留近一年历史。</p>{periodButtons}</div><div className="cockpitGrid">
   <article><h3>市场参与 · 上涨占比</h3><p className="cockpitNote">当前 {num(upLine.values.at(-1))}% · {reading.breadth.direction.label}</p><Chart dates={history.map(r=>r.date)} lines={[upLine]} unit="%"/></article>
   <article><h3>市场领导力 · 共同起点100</h3><p className="cockpitNote">上升表示相对标普更强 · {reading.relative.direction.label}</p><Chart dates={relativeDates} lines={relativeLines}/></article>
   <article><h3>机构仓位 · {contract?.label??'等待数据'}</h3><p className="cockpitNote">杠杆基金历史位置 {num(contract?.percentiles.leveraged,0)}% · 此前{contract?.percentile_weeks??0}周 · {reading.positions.direction.label}</p><Chart dates={posHistory.map(r=>r.date)} lines={[{label:'杠杆基金',color:BLUE,values:posHistory.map(r=>r.leveraged)},{label:'资产管理',color:TEAL,values:posHistory.map(r=>r.asset)}]} unit="%" zero/></article>
   <article><h3>行业扩散 · 近20日相对标普</h3><div className="marketSectorRelative">{sectors.map(f=>{const v=spy?((1+f.returns['20']/100)/(1+spy.returns['20']/100)-1)*100:null;return <div key={f.ticker}><span>{f.label}</span><b>{pct(v)}</b></div>})}</div></article>
  </div></details>
  {!current(flows)&&<section aria-labelledby="pending-market"><GroupHeading id="pending-market" title="待接通的数据" subtitle="缺失保持空白，恢复后按频率归位"/>{flowCard}</section>}
  {detail&&<Drawer title={titles[detail]} onClose={()=>setDetail(null)}><p className="cockpitExplanation">{descriptions[detail]}</p>{reading[detail]&&<p className="marketMethodNote">{reading[detail].basis}</p>}{detail==='positions'&&contract&&<div className="marketEvidence">{(['leveraged','asset'] as const).map((key,i)=><div key={key}><span>{i?'资产管理':'杠杆基金'} · 此前{contract.percentile_weeks}周历史位置</span><strong>{num(contract.percentiles[key],0)}%</strong></div>)}</div>}{detailData&&<><Chart dates={detailData.dates} lines={detailData.lines} unit={detailData.unit} bars={detail==='flows'} zero={detail==='flows'}/><DataTable {...detailData}/></>}{detail==='breadth'&&<><h3 className="marketDetailSubheading">累计上涨减下跌 · 只看方向</h3><Chart dates={history.map(r=>r.date)} lines={[breadthLine]} unit="家" zero/><p className="cockpitNote">平盘 {latest?.counts.unchanged??'—'} 只；累计线已将图中起点设为0。</p></>}{detail==='sectors'&&heatmap}<details className="marketSourceDetails"><summary>数据口径与记录</summary><p>页面核对收盘日：{targetDate}。观察日期：{sourcePanel?.observation_date??latest?.date??'未取得'}。</p>{sourcePanel?.sources?.length?sourcePanel.sources.map(s=><div key={s.sha256}><a href={s.url} target="_blank" rel="noreferrer">{s.provider}</a><p>读取：{s.fetched_at}</p><code>{s.sha256}</code></div>):<p>{detail==='breadth'||detail==='highs'?'固定样本的已保存行情统计，非全市场。':'本次未取得可核验来源记录。'}</p>}</details><p className="cockpitNote">周报、月报保留实际统计日期。状态和变化只是事实描述，不是预测。</p></Drawer>}
 </div>
}
export default function MarketDashboard(){
 const {reports,loading,refresh}=useDailyData(PATHS);
 const targetDate=(reports[PATHS[0]] as {source_latest_complete_date?:string}|null)?.source_latest_complete_date??'';
 return <TrackerShell active="大盘" title="大盘" subtitle="先看每日参与，再看周度仓位与月度融资。" overview><div className="mvpPageTitle"><div><h1>大盘</h1><p>先看结论，再看证据</p></div><button className="mvpRefresh" onClick={refresh}>↻ 刷新</button></div>{loading?<p className="marketLoading" role="status">正在读取今日快照…</p>:!targetDate?<div className="marketError" role="alert">暂时无法核对收盘日，请刷新重试。</div>:<MarketView cockpit={reports[PATHS[1]] as CockpitReport|null} sample={reports[PATHS[2]] as SampleReport|null} targetDate={targetDate}/>}</TrackerShell>
}
