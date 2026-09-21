"use client";
import {useEffect,useState} from "react";
import {TrackerShell} from "../resonance/tracker-ui";

type Level={label:string;tone:string};
type Indicator={value:number|null;valid_count:number;reliable:boolean;level:Level;risk:number|null;change_1d:number|null;change_5d:number|null;trend:string;percentile:number|null;percentile_samples:number};
type Snapshot={date:string;recorded_at?:string;observation_kind:string;spy:number|null;explanation:string;quality:{status:string;reasons:string[];universe_size:number;valid_ticker_count:number;missing_ticker_count:number;coverage:number};temperature:{score:number|null;status:Level;change_1d:number|null;change_5d:number|null;subscores:Record<string,{score:number|null;weight:number}>};indicators:Record<string,Indicator>;counts:{advances:number;declines:number;unchanged:number;new_highs:number;new_lows:number}};
type Spec={label:string;group:string;unit:string;formula:string};
type Report={schema_version:string;as_of:string;universe:{name:string;observed_at:string;members:string[];common_list_count:number;limitation:string};config:{version:string;indicators:Record<string,Spec>;subscores:Record<string,{label:string;weight:number}>;indicator_order:string[];temperature_bands:{maximum:number;label:string;tone:string}[]};history:Snapshot[]};
const GROUPS=[['BREADTH','多少股票在参与'],['PARTICIPATION','成交是否活跃'],['LEADERSHIP','上涨是否集中'],['STRUCTURE','股票之间有多分化']] as const;
const PERIODS=[['1M',21],['3M',63],['6M',126],['1Y',252]] as const;
function num(v:number|null,digits=1){return v===null||!Number.isFinite(v)?'—':v.toLocaleString('en-US',{minimumFractionDigits:digits,maximumFractionDigits:digits})}
function delta(v:number|null,unit=''){return v===null?'—':`${v>0?'↑ +':v<0?'↓ ':'→ '}${num(v)}${unit}`}
function Sparkline({values,label}:{values:(number|null)[];label:string}){
 const data=values.filter((v):v is number=>v!==null);if(data.length<2)return <span className="marketSparkEmpty">趋势积累中</span>;
 const low=Math.min(...data),high=Math.max(...data),span=high-low||1;
 const points=values.map((v,i)=>v===null?null:`${i/(values.length-1)*140},${32-(v-low)/span*28}`);
 const segments:string[][]=[];for(const p of points){if(p===null){segments.push([])}else{if(!segments.length)segments.push([]);segments.at(-1)!.push(p)}}
 return <svg className="marketSpark" viewBox="0 0 140 36" role="img" aria-label={label}>{segments.map((p,i)=><polyline key={i} points={p.join(' ')} fill="none" stroke="currentColor" strokeWidth="2"/>)}</svg>
}

