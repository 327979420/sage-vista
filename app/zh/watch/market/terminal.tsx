'use client';
import {useEffect,useState} from 'react';
import {useLocale} from '../../../i18n/locale';

// Market, terminal view: four numbers for the day, 30 sessions of breadth you can scrub through,
// and a heatmap of 17 reference funds. Everything comes from the published daily files.
type Snapshot = {date:string; spy:number; indicators:Record<string,{value:number|null}|undefined>; counts?:{advances:number;declines:number}; temperature?:{score:number|null;status?:{label:string}}};
export type Internals = {history:Snapshot[]};
export type External = {indicators:{vix?:{value:number;change_previous:number|null;observation_date:string}}};
type Fund = {ticker:string; name:string; return_1d:number; return_5d:number; return_20d:number};
export type Watch = {as_of:string; funds:Fund[]};
export type Today = {market:{breadth:number|null;breadth_sample:number|null;light:string|null}; signal_week:string};
type Props = {internals:Internals|null; external:External|null; watch:Watch|null; today:Today|null};

const FUND_EN:Record<string,string> = {SPY:'S&P 500',QQQ:'Nasdaq 100',DIA:'Dow Jones',IWM:'Russell 2000',RSP:'S&P 500 equal weight',MDY:'S&P MidCap 400',VTI:'Total US market',IWD:'Russell 1000 Value',IWF:'Russell 1000 Growth',MTUM:'US momentum',QUAL:'US quality',USMV:'US min volatility',HYG:'High-yield bonds',LQD:'Investment-grade bonds',TLT:'Long Treasuries',GLD:'Gold',UUP:'US dollar'};
const GROUPS:[string,string,string[]][] = [['大盘','Broad market',['SPY','VTI','DIA','QQQ','RSP']],['规模','Size',['IWM','MDY']],['风格','Style',['IWD','IWF','MTUM','QUAL','USMV']],['债券','Bonds',['HYG','LQD','TLT']],['避险','Safe havens',['GLD','UUP']]];
const BANDS:[string,number,string][] = [['CALM',30,'var(--t-go)'],['NORMAL',50,'var(--t-go)'],['ELEVATED',65,'var(--t-wait)'],['HOT',80,'var(--t-loss)'],['EXTREME',100,'#ff5c5c']];
const signed = (v:number,d=2) => `${v>0?'+':v<0?'−':''}${Math.abs(v).toFixed(d)}`;
const LINES:[string,string,string,string][] = [['above200','200 日','200-day','#e6e9ec'],['above50','50 日','50-day','var(--t-go)'],['above20','20 日','20-day','#7cc4ff']];

