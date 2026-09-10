"use client";
import IndustryContext from "../../industry-radar/context";
import {useEffect,useState,useRef} from "react";

type Group={timeframe:string;group:string;available:boolean;contribution:number;strengths:Record<string,number>;missing_factor_ids:string[]};
type WatchEntry={confirmation_kinds?:string[];path:string;timeframe:string;trigger_date:string;trigger_close:number;state:string;invalidated_at:string|null;observation_return:number;observed_sessions:number};
type Row={nomination_price?:number|null;watch_entries?:WatchEntry[];watch_since?:string|null;watch_return?:number|null;watch_as_of?:string;entry_paths?:{confirmation_kinds?:string[];path:string;timeframe:string;confirmed_through:string;cross_date:string|null}[];symbol:string;rank:number|null;price:number|null;status:string;new_nomination:boolean;origin_date:string|null;total:number|null;coverage:number|null;frames:Record<string,number>|null;periods:{monthly:string;weekly:string}|null;high_score_eligible:boolean;reason_codes:string[];checks?:Record<string,{status:string;reason:string}>;groups?:Group[]};
export type CandidateData={view_version?:string;detail_path?:string;as_of:string;result_role:string;policy_version:string;source_snapshot:string;automatic_updates_connected:boolean;refresh_status?:{status:string;target_as_of:string;reason?:string};input_coverage:{repaired_count:number;excluded_count:number};counts:Record<string,number>;ranked_symbols:string[];selected_symbols:string[];new_nomination_symbols:string[];continuing_ranked_symbols:string[];factor_catalog:Record<string,{name:string;timeframe:string;role?:string;research_status?:string}>;reviews:Row[]};
const frameNames:Record<string,string>={monthly_completed:"月线",weekly_completed:"周线",daily:"日线"};
const pathNames:Record<string,string>={bottom_macd:"两底金叉",three_push_breakout:"三推突破",support_reversal:"支撑反转"};
function GateTags({row}:{row:Row}){
 const paths=row.watch_entries?.filter(p=>p.state==="active");
 const items=paths?.length?paths:row.entry_paths??[];
 const kinds=[...new Set(items.map(p=>p.path))];
 return <span className="candidateGateTags">{kinds.map(kind=><span className={`candidateGateTag gate-${kind}`} key={kind}>{(kind==="support_reversal"&&items.some(p=>p.path===kind&&p.confirmation_kinds?.includes("negative_histogram_pullback"))?"支撑反转·动能改善":pathNames[kind]??kind)} · {["monthly_completed","weekly_completed","daily"].filter(tf=>items.some(p=>p.path===kind&&p.timeframe===tf)).map(tf=>frameNames[tf].replace("线","")).join("/")}</span>)}</span>;
}
const returnText=(v:number|null|undefined)=>v===null||v===undefined?"—":`${v>=0?"+":""}${(v*100).toFixed(2)}%`;
const reasons:Record<string,string>={
 negative_histogram_not_confirmed:"负柱尚未连续两次缩短",bearish_candle_evidence_unavailable:"阴线风险检查数据不足",large_full_body_bearish_candle:"三根确认K线中有大实体双短影阴线",no_confirmed_breakout_support_retest:"尚无符合条件的已确认突破支撑回踩",
 no_surviving_new_rule_structure:"历史重核未找到仍有效的新版门票结构",no_confirmed_reversal_entry:"尚无已确认的底部反转门票",monthly_not_confirmed:"月线方向未获许可（正柱衰减、刚转负或负柱改善未确认）",weekly_not_confirmed:"周线方向尚未确认",weekly_near_bear_cross:"周线正柱已接近死叉",monthly_high_zone:"月线价格或MACD处于高位区",near_observed_history_high:"接近已观测历史高点",no_pullback_60d:"相对前60日高点回调不足",structure_broken:"局部波段回撤过深，未收复0.618（不等于门票结构失效）",no_available_background:"长期上涨或长期筑底背景未确认",no_initial_daily_cross:"没有首次提名所需的当日日线金叉",daily_tradability_not_met:"价格或成交额未达到可交易门槛",historical_adjustment_changed:"供应商复权历史已变化，待核对",empty_invalid_or_old_cache:"原缓存为空、无效或过旧",recent_session_missing:"近期交易日行情缺失",adjustment_anchor_missing:"缺少旧尾日复权核对锚点",completed_months_below_61:"不足61根完整月线",monthly_high_window_missing:"月线高位检验历史不足",daily_history_below_420:"不足420个日线交易会话",local_structure_unavailable:"支撑结构证据不足",source_history_unavailable:"缺少行情来源",
 positive_histogram_supported:"正柱保持或增强",negative_histogram_improving:"负柱改善",positive_histogram_shrinking:"正柱缩短：周分按75%计入",below_observed_high_proves_below_all_time_high:"远离已观测高点，采用保守高位检查",monthly_high_zone_clear:"月线高位检查通过",pullback_60d:"已有足够回调",structure_intact:"原支撑结构保持",deep_sweep_reclaimed:"深度回撤后已重新收复关键支撑",deep_pullback_warning:"回调较深，但尚未触发结构破坏",uptrend_pullback:"长期上涨后的回调",long_base_pullback:"长期筑底背景中的回调",
};
const explain=(code:string)=>reasons[code]??(code.startsWith("raw OHLC relationship")?"原始行情高低价关系异常":`数据检查未通过：${code}`);
const statusName=(r:Row)=>r.rank?"允许入榜":r.status==="not_nominated"?"未触发新提名":r.status==="excluded"?"未获许可":"数据不足";
const researchNames:Record<string,string>={candidate:"候选，未验证",rejected:"旧研究未通过",testing:"待验证",pending:"待研究",unstable:"结果不稳定",insufficient_sample:"样本不足",paused:"暂停",validated:"已验证"};
const pct=(v:number|null)=>v===null?"—":`${(100*v).toFixed(1)}%`;

