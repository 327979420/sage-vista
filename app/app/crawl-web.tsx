'use client';
import {useEffect,useMemo,useState,type MouseEvent} from 'react';
import {sharedJson} from '../json-cache';

// The daily candidate scan as a spider web: every dot is one stock the scan reviewed (public
// cr056-ranking.json). The closer to the centre, the further it got; a radar sweep lights the
// web on each visit. Nothing here is simulated: positions are fixed per stock, colours are its result.
type Review = {symbol:string; rank:number|null; status:string; reason_codes?:string[]};
type Ranking = {as_of:string; reviews:Review[]};
type Dot = {sym:string; ring:number; rank:number|null; why:string|null; status:string; th:number; x:number; y:number};

const RINGS:Record<number,[number,number]> = {1:[18,32],2:[37,45],3:[50,82],4:[87,95]};
const ringOf = (r:Review) => r.rank!==null&&r.rank<=5?0:r.status==='scored'||r.status==='partial'?1:r.status==='not_nominated'?2:r.status==='excluded'?3:4;
const hash = (s:string) => {let h=2166136261;for(const ch of s){h^=ch.charCodeAt(0);h=Math.imul(h,16777619)}return (h>>>0)/4294967296};
const polar = (r:number,th:number) => [100+r*Math.sin(th*Math.PI/180),100-r*Math.cos(th*Math.PI/180)];
const REASONS:Record<string,[string,string]> = {
 monthly_not_confirmed:['月线没确认','monthly not confirmed'], structure_broken:['结构破坏','structure broken'],
 daily_tradability_not_met:['日线成交不够','daily liquidity too low'], near_observed_history_high:['接近历史高点','near its high'],
 monthly_high_zone:['月线高位','monthly high zone'], no_available_background:['没有可用背景','no usable background'],
 completed_months_below_61:['月线历史不足','too little monthly history'], no_confirmed_reversal_entry:['没有确认的反转入场','no confirmed reversal'],
 weekly_not_confirmed:['周线没确认','weekly not confirmed'], empty_invalid_or_old_cache:['数据为空或过旧','data missing or old'],
};

function layout(reviews:Review[]) {
 const groups:Record<number,Review[]>={0:[],1:[],2:[],3:[],4:[]};
 reviews.forEach(r=>groups[ringOf(r)].push(r));
 const dots:Dot[]=[];
 for(const k of [1,2,3,4]){const g=groups[k],[r0,r1]=RINGS[k];g.forEach((r,i)=>{const th=(((i+0.5+(hash(r.symbol)-0.5)*0.8)/g.length)*360+360)%360,[x,y]=polar(r0+hash(r.symbol+'#')*(r1-r0),th);dots.push({sym:r.symbol,ring:k,rank:r.rank,why:r.reason_codes?.[0]??null,status:r.status,th,x,y})})}
 groups[0].sort((a,b)=>(a.rank??0)-(b.rank??0)).forEach((r,i)=>{const th=36+i*72,[x,y]=polar(10,th);dots.push({sym:r.symbol,ring:0,rank:r.rank,why:null,status:r.status,th,x,y})});
 const path=(ring:number)=>dots.filter(d=>d.ring===ring).map(d=>`M${d.x.toFixed(2)} ${d.y.toFixed(2)}h.01`).join('');
 let web='';
 for(let s=0;s<24;s++){const [a,b]=polar(6,s*15),[c,d]=polar(97,s*15);web+=`M${a.toFixed(2)} ${b.toFixed(2)}L${c.toFixed(2)} ${d.toFixed(2)}`}
 for(const r of [15,34.5,47.5,84.5,97])for(let s=0;s<=24;s++){const [a,b]=polar(r,s*15);web+=`${s?'L':'M'}${a.toFixed(2)} ${b.toFixed(2)}`}
 const counts=[0,1,2,3,4].map(k=>k?groups[k].length:groups[0].length);
 return {dots,web,counts,tops:dots.filter(d=>d.ring===0),paths:[1,2,3,4].map(path)};
}

