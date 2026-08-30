"use client";
import {useEffect,useMemo,useState} from "react";
import {TrackerShell} from "../tracker-ui";

type Condition={id:string;label:string;hit:boolean};
type ChartPoint={date:string;high:number;low:number;close:number;ema20:number;ema50:number;ema200:number};
type PatternRow={
 symbol:string;price?:number;available:boolean;stage:string;stage_zh:string;match_count:number;total_conditions:number;match_pct:number;
 action_zh:string;conditions:Condition[];chart?:ChartPoint[];reference_note_zh?:string;reason?:string;
 prior_advance?:{low_date:string;high_date:string;low:number;high:number;advance_pct:number};
 pullback?:{objective_pullback_pct:number|null;prior_60_session_high:number|null;retracement_pct:number|null;golden_pocket:boolean;ema_support:boolean;ema_matches:{bottom:string;bottom_date:string;ema:string;ema_value:number;distance_pct:number}[]};
 double_bottom?:{first_date:string;second_date:string;first_price:number;second_price:number;neckline:number;invalidation:number}|null;
 second_bottom_macd?:{hit:boolean;cross_date:string|null;distance_from_second_bottom_sessions:number|null};
 three_push?:{high_dates:string[];high_prices:number[];breakout_date:string|null;breakout_close:number|null;breakout_level:number|null;current_line:number}|null;
 ema_realign?:{hit:boolean;cross_date:string|null;strength_date?:string|null;full_alignment?:boolean;ema20:number;ema50:number;ema200:number};
 sequence?:{double_bottom_first_date:string|null;double_bottom_second_date:string|null;breakout_date:string|null;completion_date:string|null};
 risk_gate?:{clear:boolean;blocked:boolean;reasons_zh:string[];unresolved_pressure_rounds:number;multi_top?:{dates:string[];prices:number[];zone_low:number;zone_high:number}|null;top_exhaustion?:{doji_date:string;confirmation_date:string}[]};
 legacy_v1?:{pattern_version:string;stage:string;match_count:number;total_conditions:number};
 legacy_v2?:{pattern_version:string;stage:string;match_count:number;total_conditions:number};
 trade_map?:{signal_close:number|null;earliest_entry:string|null;target_previous_high:number|null;invalidation_second_bottom:number|null;estimated_reward_risk:number|null};
 mechanism_profile?:{status:string;completed:{id:string;label:string}[];missing:{id:string;label:string}[];risk_reasons_zh:string[];examples_are_templates:boolean};
};
type Favorite={as_of:string;pattern_version:string;generalization_version?:string;production_scoring_changed:boolean;summary:{watchlist:number;entry_ready:number;risk_blocked?:number;waiting_breakout:number;breakout_incomplete:number;forming:number;launched:number;near_match?:number;blocked_near_match?:number};candidates?:PatternRow[];entry_ready_candidates?:PatternRow[];near_matches?:PatternRow[];reference_cases:PatternRow[];warning_zh:string;forward_tracking:{minimum_conclusion_sample:number;minimum_months:number;minimum_market_states:number};generalization_policy?:{legacy_only_cases:string[];review_loop:string[]}};

const stages=[
 ["01","发生回调","从前高至少回落5%"],
 ["02","形成双底","两个底必须由右侧K线确认"],
 ["03","三推突破","完整收盘突破下降趋势线"],
 ["04","踩到位置","Golden Pocket或EMA20/50/200"],
] as const;
const stageTone:Record<string,string>={entry_ready:"ready",risk_blocked:"invalid",waiting_breakout:"waiting",breakout_incomplete:"incomplete",bottom_confirmed:"forming",pullback_forming:"forming",launched:"launched",target_reached:"reached",invalidated:"invalid"};
const money=(value:number|null|undefined)=>value==null?"—":`$${value.toFixed(2)}`;

