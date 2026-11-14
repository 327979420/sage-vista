'use client';
import {useEffect,useId,useRef} from 'react';

// SV's crow, drawn only with light: a low-poly wireframe whose vertices are moved every frame by a
// small rig, the way interactive mascots layer motions. It assembles from scattered points, its
// head and eye follow the pointer (it turns round when you go behind it), it bobs, flicks its tail
// and breathes, opens its beak and sends out rings while talking, glitches now and then, and dozes
// when left alone. With reduced motion it is drawn once, still.
const P = {B:[3,50],A:[28,40],C:[29,56],H1:[37,31],H2:[52,30],H3:[61,38],K1:[75,50],K2:[93,62],T1:[118,87],T2:[114,96],T3:[97,91],
 U1:[82,87],U2:[63,91],U3:[46,83],N1:[35,69],N2:[31,60],W:[61,63],W2:[87,75]} as const;
type V = keyof typeof P;
type Pt = [number,number];
const KEYS = Object.keys(P) as V[];
const HEAD = new Set<V>(['B','A','C','H1','H2','N2']), TAIL = new Set<V>(['T1','T2','T3']);
const NECK:Pt = [46,50], RUMP:Pt = [92,80], EYE:Pt = [41,40];
const OUTLINE:V[] = ['B','A','H1','H2','H3','K1','K2','T1','T2','T3','U1','U2','U3','N1','N2','C','B'];
const FACETS:[V,V][] = [['A','N2'],['H1','N2'],['H2','N2'],['H3','N2'],['H3','N1'],['H3','W'],['W','K1'],['W','N1'],['W','U3'],['W','W2'],['W2','K1'],['W2','K2'],['W2','T3'],['W2','U1'],['W2','U2'],['W','U2'],['K2','T3'],['A','C'],['W2','T1']];
const pts = (q:Record<V,Pt>) => OUTLINE.map(v=>`${q[v][0].toFixed(2)},${q[v][1].toFixed(2)}`).join(' ');
const rot = ([x,y]:Pt,[cx,cy]:Pt,deg:number):Pt => {const r=deg*Math.PI/180,c=Math.cos(r),s=Math.sin(r);return [cx+(x-cx)*c-(y-cy)*s,cy+(x-cx)*s+(y-cy)*c]};
const BASE = Object.fromEntries(KEYS.map(k=>[k,[...P[k]]])) as Record<V,Pt>;
const ease = (t:number) => 1-Math.pow(1-Math.min(Math.max(t,0),1),3);

