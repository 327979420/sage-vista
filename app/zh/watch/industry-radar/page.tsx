"use client";
import {useEffect,useState} from "react";
import {TrackerShell} from "../resonance/tracker-ui";
import {EmptyState,SectionHeader,StatusBadge} from "../resonance/product-ui";

type Theme={theme_id:string;name:string;state:string;source_provider?:string;source?:string;error_reason?:string|null;return_20d:number|null;relative_20d:number|null;relative_60d:number|null;breadth_above_sma50:number|null;breadth_change_10d:number|null;member_count:number;raw_holdings_count?:number;us_resolvable_count?:number;valid_member_count:number;context:string};
type IndustryReport={as_of:string;membership_version:string|null;future_data_used:boolean;themes:Theme[]};
type MarketFund={ticker:string;name:string;role:string;return_1d:number;return_5d:number;return_20d:number;above_ema20:boolean;above_ema50:boolean};
type MarketLayer={state:string;signals:Record<string,boolean>};
type MarketReport={as_of:string;future_data_used:boolean;market_temperature:{score:number;max_score:number;state:string;explanation:string};layers:{trend:MarketLayer;breadth:MarketLayer;risk_appetite:MarketLayer};funds:MarketFund[]};

const stateLabels:Record<string,string>={Leadership:"主线领先", "Pullback Watch":"强势回调",Recovery:"修复观察",Neutral:"中性",Unavailable:"数据不足"};
const themeNames:Record<string,string>={"Biotechnology":"生物科技","Cloud Computing":"云计算","Cybersecurity":"网络安全","Medical Devices":"医疗器械","Digital Assets":"数字资产","Semiconductors":"半导体","Robotics":"机器人","Fintech":"金融科技","Defense":"国防","Defense & Aerospace":"国防与航空航天","Electric Vehicles & Battery":"电动车与电池","EV / Battery":"电动车与电池","Grid Modernization":"电网现代化","Water":"水务","Water Infrastructure":"水务基础设施","Infrastructure":"基础设施","Energy":"能源","Oil & Gas / Energy":"石油与能源","Uranium":"铀矿","Memory":"存储芯片","AI Infrastructure":"AI基础设施"};
const pct=(v:number|null)=>v===null?"—":`${v>=0?"+":""}${(v*100).toFixed(1)}%`;
const cn=(theme:Theme)=>themeNames[theme.name]??theme.name;
const breadth=(theme:Theme)=>theme.breadth_above_sma50===null?"—":`${(theme.breadth_above_sma50*100).toFixed(0)}%`;

function ThemeCard({theme,kind}:{theme:Theme;kind:"leader"|"pullback"|"recovery"|"risk"}){
 const guidance=kind==="leader"?"趋势热点：优先在个股技术形态合格时核对":kind==="pullback"?"曾经强势、目前广度回落：等支撑企稳，不追高":kind==="recovery"?"短期回暖但长趋势仍混合：只观察，不当主线":"相对强弱偏弱：降低行业信心，不单独否决个股";
 return <article className="themeActionCard" data-kind={kind}><header><div><small>{theme.source??"无ETF"} · {stateLabels[theme.state]}</small><h3>{cn(theme)}</h3></div><StatusBadge state={theme.state}>{stateLabels[theme.state]}</StatusBadge></header><div className="themeStats"><span><small>相对大盘20日</small><b>{pct(theme.relative_20d)}</b></span><span><small>相对大盘60日</small><b>{pct(theme.relative_60d)}</b></span><span><small>站上50日线成员</small><b>{breadth(theme)}</b></span></div><p>{guidance}</p><small>有效样本 {theme.valid_member_count}/{theme.member_count} · 数据源 {theme.source_provider??"—"}</small></article>;
}

