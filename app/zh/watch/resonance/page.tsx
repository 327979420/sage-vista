"use client";
import {useEffect,useMemo,useState} from "react";
import {TrackerShell,useTracker} from "./tracker-ui";

type IndustryTheme={theme_id:string;name:string;state:string;etf_context?:{favorable_setup:boolean;confirming_funds:string[]}};
type Classification={sector?:string;industry_group?:string;industry?:string;market_cap?:string};
type IndustryLink={theme_id:string;state:string;etf_context?:IndustryTheme["etf_context"]};
type IndustryReport={as_of:string;membership_version:string|null;future_data_used:boolean;themes:IndustryTheme[];ticker_context:Record<string,IndustryLink[]>;classification_by_ticker?:Record<string,Classification>};
type FactorState={factor_id:string;available:boolean;hit:boolean;recent_hit:boolean;bars_since_hit:number|null};
type FactorSnapshot={as_of:string;future_data_used:boolean;symbols:{symbol:string;factors:FactorState[]}[]};
type FactorRegistry={factors:{id:string;name_zh:string}[]};
type MarketFund={ticker:string;return_1d:number;return_20d:number;above_ema50:boolean};
type MarketReport={as_of:string;market_temperature:{state:string;score:number;max_score:number;explanation:string};layers:{trend:{state:string};breadth:{state:string};risk_appetite:{state:string}};ratios:Record<string,number>;funds:MarketFund[]};
type RareSignal={symbol:string;price:number;level:string;total_score:number;official_score:number;experimental_observational_score:number;components:string[];risks:string[]};
type RareReport={as_of:string;signals:RareSignal[]};
type SignalCase={symbol:string;first_seen_date:string;last_seen_date:string;lifecycle:string;latest_current_status:string;forward:{elapsed_sessions:number;status:string}};
type SignalHistory={cases:SignalCase[]};

const stateLabel:Record<string,string>={"Leadership":"领先","Pullback Watch":"回调观察","Recovery":"修复","Neutral":"中性","Unavailable":"数据不足"};
const json=(path:string)=>fetch(path,{cache:"no-store"}).then(x=>x.ok?x.json():null);
const pct=(value:number|undefined)=>value===undefined?"—":`${value>=0?"+":""}${(value*100).toFixed(1)}%`;

