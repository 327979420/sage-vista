"use client";

import React,{useEffect,useState} from "react";
import {TrackerShell} from "../tracker-ui";
import {TimeframeProfile,TimeframeProfilePanel} from "./timeframe-profile";

type FactorPeriod={samples:number;win_rate_pct:number;profit_factor:number;expectancy_pct:number;win_delta_pct:number;median_delta_pct:number;trimmed_mean_delta_pct:number;expectancy_delta_pct:number;top_decile_enrichment_ratio:number};
type BaselinePeriod={samples:number;win_rate_pct:number;median_pct:number;profit_factor:number;expectancy_pct:number;net_50bps_expectancy_pct:number};
type EffectivenessFactor={factor_id:string;name_zh:string;family:string;family_zh:string;family_color:string;timeframe_zh:string;quadrant:string;production_role_zh:string;official_weight:number;shadow_weight:number;latest_verdict_zh:string;action:string;evidence_note_zh:string;periods_20d:Record<string,FactorPeriod|null>};
type QuadrantMeta={order:number;label_zh:string;short_zh:string;description_zh:string;action_zh:string};
type Effectiveness={source_experiment:string;coverage:{period:string;factors:number};headline:{common_gate:string;score:string;add_on:string;pairs:string};quadrant_order:string[];quadrants:Record<string,QuadrantMeta>;family_legend:{family:string;label_zh:string;color:string}[];baseline_20d:Record<string,BaselinePeriod>;factors:EffectivenessFactor[];research_only:{factor_id:string;name_zh:string;summary_zh:string}[];warning:string};
type V2Factor={factor_id:string;name?:string;available:boolean;hit:boolean;active_now:boolean;bars_since_hit:number|null;points:number;counted_in_resonance?:boolean;confirmation_bonus?:number;factor_family?:string;timeframe?:string;research_status?:string;score_rule?:string};
type TechnicalResonance={positive_hit_count:number;family_count:number;families:string[];parent_child_confirmation_bonus:number;timeframe_resonance_bonus:number;risk_hit_count:number;formula:string};
type SupportPlan={available:boolean;level:number|null;source:string;structural_stop?:number};
type V2Row={rank:number;symbol:string;price:number;technical_score:number;technical_resonance?:TechnicalResonance;market_adjustment:number;industry_adjustment:number;final_priority:number;score_equation:string;reasons:string[];industry_states:string[];factor_ledger:V2Factor[];timeframe_profile?:TimeframeProfile;execution_policy_version?:string;support_plan?:SupportPlan};
type V2Day={date:string;market:{state:string;score:number}|null;historical_membership_safe:boolean;triggered_count:number;candidate_count:number;rare_policy?:string;rare_symbols?:string[];ranking:V2Row[]};
type UnifiedV2={coverage:{start:string;end:string;sessions:number};days:V2Day[]};
type LedgerEvent={event_id:string;symbol:string;signal_date:string;source_systems:string[];selection:{rank:number|null;technical_score:number|null;final_priority:number|null;score_equation:string|null;reasons:string[]};evaluation:{elapsed_sessions:number;returns:Record<string,number|null>;mfe:number|null;mae:number|null;status:string}};
type Ledger={selection_future_data_used:boolean;coverage:{events:number};summary:{unified_v2_events:number;production_forward_events:number;support_stop_2r?:{resolved_samples:number}};events:LedgerEvent[]};

const periodNames:Record<string,string>={development:"2001—2024 开发",validation_2025:"2025 验证",forward_2026:"2026 前向"};
const sourceNames:Record<string,string>={unified_v2:"多因子",technical_tracker:"技术榜",multi_factor_radar:"旧稀有机会",favorite_pattern_tracker:"我最喜欢形态"};
const evaluationNames:Record<string,string>={data_unavailable:"等待行情",pending:"等待入场",observing:"持续跟踪",matured:"已满100日"};
const signed=(value:number)=>`${value>0?"+":""}${value.toFixed(1)}%`;