type FactorDetail={factor_id:string;available:boolean;hit:boolean;recent_hit:boolean;bars_since_hit:number|null;latest_hit_date:string|null;runtime_status:string;score_role:string;completed_through:string;period_bar_count:number;minimum_bars:number;evidence?:{ratio?:number;histogram?:number;previous_histogram?:number}};
type DetailBundle={source_snapshot:string;reviews:Record<string,{groups:Group[];factors:FactorDetail[];entry_gate?:{evidence?:{daily?:{pullback_momentum?:{confirmed:boolean;reason:string;momentum:{histogram:number[];dates:string[]};bearish_candle:{available:boolean;blocked:boolean}}}}};checks?:Record<string,{status:string;reason:string}>;structures?:{path:string;timeframe:string;trigger_date:string;structure_floor:number;state:string;invalidated_at:string|null}[]}>};
function PeriodFactors({data,symbol}:{data:CandidateData;symbol:string}){
 const [showAll,setShowAll]=useState(false);
 const [bundle,setBundle]=useState<DetailBundle|null>(null);const [failed,setFailed]=useState(false);
 useEffect(()=>{let active=true;
  if(data.detail_path!=="/cr056-factor-details.json.gz")return;
  fetch(data.detail_path,{cache:"no-store"}).then(async response=>{
   if(!response.ok||!response.body)throw new Error("details unavailable");
   const bytes=new Uint8Array(await response.arrayBuffer());
   const stream=new Blob([bytes]).stream();
   const parsed=await new Response(bytes[0]===31&&bytes[1]===139?stream.pipeThrough(new DecompressionStream("gzip")):stream).json();
   if(parsed.source_snapshot!==data.source_snapshot)throw new Error("snapshot mismatch");
   if(active)setBundle(parsed);
  }).catch(()=>{if(active)setFailed(true)});return()=>{active=false};
 },[data.detail_path,data.source_snapshot]);
 if(!data.detail_path)return null;
 if(failed)return <p role="status">本次快照的分项暂不可用，请刷新；未混用其他版本证据。</p>;
 if(!bundle)return <p role="status">正在读取月、周、日因子明细…</p>;
 const detail=bundle.reviews[symbol];if(!detail)return <p>该股票尚未通过门票或数据检查，本次没有深度检测结果。</p>;
 const strengths=Object.assign({},...detail.groups.map(g=>g.strengths));
 const momentum=detail.entry_gate?.evidence?.daily?.pullback_momentum;
 return <div className="v2Ledger periodFactorLedger">{momentum&&<section><h4>突破回踩动能检查</h4><p>三根负柱：{momentum.momentum.histogram.map(v=>v.toFixed(4)).join(" → ")}<small>{momentum.momentum.dates.join(" / ")}</small></p><p>{momentum.confirmed?"满足突破回踩动能门票":explain(momentum.reason)}</p><p>大实体双短影阴线：{!momentum.bearish_candle.available?"证据不足":momentum.bearish_candle.blocked?"有，阻止本次动能门票":"未发现"}</p><small>满足门票后仍需通过方向与位置检查，不代表已执行买入。</small></section>}{detail.checks&&<section><h4>本次准入检查（含排除原因）</h4>{Object.entries(detail.checks).map(([key,c])=><p key={key}><span>{explain(c.reason)}</span><b>{c.status==="allowed"?"通过":c.status==="blocked"?"未通过":"证据不足"}</b></p>)}</section>}<details><summary>核对门票原始结构底部</summary><small>这里是旧门票保存的结构底，不是当前回踩支撑或已确定的交易止损。当前回踩支撑规则正在核对。</small>{detail.structures?.filter(p=>p.state==="active").map((p,i)=><p key={i}><span>{frameNames[p.timeframe]} · {pathNames[p.path]}<small>触发 {p.trigger_date}</small></span><b>${p.structure_floor.toFixed(2)}</b></p>)}</details><label className="factorVisibility"><input type="checkbox" checked={showAll} onChange={e=>setShowAll(e.target.checked)}/> 显示全部检查（含未命中与缺数据）</label>{Object.entries(frameNames).map(([tf,name])=>{
  const factors=detail.factors.filter(f=>data.factor_catalog[f.factor_id]?.timeframe===tf);
  return <details key={tf} open><summary>{name} · {factors.length}项检查 · {factors.filter(f=>f.available&&f.hit).length}项当前命中</summary>
   <p className="periodFactorNote">截至 {factors[0]?.completed_through??"—"}；窗口按{name}K线根数计算。近期命中保留发生日期。</p>
   {detail.groups.filter(g=>g.timeframe===tf&&g.contribution>0).map(g=><p className="periodFactorNote" key={g.group}>证据组：{Object.keys(g.strengths).map(id=>data.factor_catalog[id]?.name.replace(/(\d+)日/g,"$1根")).join("／")} · 原始贡献 {g.contribution.toFixed(2)}</p>)}
   {factors.filter(f=>showAll||f.hit||f.recent_hit||!f.available).map(f=>{const meta=data.factor_catalog[f.factor_id];
    const state=!f.available?(f.runtime_status==="definition_required"?"未实现，不计分":`数据不足：需${f.minimum_bars}根，现有${f.period_bar_count}根`):
     f.score_role==="risk"?(f.hit?"风险命中，单独参考":"未命中风险"):
     f.score_role==="ticket"||f.score_role==="qualification"?(f.hit?"条件满足，不重复加分":"条件未满足，不计分"):
     strengths[f.factor_id]>0?(f.hit?"命中":"近期命中"):
     f.hit||f.recent_hit?"检测命中，依赖或去重后未计入":"未命中";
    return <p key={f.factor_id}><i>{f.available&&f.hit?"✓":"○"}</i><span>{meta?.name.replace(/(\d+)日/g,"$1根")??f.factor_id}<small>{f.latest_hit_date?`最近命中 ${f.latest_hit_date} · `:""}{meta?.research_status?`原研究：${researchNames[meta.research_status]??meta.research_status}`:""}{typeof f.evidence?.ratio==="number"?` · 本期成交量比 ${f.evidence.ratio.toFixed(2)}`:""}{typeof f.evidence?.histogram==="number"&&typeof f.evidence?.previous_histogram==="number"?` · MACD柱 ${f.evidence.previous_histogram.toFixed(2)} → ${f.evidence.histogram.toFixed(2)}`:""}</small></span><b>{state}</b></p>})}
  </details>
 })}</div>
}