export function CrowArt({className,talking=false}:{className?:string;talking?:boolean}) {
 const svg=useRef<SVGSVGElement>(null);
 const uid=useId().replace(/[^a-zA-Z0-9]/g,''), glow=`crowGlow${uid}`, scan=`crowScan${uid}`, clip=`crowClip${uid}`;
 useEffect(()=>{if(svg.current)svg.current.dataset.talk=talking?'1':''},[talking]);
 useEffect(()=>{
  const el=svg.current; if(!el)return;
  const outline=[...el.querySelectorAll<SVGPolygonElement>('[data-o]')];
  const facets=[...el.querySelectorAll<SVGLineElement>('line[data-f]')];
  const nodes=[...el.querySelectorAll<SVGCircleElement>('circle[data-v]')];
  const eye=el.querySelector<SVGGElement>('[data-eye]'), pupil=el.querySelector<SVGCircleElement>('[data-pupil]');
  const mouth=el.querySelector<SVGLineElement>('[data-mouth]'), root=el.querySelector<SVGGElement>('[data-root]'), caw=el.querySelector<SVGGElement>('[data-caw]');
  const draw=(q:Record<V,Pt>,eyeAt:Pt,look:Pt,flip:number,glow:number)=>{
   const s=pts(q); outline.forEach(o=>o.setAttribute('points',s));
   facets.forEach(f=>{const a=q[f.dataset.a as V],b=q[f.dataset.b as V];f.setAttribute('x1',a[0].toFixed(2));f.setAttribute('y1',a[1].toFixed(2));f.setAttribute('x2',b[0].toFixed(2));f.setAttribute('y2',b[1].toFixed(2))});
   nodes.forEach(n=>{const p=q[n.dataset.v as V];n.setAttribute('cx',p[0].toFixed(2));n.setAttribute('cy',p[1].toFixed(2))});
   eye?.setAttribute('transform',`translate(${eyeAt[0].toFixed(2)} ${eyeAt[1].toFixed(2)})`); eye?.setAttribute('opacity',glow.toFixed(2));
   pupil?.setAttribute('cx',look[0].toFixed(2)); pupil?.setAttribute('cy',look[1].toFixed(2));
   const m=[(q.A[0]+q.C[0])/2,(q.A[1]+q.C[1])/2]; mouth?.setAttribute('x1',(q.B[0]+2).toFixed(2)); mouth?.setAttribute('y1',q.B[1].toFixed(2)); mouth?.setAttribute('x2',m[0].toFixed(2)); mouth?.setAttribute('y2',m[1].toFixed(2));
   caw?.setAttribute('transform',`translate(${q.B[0].toFixed(2)} ${q.B[1].toFixed(2)})`);
   root?.setAttribute('transform',`translate(60 0) scale(${flip.toFixed(3)} 1) translate(-60 0)`);
  };
  if(window.matchMedia('(prefers-reduced-motion: reduce)').matches){draw(BASE,EYE,[0,0],1,1);return}
  // Scattered start points for the assembly, fixed per mount.
  const scatter=Object.fromEntries(KEYS.map(k=>[k,[(Math.random()-.5)*90,(Math.random()-.5)*70]])) as Record<V,Pt>;
  let pointer:{x:number;y:number}|null=null, lastMove=performance.now(), raf=0;
  const start=performance.now();
  const s={head:0,flip:1,lookX:0,lookY:0,bobAt:start+2500+Math.random()*3000,flickAt:start+3500+Math.random()*3000,glitchAt:start+6000+Math.random()*5000};
  const onMove=(e:PointerEvent)=>{pointer={x:e.clientX,y:e.clientY};lastMove=performance.now()};
  window.addEventListener('pointermove',onMove,{passive:true});
  const frame=(now:number)=>{
   const t=(now-start)/1000, box=el.getBoundingClientRect();
   const cx=box.left+box.width*.35, cy=box.top+box.height*.4;
   const dx=pointer?pointer.x-cx:-200, dy=pointer?pointer.y-cy:-40;
   const asleep=now-lastMove>25000, talk=el.dataset.talk==='1';
   // Gaze: turn round when the pointer is well behind the crow; tilt the head toward it.
   const wantFlip=dx>60?-1:dx<-20?1:s.flip>0?1:-1;
   s.flip+=(wantFlip-s.flip)*.08;
   const facing=s.flip>=0?-1:1;                     // which way the beak points on screen
   const along=dx*facing;                             // distance in front of the beak
   let headTarget=Math.max(-18,Math.min(16,-Math.atan2(dy,Math.max(40,Math.abs(along)))*180/Math.PI*.55));
   if(asleep)headTarget=-16;
   // Idle life: a quick bob every few seconds, a tail flick, breathing.
   if(now>s.bobAt){s.bobAt=now+4500+Math.random()*5000}
   const bobPhase=(now-(s.bobAt-4500))/1000;
   const bob=!asleep&&bobPhase>0&&bobPhase<.35?-Math.sin(bobPhase/.35*Math.PI)*14:0;
   if(now>s.flickAt){s.flickAt=now+3500+Math.random()*4000}
   const flickPhase=(now-(s.flickAt-3500))/1000;
   const flick=flickPhase>0&&flickPhase<.25?-Math.sin(flickPhase/.25*Math.PI)*12:0;
   s.head+=((headTarget+bob)-s.head)*.12;
   const breath=Math.sin(t*(asleep?.9:1.7))*.012;
   const beak=talk?Math.abs(Math.sin(t*9))*4.5:0;
   const intro=ease(t/1.4);
   const q={} as Record<V,Pt>;
   for(const k of KEYS){
    let p:Pt=[BASE[k][0],BASE[k][1]];
    if(!HEAD.has(k)&&!TAIL.has(k))p=[p[0],91-(91-p[1])*(1+breath)];
    if(k==='C')p=[p[0]-beak*.3,p[1]+beak];
    if(HEAD.has(k))p=rot(p,NECK,s.head);
    if(TAIL.has(k))p=rot(p,RUMP,flick);
    q[k]=[p[0]+scatter[k][0]*(1-intro),p[1]+scatter[k][1]*(1-intro)];
   }
   const eyeAt=rot(EYE,NECK,s.head);
   s.lookX+=((-Math.max(-1.3,Math.min(1.3,along/120)))-s.lookX)*.15; s.lookY+=((Math.max(-1.1,Math.min(1.1,dy/120)))-s.lookY)*.15;
   draw(q,[eyeAt[0]+scatter.A[0]*(1-intro),eyeAt[1]+scatter.A[1]*(1-intro)],[s.lookX,s.lookY],s.flip,asleep?.45:1);
   el.dataset.glitch=now>s.glitchAt&&now<s.glitchAt+140?'1':'';
   if(now>s.glitchAt+140)s.glitchAt=now+7000+Math.random()*7000;
   el.dataset.asleep=asleep?'1':'';
   raf=requestAnimationFrame(frame);
  };
  raf=requestAnimationFrame(frame);
  return()=>{cancelAnimationFrame(raf);window.removeEventListener('pointermove',onMove)};
 },[]);
 const s=pts(BASE);
 return <svg ref={svg} className={className} viewBox="0 0 120 110" aria-hidden="true">
  <defs>
   <filter id={glow} x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="1.8" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
   <linearGradient id={scan} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#5fe1ff" stopOpacity="0"/><stop offset=".5" stopColor="#5fe1ff" stopOpacity=".55"/><stop offset="1" stopColor="#5fe1ff" stopOpacity="0"/></linearGradient>
   <clipPath id={clip}><polygon data-o="" points={s}/></clipPath>
  </defs>
  <g className="crowPerch" filter={`url(#${glow})`}>
   <path d="M4 100 H44 L50 96 H116" fill="none" stroke="#5fd38a" strokeWidth=".9" strokeOpacity=".7"/>
   <path className="crowPerchPulse" d="M4 100 H44 L50 96 H116" fill="none" stroke="#c8ffe0" strokeWidth="1.4" pathLength={1}/>
   <circle cx="44" cy="100" r="1.4" fill="#5fd38a"/><circle cx="116" cy="96" r="1.4" fill="#5fd38a"/>
  </g>
  <g className="crowMotes">{[18,40,64,88,104].map((x,i)=><circle key={x} cx={x} cy="92" r=".9" fill="#9cefff" style={{animationDelay:`${i*.9}s`}}/>)}</g>
  <g data-root="">
   <polygon data-o="" points={s} fill="#5fe1ff" fillOpacity=".05"/>
   <polygon data-o="" className="crowGhost crowGhostR" points={s} fill="none" stroke="#ff5c8a" strokeWidth="1"/>
   <polygon data-o="" className="crowGhost crowGhostB" points={s} fill="none" stroke="#5c8aff" strokeWidth="1"/>
   <g clipPath={`url(#${clip})`}><rect className="crowScanLine" x="0" y="20" width="120" height="10" fill={`url(#${scan})`} opacity=".55"/></g>
   <g stroke="#5fe1ff" strokeWidth=".6" strokeOpacity=".32">{FACETS.map(([a,b])=><line key={a+b} data-f="" data-a={a} data-b={b} x1={P[a][0]} y1={P[a][1]} x2={P[b][0]} y2={P[b][1]}/>)}</g>
   <g filter={`url(#${glow})`}>
    <polygon data-o="" className="crowOutline" points={s} fill="none" stroke="#5fe1ff" strokeWidth="1.3" strokeLinejoin="round"/>
    <polygon data-o="" className="crowTrace" points={s} fill="none" stroke="#e8fbff" strokeWidth="1.9" strokeLinejoin="round" pathLength={1}/>
    <line data-mouth="" x1="5" y1="50" x2="29" y2="48" stroke="#5fe1ff" strokeWidth=".8"/>
    <path d="M58 90 L56 99 M69 89 L69 99 M52 99 H61 M65 99 H74" stroke="#5fe1ff" strokeWidth="1" fill="none"/>
   </g>
   {KEYS.map((v,i)=><circle key={v} data-v={v} className="crowNode" cx={P[v][0]} cy={P[v][1]} r="1.15" fill="#bff3ff" style={{animationDelay:`${(i*.37)%3}s`}}/>)}
   <g data-eye="" transform={`translate(${EYE[0]} ${EYE[1]})`} filter={`url(#${glow})`}>
    <g className="crowEye"><circle r="3.4" fill="none" stroke="#f0b23a" strokeWidth=".9"/><circle data-pupil="" r="1.5" fill="#ffd27a"/></g>
   </g>
   <g data-caw="" transform="translate(3 50)" className="crowCaw" fill="none" stroke="#9cefff" strokeWidth=".8">{[0,1,2].map(i=><path key={i} d="M-2 -6 A 8 8 0 0 0 -2 6" style={{animationDelay:`${i*.25}s`}}/>)}</g>
  </g>
 </svg>;
}