export default function IndustryRadar(){
 const [industry,setIndustry]=useState<IndustryReport|null>(null),[market,setMarket]=useState<MarketReport|null>(null),[sort,setSort]=useState<"state"|"relative_20d"|"breadth_above_sma50">("state");
 useEffect(()=>{fetch("/industry-radar.json",{cache:"no-store"}).then(x=>x.ok?x.json():null).then(setIndustry);fetch("/market-etf-watch.json",{cache:"no-store"}).then(x=>x.ok?x.json():null).then(setMarket)},[]);
 const available=(industry?.themes??[]).filter(x=>x.state!=="Unavailable"),unavailable=(industry?.themes??[]).filter(x=>x.state==="Unavailable");
 const leaders=available.filter(x=>x.state==="Leadership").sort((a,b)=>(b.relative_20d??-99)-(a.relative_20d??-99));
 const pullbacks=available.filter(x=>x.state==="Pullback Watch").sort((a,b)=>(b.relative_60d??-99)-(a.relative_60d??-99));
 const recoveries=available.filter(x=>x.state==="Recovery").sort((a,b)=>(b.relative_20d??-99)-(a.relative_20d??-99));
 const risks=available.filter(x=>x.state==="Neutral").sort((a,b)=>(a.relative_60d??99)-(b.relative_60d??99)).slice(0,4);
 const order:Record<string,number>={Leadership:0,"Pullback Watch":1,Recovery:2,Neutral:3};
 const ranked=available.slice().sort((a,b)=>sort==="state"?(order[a.state]-order[b.state])||((b.relative_20d??-99)-(a.relative_20d??-99)):((b[sort]??-99)-(a[sort]??-99)));
 const marketFunds=(market?.funds??[]).filter(x=>["SPY","QQQ","IWM","RSP"].includes(x.ticker));
 const trend=market?.layers.trend.state==="supportive",mixed=market?.layers.breadth.state==="narrow_or_mixed",riskOn=market?.layers.risk_appetite.state==="risk_seeking";
 const marketTitle=trend&&riskOn?mixed?"趋势支持，但上涨集中":"趋势与风险偏好支持":"市场需要防守";
 const marketAction=trend&&riskOn?mixed?"今天怎么用：可以做，但只选个股技术证据最完整的机会，不追高。":"今天怎么用：允许正常筛选，仍按个股风险计划执行。":"今天怎么用：降低仓位和优先级，等待大盘重新站稳。";
 return <TrackerShell active="行业与大盘" title="行业与大盘" subtitle="先判断今天能不能做，再看资金集中在哪些行业；只提供决策背景，不暗改个股技术分。"><div className="irV2">
  {market&&<section className="marketDecisionHero"><div><small>大盘决策 · 数据截至 {market.as_of}</small><h2>{marketTitle}</h2><p>{marketAction}</p><mark>{market.market_temperature.score}/{market.market_temperature.max_score} · {market.market_temperature.state}</mark></div><div className="marketLayers"><article><small>趋势</small><b>{trend?"支持":"不支持"}</b><span>SPY/QQQ 与均线关系</span></article><article><small>广度</small><b>{mixed?"上涨集中":"扩散"}</b><span>等权与小盘是否跟上</span></article><article><small>风险偏好</small><b>{riskOn?"资金愿意冒险":"转向防守"}</b><span>成长与信用市场</span></article></div></section>}

  <section className="marketFundStrip">{marketFunds.map(fund=><article key={fund.ticker}><header><b>{fund.ticker}</b><span>{fund.name}</span></header><strong className={fund.return_20d>=0?"positive":"negative"}>{pct(fund.return_20d)}</strong><small>20日 · EMA20 {fund.above_ema20?"上方":"下方"} / EMA50 {fund.above_ema50?"上方":"下方"}</small></article>)}</section>

  <section className="svPanel"><SectionHeader eyebrow="TODAY&apos;S INDUSTRY MAP" title="今天先看哪些行业" description="主线看相对强弱和成员广度；回调与修复分开，不把短期反弹误写成长期主线。"/><div className="industryDecisionColumns"><section><header><small>01</small><h3>趋势主线</h3><p>行业相对大盘强、较多成分股站上50日线。</p></header><div>{leaders.map(theme=><ThemeCard key={theme.theme_id} theme={theme} kind="leader"/>)}{!leaders.length&&<EmptyState title="当前没有明确主线"/>}</div></section><section><header><small>02</small><h3>回调与修复</h3><p>优先等回撤到支撑，不在刚突破时追高。</p></header><div>{pullbacks.map(theme=><ThemeCard key={theme.theme_id} theme={theme} kind="pullback"/>)}{recoveries.map(theme=><ThemeCard key={theme.theme_id} theme={theme} kind="recovery"/>)}{!pullbacks.length&&!recoveries.length&&<EmptyState title="当前没有回调或修复候选"/>}</div></section></div></section>

  <section className="svPanel"><SectionHeader eyebrow="WEAK CONTEXT" title="当前偏弱的行业背景" description="这不是自动卖出或一票否决，只提醒个股缺少行业顺风。"/><div className="industryRiskGrid">{risks.map(theme=><ThemeCard key={theme.theme_id} theme={theme} kind="risk"/>)}</div></section>

  <section className="svPanel"><SectionHeader eyebrow="FULL AUDIT TABLE" title="完整行业状态表" description="数值直接读取生产数据，不在页面重新计算。相对强弱均相对SPY。" action={<label className="irSort">排序 <select value={sort} onChange={e=>setSort(e.target.value as typeof sort)}><option value="state">实用状态</option><option value="relative_20d">20日相对强弱</option><option value="breadth_above_sma50">成员广度</option></select></label>}/><div className="irTableV2" role="table" aria-label="行业雷达主题表"><div className="irRowV2 irHeadV2" role="row"><span>行业 / 参考ETF</span><span>状态</span><span>20日相对</span><span>60日相对</span><span>成员广度</span><span>10日变化</span><span>有效成员</span><span>数据质量</span></div>{ranked.map(t=><div className="irRowV2" role="row" key={t.theme_id}><div><b>{cn(t)}</b><small>{t.source??"—"} · {t.name}</small></div><span><StatusBadge state={t.state}>{stateLabels[t.state]}</StatusBadge></span><strong>{pct(t.relative_20d)}</strong><span>{pct(t.relative_60d)}</span><span>{breadth(t)}</span><span>{pct(t.breadth_change_10d)}</span><span><b>{t.valid_member_count}</b> / {t.member_count}</span><span><b>{t.source_provider??"—"}</b><small>原始 {t.raw_holdings_count??t.member_count} · 美股可识别 {t.us_resolvable_count??"—"}</small></span></div>)}</div></section>

  <details className="svAuditDetails"><summary>数据质量与暂不可用行业（{unavailable.length}）</summary>{unavailable.length?<div className="irUnavailable">{unavailable.map(t=><article key={t.theme_id}><StatusBadge state="Unavailable">数据不足</StatusBadge><b>{cn(t)}</b><span>{t.valid_member_count}/{t.member_count} 有效 · {t.source??t.source_provider??"—"}</span><p>{t.error_reason??t.context}</p></article>)}</div>:<EmptyState title="没有不可用行业"/>}<footer>行业数据截至 {industry?.as_of??"—"} · 大盘数据截至 {market?.as_of??"—"} · 成分版本 {industry?.membership_version??"—"} · 未使用未来数据：{String(Boolean(industry&&!industry.future_data_used&&market&&!market.future_data_used))}</footer></details>
  <p className="contextOnlyNotice">研究边界：行业与大盘目前只调整观察优先级，不改变个股正式技术分。回测通过并更新规则手册前，不会偷偷加权。</p>
 </div></TrackerShell>;
}
