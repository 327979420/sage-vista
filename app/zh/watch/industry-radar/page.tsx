"use client";
import {useEffect,useState} from "react";
import {TrackerShell} from "../resonance/tracker-ui";
import {EmptyState,SectionHeader,StatusBadge} from "../resonance/product-ui";

type Theme={theme_id:string;name:string;state:string;source_provider?:string;source?:string;error_reason?:string|null;return_20d:number|null;relative_20d:number|null;relative_60d:number|null;breadth_above_sma50:number|null;member_count:number;valid_member_count:number;context:string};
type IndustryReport={as_of:string;membership_version:string|null;future_data_used:boolean;themes:Theme[]};
type MarketFund={ticker:string;name:string;return_20d:number;above_ema20:boolean;above_ema50:boolean};
type MarketLayer={state:string};
type MarketReport={as_of:string;future_data_used:boolean;market_temperature:{score:number;max_score:number;state:string};layers:{trend:MarketLayer;breadth:MarketLayer;risk_appetite:MarketLayer};funds:MarketFund[]};

const stateLabels:Record<string,string>={Leadership:"主线领先","Pullback Watch":"强势回调",Recovery:"修复观察",Neutral:"中性",Unavailable:"数据不足"};
const themeNames:Record<string,string>={"Biotechnology":"生物科技","Cloud Computing":"云计算","Cybersecurity":"网络安全","Medical Devices":"医疗器械","Digital Assets":"数字资产","Semiconductors":"半导体","Robotics & Automation":"机器人","Fintech":"金融科技","Defense & Aerospace":"国防与航空航天","EV / Battery":"电动车与电池","Grid Modernization":"电网现代化","Water Infrastructure":"水务基础设施","Infrastructure":"基础设施","Oil & Gas / Energy":"石油与能源","Uranium":"铀矿","Battery Materials":"电池材料","Clean Energy":"清洁能源","Copper Miners":"铜矿","Critical Minerals":"关键矿产","Solar":"太阳能"};
const MARKET_ETFS=["SPY","QQQ","IWM","RSP"];
const EVERYDAY_ETFS=["SOXX","IGV","CIBR","SKYY","BOTZ","XBI","XLE","XAR","PAVE","FINX","BKCH","IHI"];
const pct=(v:number|null)=>v===null?"—":`${v>=0?"+":""}${(v*100).toFixed(1)}%`;
const breadth=(v:number|null)=>v===null?"—":`${(v*100).toFixed(0)}%`;
const cn=(theme:Theme)=>themeNames[theme.name]??theme.name;

