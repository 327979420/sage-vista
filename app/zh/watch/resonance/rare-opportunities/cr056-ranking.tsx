"use client";
import IndustryContext from "../../industry-radar/context";
import {useEffect,useState} from "react";

type Group={group:string;available:boolean;contribution:number;strengths:Record<string,number>;missing_factor_ids:string[]};
type Row={symbol:string;rank:number|null;price:number|null;status:string;new_nomination:boolean;origin_date:string|null;total:number|null;coverage:number|null;frames:Record<string,number>|null;periods:{monthly:string;weekly:string}|null;high_score_eligible:boolean;reason_codes:string[];checks?:Record<string,{status:string;reason:string}>;groups?:Group[]};
export type CandidateData={as_of:string;result_role:string;policy_version:string;source_snapshot:string;automatic_updates_connected:boolean;refresh_status?:{status:string;target_as_of:string;reason?:string};input_coverage:{repaired_count:number;excluded_count:number};counts:Record<string,number>;ranked_symbols:string[];selected_symbols:string[];new_nomination_symbols:string[];continuing_ranked_symbols:string[];factor_catalog:Record<string,{name:string;timeframe:string}>;reviews:Row[]};
const frameNames:Record<string,string>={monthly_completed:"月线",weekly_completed:"周线",daily:"日线"};
const reasons:Record<string,string>={
 monthly_not_confirmed:"月线方向未获许可（柱缩短、刚转负或改善未确认）",weekly_not_confirmed:"周线方向尚未确认",weekly_near_bear_cross:"周线正柱已接近死叉",monthly_high_zone:"月线价格或MACD处于高位区",near_observed_history_high:"接近已观测历史高点",no_pullback_60d:"相对前60日高点回调不足",structure_broken:"原支撑结构已破坏",no_available_background:"长期上涨或长期筑底背景未确认",no_initial_daily_cross:"没有首次提名所需的当日日线金叉",daily_tradability_not_met:"价格或成交额未达到可交易门槛",historical_adjustment_changed:"供应商复权历史已变化，待核对",empty_invalid_or_old_cache:"原缓存为空、无效或过旧",recent_session_missing:"近期交易日行情缺失",adjustment_anchor_missing:"缺少旧尾日复权核对锚点",completed_months_below_61:"不足61根完整月线",monthly_high_window_missing:"月线高位检验历史不足",daily_history_below_420:"不足420个日线交易会话",local_structure_unavailable:"支撑结构证据不足",source_history_unavailable:"缺少行情来源",
 positive_histogram_supported:"正柱保持或增强",negative_histogram_improving:"负柱改善",positive_histogram_shrinking:"正柱缩短：周分按75%计入",below_observed_high_proves_below_all_time_high:"远离已观测高点，采用保守高位检查",monthly_high_zone_clear:"月线高位检查通过",pullback_60d:"已有足够回调",structure_intact:"原支撑结构保持",deep_sweep_reclaimed:"深度回撤后已重新收复关键支撑",deep_pullback_warning:"回调较深，但尚未触发结构破坏",uptrend_pullback:"长期上涨后的回调",long_base_pullback:"长期筑底背景中的回调",
};
const explain=(code:string)=>reasons[code]??(code.startsWith("raw OHLC relationship")?"原始行情高低价关系异常":`数据检查未通过：${code}`);
const statusName=(r:Row)=>r.rank?"允许入榜":r.status==="not_nominated"?"未触发新提名":r.status==="excluded"?"未获许可":"数据不足";
const pct=(v:number|null)=>v===null?"—":`${(100*v).toFixed(1)}%`;

