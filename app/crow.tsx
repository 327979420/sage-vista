'use client';
import {useEffect,useState} from 'react';
import {usePathname} from 'next/navigation';
import {useLocale} from './i18n/locale';
import {sharedJson} from './json-cache';

// SV's guide: a crow perched in the corner of every page. It blinks and tilts its head; click it
// for a tip about the page you are on, one live fact from today's published data, and where to go
// next. It greets each page once per browser (after the welcome tour) and can be tucked away.
// A low-poly wireframe crow drawn only with light: a glowing outline with a pulse running
// along it, faint inner facets, flickering vertices, a lit eye and a hologram scan line.
const P = {B:[3,50],A:[28,40],C:[29,56],H1:[37,31],H2:[52,30],H3:[61,38],K1:[75,50],K2:[93,62],T1:[118,87],T2:[114,96],T3:[97,91],
 U1:[82,87],U2:[63,91],U3:[46,83],N1:[35,69],N2:[31,60],W:[61,63],W2:[87,75]} as const;
type V = keyof typeof P;
const OUTLINE:V[] = ['B','A','H1','H2','H3','K1','K2','T1','T2','T3','U1','U2','U3','N1','N2','C','B'];
const FACETS:[V,V][] = [['A','N2'],['H1','N2'],['H2','N2'],['H3','N2'],['H3','N1'],['H3','W'],['W','K1'],['W','N1'],['W','U3'],['W','W2'],['W2','K1'],['W2','K2'],['W2','T3'],['W2','U1'],['W2','U2'],['W','U2'],['K2','T3'],['A','C'],['W2','T1']];
const pts = (vs:V[]) => vs.map(v=>P[v].join(',')).join(' ');
export function CrowArt({className}:{className?:string}) {
 return <svg className={className} viewBox="0 0 120 110" aria-hidden="true">
  <defs>
   <filter id="crowGlow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="1.8" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
   <linearGradient id="crowScan" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#5fe1ff" stopOpacity="0"/><stop offset=".5" stopColor="#5fe1ff" stopOpacity=".55"/><stop offset="1" stopColor="#5fe1ff" stopOpacity="0"/></linearGradient>
   <clipPath id="crowShape"><polygon points={pts(OUTLINE)}/></clipPath>
  </defs>
  <g className="crowPerch" filter="url(#crowGlow)">
   <path d="M4 100 H44 L50 96 H116" fill="none" stroke="#5fd38a" strokeWidth=".9" strokeOpacity=".7"/>
   <path className="crowPerchPulse" d="M4 100 H44 L50 96 H116" fill="none" stroke="#c8ffe0" strokeWidth="1.4" pathLength={1}/>
   <circle cx="44" cy="100" r="1.4" fill="#5fd38a"/><circle cx="116" cy="96" r="1.4" fill="#5fd38a"/>
  </g>
  <g className="crowBody">
   <polygon points={pts(OUTLINE)} fill="#5fe1ff" fillOpacity=".05"/>
   <g clipPath="url(#crowShape)"><rect className="crowScanLine" x="0" y="20" width="120" height="10" fill="url(#crowScan)"/></g>
   <g stroke="#5fe1ff" strokeWidth=".6" strokeOpacity=".32">{FACETS.map(([a,b])=><line key={a+b} x1={P[a][0]} y1={P[a][1]} x2={P[b][0]} y2={P[b][1]}/>)}</g>
   <g filter="url(#crowGlow)">
    <polygon className="crowOutline" points={pts(OUTLINE)} fill="none" stroke="#5fe1ff" strokeWidth="1.3" strokeLinejoin="round" pathLength={1}/>
    <polygon className="crowTrace" points={pts(OUTLINE)} fill="none" stroke="#e8fbff" strokeWidth="1.9" strokeLinejoin="round" pathLength={1}/>
    <path d="M5 50 L29 48" stroke="#5fe1ff" strokeWidth=".8" fill="none"/>
    <path d="M58 90 L56 99 M69 89 L69 99 M52 99 H61 M65 99 H74" stroke="#5fe1ff" strokeWidth="1" fill="none"/>
   </g>
   {(Object.keys(P) as V[]).map((v,i)=><circle key={v} className="crowNode" cx={P[v][0]} cy={P[v][1]} r="1.15" fill="#bff3ff" style={{animationDelay:`${(i*0.37)%3}s`}}/>)}
  </g>
  <g className="crowEye" filter="url(#crowGlow)">
   <circle cx="41" cy="40" r="3.4" fill="none" stroke="#f0b23a" strokeWidth=".9"/>
   <circle cx="41" cy="40" r="1.5" fill="#ffd27a"/>
  </g>
 </svg>;
}

