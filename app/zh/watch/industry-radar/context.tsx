"use client";
import {useEffect,useState} from "react";

type Fund={symbol:string;as_of:string;available:boolean;state:string;latest_bar:string|null;row_count:number;pullback_from_60d_high?:number;support_levels?:string[]};
type Theme={theme_id:string;name:string;reference_etf:string|null;source_url:string|null;membership_as_of:string|null;membership_source_url:string|null;members:string[];manual:boolean};
type Context={as_of:string;themes:Theme[];funds:Record<string,Fund>;ticker_themes:Record<string,string[]>;classifications:Record<string,{sector:string|null;industry:string|null}>;classification_as_of:string|null;coverage:{themes:number;reference_etfs:number;available_etfs:number;dated_membership_themes:number}};
type Market={as_of:string;funds:unknown[];layers:Record<string,{state:string}>};
const labels:Record<string,string>={"Rising Pullback At Support":"长期趋势中回调至支撑",Uptrend:"上行趋势","Pullback Unconfirmed":"回调待确认","Weak Or Unconfirmed":"偏弱或待确认",Unavailable:"行情不足",supportive:"支持",defensive:"防守",broad:"较广",narrow_or_mixed:"集中或分化",risk_seeking:"风险偏好",mixed_or_defensive:"分化或防守"};
const names:Record<string,string>={"semiconductors":"半导体","software-applications":"软件与应用","cybersecurity":"网络安全","cloud-computing":"云计算","robotics-automation":"机器人与自动化","uranium":"铀矿","copper-miners":"铜矿","clean-energy":"清洁能源","solar":"太阳能","oil-gas":"石油与能源","critical-minerals":"关键矿产","battery-materials":"电池材料","defense-aerospace":"国防与航空","infrastructure":"基础设施","grid-modernization":"电网现代化","fintech":"金融科技","digital-assets":"数字资产","biotechnology":"生物科技","medical-devices":"医疗器械","ev-battery":"电动车与电池","water-infrastructure":"水务基础设施","ai-infrastructure":"AI基础设施","ai-software-applications":"AI软件与应用","memory-storage":"内存与存储","semiconductor-equipment":"半导体设备","data-center-power":"数据中心电力"};

export function ContextView({context,market,symbol,asOf,candidates=[],candidateDate}:{context:Context|null;market:Market|null;symbol?:string;asOf?:string;candidates?:string[];candidateDate?:string}){
 const sameDay=Boolean(context&&(!asOf||asOf===context.as_of));
 const classification=symbol?context?.classifications[symbol]:null;
 const themes=symbol?context?.themes.filter(t=>context.ticker_themes[symbol]?.includes(t.theme_id))??[]:context?.themes??[];
 return <section className="svPanel" aria-label="独立行业与大盘背景"><h2>{symbol?`${symbol} · 行业与大盘背景`:"行业—ETF—股票对照"}</h2>
  <p>背景单独展示，不改变技术分、排名或入榜门槛。{market?`大盘 ${market.as_of} · ${market.funds.length} ETF · 趋势${labels[market.layers.trend.state]??market.layers.trend.state}／广度${labels[market.layers.breadth.state]??market.layers.breadth.state}／风险偏好${labels[market.layers.risk_appetite.state]??market.layers.risk_appetite.state}`:"大盘背景暂不可用"}</p>
  {(market&&(asOf??context?.as_of)&&market.as_of!==(asOf??context?.as_of))&&<p role="status">大盘日期与目标 {asOf??context?.as_of} 不一致，不作为同日背景。</p>}
  {context?<><p>ETF 数据目标日 {context.as_of} · 可用 {context.coverage.available_etfs}/{context.coverage.reference_etfs} · 注册 {context.coverage.themes} 主题 · 有带日期持仓 {context.coverage.dated_membership_themes} 主题。</p>{!sameDay&&<p role="status">行业日期与榜单 {asOf} 不一致，不作为同日背景。</p>}
   {symbol&&<p>公司分类：{classification?`${classification.sector??"未分类"} / ${classification.industry??"未分类"}`:"未匹配"} · FinanceDatabase 静态快照 {context.classification_as_of??"缺失"}。公司分类不等于 ETF 实际持仓。</p>}
   {themes.map(t=>{const f=t.reference_etf?context.funds[t.reference_etf]:null;const matched=t.members.filter(s=>candidates.includes(s));return <article key={t.theme_id}><h3>{names[t.theme_id]??t.name} · {t.reference_etf??"无精确ETF代理／待补"}</h3><p>{f?.available?labels[f.state]??f.state:"ETF行情不可用"} · 实际行情日 {f?.latest_bar??"—"}{f?.available&&f.pullback_from_60d_high!==undefined?` · 距60日高点回调 ${(f.pullback_from_60d_high*100).toFixed(1)}%`:""} {t.source_url&&<a href={t.source_url} target="_blank" rel="noreferrer">官方参考来源</a>}</p><p>官方持仓快照：{t.membership_as_of??"暂无可用证据"} · 已解析股票 {t.members.length} 只。{t.membership_source_url&&<a href={t.membership_source_url} target="_blank" rel="noreferrer">持仓来源</a>} {symbol?"仅表示快照当时的持仓关系，非当前实时持仓。":`合格候选交集（榜单 ${candidateDate??"日期未知"}）：${matched.join("、")||"无匹配"}`}</p>{!symbol&&t.members.length>0&&<details><summary>查看静态股票对照</summary><p>{t.members.join("、")}</p></details>}</article>})}
   {symbol&&!themes.length&&<p>没有该股票的带日期官方 ETF 持仓关联；不据此排除候选，也不由公司分类猜测持仓。</p>}
   <p>ETF趋势是独立背景，不能冒称全行业热度。成员广度仍以原数据覆盖为准；5个人工主题不自动匹配代理。旧快照仅有代码身份，不代表新版 M06 formal 历史接入。</p>
  </>:<p role="status">行业对照暂不可用，等待背景产物更新。</p>}
 </section>;
}

export default function IndustryContext({symbol,asOf}:{symbol?:string;asOf?:string}){
 const overview=!symbol;
 const [candidateDate,setCandidateDate]=useState<string>();
 const [context,setContext]=useState<Context|null>(null),[market,setMarket]=useState<Market|null>(null),[candidates,setCandidates]=useState<string[]>([]);
 useEffect(()=>{let active=true;
  fetch("/industry-radar.json",{cache:"no-store"}).then(r=>r.ok?r.json():null).then(d=>{if(active)setContext(d?.display_context??null)}).catch(()=>{});
  fetch("/market-etf-watch.json",{cache:"no-store"}).then(r=>r.ok?r.json():null).then(d=>{if(active)setMarket(d)}).catch(()=>{});
  if(overview)fetch("/cr056-ranking.json",{cache:"no-store"}).then(r=>r.ok?r.json():null).then(d=>{if(active){setCandidates(d?.ranked_symbols??[]);setCandidateDate(d?.as_of)}}).catch(()=>{});
  return ()=>{active=false};
 },[overview]);
 return <ContextView context={context} market={market} symbol={symbol} asOf={asOf} candidates={candidates} candidateDate={candidateDate}/>;
}