export function filterCandidateRows(rows:Row[],filters:{from:string;to:string;minimum:string;maximum:string;sort:string}){
 const filtered=rows.filter(r=>(!filters.from||(r.origin_date!==null&&r.origin_date>=filters.from))&&(!filters.to||(r.origin_date!==null&&r.origin_date<=filters.to))&&(!filters.minimum||(r.total!==null&&r.total>=Number(filters.minimum)))&&(!filters.maximum||(r.total!==null&&r.total<=Number(filters.maximum))));
 return filtered.sort((a,b)=>{
  const tie=(a.rank??Infinity)-(b.rank??Infinity)||a.symbol.localeCompare(b.symbol);
  if(filters.sort.startsWith("date")){
   if(a.origin_date===null||b.origin_date===null)return a.origin_date===b.origin_date?tie:a.origin_date===null?1:-1;
   return (filters.sort==="date_new"?b.origin_date.localeCompare(a.origin_date):a.origin_date.localeCompare(b.origin_date))||tie;
  }
  if(a.total===null||b.total===null)return a.total===b.total?tie:a.total===null?1:-1;
  return (filters.sort==="score_low"?a.total-b.total:b.total-a.total)||tie;
 });
}

export function CandidateView({data,latestDate,initialQuery=""}:{data:CandidateData;latestDate?:string;initialQuery?:string}){
 const observationReady=data.view_version==="nomination-observation-1";
 const detailRef=useRef<HTMLElement>(null);
 const [filters,setFilters]=useState({from:"",to:"",minimum:"",maximum:"",sort:"score_high"});
 const [mode,setMode]=useState("continuing");const [query,setQuery]=useState(initialQuery);const [symbol,setSymbol]=useState(initialQuery);
 const bySymbol=new Map(data.reviews.map(r=>[r.symbol,r]));
 const listed=(mode==="new"?data.new_nomination_symbols:mode==="continuing"?data.continuing_ranked_symbols:data.ranked_symbols).map(s=>bySymbol.get(s)!).filter(Boolean);
 const searched=(query?data.reviews:listed).filter(r=>initialQuery&&query===initialQuery?r.symbol.toUpperCase()===initialQuery.toUpperCase():r.symbol.toLowerCase().includes(query.toLowerCase()));
 const filtered=mode==="continuing"?filterCandidateRows(searched,filters):searched;
 const visible=filtered.slice(0,50);const selected=visible.find(r=>r.symbol===symbol)??visible[0];
 const periods=listed.find(r=>r.periods)?.periods??data.reviews.find(r=>r.periods)?.periods;
 const alerts=data.reviews.filter(r=>r.high_score_eligible).length;
 const stale=Boolean(latestDate&&latestDate>data.as_of);
 return <div className="candidateSurface">
  <div className="candidateHeading"><div><small>月定方向 · 周确认 · 日择时</small><h2>候选榜</h2><p>{data.as_of} 收盘 · 达到60分警报线 {alerts}只</p></div><a href="/zh/backtest">回测与收益报告 →</a></div>
  <div className="replayCoverage" role="status"><mark>{stale?`更新落后：已有 ${latestDate} 行情，本榜仍为 ${data.as_of}`:"已核验快照"}</mark><span>{data.automatic_updates_connected?"随现有日终流程自动复评":"新榜自动日更尚未接通"}</span>{data.refresh_status?.status==="failed"&&<mark>{data.refresh_status.target_as_of} 自动复评未完成，保留 {data.as_of} 榜单</mark>}<span>行情可用 {data.input_coverage.repaired_count}只／来源排除 {data.input_coverage.excluded_count}只</span></div>
  <section className="researchReplay candidateWorkspace">
   <div className="candidateToolbar"><div className="candidateTabs" role="group" aria-label="候选范围">{[["new","新提名",data.new_nomination_symbols.length],["continuing","持续观察",data.continuing_ranked_symbols.length]].map(([id,label,count])=><button key={id} type="button" aria-pressed={mode===id} onClick={()=>{setMode(String(id));setQuery("")}}>{label} <b>{count}只</b></button>)}</div><label>查找股票 <input aria-label="查找股票" value={query} onChange={e=>setQuery(e.target.value.trim())} placeholder="代码，含未入榜原因"/></label></div>
   {mode==="continuing"&&<details className="candidateFilters"><summary>筛选与排序 · {filtered.length}只{(filters.from||filters.to||filters.minimum||filters.maximum)?" · 已筛选":""}</summary><div>
    <label>排列方式<select aria-label="排列方式" value={filters.sort} onChange={e=>setFilters({...filters,sort:e.target.value})}><option value="score_high">分数从高到低</option><option value="score_low">分数从低到高</option><option value="date_new">最近提名优先</option><option value="date_old">最早提名优先</option></select></label>
    <label>原提名从<input aria-label="原提名开始日期" type="date" value={filters.from} onInput={e=>setFilters({...filters,from:e.currentTarget.value})}/></label>
    <label>到<input aria-label="原提名结束日期" type="date" value={filters.to} onInput={e=>setFilters({...filters,to:e.currentTarget.value})}/></label>
    <label>最低分<input aria-label="最低分" type="number" min="0" max="100" value={filters.minimum} onChange={e=>setFilters({...filters,minimum:e.target.value})}/></label>
    <label>最高分<input aria-label="最高分" type="number" min="0" max="100" value={filters.maximum} onChange={e=>setFilters({...filters,maximum:e.target.value})}/></label>
    <button type="button" onClick={()=>setFilters({from:"",to:"",minimum:"",maximum:"",sort:"score_high"})}>重置筛选</button>
   </div><p>时间指原提名日期；#编号保留后台原排名。筛选只改变当前视图。</p></details>}
   {!observationReady&&<p className="candidateHint">上榜收益基准更新中，暂不显示旧口径涨跌。</p>}
   <p className="candidateHint">按本次复评总分排序；三类形态标签不额外加分。</p>
   <p className="candidateHint">蓝色：两底金叉 · 紫色：三推突破 · 橙色：支撑反转。标签表示门票来源，不代表现在可以买入。</p>
   <p className="candidateHint">{query?"搜索包含未入榜股票；诊断结果不代表获准入榜。":mode==="new"?"当日新提名：通过当前版本门票、方向与评分检查。":"持续观察：此前已触发新版门票，结构仍有效；每日复评，无需每天重新触发。"}</p>
   {visible.length?<div className="replayTable"><div className="v2RankRow replayHead"><span>股票／排名</span><span>总分</span><span>月／周／日</span><span>上榜后涨跌</span><span>当前状态</span><span>入选或排除原因</span></div>{visible.map(r=><button type="button" className={`v2RankRow ${selected?.symbol===r.symbol?"isSelected":""}`} key={r.symbol} onClick={()=>{setSymbol(r.symbol);requestAnimationFrame(()=>detailRef.current?.scrollIntoView({behavior:"smooth",block:"start"}))}}><b>{r.rank?`#${r.rank} · `:""}{r.symbol}{data.selected_symbols.includes(r.symbol)&&<mark>优先复核</mark>}<small>{r.price===null?"价格不可用":`$${r.price}`}</small><GateTags row={r}/></b><strong>{r.total?.toFixed(2)??"—"}</strong><span>{r.frames?(["monthly_completed","weekly_completed","daily"].map(tf=>(r.frames![tf]*100).toFixed(1)).join(" / ")):"—"}</span><span>{returnText(observationReady?r.watch_return:null)}<small>{r.origin_date?`${r.origin_date}`:"尚无上榜日期"}</small>{r.watch_as_of&&r.watch_as_of!==data.as_of&&<small>截至 {r.watch_as_of}</small>}</span><span>{statusName(r)}<small>{r.new_nomination?"当日新提名":r.origin_date?`原提名 ${r.origin_date}`:"尚无提名"}</small></span><span>{r.reason_codes.length?r.reason_codes.map(explain).join("；"):r.rank?"月周方向、回调与背景许可通过":"请核对计分覆盖与当前状态"}</span></button>)}</div>:<div className="rareEmpty"><b>{mode==="new"&&!query?"当日没有合格新提名":"没有匹配股票"}</b><p>{mode==="new"&&!query?"计算已完成；可切换持续观察查看旧提名的最新复评。":"可切换范围或修改股票代码。"}</p></div>}
   {filtered.length>50&&<p>共 {filtered.length}只，当前显示前50只；输入股票代码可缩小范围。</p>}
   {selected&&<article ref={detailRef} className="v2Audit candidateDetail"><header><div><small>{data.as_of} · {statusName(selected)}</small><h3>{selected.symbol} · 分项与原因</h3><p>月线截止 {selected.periods?.monthly??"不可用"} · 周线截止 {selected.periods?.weekly??"不可用"}</p></div><strong>{selected.total?.toFixed(2)??"未入榜"}<small>{selected.total===null?"分项仅供诊断":"人工复核优先级"}</small></strong></header>

    <p className="candidateHint">上榜触发日期：{selected.origin_date??"尚未上榜"} · 上榜收盘基准：{selected.nomination_price!=null?`$${selected.nomination_price.toFixed(2)}`:"当日行情不可用"} · 上榜后涨跌：{returnText(observationReady?selected.watch_return:null)} · 复评截至：{selected.watch_as_of??data.as_of}</p>
    {selected.frames&&<div className="v2Equation candidateScores">{Object.entries(frameNames).map(([tf,name])=><span key={tf}>{name}<b>{(selected.frames![tf]*100).toFixed(1)}</b><small>权重 {tf==="monthly_completed"?"3":tf==="weekly_completed"?"2":"1"}</small></span>)}</div>}
    <p>{selected.reason_codes.length?selected.reason_codes.map(explain).join("；"):selected.rank?"所有必要方向与位置许可均已通过。":"当前未获准入榜，请核对计分覆盖与状态。"}</p>
    <GateTags row={selected}/>
    {!!selected.watch_entries?.length&&<div className="candidateWatchReturns"><p>各类门票触发记录 · 早于上榜的记录属于历史重核</p>{selected.watch_entries.map(p=><p key={`${p.path}-${p.timeframe}`}><span>{frameNames[p.timeframe]} · {pathNames[p.path]}{p.confirmation_kinds?.includes("negative_histogram_pullback")?" · 负柱连续改善":""}<small>门票触发：{p.trigger_date} 收盘 ${p.trigger_close.toFixed(2)} · {p.observed_sessions}个交易日{p.state!=="active"?` · 结构失效 ${p.invalidated_at}`:` · 截至 ${selected.watch_as_of??data.as_of} 结构仍有效`}</small></span><b>{returnText(p.observation_return)}</b></p>)}<small>截至 {selected.watch_as_of}，不含交易费用和分红。主表从上榜日计算；这里单独展示各门票后的历史观察涨跌，不能当作上榜后收益。历史重核不是当时已发出的真实警报。</small></div>}

    {selected.checks&&<details className="candidateSecondary"><summary>方向与位置检查</summary><ul>{Object.entries(selected.checks).map(([key,c])=><li key={key}>{explain(c.reason)}</li>)}</ul></details>}
    <details className="candidateSecondary"><summary>查看月、周、日命中与风险明细</summary><PeriodFactors key={data.source_snapshot} data={data} symbol={selected.symbol}/></details>
    <details className="candidateSecondary"><summary>大盘与行业背景</summary><IndustryContext symbol={selected.symbol} asOf={data.as_of}/></details>
    {selected.groups&&<div className="v2Ledger">{selected.groups.map(g=><section key={g.group}><h4>证据组贡献 {g.contribution.toFixed(2)}{!g.available&&" · 数据不足"}</h4>{Object.entries(g.strengths).map(([fid,q])=><p key={fid}><i>{q>0?"✓":"○"}</i><span>{data.factor_catalog[fid]?.name??fid}<small>{frameNames[data.factor_catalog[fid]?.timeframe]} · 候选因子</small></span><b>{g.missing_factor_ids.includes(fid)?"不可用":q===1?"命中":q>0?"较弱／近期":"未计入"}</b></p>)}</section>)}</div>}
    <p className="candidateHint">月、周、日按3∶2∶1加权，同组证据封顶。覆盖 {pct(selected.coverage)}；分数是复核优先级，不是收益概率。</p>
   </article>}
   <details className="candidateSecondary"><summary>数据与评分说明</summary><p>候选策略仅供人工复核，尚未验证收益。完整月线 {periods?.monthly??"—"} · 完整周线 {periods?.weekly??"—"}。警报还要求完整覆盖及至少两个证据家族。股票来源为现有观察池，不代表完整市场；失格退出排名，原提名保留。</p></details>
   <footer>政策 {data.policy_version} · 行情来源 EODHD · 新评分未覆盖旧提名记录。{data.automatic_updates_connected?"本页按每次成功复评更新；失败保留原日期与榜单。":"自动复评接通前，此页仅展示本次已核快照。"}</footer>
  </section>
 </div>;
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