export function CandidateView({data,latestDate,initialQuery=""}:{data:CandidateData;latestDate?:string;initialQuery?:string}){
 const [mode,setMode]=useState("all");const [query,setQuery]=useState(initialQuery);const [symbol,setSymbol]=useState(initialQuery);
 const bySymbol=new Map(data.reviews.map(r=>[r.symbol,r]));
 const listed=(mode==="new"?data.new_nomination_symbols:mode==="continuing"?data.continuing_ranked_symbols:data.ranked_symbols).map(s=>bySymbol.get(s)!).filter(Boolean);
 const filtered=(mode==="excluded"?data.reviews.filter(r=>!r.rank):query&&mode==="all"?data.reviews:listed).filter(r=>initialQuery&&query===initialQuery?r.symbol.toUpperCase()===initialQuery.toUpperCase():r.symbol.toLowerCase().includes(query.toLowerCase()));
 const visible=filtered.slice(0,50);const selected=visible.find(r=>r.symbol===symbol)??visible[0];
 const periods=listed.find(r=>r.periods)?.periods??data.reviews.find(r=>r.periods)?.periods;
 const alerts=data.reviews.filter(r=>r.high_score_eligible).length;
 const stale=Boolean(latestDate&&latestDate>data.as_of);
 return <>
  <section className="rareFirstView">
   <article className="tone-blue"><small>新模型行情截止</small><b>{data.as_of}</b><p>完整月线 {periods?.monthly??"—"}<br/>完整周线 {periods?.weekly??"—"}</p></article>
   <article className="tone-amber"><small>当日新提名</small><b>{data.new_nomination_symbols.length}只</b><p>当日首次金叉、方向许可与计分覆盖均合格</p></article>
   <article className="tone-violet"><small>持续观察合格榜</small><b>{data.continuing_ranked_symbols.length}只</b><p>原提名冻结，复评无需再次金叉</p></article>
   <article className="tone-rose"><small>达到60分警报线</small><b>{alerts}只</b><p>还需完整覆盖与至少两个证据家族</p></article>
  </section>
  <div className="replayCoverage" role="status"><mark>{stale?`更新落后：已有 ${latestDate} 行情，本榜仍为 ${data.as_of}`:"已核验快照"}</mark><span>{data.automatic_updates_connected?"随现有日终流程自动复评":"新榜自动日更尚未接通"}</span>{data.refresh_status?.status==="failed"&&<mark>{data.refresh_status.target_as_of} 自动复评未完成，保留 {data.as_of} 榜单</mark>}<span>行情可用 {data.input_coverage.repaired_count}只／来源排除 {data.input_coverage.excluded_count}只</span></div>
  <p>候选策略仅供人工复核，尚未验证收益。月→周→日先判断许可，再按各周期固定满分归一、3∶2∶1加权。失格退出当前排名，原提名继续保留。股票身份来自旧缓存观察池，覆盖不等于完整市场。</p>
  <section className="researchReplay">
   <header><div><small>月定方向 · 周确认 · 日择时</small><h2>多因子候选排行榜</h2><p>先看前5只，再点击股票核对分项；“优先复核”不表示达到警报线。</p></div></header>
   <div className="archiveLoadBar"><label>查看 <select aria-label="候选范围" value={mode} onChange={e=>{setMode(e.target.value);setQuery("")}}><option value="all">全部合格榜</option><option value="new">当日新提名</option><option value="continuing">持续观察</option><option value="excluded">未入榜及数据不足</option></select></label><label>股票代码 <input aria-label="查找股票" value={query} onChange={e=>setQuery(e.target.value.trim())} placeholder="例如 DHR、SAIA"/></label></div>
   {visible.length?<div className="replayTable"><div className="v2RankRow replayHead"><span>股票／排名</span><span>总分</span><span>月／周／日</span><span>覆盖</span><span>当前状态</span><span>入选或排除原因</span></div>{visible.map(r=><button type="button" className={`v2RankRow ${selected?.symbol===r.symbol?"isSelected":""}`} key={r.symbol} onClick={()=>setSymbol(r.symbol)}><b>{r.rank?`#${r.rank} · `:""}{r.symbol}{data.selected_symbols.includes(r.symbol)&&<mark>优先复核</mark>}<small>{r.price===null?"价格不可用":`$${r.price}`}</small></b><strong>{r.total?.toFixed(2)??"—"}</strong><span>{r.frames?(["monthly_completed","weekly_completed","daily"].map(tf=>(r.frames![tf]*100).toFixed(1)).join(" / ")):"—"}</span><span>{pct(r.coverage)}</span><span>{statusName(r)}<small>{r.new_nomination?"当日新提名":r.origin_date?`原提名 ${r.origin_date}`:"尚无提名"}</small></span><span>{r.reason_codes.length?r.reason_codes.map(explain).join("；"):r.rank?"月周方向、回调与背景许可通过":"请核对计分覆盖与当前状态"}</span></button>)}</div>:<div className="rareEmpty"><b>{mode==="new"&&!query?"当日没有合格新提名":"没有匹配股票"}</b><p>{mode==="new"&&!query?"计算已完成；可切换持续观察查看旧提名的最新复评。":"可切换范围或修改股票代码。"}</p></div>}
   {filtered.length>50&&<p>共 {filtered.length}只，当前显示前50只；输入股票代码可缩小范围。</p>}
   {selected&&<article className="v2Audit"><header><div><small>{data.as_of} · {statusName(selected)}</small><h3>{selected.symbol} · 分项与原因</h3><p>月线截止 {selected.periods?.monthly??"不可用"} · 周线截止 {selected.periods?.weekly??"不可用"}</p></div><strong>{selected.total?.toFixed(2)??"未入榜"}<small>{selected.total===null?"分项仅供诊断":"人工复核优先级"}</small></strong></header>
    <IndustryContext symbol={selected.symbol} asOf={data.as_of}/>
    {selected.frames&&<div className="v2Equation">{Object.entries(frameNames).map(([tf,name])=><span key={tf}>{name}<b>{(selected.frames![tf]*100).toFixed(1)}</b></span>)}</div>}
    <p>{selected.reason_codes.length?selected.reason_codes.map(explain).join("；"):selected.rank?"所有必要方向与位置许可均已通过。":"当前未获准入榜，请核对计分覆盖与状态。"}</p>
    {selected.checks&&<ul>{Object.entries(selected.checks).map(([key,c])=><li key={key}>{explain(c.reason)}</li>)}</ul>}
    {selected.groups&&<div className="v2Ledger">{selected.groups.map(g=><section key={g.group}><h4>证据组贡献 {g.contribution.toFixed(2)}{!g.available&&" · 数据不足"}</h4>{Object.entries(g.strengths).map(([fid,q])=><p key={fid}><i>{q>0?"✓":"○"}</i><span>{data.factor_catalog[fid]?.name??fid}<small>{frameNames[data.factor_catalog[fid]?.timeframe]} · 候选因子</small></span><b>{g.missing_factor_ids.includes(fid)?"不可用":q===1?"命中":q>0?"较弱／近期":"未计入"}</b></p>)}</section>)}</div>}
    <p>同组证据封顶，父子确认与家族上限已在后台计入；周线正柱缩短时周分乘0.75。分项不是收益概率，当前新榜未生成交易计划。</p>
   </article>}
   <p><a href="/zh/backtest">打开回测：收益曲线与历史报告</a></p>
   <footer>政策 {data.policy_version} · 行情来源 EODHD · 新评分未覆盖旧提名记录。{data.automatic_updates_connected?"本页按每次成功复评更新；失败保留原日期与榜单。":"自动复评接通前，此页仅展示本次已核快照。"}</footer>
  </section>
 </>;
}

