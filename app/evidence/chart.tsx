'use client';
import {useEffect,useRef,useState} from 'react';
import type {IChartApi,Time,SeriesMarker,LogicalRange,MouseEventParams,ISeriesApi} from 'lightweight-charts';
import {useLocale,Localized} from '../i18n/locale';
import type {Ticket} from './data';
export function chartDate(time:Time|undefined) {
 if(typeof time==='object')return `${time.year}-${String(time.month).padStart(2,'0')}-${String(time.day).padStart(2,'0')}`;
 return typeof time==='string'?time:undefined;
}
export function shapeRange(ticket:Ticket) {
 const first=ticket.weekly.findIndex(b=>b.date===ticket.pushes[0]?.date);
 const signal=ticket.weekly.findIndex(b=>b.date===ticket.signal_week);
 return {from:(first<0?0:first)-8,to:(signal<0?ticket.weekly.length-1:signal)+12};
}
export function futureWeeks(day:string) {
 return Array.from({length:12},(_,i)=>({time:new Date(Date.parse(day)+(i+1)*7*86400000).toISOString().slice(0,10)}));
}
export function EvidenceChart({ticket}:{ticket:Ticket}) {
 const priceRef=useRef<HTMLDivElement>(null),macdRef=useRef<HTMLDivElement>(null);
 const {locale}=useLocale();const [failed,setFailed]=useState(false);
 useEffect(()=>{
  let active=true;let price:IChartApi|undefined,macd:IChartApi|undefined;let observer:ResizeObserver|undefined;
  const top=priceRef.current,bottom=macdRef.current;if(!top||!bottom)return;
  void import('lightweight-charts').then(({createChart,ColorType,LineStyle,CrosshairMode})=>{
   if(!active)return;
   const style=getComputedStyle(top),text=style.color,background=getComputedStyle(document.body).backgroundColor;
   const opts={layout:{background:{type:ColorType.Solid,color:background},textColor:text,fontSize:13},rightPriceScale:{minimumWidth:66},grid:{vertLines:{color:'#94a3b81a'},horzLines:{color:'#94a3b81a'}},crosshair:{mode:CrosshairMode.Normal},timeScale:{borderVisible:false},localization:{locale:locale==='en'?'en-US':'zh-CN'}};
   price=createChart(top,{...opts,width:top.clientWidth,height:top.clientHeight});macd=createChart(bottom,{...opts,width:bottom.clientWidth,height:140});
   const candles=price.addCandlestickSeries({upColor:'#428d78',downColor:'#bf6964',borderVisible:false,wickUpColor:'#428d78',wickDownColor:'#bf6964'});
   const future=futureWeeks(ticket.signal_week);
   candles.setData([...ticket.weekly.map(b=>({time:b.date,open:b.open,high:b.high,low:b.low,close:b.close})),...future]);
   const first=ticket.weekly[0].date,last=ticket.weekly[ticket.weekly.length-1].date;
   const markers:SeriesMarker<Time>[]=[...ticket.pushes.map((p,i)=>({time:p.date,position:'aboveBar' as const,shape:'arrowDown' as const,size:1.5,color:'#946317',text:`${locale==='en'?'Push':'推'} ${i+1}`})),...ticket.bottoms.map((p,i)=>({time:p.date,position:'belowBar' as const,shape:'arrowUp' as const,size:1.5,color:'#23775c',text:`${locale==='en'?'Bottom':'底'} ${i+1}`})),{time:ticket.signal_week,position:'belowBar',shape:'arrowUp',color:'#6689bd',text:locale==='en'?'Signal':'信号'}];
   candles.setMarkers(markers.filter(m=>String(m.time)>=first&&String(m.time)<=last).sort((a,b)=>String(a.time).localeCompare(String(b.time))));
   const [a,b]=ticket.trend_line;
   if(a&&b&&a.date!==b.date&&ticket.weekly.some(w=>w.date===a.date)&&ticket.weekly.some(w=>w.date===b.date)){
    const weeklyIndex=(date:string)=>ticket.weekly.findIndex(w=>w.date===date);
    const slope=(b.price-a.price)/(weeklyIndex(b.date)-weeklyIndex(a.date));
    const line=price.addLineSeries({color:'#946317',lineWidth:3,lineStyle:LineStyle.Dashed,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});
    line.setData(ticket.weekly.filter(w=>w.date>=a.date).map(w=>({time:w.date,value:a.price+slope*(weeklyIndex(w.date)-weeklyIndex(a.date))})));
   }
   for(const [value,color,title] of [[ticket.order.limit,'#6689bd',locale==='en'?'Limit':'限价'],[ticket.order.stop,'#bf6964',locale==='en'?'Stop':'止损'],[ticket.order.target,'#428d78',locale==='en'?'Target 3R':'目标 3R']] as const)candles.createPriceLine({price:value,color,lineWidth:1,lineStyle:LineStyle.Dashed,axisLabelVisible:true,title});
   const dif=macd.addLineSeries({color:'#6689bd',lineWidth:2,title:'DIF',priceLineVisible:false}),dea=macd.addLineSeries({color:'#b59463',lineWidth:1,title:'DEA',priceLineVisible:false});
   dif.setData([...ticket.weekly.map(b=>({time:b.date,value:b.dif})),...future]);dea.setData([...ticket.weekly.map(b=>({time:b.date,value:b.dea})),...future]);
   dif.createPriceLine({price:0,color:'#94a3b8',lineWidth:1,lineStyle:LineStyle.Dashed,axisLabelVisible:false,title:''});
   let moving=false;
   const sync=(target:IChartApi)=>(range:LogicalRange|null)=>{if(moving||!range)return;moving=true;target.timeScale().setVisibleLogicalRange(range);moving=false};
   price.timeScale().subscribeVisibleLogicalRangeChange(sync(macd));macd.timeScale().subscribeVisibleLogicalRangeChange(sync(price));
   const byDate=new Map(ticket.weekly.map(b=>[b.date,b]));
   const cross=(target:IChartApi,series:ISeriesApi<'Line'>|ISeriesApi<'Candlestick'>,field:'dif'|'close')=>(event:MouseEventParams)=>{
    if(moving)return;moving=true;const bar=byDate.get(chartDate(event.time)??'');
    if(event.time&&bar)target.setCrosshairPosition(bar[field],event.time,series);else target.clearCrosshairPosition();moving=false;
   };
   price.subscribeCrosshairMove(cross(macd,dif,'dif'));macd.subscribeCrosshairMove(cross(price,candles,'close'));
   const range=shapeRange(ticket);price.timeScale().setVisibleLogicalRange(range);macd.timeScale().setVisibleLogicalRange(range);
   observer=new ResizeObserver(()=>{price?.applyOptions({width:top.clientWidth,height:top.clientHeight});macd?.applyOptions({width:bottom.clientWidth})});observer.observe(top);observer.observe(bottom);
  }).catch(()=>{if(active)setFailed(true)});
  return()=>{active=false;observer?.disconnect();price?.remove();macd?.remove()};
 },[ticket,locale]);
 return <Localized><figure className="svEvidenceFigure"><figcaption>周线凭证 · 价格与 MACD 同步</figcaption><div ref={priceRef} className="svPriceChart" role="img" aria-label="周线蜡烛图、三推、底部、信号和订单价位"/><div ref={macdRef} className="svMacdChart" role="img" aria-label="周线 DIF 与 DEA"/>{failed&&<p role="status">图表暂时无法加载，证据数值仍可查看。</p>}<small>蜡烛只显示截至信号周的数据；右侧12周为空白观察区。</small><p className="svAppSource">TradingView Lightweight Charts™ · <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView</a></p></figure></Localized>;
}