function PriceChart({row}:{row:PatternRow}){
 const points=row.chart??[];
 if(points.length<2)return <div className="favoriteChartEmpty">该股票的同日图形数据暂不可用。</div>;
 const width=920,height=340,pad={left:48,right:28,top:24,bottom:38};
 const values=points.flatMap(point=>[point.high,point.low,point.ema20,point.ema50,point.ema200]);
 const minimum=Math.min(...values),maximum=Math.max(...values),range=Math.max(1,maximum-minimum);
 const x=(index:number)=>pad.left+index/(points.length-1)*(width-pad.left-pad.right);
 const y=(value:number)=>pad.top+(maximum-value)/range*(height-pad.top-pad.bottom);
 const path=(key:"close"|"ema20"|"ema50"|"ema200")=>points.map((point,index)=>`${index?"L":"M"}${x(index).toFixed(1)},${y(point[key]).toFixed(1)}`).join(" ");
 const indexOf=(date?:string|null)=>date?points.findIndex(point=>point.date===date):-1;
 const markers=[
  [row.double_bottom?.first_date,"双底1","bottom"],
  [row.double_bottom?.second_date,"双底2","bottom"],
  [row.three_push?.breakout_date,"三推突破","breakout"],
 ] as const;
 const target=row.trade_map?.target_previous_high;
 return <div className="favoriteChart"><svg role="img" aria-label={`${row.symbol} 日线形态图`} viewBox={`0 0 ${width} ${height}`}>
  {[0,.25,.5,.75,1].map(step=>{const value=maximum-range*step;return <g key={step}><line x1={pad.left} x2={width-pad.right} y1={y(value)} y2={y(value)} className="grid"/><text x={6} y={y(value)+4}>{value.toFixed(0)}</text></g>})}
  {target&&<g><line x1={pad.left} x2={width-pad.right} y1={y(target)} y2={y(target)} className="target"/><text x={width-pad.right-4} y={y(target)-7} textAnchor="end" className="targetLabel">前高 {money(target)}</text></g>}
  <path d={path("ema200")} className="ema200"/><path d={path("ema50")} className="ema50"/><path d={path("ema20")} className="ema20"/><path d={path("close")} className="price"/>
  {row.three_push?.high_dates?.length===3&&(()=>{const first=indexOf(row.three_push?.high_dates[0]),third=indexOf(row.three_push?.high_dates[2]);return first>=0&&third>=0?<line x1={x(first)} y1={y(row.three_push!.high_prices[0])} x2={width-pad.right} y2={y(row.three_push!.current_line)} className="trendline"/>:null})()}
  {markers.map(([date,label,tone])=>{const index=indexOf(date);if(index<0)return null;return <g key={`${label}-${date}`} className={`marker ${tone}`}><line x1={x(index)} x2={x(index)} y1={pad.top} y2={height-pad.bottom}/><circle cx={x(index)} cy={y(points[index].close)} r="5"/><text x={x(index)+6} y={pad.top+15}>{label}</text></g>})}
  <text x={pad.left} y={height-10}>{points[0].date}</text><text x={width-pad.right} y={height-10} textAnchor="end">{points.at(-1)?.date}</text>
 </svg><div className="favoriteLegend"><span className="price">价格</span><span className="ema20">EMA20</span><span className="ema50">EMA50</span><span className="ema200">EMA200</span><span className="target">前高目标</span></div></div>;
}

function Evidence({row}:{row:PatternRow}){
 return <div className="favoriteEvidence">{row.conditions?.map(item=><article className={item.hit?"hit":"miss"} key={item.id}><i>{item.hit?"✓":"○"}</i><span>{item.label}</span></article>)}</div>;
}