export default function RareOpportunities(){
 const [effectiveness,setEffectiveness]=useState<Effectiveness|null>(null);
 const [unified,setUnified]=useState<UnifiedV2|null>(null);
 const [ledger,setLedger]=useState<Ledger|null>(null);
 const [v2Symbol,setV2Symbol]=useState("");
 const [ledgerMonth,setLedgerMonth]=useState("2026-08");

 useEffect(()=>{
  fetch("/factor-effectiveness.json",{cache:"no-store"}).then(x=>x.ok?x.json():null).then(setEffectiveness).catch(()=>setEffectiveness(null));
  fetch("/unified-v2-latest.json",{cache:"no-store"}).then(x=>x.ok?x.json():null).then(setUnified).catch(()=>setUnified(null));
  fetch("/opportunity-ledger-latest.json",{cache:"no-store"}).then(x=>x.ok?x.json():null).then(x=>{setLedger(x);if(x?.events?.length)setLedgerMonth(x.events.at(-1).signal_date.slice(0,7))}).catch(()=>setLedger(null));
 },[]);

 const day=unified?.days.at(-1);
 const selected=day?.ranking.find(item=>item.symbol===v2Symbol)??day?.ranking[0];
 const rareSymbols=new Set(day?.rare_symbols??[]);
 const rare=day?.ranking.filter(item=>rareSymbols.size?rareSymbols.has(item.symbol):true).slice(0,5)??[];
 const months=Array.from(new Set((ledger?.events??[]).map(item=>item.signal_date.slice(0,7)))).sort().reverse();
 const ledgerRows=(ledger?.events??[]).filter(item=>item.signal_date.startsWith(ledgerMonth)).slice().reverse().slice(0,100);
 const latest20=effectiveness?.baseline_20d.forward_2026;

 return <TrackerShell active="多因子机会" title="多因子" subtitle="复杂版：技术颗数、家族、重复确认和跨周期共振，一页看清。">
  <div className="rareRadar">{unified&&<>
   <section className="rareFirstView">
    <article className="tone-blue"><i className="rareMetricIcon">1</i><small>今天更新到</small><b>{day?.date??"—"}</b><p>{day?.triggered_count??"—"}只MACD刚金叉 → {day?.candidate_count??"—"}只通过长期趋势</p></article>
    <article className="tone-amber"><i className="rareMetricIcon">2</i><small>现在先看</small><b>{rare.length}只精选</b><p>{rare[0]?`第一名 ${rare[0].symbol} · ${rare[0].technical_resonance?.positive_hit_count??0}颗 · ${rare[0].technical_resonance?.family_count??0}家族`:"今天没有候选"}</p></article>
    <article className="tone-violet"><i className="rareMetricIcon">3</i><small>旧实验事实</small><b>{latest20?`${latest20.win_rate_pct.toFixed(1)}%`:"等待结论"}</b><p>{latest20?`共同门票 ${latest20.samples}个样本 · PF ${latest20.profit_factor.toFixed(2)}`:"旧高分没有验证单调性"}</p></article>
    <article className="tone-rose"><i className="rareMetricIcon">4</i><small>风险执行仍不变</small><b>支撑 −5%</b><p>最大计划亏损10% · 2R止盈 · {ledger?.summary.support_stop_2r?.resolved_samples??0}笔完成</p></article>
   </section>

   <div className="rareRegistryLine"><span><b>运行逻辑</b></span><span>① MACD刚金叉＋长期趋势作门票</span><span>② 其余真实命中全部算颗数</span><span>③ 家族、重复确认、跨周期再加共振</span><span>④ 行业与大盘只处理技术同分</span></div>

   {effectiveness&&<section className="factorResults latestFactorStudy">
    <header><div><small>LATEST AUDITED STUDY · HISTORICAL FACT</small><h2>旧实验仍然保留，但不再隐藏当天命中</h2><p>{effectiveness.headline.common_gate} 旧实验没有证明“分越高越赚钱”；新共振分先服务人工挑选，再做前向对照。</p></div><mark>{effectiveness.coverage.period}</mark></header>
    <div className="factorResultGrid baselinePeriods">{Object.entries(effectiveness.baseline_20d).map(([period,item])=><article key={period} data-tone="validated"><header><div><b>{periodNames[period]??period}</b><span>共同门票 · 20日</span></div><strong>{item.win_rate_pct.toFixed(1)}%<small>胜率</small></strong></header><div><span>样本 <b>{item.samples}</b></span><span>PF <b>{item.profit_factor.toFixed(2)}</b></span><span>中位 <b>{signed(item.median_pct)}</b></span></div><footer>扣50bps期望 {signed(item.net_50bps_expectancy_pct)}</footer></article>)}</div>
    <div className="studyVerdictStrip"><article data-tone="rejected"><b>旧高分没有更可靠</b><p>{effectiveness.headline.score}</p></article><article data-tone="testing"><b>现在恢复客观颗数</b><p>0权重只代表未验证，不代表今天没有命中。</p></article><article data-tone="testing"><b>以后逐周对照</b><p>旧1.3、纯颗数与完整共振同时保存。</p></article></div>
   </section>}

   {effectiveness&&<section className="factorQuadrantLibrary">
    <header><div><small>FACTOR LIBRARY · FOUR QUADRANTS</small><h2>{effectiveness.coverage.factors}个因子，现在分别怎么处理</h2><p>象限保留研究结论；只要今天客观命中，仍会进入复杂版颗数。<b>命中不等于验证有效。</b></p></div><mark>来源：{effectiveness.source_experiment}</mark></header>
    <div className="factorFamilyLegend">{effectiveness.family_legend.map(item=><span key={item.family} style={{"--family-color":item.color} as React.CSSProperties}><i/>{item.label_zh}</span>)}</div>
    <div className="factorQuadrantGrid">{effectiveness.quadrant_order.map(key=>{const meta=effectiveness.quadrants[key],items=effectiveness.factors.filter(item=>item.quadrant===key);return <section className="factorQuadrant" data-quadrant={key} key={key}><header><div><i>{meta.order}</i><span><b>{meta.label_zh}</b><small>{meta.short_zh}</small></span></div><strong>{items.length}<small>个因子</small></strong></header><p>{meta.description_zh}</p><div>{items.map(item=><article className="factorQuadrantItem" key={item.factor_id} style={{"--family-color":item.family_color} as React.CSSProperties}><header><div><b>{item.name_zh}</b><span><i/>{item.family_zh} · {item.timeframe_zh}</span></div><mark>{item.production_role_zh}</mark></header><p>{item.action}</p><footer><span>{item.latest_verdict_zh}</span><b>命中时计1颗</b></footer><details><summary>查看旧实验依据</summary><p>{item.evidence_note_zh}</p></details></article>)}</div><footer>{meta.action_zh}</footer></section>})}</div>
    <aside><b>研究专用：</b>{effectiveness.research_only.map(item=><span key={item.factor_id}>{item.name_zh}：{item.summary_zh}</span>)}</aside>
    <footer>{effectiveness.warning}</footer>
   </section>}

   <section className="researchReplay">
    <header><div><small>MULTI-FACTOR · COUNTED RESONANCE</small><h2>复杂多因子共振排行榜</h2><p>先看技术命中颗数、家族覆盖、重复确认和跨周期共振；行业与大盘不会盖过技术。</p></div><mark>只显示最新 · 历史在Git留档</mark></header>
    {day?<>
     <div className="replayCoverage"><span>当日候选 <b>{day.candidate_count}</b>只</span><span>精选 <b>{rare.length}</b>只</span><span>大盘 {day.market?.state??"不可用"}</span><mark>{day.historical_membership_safe?"行业按当日成员关系":"没有安全行业映射"}</mark></div>
     <div className="replayTable">
      <div className="v2RankRow replayHead"><span>排名 / 股票</span><span>共振分</span><span>颗数 / 家族</span><span>跨周期</span><span>行业 / 大盘</span><span>为什么入选</span></div>
      {day.ranking.map(item=><button type="button" className={`v2RankRow ${selected?.symbol===item.symbol?"isSelected":""}`} key={item.symbol} onClick={()=>setV2Symbol(item.symbol)}><b>#{item.rank} · {item.symbol}{rare.some(row=>row.symbol===item.symbol)&&<mark>精选</mark>}<small>${item.price}</small></b><strong>{item.technical_score}<small>共振分</small></strong><span><b>{item.technical_resonance?.positive_hit_count??0}颗</b><small>{item.technical_resonance?.family_count??0}家族</small></span><span>+{item.technical_resonance?.timeframe_resonance_bonus??0}<small>周期奖金</small></span><span>行业 {item.industry_adjustment}<small>大盘 {item.market_adjustment}</small></span><span>{item.reasons.join(" · ")}</span></button>)}
     </div>
     {selected&&<article className="v2Audit"><header><div><small>WHY IT RANKS HERE</small><h3>#{selected.rank} · {selected.symbol}</h3><p>{day.date} · ${selected.price}</p></div><strong>{selected.technical_score}<small>技术共振分</small></strong></header>
      <div className="v2Equation"><span>命中 <b>{selected.technical_resonance?.positive_hit_count??0}颗</b></span><i>＋</i><span>家族 <b>{selected.technical_resonance?.family_count??0}</b></span><i>＋</i><span>重复确认 <b>{selected.technical_resonance?.parent_child_confirmation_bonus??0}</b></span><i>＋</i><span>周期 <b>{selected.technical_resonance?.timeframe_resonance_bonus??0}</b></span></div>
      <div className="v2Ledger"><section><h4>命中并计入颗数</h4>{selected.factor_ledger?.filter(item=>item.counted_in_resonance).map(item=><p key={item.factor_id}><i>✓</i><span>{item.name}<small>{item.factor_family} · {item.timeframe} · {item.research_status}{item.confirmation_bonus?" · double confirmation":""}</small></span><b>+1</b></p>)}</section><section><h4>共同门票与风险单列</h4>{selected.factor_ledger?.filter(item=>item.hit&&!item.counted_in_resonance).map(item=><p key={item.factor_id}><i>△</i><span>{item.name}<small>{item.score_rule}</small></span><b>—</b></p>)}</section><section><h4>可检测但未命中</h4>{selected.factor_ledger?.filter(item=>item.available&&!item.hit).map(item=><p key={item.factor_id}><i>○</i><span>{item.name}<small>{item.research_status}</small></span><b>0</b></p>)}</section><section><h4>当前无法客观检测</h4>{selected.factor_ledger?.filter(item=>!item.available).map(item=><p key={item.factor_id}><i>—</i><span>{item.name}<small>规则仍需定义</small></span><b>—</b></p>)}</section></div>
     </article>}
     <footer>{day.rare_policy}。页面只读取{day.date}紧凑快照；完整历史覆盖 {unified.coverage.start} 至 {unified.coverage.end}，保存在Git后台。</footer>
    </>:<div className="rareEmpty"><b>新共振榜正在生成</b><p>旧1.3榜保留在历史，但不冒充今天的新排名。</p></div>}
   </section>

   {selected?.timeframe_profile&&<TimeframeProfilePanel profile={selected.timeframe_profile}/>}

   {selected&&<section className="researchReplay"><header><div><small>RISK PLAN · SIGNAL-DAY SNAPSHOT</small><h2>{selected.symbol}的支撑与离场计划</h2><p>排行变了，止损和退出没有偷偷改变。</p></div><mark>{selected.execution_policy_version??"旧批次"}</mark></header><div className="replayCoverage"><span>当时价格 <b>${selected.price}</b></span><span>支撑 <b>{selected.support_plan?.level?`$${selected.support_plan.level}`:"未记录"}</b></span><span>来源 <b>{selected.support_plan?.source??"—"}</b></span><span>结构止损 <b>{selected.support_plan?.structural_stop?`$${selected.support_plan.structural_stop}`:"—"}</b></span><mark>支撑下5%与入场下10%取更高者</mark></div></section>}

   <section className="researchReplay"><header><div><small>PERMANENT OPPORTUNITY LEDGER</small><h2>统一机会账本</h2><p>旧排名和新共振榜都永久保留版本；未来涨跌只负责评价。</p></div>{ledger&&<select aria-label="账本月份" value={ledgerMonth} onChange={event=>setLedgerMonth(event.target.value)}>{months.map(month=><option key={month}>{month}</option>)}</select>}</header>{ledger?<><div className="replayCoverage"><span>永久记录 <b>{ledger.coverage.events}</b>条</span><span>排行事件 <b>{ledger.summary.unified_v2_events}</b>条</span><span>真实Forward <b>{ledger.summary.production_forward_events}</b>条</span><mark>{ledger.selection_future_data_used?"数据异常":"防前视通过"}</mark></div><div className="replayTable"><div className="replayRow replayHead"><span>触发日 / 排名</span><span>股票</span><span>当时分数</span><span>1日</span><span>5日</span><span>20日</span><span>60日</span><span>跟踪状态</span></div>{ledgerRows.map(item=><article className="replayRow" key={item.event_id}><span>{item.signal_date}<small>{item.selection.rank?`当日 #${item.selection.rank}`:"真实提醒"}</small></span><b>{item.symbol}<small>{item.source_systems.map(source=>sourceNames[source]??source).join(" + ")}</small></b><span><b>{item.selection.technical_score??item.selection.final_priority??"—"}</b><small>{item.selection.score_equation??item.selection.reasons.slice(0,2).join(" · ")}</small></span>{(["1","5","20","60"] as const).map(horizon=>{const value=item.evaluation.returns[horizon];return <strong key={horizon} className={value===null?"pending":value>=0?"positive":"negative"}>{value===null?"进行中":`${value>0?"+":""}${(value*100).toFixed(1)}%`}</strong>})}<span>{evaluationNames[item.evaluation.status]??item.evaluation.status}<small>{item.evaluation.elapsed_sessions}个交易日 · MFE {item.evaluation.mfe===null?"—":`${(item.evaluation.mfe*100).toFixed(1)}%`} · MAE {item.evaluation.mae===null?"—":`${(item.evaluation.mae*100).toFixed(1)}%`}</small></span></article>)}</div><footer>每条记录冻结当日模型版本，不会用新分覆盖旧事件。</footer></>:<div className="rareEmpty"><b>统一机会账本等待生成</b></div>}</section>
  </>}</div>
 </TrackerShell>;
}