export default function CandidateRanking(){
 const [initialQuery]=useState(()=>typeof window==="undefined"?"":(new URLSearchParams(window.location.search).get("symbol")??"").trim().toUpperCase());
 const [data,setData]=useState<CandidateData|null>(null);const [error,setError]=useState(false);const [latestDate,setLatestDate]=useState<string>();
 useEffect(()=>{
  let active=true;
  fetch("/cr056-ranking.json",{cache:"no-store"}).then(r=>{if(!r.ok)throw new Error("missing");return r.json()}).then(d=>{if(d.result_role!=="legacy_comparison"||!Array.isArray(d.ranked_symbols)||!Array.isArray(d.reviews))throw new Error("invalid");if(active)setData(d)}).catch(()=>{if(active)setError(true)});
  fetch("/update-status.json",{cache:"no-store"}).then(r=>r.ok?r.json():null).then(d=>{if(active)setLatestDate(d?.source_latest_complete_date)}).catch(()=>{});
  return ()=>{active=false};
 },[]);
 return data?<CandidateView data={data} latestDate={latestDate} initialQuery={initialQuery}/>:<section className="rareEmpty" role="status"><b>{error?"新模型快照暂时不可用":"正在读取已核新模型快照"}</b><p>{error?"请稍后刷新；没有把旧版排行当作新榜。":"新提名和持续观察将使用同一份后台结果。"}</p></section>;
}