type Tip = {zh:string; en:string; next?:string};
const TIPS:Record<string,Tip> = {
 '/':{zh:'先看这里：闸门灯和本周信号告诉你今天要不要动。没有新信号，今天就不用做事。',en:'Start here: the gate light and this week’s signals tell you whether to act today. No new signal means nothing to do.',next:'/signals'},
 '/signals':{zh:'每张卡是一个 3W 信号：入场、止损和目标都画在价格阶梯上。打开一张，看它过了哪几道检查。',en:'Each card is one 3W signal, with entry, stop and target on a price ladder. Open one to see the checks it passed.',next:'/forward'},
 '/forward':{zh:'这是规则冻结之后的真实记录。满 100 笔才算证明，现在还在攒。',en:'The real record since the rules were frozen. It takes 100 closed trades to prove anything; it is still building.',next:'/portfolio'},
 '/portfolio':{zh:'模拟账户：一半跟行业趋势篮子，一半等 3W 信号。圆点越靠右，离 200 日线越远。',en:'The paper account: half follows the sector trend basket, half waits for 3W signals. Dots further right are further above their 200-day line.',next:'/zh/watch/market'},
 '/zh/watch/market':{zh:'先看涨跌家数和广度，再看资金流：钱在流进还是流出这 16 只大型 ETF。',en:'Check how many stocks rose and the breadth first, then the fund flows: is money going into or out of 16 big ETFs?',next:'/zh/watch/industry-radar'},
 '/zh/watch/industry-radar':{zh:'轮动地图右上角是领涨的主题。点下面任意一行，能看到成分股；绿色的今天在多因子榜上。',en:'Top right of the rotation map are the leading themes. Open any row below to see its members; green ones are on today’s multi-factor list.',next:'/zh/watch/resonance/rare-opportunities'},
 '/zh/watch/resonance/rare-opportunities':{zh:'分数决定先研究哪只，不是胜率。前 5 只最值得先看；下面可以搜任意代码。',en:'The score says what to research first; it is not a win rate. Start with the top five, or search any ticker below.',next:'/patterns'},
 '/patterns':{zh:'每张小图是一只股票：黄色在等突破，绿色已经突破。点一张图看完整日线。',en:'Each small chart is one stock: yellow is waiting to break out, green already has. Click one for the full daily chart.',next:'/zh/watch/resonance/rare-opportunities'},
 '/zh/backtest':{zh:'每一条是一次检验：红色没通过，绿色有用。历史只能给线索，证明要靠前向记录。',en:'Each bar is one test: red did not pass, green was useful. History only gives hints; the forward record is the proof.',next:'/forward'},
 '/archive':{zh:'原来的工具都在这里，定义没变。新版在左边菜单里。',en:'The original tools live here, unchanged. The new versions are in the side menu.',next:'/learn'},
 '/learn':{zh:'四步看懂 3W，一张图讲完。看完再去信号页，会更容易读懂。',en:'3W in four steps on one chart. The Signals page is easier to read afterwards.',next:'/signals'},
 '/zh/watch/resonance/about':{zh:'点每一步，看今天约 1,500 只股票是怎么一步步筛到几只的。',en:'Click each step to see how today’s 1,500 or so stocks narrow to a handful.',next:'/'},
};
const ALIASES:Record<string,string> = {'/opportunities':'/signals','/scorecard':'/forward','/zh/watch/resonance/favorite-pattern':'/patterns'};
const NAMES:Record<string,[string,string]> = {'/':['今日','Today'],'/signals':['信号','Signals'],'/forward':['前向记录','Forward record'],'/portfolio':['我的组合','My portfolio'],'/zh/watch/market':['大盘','Market'],'/zh/watch/industry-radar':['行业','Sectors'],'/zh/watch/resonance/rare-opportunities':['多因子','Multi-factor'],'/patterns':['形态','Daily setups'],'/zh/backtest':['回测','Backtests'],'/archive':['研究档案','Archive'],'/learn':['学习','Learn'],'/zh/watch/resonance/about':['关于 SV','About SV']};
type Today = {new_signals_this_week?:number; orders_to_place?:number; market?:{light?:string|null; breadth?:number|null; distance_pct?:number|null}};
const SEEN='sv-crow-seen', HIDDEN='sv-crow-hidden';
const read=(k:string)=>{try{return localStorage.getItem(k)}catch{return null}};
const write=(k:string,v:string)=>{try{localStorage.setItem(k,v)}catch{/* private mode: the crow just forgets */}};

