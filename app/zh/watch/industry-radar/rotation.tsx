'use client';
import {useEffect,useState} from 'react';
import {useLocale} from '../../../i18n/locale';

// Sectors, rotation and browser: every scored theme on a map of longer-term vs recent strength
// against SPY (four quadrants: leading, fading, lagging, improving), and a sortable list where
// each theme opens to show its numbers and member stocks, with today's candidates marked.
export type ScoredTheme = {theme_id:string; name:string; state:string; strength_percentile:number|null; relative_5d:number|null; relative_20d:number|null; relative_60d:number|null;
 return_20d:number|null; breadth_above_sma50:number|null; breadth_positive_20d:number|null; breadth_change_10d:number|null};
type Props = {themes:ScoredTheme[]; members:Record<string,string[]>; etfs:Record<string,string>; candidates:string[]; names:Record<string,string>; selected:string|null; onSelect:(id:string)=>void};
const QUADS:[string,string,string,string][] = [['lead','领涨','Leading','var(--t-go)'],['fade','走弱','Fading','var(--t-wait)'],['lag','落后','Lagging','var(--t-loss)'],['improve','改善','Improving','#7cc4ff']];
const quad = (t:ScoredTheme,recent:'relative_20d'|'relative_5d') => {const long=(t.relative_60d??0)>=0, now=(t[recent]??0)>=0;return long?(now?0:1):(now?3:2)};
const pct = (v:number|null,d=1) => v===null?'—':`${v>0?'+':v<0?'−':''}${Math.abs(v*100).toFixed(d)}%`;
const SORTS:[keyof ScoredTheme,string,string][] = [['strength_percentile','强度','Strength'],['relative_20d','20 日相对','20d vs SPY'],['relative_5d','5 日相对','5d vs SPY'],['breadth_above_sma50','广度','Breadth']];