export default function IndustryRadar(){
 const [industry,setIndustry]=useState<IndustryReport|null>(null),[market,setMarket]=useState<MarketReport|null>(null);
 useEffect(()=>{fetch("/industry-radar.json",{cache:"no-store"}).then(x=>x.ok?x.json():null).then(setIndustry);fetch("/market-etf-watch.json",{cache:"no-store"}).then(x=>x.ok?x.json():null).then(setMarket)},[]);
 const marketFunds=(market?.funds??[]).filter(x=>MARKET_ETFS.includes(x.ticker));
 const themeOrder=new Map(EVERYDAY_ETFS.map((ticker,index)=>[ticker,index]));
 const themes=(industry?.themes??[]).slice().sort((a,b)=>(themeOrder.get(a.source??"")??999)-(themeOrder.get(b.source??"")??999)||((b.relative_20d??-99)-(a.relative_20d??-99)));
 const trend=market?.layers.trend.state==="supportive",mixed=market?.layers.breadth.state==="narrow_or_mixed",riskOn=market?.layers.risk_appetite.state==="risk_seeking";
 const marketTitle=trend&&riskOn?mixed?"大盘向上，但行情比较集中":"大盘趋势支持做多":"大盘偏防守";
 const marketAction=trend&&riskOn?mixed?"可以找机会，但只做技术形态最完整的股票。":"可以正常筛选，仍按个股止损执行。":"降低仓位和优先级，等待 SPY/QQQ 重新站稳。";
 return <TrackerShell active="行业与大盘" title="行业与大盘" subtitle="先看 SPY 等大盘，再读 SOXX 等常用行业 ETF；它们只提供背景，不暗改个股技术分。"><div className="irV2">
  {market?<section className="marketDecisionHero"><div><small>大盘结论 · 数据截至 {market.as_of}</small><h2>{marketTitle}</h2><p>{marketAction}</p><mark>{market.market_temperature.score}/{market.market_temperature.max_score} · {market.market_temperature.state}</mark></div><div className="marketLayers"><article><small>趋势</small><b>{trend?"支持":"不支持"}</b><span>SPY/QQQ 与均线关系</span></article><article><small>广度</small><b>{mixed?"上涨集中":"较为扩散"}</b><span>等权与小盘是否跟上</span></article><article><small>风险偏好</small><b>{riskOn?"愿意冒险":"转向防守"}</b><span>只影响优先级，不改技术分</span></article></div></section>:<EmptyState title="正在读取大盘数据"/>}

  <section className="marketFundStrip" aria-label="常看大盘ETF">{marketFunds.map(fund=><article key={fund.ticker}><header><b>{fund.ticker}</b><span>{fund.name}</span></header><strong className={fund.return_20d>=0?"positive":"negative"}>{pct(fund.return_20d)}</strong><small>20日 · EMA20 {fund.above_ema20?"上方":"下方"} / EMA50 {fund.above_ema50?"上方":"下方"}</small></article>)}</section>

  <section className="svPanel"><SectionHeader eyebrow="EVERYDAY SECTOR ETFS" title="常用行业，一张表读完" description="优先显示 SOXX、IGV、CIBR、SKYY、BOTZ 等常看行业。相对强弱均与 SPY 比较；数据不足就明确写出来，不补猜。"/><div className="irTableV2" role="table" aria-label="常用行业ETF状态"><div className="irRowV2 irHeadV2" role="row"><span>行业 / ETF</span><span>状态</span><span>行业20日</span><span>相对SPY 20日</span><span>相对SPY 60日</span><span>站上50日线</span><span>一句话用法</span><span>样本</span></div>{themes.map(theme=><div className="irRowV2" role="row" key={theme.theme_id}><div><b>{cn(theme)}</b><small>{theme.source??"暂无可靠ETF"} · {theme.name}</small></div><span><StatusBadge state={theme.state}>{stateLabels[theme.state]??theme.state}</StatusBadge></span><strong>{pct(theme.return_20d)}</strong><span>{pct(theme.relative_20d)}</span><span>{pct(theme.relative_60d)}</span><span>{breadth(theme.breadth_above_sma50)}</span><span>{theme.state==="Leadership"?"主线中等回调机会":theme.state==="Pullback Watch"?"等支撑确认，不追高":theme.state==="Recovery"?"只观察修复确认":theme.state==="Unavailable"?"数据不足，不做判断":"中性背景，靠个股形态"}</span><span>{theme.valid_member_count}/{theme.member_count}</span></div>)}</div>{!themes.length&&<EmptyState title="正在读取行业数据"/>}</section>

  <details className="svAuditDetails"><summary>查看数据边界</summary><footer>行业数据截至 {industry?.as_of??"—"} · 大盘数据截至 {market?.as_of??"—"} · 成分版本 {industry?.membership_version??"—"} · 未使用未来数据：{String(Boolean(industry&&!industry.future_data_used&&market&&!market.future_data_used))}</footer></details>
  <p className="contextOnlyNotice">使用规则：大盘防守或行业偏弱只降低观察优先级；大盘回调到支撑可以成为机会背景，但必须由个股形态确认。行业与大盘仍不参与正式技术评分。</p>
 </div></TrackerShell>;
}
