'use client';
import type {SignalRow} from './signal-rows';

// One real signal drawn from its ticket: weekly candles, the falling highs, the flat bottoms, the
// signal week, then the limit, stop and 3R target. Pure CSS timing (see .fvCandle etc. in
// terminal.css), so it replays whenever the parent changes its key. `compact` is the card version:
// the last 40 weeks, no axis, and today's price as a white dot so the card still shows where it is.
export default function SignalChart({r,en,compact=false}:{r:SignalRow;en:boolean;compact?:boolean}) {
 const c=r.chart;
 if(!c||c.bars.length<2)return null;
 const bars=compact?c.bars.slice(-40):c.bars, n=bars.length;
 const W=compact?320:600, H=compact?132:320, P=compact?6:10, RIGHT=compact?92:118, BOTTOM=compact?4:16;
 const top=Math.max(...bars.map(b=>b[2])), now=compact?r.close:null;
 // Price fills the frame; a target far above is pinned to the top edge with an arrow.
 const lo=Math.min(...bars.map(b=>b[3]),r.stop,now??Infinity), hi=Math.max(top,now??-Infinity,Math.min(r.target,top*1.12));
 const y=(v:number)=>P+(hi-v)/(hi-lo)*(H-2*P-BOTTOM), bw=(W-RIGHT)/n, x=(i:number)=>i*bw+bw/2;
 const at=(d:string)=>{const k=bars.findIndex(b=>b[0]>=d);return k<0?n-1:k};
 const seen=(d:string)=>d>=bars[0][0];
 const last=n-1, trend=c.trend.filter(p=>seen(p[0])), t0=trend[0]??c.trend[0], t1=c.trend.at(-1);
 const level=(v:number)=>Math.max(P,Math.min(H-P-BOTTOM,y(v)));
 const bottoms=c.bottoms.filter(p=>seen(p[0])), flat=bottoms.length?Math.min(...bottoms.map(b=>b[1])):null;
 const step=compact?10:16, size=compact?3:4.5;
 const levels=[['target',r.target,en?(compact?'3R':'target 3R'):(compact?'3R':'目标 3R'),2.1],['limit',r.limit,en?'limit':'挂单',2.25],['stop',r.stop,en?'stop':'止损',2.4]] as const;
 return <svg className="fvChart" data-compact={compact||undefined} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={en?`${r.symbol} weekly chart: the triangle, limit, stop and target`:`${r.symbol} 周线：三角形、挂单、止损和目标`}>
  {bars.map((b,i)=>{const up=b[4]>=b[1];return <g key={b[0]} className="fvCandle" data-up={up||undefined} style={{animationDelay:`${i*step}ms`}}>
   <line x1={x(i)} x2={x(i)} y1={y(b[2])} y2={y(b[3])}/><rect x={x(i)-bw*.32} width={bw*.64} y={y(Math.max(b[1],b[4]))} height={Math.max(1,Math.abs(y(b[1])-y(b[4])))}/></g>})}
  {t0&&t1&&seen(t1[0])&&(()=>{const i0=at(t0[0]),i1=at(t1[0]),slope=(t1[1]-t0[1])/Math.max(1,i1-i0);return <line className="fvTrend" x1={x(i0)} y1={y(t0[1])} x2={x(last)} y2={y(t0[1]+slope*(last-i0))}/>})()}
  {flat!==null&&<line className="fvFlat" x1={x(at(bottoms[0][0]))} x2={x(last)} y1={y(flat)} y2={y(flat)}/>}
  {c.pushes.filter(p=>seen(p[0])).map((p,k)=><circle key={p[0]} className="fvDot" data-kind="push" cx={x(at(p[0]))} cy={y(p[1])} r={size} style={{animationDelay:`${1.05+k*.12}s`}}/>)}
  {bottoms.map((p,k)=><circle key={p[0]} className="fvDot" data-kind="bottom" cx={x(at(p[0]))} cy={y(p[1])} r={size} style={{animationDelay:`${1.35+k*.12}s`}}/>)}
  <circle className="fvRing" cx={x(last)} cy={y(bars[last][4])} r={compact?6:9}/>
  {levels.map(([kind,v,label,delay])=><g key={kind} className="fvLevel" data-kind={kind} style={{animationDelay:`${delay}s`}}>
   <line x1={x(last)} x2={W-4} y1={level(v)} y2={level(v)}/><text x={W-4} y={level(v)-4} textAnchor="end">{label} {v.toFixed(2)}{y(v)<P?' ↑':''}</text></g>)}
  {/* Today's price as a white dot past the signal week; its number is in the card header. */}
  {now!==null&&<g className="fvNow" style={{animationDelay:'2.6s'}}><circle cx={W-RIGHT+8} cy={level(now)} r="4"/></g>}
  {!compact&&<><text className="fvAxis" x="2" y={H-2}>{bars[0][0].slice(0,7)}</text>
   <text className="fvAxis" x={x(last)} y={H-2} textAnchor="middle">{r.week.slice(5)}</text></>}
 </svg>;
}