export default function SectorRotation({themes,members,etfs,candidates,names,selected,onSelect}:Props) {
 const {locale}=useLocale(), en=locale==='en';
 const [recent,setRecent]=useState<'relative_20d'|'relative_5d'>('relative_20d');
 const [sort,setSort]=useState<keyof ScoredTheme>('strength_percentile');
 const [open,setOpen]=useState<string|null>(null);
 const [quadFilter,setQuadFilter]=useState<number|null>(null);
 const [focus,setFocus]=useState<string|null>(null);
 const choose=(id:string)=>{setFocus(id);onSelect(id)};
 const [ready,setReady]=useState(false);
 useEffect(()=>{const t=setTimeout(()=>setReady(true),150);return()=>clearTimeout(t)},[]);
 const usable=themes.filter(t=>t.relative_60d!==null&&t[recent]!==null);
 if(usable.length<3)return null;
 const name=(t:ScoredTheme)=>en?t.name:names[t.theme_id]??t.name;
 const xs=usable.map(t=>Math.abs(t.relative_60d!)), ys=usable.map(t=>Math.abs(t[recent]!));
 const xMax=Math.max(0.02,...xs)*1.15, yMax=Math.max(0.01,...ys)*1.15;
 const X=(v:number)=>50+v/xMax*44, Y=(v:number)=>50-v/yMax*40;

 const counts=QUADS.map((_,i)=>usable.filter(t=>quad(t,recent)===i).length);
 const listed=[...usable].filter(t=>quadFilter===null||quad(t,recent)===quadFilter).sort((a,b)=>((b[sort] as number|null)??-9)-((a[sort] as number|null)??-9));
 const cand=new Set(candidates);
 const picked=usable.find(t=>t.theme_id===focus)??usable.find(t=>t.theme_id===selected)??listed[0];
 const toggle=(id:string)=>{setOpen(open===id?null:id);choose(id)};
 return <>
  <section className="ovPanel" aria-label={en?'Rotation map':'轮动地图'}>
   <header><small>{en?'Rotation map · each theme against SPY · point at a dot':'轮动地图 · 每个主题对比 SPY · 指向任意一点'}</small>
    <span className="fwSpans"><button type="button" aria-pressed={recent==='relative_20d'} onClick={()=>setRecent('relative_20d')}>{en?'recent = 20d':'近期 = 20 日'}</button><button type="button" aria-pressed={recent==='relative_5d'} onClick={()=>setRecent('relative_5d')}>{en?'recent = 5d':'近期 = 5 日'}</button></span></header>
   <div className="roBody">
    <div className="roMap">
     <i className="roAxisX"/><i className="roAxisY"/>
     {QUADS.map(([k,zh,enL,c],i)=><button key={k} type="button" className="roQuad" data-q={k} aria-pressed={quadFilter===i} onClick={()=>setQuadFilter(quadFilter===i?null:i)} style={{color:c}}>{en?enL:zh} · {counts[i]}</button>)}
     {usable.map(t=>{const q=QUADS[quad(t,recent)], b=t.breadth_above_sma50??0.5;return <button key={t.theme_id} type="button" className="roDot" data-on={t.theme_id===picked?.theme_id||undefined} data-dim={quadFilter!==null&&quad(t,recent)!==quadFilter||undefined}
      aria-label={`${name(t)} ${pct(t.relative_60d)} / ${pct(t[recent])}`} onMouseEnter={()=>choose(t.theme_id)} onFocus={()=>choose(t.theme_id)} onClick={()=>toggle(t.theme_id)}
      style={{left:`${ready?X(t.relative_60d!):50}%`,top:`${ready?Y(t[recent]!):50}%`,background:q[3],width:`${10+b*14}px`,height:`${10+b*14}px`}}><span>{etfs[t.theme_id]??name(t)}</span></button>})}
    </div>
    <div className="roSide">
     {picked?<>
      <b className="roName">{name(picked)} <em>{etfs[picked.theme_id]}</em></b>
      <span className="roQuadTag" style={{color:QUADS[quad(picked,recent)][3]}}>{QUADS[quad(picked,recent)][en?2:1]}</span>
      <dl className="roNums">
       <div><dt>{en?'60d vs SPY':'60 日相对'}</dt><dd data-tone={(picked.relative_60d??0)>=0?'go':'loss'}>{pct(picked.relative_60d)}</dd></div>
       <div><dt>{en?'20d vs SPY':'20 日相对'}</dt><dd data-tone={(picked.relative_20d??0)>=0?'go':'loss'}>{pct(picked.relative_20d)}</dd></div>
       <div><dt>{en?'5d vs SPY':'5 日相对'}</dt><dd data-tone={(picked.relative_5d??0)>=0?'go':'loss'}>{pct(picked.relative_5d)}</dd></div>
       <div><dt>{en?'Above 50-day':'站上 50 日线'}</dt><dd>{picked.breadth_above_sma50===null?'—':`${Math.round(picked.breadth_above_sma50*100)}%`}</dd></div>
      </dl>
      <p className="roHint">{en?'Right = stronger than SPY over 60 days; up = stronger recently. Bigger dot = more members above their 50-day line.':'越靠右：60 日比 SPY 强；越靠上：近期比 SPY 强。点越大：站上 50 日线的成分股越多。'}</p>
     </>:<p className="roHint">{en?'Point at a theme to read it.':'指向一个主题看数字。'}</p>}
    </div>
   </div>
   <p className="mkFoot"><span>{en?'weaker over 60 days':'60 日弱于 SPY'}</span><span>{en?'click a quadrant to filter the list below':'点象限名可以筛选下面的列表'}</span><span>{en?'stronger over 60 days':'60 日强于 SPY'}</span></p>
  </section>
  <section className="ovPanel" aria-label={en?'Theme browser':'主题浏览'}>
   <header><small>{en?`Theme browser · ${listed.length} themes${quadFilter!==null?` · ${QUADS[quadFilter][2]}`:''} · click a row to open it`:`主题浏览 · ${listed.length} 个${quadFilter!==null?` · ${QUADS[quadFilter][1]}`:''} · 点一行展开`}</small>
    <span className="fwSpans">{SORTS.map(([k,zh,enL])=><button key={k} type="button" aria-pressed={sort===k} onClick={()=>setSort(k)}>{en?enL:zh}</button>)}</span></header>
   <ul className="roList">{listed.map(t=>{const q=QUADS[quad(t,recent)], ms=members[t.theme_id]??[], hits=ms.filter(m=>cand.has(m));return <li key={t.theme_id} data-open={open===t.theme_id||undefined}>
    <button type="button" className="roRow" aria-expanded={open===t.theme_id} onClick={()=>toggle(t.theme_id)} onMouseEnter={()=>choose(t.theme_id)}>
     <span className="roRowName"><b>{name(t)}</b><em>{etfs[t.theme_id]}</em></span>
     <span className="roBar"><i style={{width:`${ready?t.strength_percentile??0:0}%`,background:q[3]}}/></span>
     <span className="roCell" data-tone={(t.relative_20d??0)>=0?'go':'loss'}>{pct(t.relative_20d)}</span>
     <span className="roCell roHideS">{t.breadth_above_sma50===null?'—':`${Math.round(t.breadth_above_sma50*100)}%`}</span>
     <span className="roCell" style={{color:q[3]}}>{q[en?2:1]}</span>
     <span className="roCell roHideS">{hits.length?(en?`${hits.length} candidates`:`${hits.length} 只候选`):''}</span>
    </button>
    {open===t.theme_id&&<div className="roOpen">
     <dl className="roNums">
      <div><dt>{en?'Theme return 20d':'主题 20 日涨跌'}</dt><dd data-tone={(t.return_20d??0)>=0?'go':'loss'}>{pct(t.return_20d)}</dd></div>
      <div><dt>{en?'60d vs SPY':'60 日相对'}</dt><dd data-tone={(t.relative_60d??0)>=0?'go':'loss'}>{pct(t.relative_60d)}</dd></div>
      <div><dt>{en?'Members up over 20d':'20 日上涨的成分股'}</dt><dd>{t.breadth_positive_20d===null?'—':`${Math.round(t.breadth_positive_20d*100)}%`}</dd></div>
      <div><dt>{en?'Breadth change 10d':'广度 10 日变化'}</dt><dd data-tone={(t.breadth_change_10d??0)>=0?'go':'loss'}>{t.breadth_change_10d===null?'—':`${t.breadth_change_10d>=0?'+':'−'}${Math.abs(Math.round(t.breadth_change_10d*100))} pt`}</dd></div>
     </dl>
     <p className="roHint">{en?`${ms.length} member stocks${hits.length?`; on today’s multi-factor list: ${hits.join(', ')}`:''}.`:`${ms.length} 只成分股${hits.length?`；今天在多因子榜上的：${hits.join('、')}`:''}。`}</p>
     <div className="roChips">{ms.map(m=>cand.has(m)?<a key={m} href={`/zh/watch/resonance/rare-opportunities?symbol=${m}`} data-hit="true">{m}</a>:<span key={m}>{m}</span>)}</div>
    </div>}
   </li>})}</ul>
  </section>
 </>;
}