export default function FavoritePatternPage(){
 const [data,setData]=useState<Favorite|null>(null);
 useEffect(()=>{fetch("/favorite-pattern.json",{cache:"no-store"}).then(x=>x.ok?x.json():null).then(setData).catch(()=>setData(null))},[]);
 const [symbol,setSymbol]=useState("");
 const formalRows=useMemo(()=>data?.entry_ready_candidates??data?.candidates?.filter(row=>row.stage==="entry_ready")??[],[data]);
 const nearRows=useMemo(()=>data?.near_matches??data?.candidates?.filter(row=>row.match_count>=3&&row.stage!=="entry_ready"&&row.stage!=="launched")??[],[data]);
 const visibleRows=useMemo(()=>[...formalRows,...nearRows],[formalRows,nearRows]);
 const selected=useMemo(()=>visibleRows.find(row=>row.symbol===symbol)??formalRows[0]??nearRows[0],[visibleRows,formalRows,nearRows,symbol]);
 return <TrackerShell active="我最喜欢形态" title="我最喜欢形态" subtitle="每天追踪你真正愿意做的日线共振，而不是再堆一套评分。">
  <div className="favoritePage">
   <section className="favoriteIntro"><div><small>MY FAVORITE DAILY SETUP · SIMPLE SHAPE</small><h2>只看你最关心的四件事</h2><p>回调、双底、三推收盘突破，再加Golden Pocket或EMA20/50/200承接。四项齐全后再看独立风险闸门；旧七阶段仍留档，但不再把简单好形态挡在门外。4/4不是胜率。</p><p className="favoriteReferenceLine">复杂证据去多因子页看 · 这里专心看形态</p></div><mark>V3 · 生产权重 0</mark></section>
   <section className="favoriteFunnel" aria-label="形态四项流程">{stages.map(([index,title,note])=><article key={index}><i>{index}</i><b>{title}</b><span>{note}</span></article>)}</section>
   {data?<>
    <section className="favoriteMetrics"><article><small>数据日</small><b>{data.as_of}</b><span>{data.pattern_version}</span></article><article><small>形态完整</small><b>{data.summary.entry_ready}</b><span>4/4＋风险清除</span></article><article><small>3/4接近机会</small><b>{data.summary.near_match??nearRows.filter(row=>row.mechanism_profile?.status!=="blocked_near_match").length}</b><span>明确显示缺哪一项</span></article><article><small>风险阻断</small><b>{data.summary.risk_blocked??0}</b><span>形态不能覆盖空头风险</span></article><article><small>等待突破</small><b>{data.summary.waiting_breakout}</b><span>双底或位置已经形成</span></article><article><small>当前观察表</small><b>{data.summary.watchlist}</b><span>全市场同日扫描</span></article></section>
    <div className="favoriteWarning"><b>先说清楚：</b>{data.warning_zh}</div>
    <section className="favoriteWorkspace"><aside><header><small>FORMAL · 4/4</small><h3>形态完整</h3></header>{formalRows.length?formalRows.map(row=><button type="button" key={`formal-${row.symbol}`} onClick={()=>setSymbol(row.symbol)} className={selected?.symbol===row.symbol?"active":""}><span><b>{row.symbol}</b><small>{row.stage_zh}</small></span><strong>{row.match_count}/{row.total_conditions}<small>条件</small></strong><i className={stageTone[row.stage]??"forming"}/></button>):<div className="favoriteNone"><b>今天没有4/4新形态</b><p>不会用3/4冒充。</p></div>}<header><small>NEAR MATCH · REVIEW ONLY</small><h3>接近但未完成</h3></header>{nearRows.length?nearRows.map(row=><button type="button" key={`near-${row.symbol}`} onClick={()=>setSymbol(row.symbol)} className={selected?.symbol===row.symbol?"active":""}><span><b>{row.symbol}</b><small>{row.mechanism_profile?.status==="blocked_near_match"?"风险阻断":row.stage_zh}</small></span><strong>{row.match_count}/{row.total_conditions}<small>条件</small></strong><i className={row.mechanism_profile?.status==="blocked_near_match"?"invalid":stageTone[row.stage]??"forming"}/></button>):<div className="favoriteNone"><b>今天没有3/4近似机会</b><p>近似机会不是买入信号。</p></div>}</aside>
     <div className="favoriteDetail">{selected?<><header><div><small>POINT-IN-TIME SHAPE AUDIT</small><h3>{selected.symbol} · {selected.stage_zh}</h3><p>{selected.action_zh}</p></div><strong>{selected.match_count}/{selected.total_conditions}<small>形态颗数</small></strong></header><PriceChart row={selected}/><Evidence row={selected}/>{selected.stage!=="entry_ready"&&<div className="favoriteWarning"><b>为什么还没升级：</b>{selected.mechanism_profile?.missing?.length?selected.mechanism_profile.missing.map(item=>item.label).join("；"):"四项已齐，但风险尚未清除或已离开首次突破窗口"}。这只是近似观察，不是买入信号。</div>}<div className="favoriteFacts"><article><small>客观回调</small><b>{selected.pullback?.objective_pullback_pct!=null?`-${selected.pullback.objective_pullback_pct.toFixed(1)}%`:"等待"}</b><span>前60日高点 {money(selected.pullback?.prior_60_session_high)}</span></article><article><small>双底</small><b>{selected.double_bottom?`${selected.double_bottom.first_date} / ${selected.double_bottom.second_date}`:"等待"}</b><span>{selected.double_bottom?`颈线 ${money(selected.double_bottom.neckline)}`:"两个底尚未客观确认"}</span></article><article><small>三推突破</small><b>{selected.three_push?.breakout_date??"等待"}</b><span>{selected.three_push?.high_dates?.join(" → ")??"下降高点尚未齐全"}</span></article><article><small>位置承接</small><b>{selected.pullback?.golden_pocket?"Golden Pocket":selected.pullback?.ema_support?selected.pullback.ema_matches.map(item=>item.ema).filter((value,index,array)=>array.indexOf(value)===index).join(" / "):"等待"}</b><span>{selected.pullback?.ema_matches?.slice(0,2).map(item=>`${item.bottom}${item.ema}差${item.distance_pct}%`).join(" · ")||"尚未踩到冻结容差"}</span></article></div>{selected.risk_gate?.blocked?<div className="favoriteWarning"><b>风险否决：</b>{selected.risk_gate.reasons_zh.join("；")}</div>:<div className="favoriteWarning"><b>风险闸门：</b>当前没有命中已登记的多轮空头压力或顶部耗竭否决。</div>}<div className="favoriteTradeMap"><span>研究入场 <b>{selected.trade_map?.earliest_entry?"形态完成后下一交易日开盘":"未触发"}</b></span><span>前高目标 <b>{money(selected.trade_map?.target_previous_high)}</b></span><span>双底失效位 <b>{money(selected.trade_map?.invalidation_second_bottom)}</b></span><span>旧版对照 <b>V1 {selected.legacy_v1?`${selected.legacy_v1.match_count}/${selected.legacy_v1.total_conditions}`:"—"} · V2 {selected.legacy_v2?`${selected.legacy_v2.match_count}/${selected.legacy_v2.total_conditions}`:"—"}</b></span></div></>:<div className="favoriteNone"><b>等待当日扫描结果</b></div>}</div>
    </section>
    <section className="favoriteReferences"><header><div><small>TEACHING &amp; RISK CASES</small><h2>案例负责人工校验，不负责证明收益</h2><p>ADBE／BABA帮助核对双底、三推和EMA位置；TTD／AEVA锁住风险边界。旧七阶段仍在Git与每只股票的旧版对照中。</p></div></header><div>{data.reference_cases.filter(row=>row.symbol!=="PG").map(row=><article key={row.symbol} data-stage={row.stage}><header><b>{row.symbol}</b><mark>{row.stage_zh}</mark></header><p>{row.reference_note_zh}</p><footer>{row.available?`当前V3匹配 ${row.match_count}/${row.total_conditions}`:row.reason}</footer></article>)}</div></section>
    <section className="favoriteForward"><div><small>HUMAN-IN-THE-LOOP REVIEW</small><h2>每轮固定看漏检赢家、误收输家和门槛边界</h2><p>人工复核负责发现系统缺口；新思路先登记为后验假设，再开新版本做对照。不会拿单一案例直接改权重。</p></div><div><strong>{data.forward_tracking.minimum_conclusion_sample}<small>至少正式案例</small></strong><strong>{data.forward_tracking.minimum_months}<small>至少月份</small></strong><strong>{data.forward_tracking.minimum_market_states}<small>至少市场状态</small></strong></div></section>
   </>:<div className="favoriteLoading"><b>正在读取今天的形态状态</b><p>首次上线后的完整交易日会开始真实前向留档。</p></div>}
  </div>
 </TrackerShell>;
}
