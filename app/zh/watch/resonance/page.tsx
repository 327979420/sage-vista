"use client";
import {useEffect,useMemo,useState} from "react";
import {TrackerShell,useTracker} from "./tracker-ui";

type IndustryTheme={theme_id:string;name:string;state:string};
type IndustryReport={as_of:string;membership_version:string|null;future_data_used:boolean;themes:IndustryTheme[];ticker_context:Record<string,{theme_id:string;state:string}[]>};
type FactorState={factor_id:string;available:boolean;hit:boolean;recent_hit:boolean;bars_since_hit:number|null};
type FactorSymbol={symbol:string;factors:FactorState[]};
type FactorSnapshot={as_of:string;future_data_used:boolean;symbols:FactorSymbol[]};
type FactorRegistry={factors:{id:string;name_zh:string}[]};
type MarketReport={as_of:string;market_temperature:{state:string;score:number;max_score:number;explanation:string}};
const stateLabel:Record<string,string>={"Leadership":"领先","Pullback Watch":"回调观察","Recovery":"修复","Neutral":"中性","Unavailable":"数据不足"};
const json=(path:string)=>fetch(path,{cache:"no-store"}).then(x=>x.ok?x.json():null);

export default function Overview(){
 const tracker=useTracker();
 const [industry,setIndustry]=useState<IndustryReport|null>(null),[snapshot,setSnapshot]=useState<FactorSnapshot|null>(null),[registry,setRegistry]=useState<FactorRegistry|null>(null),[market,setMarket]=useState<MarketReport|null>(null);
 useEffect(()=>{Promise.all([json("/industry-radar.json"),json("/daily-factor-snapshot.json"),json("/factor-registry.json"),json("/market-etf-watch.json")]).then(([i,s,r,m])=>{setIndustry(i);setSnapshot(s);setRegistry(r);setMarket(m)})},[]);
 const themes=useMemo(()=>Object.fromEntries((industry?.themes??[]).map(x=>[x.theme_id,x])),[industry]);
 const factors=useMemo(()=>Object.fromEntries((registry?.factors??[]).map(x=>[x.id,x.name_zh])),[registry]);
 const factorByTicker=useMemo(()=>Object.fromEntries((snapshot?.symbols??[]).map(x=>[x.symbol,x])),[snapshot]);
 const grouped=(state:string)=>(industry?.themes??[]).filter(x=>x.state===state);
 const synced=!!tracker&&!!industry&&!!snapshot&&tracker.as_of===snapshot.as_of&&!snapshot.future_data_used&&!industry.future_data_used;
 return <TrackerShell active="今日研究总览" title="今日研究总览" subtitle="市场 → 行业 → 技术机会 → 多因子证据 → 数据审计。">
  {tracker&&<div className="dailyOverview">
   <section className="dailyMarket"><div><small>MARKET STATUS</small><h2>{market?.market_temperature.state??"等待市场环境"}</h2><p>{market?.market_temperature.explanation??"市场环境数据正在载入。"}</p></div><strong>{market?`${market.market_temperature.score}/${market.market_temperature.max_score}`:"—"}</strong></section>
   <section className="dailyPanel industrySummary"><header><div><small>INDUSTRY RADAR</small><h2>行业 / Theme 位置</h2></div><a href="/zh/watch/industry-radar">查看完整行业表 →</a></header><div className="industryStateGrid">{(["Leadership","Pullback Watch","Recovery"] as const).map(state=><article key={state}><small>{stateLabel[state]}</small><b>{grouped(state).map(x=>x.name).join(" · ")||"暂无"}</b></article>)}</div><details><summary>中性与数据不足（{grouped("Neutral").length+grouped("Unavailable").length}）</summary><p>{[...grouped("Neutral"),...grouped("Unavailable")].map(x=>`${x.name} · ${stateLabel[x.state]}`).join("；")||"暂无"}</p></details><footer><span>数据 {industry?.as_of??"—"}</span><span>成员版本 {industry?.membership_version??"—"}</span><span>{industry?.future_data_used===false?"✓ 未使用未来数据":"! 待核验"}</span></footer></section>
   <section className="dailyPanel"><header><div><small>TECHNICAL TRACKER</small><h2>今天的技术机会</h2><p>沿用现有 Technical Tracker 顺序；行业与因子只作展示上下文。</p></div><a href="/zh/watch/resonance/macd">查看完整指标共振 →</a></header><div className="dailyOpportunities">{tracker.macd_buy_top10.slice(0,5).map((item,index)=>{const member=(industry?.ticker_context[item.symbol]??[]).slice(0,3);const evidence=(factorByTicker[item.symbol]?.factors??[]).filter(x=>x.available&&(x.hit||x.recent_hit)).sort((a,b)=>(Number(b.hit)-Number(a.hit))||((a.bars_since_hit??99)-(b.bars_since_hit??99))).slice(0,3);return <article key={item.symbol}><header><i>{index+1}</i><div><b>{item.symbol}</b><small>${item.price} · Technical Score {item.macd_rank_score}</small></div><mark>{item.price_structure.label}</mark></header><div><small>近期多因子证据</small><p>{evidence.map(x=>`${factors[x.factor_id]??x.factor_id}${x.hit?" · 当前":` · ${x.bars_since_hit}日前`}`).join("；")||"暂无近期命中"}</p></div><div><small>行业 / Theme</small><p>{member.map(x=>`${themes[x.theme_id]?.name??x.theme_id} · ${stateLabel[x.state]??x.state}`).join("；")||"暂无已确认成员关系"}</p></div></article>})}</div></section>
   <section className="dailyPanel factorSummary"><header><div><small>MULTI-FACTOR CONTEXT</small><h2>27 项证据层</h2><p>Core、Auxiliary、近期事件、风险与不计分观察均来自 daily snapshot，不创建第二套排名。</p></div><a href="/zh/watch/resonance/rare-opportunities">查询任意股票证据 →</a></header><div><span><b>27</b><small>固定 factor states / eligible stock</small></span><span><b>{snapshot?.symbols.length??"—"}</b><small>当日 eligible stocks</small></span><span><b>0</b><small>official score</small></span></div></section>
   <section className={`dailyAudit ${synced?"isHealthy":"isBlocked"}`}><div><small>DATA FRESHNESS / AUDIT</small><h2>{synced?"生产数据日期一致":"日期或防前视状态待核验"}</h2></div><span>Tracker {tracker.as_of}</span><span>Factors {snapshot?.as_of??"—"}</span><span>Industry {industry?.as_of??"—"}</span><b>{synced?"future_data_used=false":"停止依赖跨系统结论"}</b></section>
  </div>}
 </TrackerShell>
}