export default function CrawlWeb({en}:{en:boolean}) {
 const [data,setData]=useState<Ranking|null>(null);
 const [hover,setHover]=useState<number>(-1);
 const [run,setRun]=useState(0);
 useEffect(()=>{let active=true;void sharedJson<Ranking>('/cr056-ranking.json').then(d=>{if(active&&d&&Array.isArray(d.reviews))setData(d)});return()=>{active=false}},[]);
 const web=useMemo(()=>data?layout(data.reviews):null,[data]);
 if(!data||!web)return null;
 const h=hover>=0?web.dots[hover]:null;
 const statusName=(d:Dot)=>d.ring===0?(en?`#${d.rank} · picked`:`#${d.rank} · 入选`):d.ring===1?(en?`#${d.rank} · ranked`:`#${d.rank} · 进入排名`):d.ring===2?(en?'not nominated':'没被提名'):d.ring===3?(en?'excluded':'排除'):(en?'data unavailable':'数据不可用');
 const onMove=(e:MouseEvent<HTMLDivElement>)=>{const r=e.currentTarget.getBoundingClientRect(),x=(e.clientX-r.left)/r.width*200,y=(e.clientY-r.top)/r.height*200;let best=-1,bd=16;web.dots.forEach((d,i)=>{const dd=(d.x-x)**2+(d.y-y)**2;if(dd<bd){bd=dd;best=i}});if(best!==hover)setHover(best)};
 const legend:[string,string,number][]=[[en?'Picked (top 5)':'入选前 5','#ffffff',web.counts[0]],[en?'Ranked':'进入排名','var(--t-go)',web.counts[0]+web.counts[1]],[en?'Not nominated':'没被提名','#7cc4ff',web.counts[2]],[en?'Excluded':'排除','#5c6670',web.counts[3]],[en?'Data unavailable':'数据不可用','var(--t-loss)',web.counts[4]]];
 const total=data.reviews.length;
 return <section className="ovPanel ovWeb" aria-label={en?'Daily candidate scan':'每日候选扫描'}>
  <header><small>{en?`03 · Daily scan web · ${data.as_of} · ${total} stocks`:`03 · 每日扫描网 · ${data.as_of} · ${total} 只股票`}</small><button type="button" onClick={()=>setRun(v=>v+1)}>↻ {en?'Sweep again':'再扫一遍'}</button></header>
  <div className="ovWebBody">
   <div className="ovWebStage" onMouseMove={onMove} onMouseLeave={()=>setHover(-1)}>
    <svg viewBox="0 0 200 200" aria-hidden="true"><path d={web.web} fill="none" stroke="#1a2128" strokeWidth=".35"/>
     {web.paths.map((p,i)=><path key={i} d={p} stroke={i===3?'#3a2620':'#1f272f'} strokeWidth={i===0?1.8:i===1?1.3:1.1} strokeLinecap="round"/>)}</svg>
    <div className="ovSweep" key={run}>
     <div className="ovBeam"/>
     <div className="ovLit"><svg viewBox="0 0 200 200" aria-hidden="true">
      {web.paths.map((p,i)=><path key={i} d={p} stroke={['var(--t-go)','#7cc4ff','#5c6670','var(--t-loss)'][i]} strokeOpacity={i===3?.7:1} strokeWidth={i===0?1.8:i===1?1.3:1.1} strokeLinecap="round"/>)}
      <path d={web.tops.map(d=>`M100 100L${d.x.toFixed(2)} ${d.y.toFixed(2)}`).join('')} stroke="#fff" strokeOpacity=".35" strokeWidth=".3"/>
      <path d={web.tops.map(d=>`M${d.x.toFixed(2)} ${d.y.toFixed(2)}h.01`).join('')} stroke="#fff" strokeWidth="3" strokeLinecap="round"/></svg>
      {web.tops.map(d=><span key={d.sym} className="ovTop" style={{left:`${d.x/2}%`,top:`${d.y/2}%`,transform:`translate(${d.x>=100?'8px':'calc(-100% - 8px)'},-50%)`}}>#{d.rank} {d.sym}</span>)}
     </div>
    </div>
    <span className="ovCore"/>
    {h&&<span className="ovHover" style={{left:`${h.x/2}%`,top:`${h.y/2}%`}}/>}
   </div>
   <div className="ovWebSide">
    <p className="ovWebLead">{en?'Each dot is a real stock from today’s scan. The closer to the centre, the further it got. Point at any dot.':'每个点是今天扫描过的一只真实股票，越靠中心走得越远。指向任意一点看是哪只。'}</p>
    <ul className="ovLegend">{legend.map(([label,color,n])=><li key={label}><i style={{background:color}}/>{label}<b>{n}</b></li>)}</ul>
    <div className="ovWebHover" aria-live="polite">{h?<><b>{h.sym}</b><span>{statusName(h)}</span>{h.why&&REASONS[h.why]&&<small>{REASONS[h.why][en?1:0]}</small>}</>:<span>{en?'Point at a dot':'指向任意一点'}</span>}</div>
   </div>
  </div>
 </section>;
}