export default function MarketTerminal({internals,external,watch,today}:Props) {
 const {locale}=useLocale(), en=locale==='en';
 const [sel,setSel]=useState<number|null>(null);
 const [show,setShow]=useState<Record<string,boolean>>({above200:true,above50:true,above20:false});
 const [span,setSpan]=useState(0);
 const [redUp,setRedUp]=useState(false);
 const [fund,setFund]=useState('SPY');
 const [ready,setReady]=useState(false);
 useEffect(()=>{const t=setTimeout(()=>setReady(true),150);return()=>clearTimeout(t)},[]);
 const hist=(internals?.history??[]).slice(-30);
 if(hist.length<2)return null;
 const last=hist[hist.length-1], prev=hist[hist.length-2], spyChg=(last.spy/prev.spy-1)*100;
 const adv=last.counts?.advances??0, dec=last.counts?.declines??0, upShare=adv+dec?adv/(adv+dec):0.5;
 const temp=last.temperature?.score??null, tempLabel=last.temperature?.status?.label??'';
 const vix=external?.indicators.vix;
 const mood=upShare<0.35?(en?'most stocks fell':'多数股票下跌'):upShare>0.65?(en?'most stocks rose':'多数股票上涨'):(en?'a mixed day':'涨跌互现');
 // Breadth chart: share of the sample above each moving average, scaled to 20–70%.
 const lo=20,hi=70,n=hist.length, X=(i:number)=>(i+0.5)/n*100, Y=(v:number)=>100-(Math.max(lo,Math.min(hi,v))-lo)/(hi-lo)*100;
 const path=(k:string)=>hist.map((h,i)=>{const v=h.indicators[k]?.value;return v==null?'':`${i?'L':'M'}${X(i).toFixed(2)} ${Y(v).toFixed(2)}`}).join(' ');
 const at=sel??n-1, row=hist[at];
 const val=(k:string)=>row.indicators[k]?.value;
 // Heatmap: colour by return over the chosen span; up colour follows the viewer's habit.
 const cap=[3,8,10][span], up=redUp?[246,53,56]:[48,204,90], down=redUp?[48,204,90]:[246,53,56], flat=[65,69,84];
 const mix=(v:number)=>{const k=Math.min(Math.abs(v)/cap,1),to=v>=0?up:down;return `rgb(${flat.map((c,i)=>Math.round(c+(to[i]-c)*k)).join(',')})`};
 const ret=(f:Fund)=>[f.return_1d,f.return_5d,f.return_20d][span]*100;
 const byT=Object.fromEntries((watch?.funds??[]).map(f=>[f.ticker,f]));
 const spanWord=en?['that day','those 5 days','those 20 days'][span]:['这一天','这 5 天','这 20 天'][span];
 const hf=byT[fund], gate=today?.market;
 return <div className="ovRoot">
  <section className="ovHead"><div>
   <small>{en?`Market · ${last.date}`:`市场 · 大盘 · ${last.date}`}</small>
   <h1>{en?`${last.date.slice(5)}: ${mood}.`:`${last.date.slice(5)}：${mood}。`}</h1>
   <p>{en?'One question on this page: is the market with us or against us? All numbers are from the daily close.':'这一页只回答一个问题：市场现在顺不顺。数字都来自每天收盘后的真实数据。'}</p>
  </div></section>
  <div className="mkKpis">
   <div className="ovPanel"><small>{en?'SPY close':'SPY 收盘'}</small><b>{last.spy.toFixed(2)}</b><span data-tone={spyChg>=0?'go':'loss'}>{signed(spyChg)}% {en?'on the day':'单日'}</span></div>
   <div className="ovPanel"><small>{en?'VIX · 30-day fear gauge':'VIX · 30 天波动预期'}</small><b>{vix?vix.value.toFixed(2):'—'}</b><span data-tone={vix&&vix.change_previous!==null&&vix.change_previous>0?'loss':'go'}>{vix&&vix.change_previous!==null?`${signed(vix.change_previous)} ${en?'vs previous':'比上一日'}`:'—'}</span></div>
   <div className="ovPanel"><small>{en?'Up : down stocks':'上涨 : 下跌 家数'}</small><b><em data-tone="go">{adv}</em> <i>:</i> <em data-tone="loss">{dec}</em></b>
    <div className="mkSplit"><span style={{width:`${ready?upShare*100:50}%`}}/><span style={{width:`${ready?(1-upShare)*100:50}%`}}/></div></div>
   <div className="ovPanel"><small>{en?'Risk temperature':'风险温度'}</small><b>{temp===null?'—':temp.toFixed(1)} <em data-tone="go">{tempLabel}</em></b>
    <div className="mkBands">{BANDS.map(([label,max,color],i)=><i key={label} title={label} style={{flex:max-(i?BANDS[i-1][1]:0),background:color,opacity:label===tempLabel?1:.25}}/>)}{temp!==null&&<span style={{left:`${ready?temp:0}%`}}/>}</div></div>
  </div>
  <div className="ovGrid mkGrid">
   <section className="ovPanel" aria-label={en?'Breadth':'广度'}>
    <header><small>{en?`Breadth · last ${n} sessions · point at a day`:`广度 · 最近 ${n} 个交易日 · 指向任意一天`}</small>
     <span className="fwSpans">{LINES.map(([k,zh,enL,color])=><button key={k} type="button" aria-pressed={show[k]} onClick={()=>setShow({...show,[k]:!show[k]})}><i style={{color}}>━</i> {en?enL:zh}</button>)}</span></header>
    <p className="mkRead"><b>{row.date}</b> SPY <em>{row.spy.toFixed(2)}</em>{LINES.map(([k,zh,enL,color])=><span key={k}>{en?enL:zh} <em style={{color}}>{val(k)==null?'—':`${val(k)!.toFixed(1)}%`}</em></span>)}{row.counts&&<span>{en?'up/down':'涨/跌'} <em>{row.counts.advances}/{row.counts.declines}</em></span>}</p>
    <div className="mkChart" onMouseLeave={()=>setSel(null)}>
     <span className="mkHalf" style={{top:`${Y(50)}%`}}><em>50%</em></span>
     <svg className="mkLines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">{LINES.map(([k,,,color])=><path key={k} d={path(k)} className="mkLine" fill="none" stroke={color} strokeOpacity={show[k]?1:0} strokeWidth={k==='above200'?2:1.4} vectorEffect="non-scaling-stroke"/>)}</svg>
     <i className="mkCross" style={{left:`${X(at)}%`}}/>
     <div className="mkCols">{hist.map((h,i)=><button key={h.date} type="button" aria-label={`${h.date} ${h.indicators.above200?.value?.toFixed(1)??'—'}%`} onMouseEnter={()=>setSel(i)} onFocus={()=>setSel(i)} onClick={()=>setSel(i)}/>)}</div>
    </div>
    <p className="mkFoot"><span>{hist[0].date.slice(5)}</span><span>{en?'Fixed sample of about 1,160 US stocks':'约 1,160 只美股固定样本'}</span><span>{last.date.slice(5)}</span></p>
   </section>
   {watch&&<section className="ovPanel" aria-label={en?'Fund heatmap':'基金热力图'}>
    <header><small>{en?'Who held up · 17 funds':'谁扛住了 · 17 只基金'}</small>
     <span className="fwSpans">{(en?['1 day','5 days','20 days']:['1 日','5 日','20 日']).map((label,i)=><button key={label} type="button" aria-pressed={i===span} onClick={()=>setSpan(i)}>{label}</button>)}</span></header>
    <div className="mkHeat">{GROUPS.map(([zh,enName,ts])=><div key={zh}><small>{en?enName:zh}</small><div>{ts.filter(t=>byT[t]).map(t=>{const v=ret(byT[t]);return <button key={t} type="button" className="mkTile" aria-pressed={t===fund} onMouseEnter={()=>setFund(t)} onFocus={()=>setFund(t)} onClick={()=>setFund(t)} style={{background:ready?mix(v):`rgb(${flat.join(',')})`}}><b>{t}</b><span>{signed(v)}%</span></button>})}</div></div>)}</div>
    <div className="mkHeatFoot">{hf&&<span><b>{hf.ticker}</b> {en?`${FUND_EN[hf.ticker]??hf.ticker}: ${ret(hf)>=0?'up':'down'} ${Math.abs(ret(hf)).toFixed(2)}% over ${spanWord}.`:`${hf.name}，${spanWord}${ret(hf)>=0?'涨了':'跌了'} ${Math.abs(ret(hf)).toFixed(2)}%。`}</span>}
     <button type="button" onClick={()=>setRedUp(!redUp)}>{redUp?(en?'Red up · green down ⇄':'红涨绿跌 ⇄'):(en?'Green up · red down ⇄':'绿涨红跌 ⇄')}</button></div>
   </section>}
  </div>
  {gate&&gate.breadth!==null&&<section className="ovPanel mkGate" aria-label={en?'What it means for 3W':'对 3W 意味着什么'}>
   <header><small>{en?'What it means for 3W':'对 3W 意味着什么'}</small><span data-tone={gate.light==='green'?'go':'wait'}>{gate.light==='green'?(en?'Gate green':'闸门绿灯'):(en?'Gate amber':'闸门黄灯')}</span></header>
   <p>{en?`The 3W gate uses its own pool of ${gate.breadth_sample} stocks: ${(gate.breadth*100).toFixed(1)}% are above their 200-day line now. Orders are judged on the signal week, so a single bad day only matters for that week's signals.`:`3W 闸门看的是它自己的 ${gate.breadth_sample} 只股票池：现在 ${(gate.breadth*100).toFixed(1)}% 站上 200 日线。下单看的是信号那一周，所以某一天大跌只影响那一周的信号。`}</p>
  </section>}
 </div>;
}
