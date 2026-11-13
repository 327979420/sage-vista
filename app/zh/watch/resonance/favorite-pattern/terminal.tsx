'use client';
import {useEffect,useState} from 'react';
import {useLocale} from '../../../../i18n/locale';

// Daily setups, terminal view: every setup as a small chart (close, support zone, falling push
// line, invalidation level), coloured by stage. Clicking one opens it in the viewer below.
type Bar = {date:string; close:number};
type Anchor = {date:string; price:number};
export type SetupRow = {symbol:string; state:string; price:number; invalidation_price:number; chart:Bar[];
 bottom:{anchors:Anchor[]; zone_lower:number; zone_upper:number}; three_push:{anchors:Anchor[]}|null; liquidity:{dollar_volume:number}};
type Props = {asOf:string; rows:SetupRow[]; counts:Record<string,number>; covered:number; onPick:(symbol:string,state:string)=>void};

function Mini({row}:{row:SetupRow}) {
 const bars=row.chart.slice(-70), lows=[...bars.map(b=>b.close),row.bottom.zone_lower,row.invalidation_price], highs=[...bars.map(b=>b.close),...(row.three_push?.anchors.map(a=>a.price)??[])];
 const lo=Math.min(...lows)*0.99, hi=Math.max(...highs)*1.01, n=bars.length;
 const X=(i:number)=>i/(n-1)*100, Y=(v:number)=>100-(v-lo)/(hi-lo)*100, idx=(d:string)=>bars.findIndex(b=>b.date===d);
 const push=(row.three_push?.anchors??[]).map(a=>[idx(a.date),a.price] as const).filter(([i])=>i>=0);
 const line=bars.map((b,i)=>`${i?'L':'M'}${X(i).toFixed(2)} ${Y(b.close).toFixed(2)}`).join('');
 return <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
  <rect x="0" width="100" y={Y(row.bottom.zone_upper)} height={Math.max(0.5,Y(row.bottom.zone_lower)-Y(row.bottom.zone_upper))} className="dsZone"/>
  <line x1="0" x2="100" y1={Y(row.invalidation_price)} y2={Y(row.invalidation_price)} className="dsStop" vectorEffect="non-scaling-stroke"/>
  {push.length>=2&&<line x1={X(push[0][0])} y1={Y(push[0][1])} x2={100} y2={Y(push[0][1]+(push[push.length-1][1]-push[0][1])/(push[push.length-1][0]-push[0][0]||1)*(n-1-push[0][0]))} className="dsPush" vectorEffect="non-scaling-stroke"/>}
  <path d={line} className="dsLine" vectorEffect="non-scaling-stroke"/>
 </svg>;
}

export default function SetupWall({asOf,rows,counts,covered,onPick}:Props) {
 const {locale}=useLocale(), en=locale==='en';
 const [ready,setReady]=useState(false);
 useEffect(()=>{const t=setTimeout(()=>setReady(true),120);return()=>clearTimeout(t)},[]);
 const total=Object.values(counts).reduce((a,b)=>a+b,0)||1;
 const stages:[string,string,string,string][]=[['unconfirmed','底部未确认','Bottom not confirmed','#5c6670'],['waiting','等待突破','Waiting to break out','var(--t-wait)'],['broken_out','已突破','Broken out','var(--t-go)']];
 const sorted=[...rows].sort((a,b)=>(a.state==='waiting'?0:1)-(b.state==='waiting'?0:1)||b.liquidity.dollar_volume-a.liquidity.dollar_volume);
 return <div className="ovRoot">
  <section className="ovHead"><div>
   <small>{en?`Candidates · Daily setups · ${asOf}`:`候选 · 形态 · ${asOf}`}</small>
   <h1>{en?`${counts.waiting??0} setups waiting to break out, ${counts.broken_out??0} already through.`:`${counts.waiting??0} 只等待突破，${counts.broken_out??0} 只已经突破。`}</h1>
   <p>{en?`From the 100 most-traded of ${covered.toLocaleString()} covered stocks: three-push pullbacks onto confirmed multi-bottom support. Click a chart to open it.`:`在 ${covered.toLocaleString()} 只已覆盖股票里成交最活跃的 100 只中，找三推回调、多底支撑。点任意一张图打开看。`}</p>
  </div></section>
  <div className="dsStages" aria-label={en?'Stages':'阶段'}>{stages.map(([k,zh,enL,c])=><div key={k} style={{flex:`${ready?(counts[k]??0)/total*100:33} 1 0`,borderTopColor:c}}><b style={{color:c}}>{counts[k]??0}</b><span>{en?enL:zh}</span></div>)}</div>
  <div className="dsWall">{sorted.map((r,i)=><button key={r.symbol} type="button" className="dsCard" data-state={r.state} onClick={()=>onPick(r.symbol,r.state)} style={{animationDelay:`${i*40}ms`}}>
   <span className="dsTop"><b>{r.symbol}</b><em>{r.state==='waiting'?(en?'waiting':'等突破'):r.state==='broken_out'?(en?'broken out':'已突破'):r.state}</em></span>
   <Mini row={r}/>
   <span className="dsFoot"><span>${r.price.toFixed(2)}</span><span>{en?'stop':'失效'} ${r.invalidation_price.toFixed(2)}</span></span>
  </button>)}</div>
  <p className="mfListLabel">{en?'Viewer · full chart, bottoms and push dates':'看图 · 完整日线、底部和三推日期'}</p>
 </div>;
}