function fact(path:string,t:Today|null,en:boolean) {
 const m=t?.market; if(!m)return null;
 const light=m.light==='green'?(en?'green':'绿灯'):m.light?(en?'amber':'黄灯'):null;
 const breadth=m.breadth!=null?`${(m.breadth*100).toFixed(1)}%`:null, dist=m.distance_pct!=null?`${m.distance_pct>=0?'+':''}${m.distance_pct.toFixed(1)}%`:null;
 if(path==='/'||path==='/signals')return en?`Today: gate ${light??'—'}, ${t?.new_signals_this_week??0} new signals this week, ${t?.orders_to_place??0} orders to place.`:`今天：闸门${light??'—'}，本周新信号 ${t?.new_signals_this_week??0} 个，待下单 ${t?.orders_to_place??0} 个。`;
 if(path==='/zh/watch/market'||path==='/portfolio')return en?`Today: SPY is ${dist??'—'} from its 200-day line; ${breadth??'—'} of the 3W pool is above it.`:`今天：SPY 距 200 日线 ${dist??'—'}，3W 股票池 ${breadth??'—'} 站上 200 日线。`;
 return null;
}

export default function CrowGuide() {
 const raw=usePathname()??'/', path=ALIASES[raw]??raw;
 const {locale}=useLocale(), en=locale==='en';
 const [open,setOpen]=useState(false);
 const [hidden,setHidden]=useState(true);
 const [hop,setHop]=useState(0);
 const [today,setToday]=useState<Today|null>(null);
 const tip=TIPS[path];
 useEffect(()=>{let active=true;void sharedJson<Today>('/app/today.json').then(d=>{if(active)setToday(d)});return()=>{active=false}},[]);
 useEffect(()=>{
  // Wait for the welcome tour to finish; greet each page once per browser.
  const t=setTimeout(()=>{
   setHidden(read(HIDDEN)==='1');
   const seen=(read(SEEN)??'').split('|');
   if(tip&&read('sv-onboarded')==='1'&&read(HIDDEN)!=='1'&&!seen.includes(path)){setOpen(true);write(SEEN,[...seen.filter(Boolean),path].join('|'))}
  },1200);
  return()=>{clearTimeout(t);setOpen(false)};
 },[path,tip]);
 if(!tip)return null;
 if(hidden)return <button type="button" className="crowTab" onClick={()=>{setHidden(false);write(HIDDEN,'0');setOpen(true)}} aria-label={en?'Bring back the crow guide':'叫回乌鸦向导'}><CrowArt/></button>;
 const f=fact(path,today,en), next=tip.next&&NAMES[tip.next];
 return <div className="crowGuide" data-open={open||undefined}>
  {open&&<div className="crowBubble" role="dialog" aria-label={en?'Crow guide':'乌鸦向导'}>
   <small>{en?`Crow guide · ${NAMES[path]?.[1]??''}`:`乌鸦向导 · ${NAMES[path]?.[0]??''}`}</small>
   <p>{en?tip.en:tip.zh}</p>
   {f&&<p className="crowFact">{f}</p>}
   <div className="crowActions">
    {next&&<a href={tip.next}>{en?`Next: ${next[1]} →`:`下一步：${next[0]} →`}</a>}
    <button type="button" onClick={()=>setOpen(false)}>{en?'Got it':'知道了'}</button>
    <button type="button" onClick={()=>{setOpen(false);setHidden(true);write(HIDDEN,'1')}}>{en?'Tuck away':'收起'}</button>
   </div>
  </div>}
  <button type="button" className="crowButton" data-hop={hop>0||undefined} key={hop} aria-expanded={open} aria-label={en?'Crow guide: a tip for this page':'乌鸦向导：这一页的提示'} onClick={()=>{setOpen(!open);setHop(hop+1)}}><CrowArt/></button>
 </div>;
}
