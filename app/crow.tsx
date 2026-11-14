'use client';
import {useEffect,useState} from 'react';
import {usePathname} from 'next/navigation';
import {useLocale} from './i18n/locale';
import {sharedJson} from './json-cache';

// SV's guide: a crow perched in the corner of every page. It blinks and tilts its head; click it
// for a tip about the page you are on, one live fact from today's published data, and where to go
// next. It greets each page once per browser (after the welcome tour) and can be tucked away.
export function CrowArt({className}:{className?:string}) {
 return <svg className={className} viewBox="0 0 120 110" aria-hidden="true">
  <defs>
   <linearGradient id="crowBody" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#1f2c38"/><stop offset=".55" stopColor="#10161c"/><stop offset="1" stopColor="#07090b"/></linearGradient>
   <radialGradient id="crowGlow"><stop offset="0" stopColor="#5fd38a" stopOpacity=".16"/><stop offset="1" stopColor="#5fd38a" stopOpacity="0"/></radialGradient>
   <linearGradient id="crowSheen" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stopColor="#2e5a66" stopOpacity=".0"/><stop offset=".5" stopColor="#3f7c86" stopOpacity=".55"/><stop offset="1" stopColor="#3b4f8a" stopOpacity=".0"/></linearGradient>
  </defs>
  <ellipse cx="58" cy="62" rx="58" ry="46" fill="url(#crowGlow)"/>
  <path className="crowTwig" d="M6 98 Q50 91 116 99" fill="none" stroke="#4a4036" strokeWidth="4" strokeLinecap="round"/>
  <path d="M92 95 q8 -10 18 -8 q-6 9 -18 8z" fill="#5fd38a" opacity=".9"/>
  <path d="M80 70 L112 90 L108 96 L104 93 L102 98 L74 80 Z" fill="#0b0f13" stroke="#4d6b78" strokeOpacity=".45" strokeWidth="1"/>
  <g className="crowBody">
   <ellipse cx="64" cy="67" rx="28" ry="20" transform="rotate(-14 64 67)" fill="url(#crowBody)" stroke="#4d6b78" strokeOpacity=".55" strokeWidth="1.2"/>
   <path d="M46 60 Q70 48 94 74 Q74 84 50 76 Z" fill="#141c24"/>
   <path d="M52 62 Q72 54 88 70" fill="none" stroke="url(#crowSheen)" strokeWidth="5" strokeLinecap="round"/>
   <path d="M56 86 L54 96 M68 86 L68 96" stroke="#3a4048" strokeWidth="2.6" strokeLinecap="round"/>
   <path d="M49 96 L59 96 M63 96 L73 96" stroke="#3a4048" strokeWidth="2.2" strokeLinecap="round"/>
  </g>
  <g className="crowHead">
   <circle cx="42" cy="45" r="16" fill="url(#crowBody)" stroke="#4d6b78" strokeOpacity=".55" strokeWidth="1.2"/>
   <path d="M30 38 Q40 30 52 34" fill="none" stroke="url(#crowSheen)" strokeWidth="3" strokeLinecap="round"/>
   <path d="M28 42 L8 48 L28 52 Z" fill="#3a4048"/>
   <path d="M10 48 L27 48" stroke="#1a1f24" strokeWidth="1"/>
   <circle cx="37" cy="42" r="4.4" fill="#f0b23a"/>
   <circle cx="36.2" cy="42" r="2.4" fill="#07090b"/>
   <circle cx="35.4" cy="41" r=".9" fill="#fff"/>
   <rect className="crowLid" x="32" y="37" width="10" height="10" rx="5" fill="#141c24"/>
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