type Line={label:string;color:string;values:(number|null)[]};
function TrendChart({title,description,dates,lines,fixedRange}:{title:string;description:string;dates:string[];lines:Line[];fixedRange?:[number,number]}){
 const [hover,setHover]=useState<number|null>(null);
 const all=lines.flatMap(l=>l.values).filter((v):v is number=>v!==null);
 const low=fixedRange?.[0]??Math.floor(Math.min(...all,100)-2), high=fixedRange?.[1]??Math.ceil(Math.max(...all,100)+2),span=high-low||1;
 const left=44,right=870,top=24,bottom=188, x=(i:number)=>left+i/Math.max(dates.length-1,1)*(right-left), y=(v:number)=>bottom-(v-low)/span*(bottom-top);
 const active=hover!==null&&hover<dates.length?hover:dates.length-1;
 return <article className="marketChart"><header><h3>{title}</h3><p>{description}</p></header>
  <div className="marketChartLegend">{lines.map(l=><span key={l.label}><i style={{background:l.color}}/>{l.label} <b>{num(l.values[active]??null)}</b></span>)}<time>{dates[active]}</time></div>
  {all.length<2?<p className="marketChartEmpty">有效历史不足，正在积累。数据缺口不会补成零。</p>:<svg viewBox="0 0 900 220" role="img" aria-label={`${title}，${dates[0]}至${dates.at(-1)}`} onMouseLeave={()=>setHover(null)}>
   {[0,1,2,3,4].map(i=>{const v=low+span*i/4;return <g key={i}><line x1={left} x2={right} y1={y(v)} y2={y(v)} stroke="#e6ebe8"/><text x={left-10} y={y(v)+4} textAnchor="end">{num(v,0)}</text></g>})}
   {lines.map(l=>{const segments:string[][]=[];l.values.forEach((v,i)=>{if(v===null){segments.push([])}else{if(!segments.length)segments.push([]);segments.at(-1)!.push(`${x(i)},${y(v)}`)}});return <g key={l.label}>{segments.map((s,i)=><polyline key={i} points={s.join(' ')} fill="none" stroke={l.color} strokeWidth="2.3" strokeLinejoin="round"/>)}</g>})}
   {dates.map((d,i)=><rect key={d} x={x(i)-(right-left)/Math.max(dates.length,1)/2} y={top} width={(right-left)/Math.max(dates.length-1,1)} height={bottom-top} fill="transparent" onMouseEnter={()=>setHover(i)}><title>{d+'\n'+lines.map(l=>l.label+': '+num(l.values[i])).join('\n')}</title></rect>)}
   {hover!==null&&hover<dates.length&&<line x1={x(hover)} x2={x(hover)} y1={top} y2={bottom} stroke="#899b94" strokeDasharray="3 3"/>}
   <text x={left} y="212">{dates[0]}</text><text x={right} y="212" textAnchor="end">{dates.at(-1)}</text>
  </svg>}
 </article>
}

function Card({id,spec,item,history,latest}:{id:string;spec:Spec;item:Indicator;history:Snapshot[];latest:Snapshot}){
 const value=id==='new_high_low'?`${latest.counts.new_highs} / ${latest.counts.new_lows}`:num(item.value,id==='rsp_spy'?3:id==='ad_line'?0:1);
 const changeUnit=spec.unit==='%'||id==='new_high_low'?'百分点':id==='rsp_spy'?'%':spec.unit;
 return <article className="marketSignal" data-tone={item.reliable?item.level.tone:'neutral'}>
  <header><h3>{spec.label}</h3><span className="marketLevel">{item.level.label}</span></header>
  <div className="marketSignalValue"><strong>{value}</strong>{id!=='new_high_low'&&<small>{spec.unit}</small>}</div>
  <div className="marketSignalTrend"><span>5日 {delta(item.change_5d,changeUnit)}</span><b data-worse={['恶化','压力升高'].includes(item.trend)} data-better={['改善','压力下降'].includes(item.trend)}>{item.trend}</b></div>
  <div className="marketSignalBottom"><small>1日 {delta(item.change_1d,changeUnit)}<br/>{id==='ad_line'?'累计线只看方向':item.percentile===null?'历史分位：样本不足':`历史分位 ${num(item.percentile,0)}%`}</small><Sparkline values={history.slice(-21).map(s=>s.indicators[id].reliable?s.indicators[id].value:null)} label={`${spec.label}最近21个交易日趋势`}/></div>
  <details><summary>怎么看这个指标</summary><p>{spec.formula}。</p><p>有效样本 {item.valid_count}；历史分位是当前值在此前有效记录中的位置，不是风险概率。{id==='rsp_spy'?'状态按比值5日涨跌判断。':''}{id==='new_high_low'?'变化与趋势使用净新高占比（新高减新低）。':''}{id==='ad_line'?'累计起点为本系列首日；这里只解释方向，不用绝对值判断风险。':''}</p></details>
 </article>
}

