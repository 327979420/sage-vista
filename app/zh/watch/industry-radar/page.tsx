"use client";
import {useEffect,useState} from "react";

type Theme={theme_id:string;name:string;state:string;relative_20d:number|null;relative_60d:number|null;strength_percentile:number|null;breadth_above_sma50:number|null;breadth_change_10d:number|null;member_count:number;valid_member_count:number;context:string};
type Report={as_of:string;status:string;membership_version:string|null;future_data_used:boolean;historical_membership_safe:boolean;themes:Theme[]};
const stateLabel:Record<string,string>={"Leadership":"领先","Pullback Watch":"回调观察","Recovery":"修复","Neutral":"中性","Unavailable":"数据不足"};
const pct=(value:number|null)=>value===null?"—":`${value>=0?"+":""}${(value*100).toFixed(1)}%`;

export default function IndustryRadar(){
 const [data,setData]=useState<Report|null>(null);
 useEffect(()=>{fetch("/industry-radar.json",{cache:"no-store"}).then(x=>x.json()).then(setData)},[]);
 return <main className="irPage"><header className="irHero"><a href="/zh/watch/resonance">← 技术追踪器</a><p>RESEARCH PROTOTYPE · 独立上下文</p><h1>Industry Radar</h1><span>行业雷达不筛选个股、不改变技术分数与排名。状态仅供人工决策参考，不是交易信号。</span></header>
 {data&&<><section className="irAudit"><div><small>数据截至</small><b>{data.as_of}</b></div><div><small>成员版本</small><b>{data.membership_version??"无可用版本"}</b></div><div><small>未来数据</small><b>{data.future_data_used?"异常":"未使用"}</b></div><div><small>研究状态</small><b>{data.status==="market_data_unavailable_safe"?"行情未配置，安全停用":"未验证研究原型"}</b></div></section>
 <section className="irTable" aria-label="行业雷达主题表"><div className="irRow irHead"><span>主题</span><span>状态</span><span>20D RS vs SPY</span><span>60D RS vs SPY</span><span>广度 &gt; SMA50</span><span>广度趋势</span><span>成员</span></div>{data.themes.map(theme=><article className="irRow" key={theme.theme_id}><div><b>{theme.name}</b><small>{theme.context}</small></div><span><mark data-state={theme.state}>{stateLabel[theme.state]??theme.state}</mark></span><span>{pct(theme.relative_20d)}</span><span>{pct(theme.relative_60d)}</span><span>{theme.breadth_above_sma50===null?"—":`${(theme.breadth_above_sma50*100).toFixed(0)}%`}</span><span>{pct(theme.breadth_change_10d)}</span><span>{theme.valid_member_count}/{theme.member_count}</span></article>)}</section>
 <footer className="irNote">强度使用主题间百分位；主题篮子为成分股等权收益。阈值是 V1 研究参数，尚未证明任何预测能力。</footer></>}
 </main>
}