export default function Overview(){
 const tracker=useTracker();
 const [industry,setIndustry]=useState<IndustryReport|null>(null),[snapshot,setSnapshot]=useState<FactorSnapshot|null>(null),[registry,setRegistry]=useState<FactorRegistry|null>(null),[market,setMarket]=useState<MarketReport|null>(null),[history,setHistory]=useState<SignalHistory|null>(null),[rare,setRare]=useState<RareReport|null>(null),[selected,setSelected]=useState<string|null>(null);
 useEffect(()=>{Promise.all([json("/industry-radar.json"),json("/daily-factor-snapshot.json"),json("/factor-registry.json"),json("/market-etf-watch.json"),json("/signal-history.json"),json("/rare-opportunity-radar.json")]).then(([i,s,r,m,h,o])=>{setIndustry(i);setSnapshot(s);setRegistry(r);setMarket(m);setHistory(h);setRare(o)})},[]);
 const themes=useMemo(()=>Object.fromEntries((industry?.themes??[]).map(x=>[x.theme_id,x])),[industry]);
 const factors=useMemo(()=>Object.fromEntries((registry?.factors??[]).map(x=>[x.id,x.name_zh])),[registry]);
 const factorByTicker=useMemo(()=>Object.fromEntries((snapshot?.symbols??[]).map(x=>[x.symbol,x])),[snapshot]);
 const rareByTicker=useMemo(()=>Object.fromEntries((rare?.signals??[]).map(x=>[x.symbol,x])),[rare]);
 const casesByTicker=useMemo(()=>{const out:Record<string,SignalCase[]>={};for(const item of history?.cases??[])(out[item.symbol]??=[]).push(item);return out},[history]);
 const opportunities=useMemo(()=>{if(rare?.signals?.length)return rare.signals.slice(0,8);return (tracker?.macd_buy_top10??[]).slice(0,8).map(x=>({symbol:x.symbol,price:x.price,level:"技术观察",total_score:0,official_score:0,experimental_observational_score:0,components:[],risks:[]}))},[rare,tracker]);
 useEffect(()=>{if(!selected&&opportunities.length)setSelected(opportunities[0].symbol)},[opportunities,selected]);
 const chosen=(selected&&rareByTicker[selected])||opportunities[0];
 const classification=chosen?industry?.classification_by_ticker?.[chosen.symbol]:undefined;
 const links=chosen?(industry?.ticker_context[chosen.symbol]??[]):[];
 const evidence=chosen?(factorByTicker[chosen.symbol]?.factors??[]).filter(x=>x.available&&(x.hit||x.recent_hit)).sort((a,b)=>(Number(b.hit)-Number(a.hit))||((a.bars_since_hit??99)-(b.bars_since_hit??99))).slice(0,5):[];
 const cases=chosen?(casesByTicker[chosen.symbol]??[]).sort((a,b)=>b.first_seen_date.localeCompare(a.first_seen_date)):[];
 const latestCase=cases[0];
 const funds=Object.fromEntries((market?.funds??[]).map(x=>[x.ticker,x]));
 const marketReference=classification?.market_cap?.match(/Nano|Micro|Small/i)?"IWM":classification?.sector==="Information Technology"?"QQQ":"SPY";
 const reference=funds[marketReference];
 const risk=market?.market_temperature.state==="防守"?{label:"高风险",tone:"high",action:"以等待和降低仓位为主"}:market?.market_temperature.state==="风险偏好"?{label:"风险较低",tone:"low",action:"可以正常研究机会，但仍按个股结构执行"}:{label:"中等风险",tone:"medium",action:"可以研究个股，避免追高并控制仓位"};
 const marketStory=!market?"市场环境数据正在载入。":market.layers.trend.state!=="supportive"?"指数趋势转弱，今天优先保护仓位，不因单一个股信号冒进。":market.layers.breadth.state!=="broad"?"指数趋势仍在，但上涨范围偏窄；强势主要集中在部分股票。":"指数趋势与市场广度同步，当前环境对多头研究相对友好。";
 const synced=!!tracker&&!!industry&&!!snapshot&&!!market&&tracker.as_of===snapshot.as_of&&tracker.as_of===market.as_of&&!snapshot.future_data_used&&!industry.future_data_used;
 const segmentCards=[["大盘股","SPY",funds.SPY?.above_ema50?"支持":"谨慎",funds.SPY?.above_ema50?"positive":"negative"],["科技成长","QQQ",funds.QQQ?.above_ema50?"偏强":"谨慎",funds.QQQ?.above_ema50?"positive":"negative"],["小盘股","IWM",market?.ratios?.["小盘相对大盘"]>0?"参与":"落后",market?.ratios?.["小盘相对大盘"]>0?"positive":"negative"],["市场广度","RSP",market?.layers.breadth.state==="broad"?"广泛":"分化",market?.layers.breadth.state==="broad"?"positive":"warning"]] as const;
 return <TrackerShell active="今日研究总览" title="今天先看风险，再找机会" subtitle="先判断市场是否适合出手，再研究个股技术、行业确认与历史表现。">
  {tracker&&<div className="marketFirstHome">
   <section className="marketRiskHero" data-tone={risk.tone}><header><div><small>MARKET RISK · 今日市场</small><h2>{market?.market_temperature.state??"等待市场环境"} · {risk.label}</h2></div><strong>{market?`${market.market_temperature.score}/${market.market_temperature.max_score}`:"—"}</strong></header><p>{marketStory}</p><div className="marketBrief"><article><small>今天发生了什么</small><b>{market?.layers.risk_appetite.state==="risk_seeking"?"风险偏好仍在":"风险偏好不足"}</b><span>成长相对大盘 {pct(market?.ratios?.["成长相对大盘"])} · 信用环境{market?.layers.risk_appetite.state==="risk_seeking"?"支持":"谨慎"}</span></article><article><small>需要注意</small><b>{market?.layers.breadth.state==="broad"?"多数股票参与":"上涨范围偏窄"}</b><span>小盘相对大盘 {pct(market?.ratios?.["小盘相对大盘"])} · 等权相对指数 {pct(market?.ratios?.["等权相对市值权重"])}</span></article><article><small>今日操作倾向</small><b>{risk.action}</b><span>市场环境只调整优先级和仓位，不篡改个股技术事实。</span></article></div></section>
   <section className="marketSegments" aria-label="不同类型股票的市场环境">{segmentCards.map(([name,ticker,label,tone])=><article key={ticker} data-tone={tone}><header><b>{name}</b><strong>{label}</strong></header><p>{ticker} · 20日 {pct(funds[ticker]?.return_20d)}</p></article>)}</section>
   <section className="opportunityWorkspace"><div className="opportunityList"><header><div><small>TODAY&apos;S OPPORTUNITIES</small><h2>今日多因子机会</h2><p>沿用旧生产规则入选和排序；27 因子、行业与大盘暂作观察证据。</p></div><a href="/zh/watch/resonance/rare-opportunities">查看完整名单 →</a></header><div className="opportunityRows">{opportunities.map((item,index)=>{const itemLinks=industry?.ticker_context[item.symbol]??[];const itemCase=(casesByTicker[item.symbol]??[]).sort((a,b)=>b.first_seen_date.localeCompare(a.first_seen_date))[0];return <button type="button" key={item.symbol} className={selected===item.symbol?"selected":""} onClick={()=>setSelected(item.symbol)}><i>{index+1}</i><span><b>{item.symbol}</b><small>${item.price} · {item.level}</small></span><strong>{item.total_score||"—"}<small>旧生产分</small></strong><span className="opportunityEvidence">{item.components.slice(0,2).join(" · ")||"技术观察"}<small>{itemLinks.slice(0,1).map(x=>`${themes[x.theme_id]?.name??x.theme_id} · ${stateLabel[x.state]??x.state}`).join("")||"行业关系待确认"}</small></span><mark>{itemCase?itemCase.latest_current_status==="current"?"持续观察":itemCase.latest_current_status==="historical_recovered"?"历史恢复":"已入池":"新触发"}</mark></button>})}</div><footer>触发后不会删除：掉榜股票继续进入永久 Tracking Pool，按日期记录后续状态和收益。</footer></div>
    <aside className="selectedResearch"><header><small>个股研究详情</small><h2>{chosen?.symbol??"—"} <span>{chosen?`$${chosen.price}`:""}</span></h2><p>{latestCase?`首次触发 ${latestCase.first_seen_date} · ${latestCase.lifecycle}`:"今天首次进入观察列表"}</p></header><section><div><b>旧生产分</b><strong>{chosen?.total_score??"—"}</strong></div><div><b>27 因子观察分</b><strong>{chosen?.experimental_observational_score??"—"}</strong></div><div><b>正式验证分</b><strong>{chosen?.official_score??"—"}</strong></div></section><dl><div><dt>技术面</dt><dd>{evidence.map(x=>`${factors[x.factor_id]??x.factor_id}${x.hit?" · 当前":` · ${x.bars_since_hit}日前`}`).join("；")||chosen?.components.slice(0,4).join("；")||"暂无近期命中"}</dd><b data-tone={evidence.some(x=>x.hit)?"positive":"neutral"}>{evidence.some(x=>x.hit)?"有效":"观察"}</b></div><div><dt>行业</dt><dd>{classification?[classification.sector,classification.industry_group,classification.industry].filter(Boolean).join(" · "):links.map(x=>`${themes[x.theme_id]?.name??x.theme_id} · ${stateLabel[x.state]??x.state}`).join("；")||"暂无可靠分类"}</dd><b data-tone={links.some(x=>x.etf_context?.favorable_setup)?"positive":"neutral"}>{links.some(x=>x.etf_context?.favorable_setup)?"ETF支持":"未确认"}</b></div><div><dt>大盘匹配</dt><dd>参考 {marketReference}：{reference?.above_ema50?"位于 EMA50 上方":"未站上 EMA50"}，20日表现 {pct(reference?.return_20d)}。</dd><b data-tone={reference?.above_ema50?"positive":"warning"}>{reference?.above_ema50?"支持":"谨慎"}</b></div><div><dt>历史追踪</dt><dd>{latestCase?`已观察 ${latestCase.forward.elapsed_sessions} 个交易日 · ${latestCase.forward.status}`:"触发后将在这里持续记录，不因掉榜删除。"}</dd><b data-tone="neutral">{cases.length} 个案例</b></div></dl><a href="/zh/watch/resonance/research?tab=forward">查看完整历史记录 →</a></aside>
   </section>
   <section className="homeLowerGrid"><article><small>PERMANENT TRACKING POOL</small><h2>永久历史信号池</h2><p>保存首次触发、每日变化、掉榜状态和 5/20/60/100 日结果。</p><strong>{history?.cases.length??"—"} 个历史案例</strong><a href="/zh/watch/resonance/research?tab=forward">查看历史追踪 →</a></article><article><small>MULTI-FACTOR RESEARCH</small><h2>多因子测试排行榜</h2><p>将放在独立研究页面，比较因子与组合的样本、胜率和跨时期稳定性，不进入首页生产排序。</p><strong>独立功能 · 即将接入</strong><a href="/zh/watch/resonance/research">进入研究中心 →</a></article></section>
   <section className={`dailyAudit ${synced?"isHealthy":"isBlocked"}`}><div><small>DATA FRESHNESS / AUDIT</small><h2>{synced?"生产数据日期一致":"日期或防前视状态待核验"}</h2></div><span>Tracker {tracker.as_of}</span><span>Market {market?.as_of??"—"}</span><span>Industry {industry?.as_of??"—"}</span><b>{synced?"future_data_used=false":"停止依赖跨系统结论"}</b></section>
  </div>}
 </TrackerShell>
}