export default function MarketDashboard(){
 const [report,setReport]=useState<Report|null>(null),[error,setError]=useState(''),[attempt,setAttempt]=useState(0),[period,setPeriod]=useState(126);
 useEffect(()=>{let active=true;Promise.all([fetch('/market-internals.json',{cache:'no-store'}),fetch('/update-status.json',{cache:'no-store'})]).then(async([r,s])=>{if(!r.ok||!s.ok)throw new Error('暂时读不到大盘数据，请稍后重试。');const data=await r.json(),status=await s.json();if(data.schema_version!=='market-internals-public-v1'||!data.history?.length)throw new Error('大盘数据格式不完整，暂不显示风险温度。');if(data.as_of!==status.source_latest_complete_date)throw new Error(`大盘数据仍在 ${data.as_of}，正在等待与最新收盘日同步。`);if(active){setReport(data);setError('')}}).catch(e=>{if(active)setError(e instanceof Error&&e.message.startsWith('大盘')?e.message:'暂时读不到大盘数据，请稍后重试。')});return()=>{active=false}},[attempt]);
 const latest=report?.history.at(-1), temp=latest?.temperature,history=report?.history.slice(-period)??[];
 const dates=history.map(s=>s.date), safe=(id:string)=>history.map(s=>s.indicators[id].reliable?s.indicators[id].value:null);
 const spyStart=history.find(s=>s.spy!==null&&s.indicators.above50.reliable&&s.indicators.above50.value!==null&&s.indicators.above50.value>0);
 const norm=(value:number|null,base:number|null|undefined)=>value===null||!base?null:value/base*100;
 return <TrackerShell active="大盘" title="大盘" subtitle="Market Overview · 看市场内部，有多少股票在一起走。">
  <div className="marketDashboard">
   {error?<div className="marketError" role="alert"><h2>大盘数据暂不可用</h2><p>{error}</p><button onClick={()=>{setError('');setAttempt(n=>n+1)}}>重新读取</button></div>:!report||!latest||!temp?<p role="status" className="marketLoading">正在读取大盘日终快照…</p>:<>
    <section className="marketTemperature" data-tone={temp.status.tone} aria-label="Market Temperature">
     <div className="marketTemperatureMain"><p className="marketEyebrow">MARKET TEMPERATURE <span>市场风险温度</span></p><div className="marketScore"><strong>{num(temp.score,1)}</strong><span>/ 100</span><b>{temp.status.label}</b></div><h2>{latest.explanation}</h2><p className="marketScoreNote">分数越高，综合压力越大。NORMAL 不代表所有指标健康，也不是涨跌预测。</p>
      <div className="marketTemperatureFoot"><span>今日 <b>{delta(temp.change_1d)}</b></span><span>5日 <b>{delta(temp.change_5d)}</b></span><span>收盘 <b>{report.as_of}</b></span></div>
     </div>
     <aside className="marketDimensions"><h3>压力来自哪里</h3>{['extension','breadth','participation','leadership'].map(id=>{const s=temp.subscores[id];const tone=s.score===null?'neutral':report.config.temperature_bands.find(b=>s.score!==null&&s.score<=b.maximum)?.tone??'neutral';return <div key={id} data-tone={tone}><span>{report.config.subscores[id].label}<small>{num(s.weight*100,0)}%</small></span><b>{num(s.score,0)}</b><meter min="0" max="100" value={s.score??0} aria-label={`${report.config.subscores[id].label} ${num(s.score,0)}`}/></div>})}</aside>
    </section>
    <section className="marketCoverage" aria-label="数据覆盖"><div><b>{report.universe.name}</b><span>有效 {latest.quality.valid_ticker_count.toLocaleString()} / {latest.quality.universe_size.toLocaleString()} 只 · {num(latest.quality.coverage*100,1)}%</span><span className="marketCoverageState" data-complete={latest.quality.status==='complete'}>{latest.quality.status==='complete'?'样本覆盖达标':'数据不完整'}</span></div><p>这批股票来自现有行情缓存，<strong>不代表整个美股市场</strong>，也不是选股候选池。{latest.quality.reasons.length>0&&latest.quality.reasons.join('；')+'。'}</p><details><summary>范围与更新时间</summary><p>{report.universe.limitation} 成员于 {report.universe.observed_at} 冻结。普通股名录 {report.universe.common_list_count.toLocaleString()} 只；本面板不是该名录的完整覆盖。</p><p>本页记录时间：{latest.recorded_at?new Date(latest.recorded_at).toLocaleString('zh-CN',{timeZone:'Australia/Melbourne',hour12:false})+'（墨尔本）':'未提供'}。缺失 {latest.quality.missing_ticker_count} 只；不同指标所需历史长度不同，有效数量在各卡片中显示。</p></details></section>
    <div className="marketSignalsHeading"><h2>市场参与信号</h2><p><span className="marketColorKey" data-tone="green"/>正常 / 健康 <span className="marketColorKey" data-tone="yellow"/>留意 <span className="marketColorKey" data-tone="orange"/>压力升高 <span className="marketColorKey" data-tone="red"/>极端压力</p></div>
    {GROUPS.map(([group,label])=><section className="marketGroup" key={group}><header><h2>{label}</h2><small>{group}</small></header><div className="marketCards">{report.config.indicator_order.filter(id=>report.config.indicators[id].group===group).map(id=><Card key={id} id={id} spec={report.config.indicators[id]} item={latest.indicators[id]} history={report.history} latest={latest}/>)}</div></section>)}
    <section className="marketHistory"><header className="marketHistoryHeading"><div><p className="marketEyebrow">THE BIGGER PICTURE</p><h2>把今天放回趋势里</h2></div><div className="marketPeriods" role="group" aria-label="历史区间">{PERIODS.map(([label,n])=><button key={label} aria-pressed={period===n} onClick={()=>setPeriod(n)}>{label}</button>)}</div></header>
     <p className="marketHistoryNotice">{report.history.some(s=>s.observation_kind==='reconstructed_current_membership')?'初始历史由当前固定成员回看得出，存在存续和覆盖偏差，并非当时已记录的全市场状态。':'历史为逐日保存的观察快照。'} 现有 {report.history.length} 个交易日；缺失处留空，未来每天追加。</p>
     <TrendChart title="市场风险温度" description="分数上升表示压力增加；历史不足时不生成温度。" dates={dates} fixedRange={[0,100]} lines={[{label:'风险温度',color:'#b5682f',values:history.map(s=>s.temperature.score)}]}/>
     <TrendChart title="市场广度" description="看短、中、长期有多少股票站在均线上方。" dates={dates} fixedRange={[0,100]} lines={[{label:'高于20日均线 %',color:'#567dca',values:safe('above20')},{label:'高于50日均线 %',color:'#28735c',values:safe('above50')},{label:'高于200日均线 %',color:'#ac8851',values:safe('above200')}]}/>
     <TrendChart title="SPY 与内部参与" description="共同有效起点设为100。若SPY上升、50日广度下降，指数和内部参与正在背离。" dates={dates} lines={[{label:'SPY（起点100）',color:'#536a97',values:history.map(s=>spyStart&&s.date>=spyStart.date?norm(s.spy,spyStart.spy):null)},{label:'50日广度（起点100）',color:'#28735c',values:history.map(s=>spyStart&&s.date>=spyStart.date&&s.indicators.above50.reliable?norm(s.indicators.above50.value,spyStart.indicators.above50.value):null)}]}/>
    </section>
    <details className="marketMethod"><summary>风险温度怎么计算</summary><p>将各指标按自己的风险解释换算，再按四个维度加权。长期广度高通常是健康；短期广度极高可能是过热，不使用“数值越高越红”的统一规则。</p><p>{Object.values(report.config.subscores).map(s=>`${s.label} ${s.weight*100}%`).join(' · ')}。权重与阈值是V1观察规则，尚未用收益验证。</p><p>{report.config.temperature_bands.map((b,i)=>`${i===0?0:report.config.temperature_bands[i-1].maximum+1}–${b.maximum} ${b.label}`).join(' · ')}</p><a href="/market-internals.json">下载当前快照与计算配置</a></details>
   </>}
  </div>
 </TrackerShell>
}
