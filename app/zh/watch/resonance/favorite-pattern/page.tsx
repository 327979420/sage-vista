"use client";
import {useEffect,useMemo,useState} from "react";
import {TrackerShell} from "../tracker-ui";

type Condition={id:string;label:string;hit:boolean};
type ChartPoint={date:string;high:number;low:number;close:number;ema20:number;ema50:number;ema200:number};
type PatternRow={
 symbol:string;price?:number;available:boolean;stage:string;stage_zh:string;match_count:number;total_conditions:number;match_pct:number;
 action_zh:string;conditions:Condition[];chart?:ChartPoint[];reference_note_zh?:string;reason?:string;
 prior_advance?:{low_date:string;high_date:string;low:number;high:number;advance_pct:number};
 pullback?:{retracement_pct:number|null;golden_pocket:boolean;ema200_support:boolean;ema200_nearest_distance_pct:number|null};
 double_bottom?:{first_date:string;second_date:string;first_price:number;second_price:number;neckline:number;invalidation:number}|null;
 second_bottom_macd?:{hit:boolean;cross_date:string|null;distance_from_second_bottom_sessions:number|null};
 three_push?:{high_dates:string[];high_prices:number[];breakout_date:string|null;breakout_close:number|null;breakout_level:number|null;current_line:number}|null;
 ema_realign?:{hit:boolean;cross_date:string|null;strength_date?:string|null;full_alignment?:boolean;ema20:number;ema50:number;ema200:number};
 sequence?:{first_confirmation_date:string|null;first_bottom?:{first_date:string;second_date:string}|null;first_macd_date:string|null;first_ema_cross_date:string|null;reset_drawdown_pct:number|null;macd_reset:boolean;second_bottom?:{first_date:string;second_date:string;neckline:number}|null;second_breakout_date:string|null;second_macd_date:string|null;ema_strength_date:string|null;full_alignment_date:string|null;completion_date:string|null};
 risk_gate?:{clear:boolean;blocked:boolean;reasons_zh:string[];unresolved_pressure_rounds:number;multi_top?:{dates:string[];prices:number[];zone_low:number;zone_high:number}|null;top_exhaustion?:{doji_date:string;confirmation_date:string}[]};
 legacy_v1?:{pattern_version:string;stage:string;match_count:number;total_conditions:number};
 trade_map?:{signal_close:number|null;earliest_entry:string|null;target_previous_high:number|null;invalidation_second_bottom:number|null;estimated_reward_risk:number|null};
 mechanism_profile?:{status:string;completed:{id:string;label:string}[];missing:{id:string;label:string}[];risk_reasons_zh:string[];examples_are_templates:boolean};
};
type Favorite={as_of:string;pattern_version:string;generalization_version?:string;production_scoring_changed:boolean;summary:{watchlist:number;entry_ready:number;risk_blocked?:number;waiting_breakout:number;breakout_incomplete:number;forming:number;launched:number;near_match?:number;blocked_near_match?:number};candidates?:PatternRow[];entry_ready_candidates?:PatternRow[];near_matches?:PatternRow[];reference_cases:PatternRow[];warning_zh:string;forward_tracking:{minimum_conclusion_sample:number;minimum_months:number;minimum_market_states:number};generalization_policy?:{legacy_only_cases:string[];review_loop:string[]}};

const stages=[
 ["01","上涨／转强","先证明多头曾经出现"],
 ["02","第一底部","双底／三底必须确认"],
 ["03","第一突破","三推趋势线收盘突破"],
 ["04","趋势转变","MACD＋EMA先完成修复"],
 ["05","真实重置","新回调、MACD重置、新pivot"],
 ["06","第二底部","新的W底或回踩守住"],
 ["07","二次启动","突破＋MACD＋EMA再次转强"],
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
  [row.sequence?.first_bottom?.first_date??row.double_bottom?.first_date,"第一底1","bottom"],
  [row.sequence?.first_bottom?.second_date??row.double_bottom?.second_date,"第一底2","bottom"],
  [row.sequence?.first_confirmation_date??row.three_push?.breakout_date,"第一次确认","breakout"],
  [row.sequence?.second_bottom?.first_date,"第二底1","bottom"],
  [row.sequence?.second_bottom?.second_date,"第二底2","bottom"],
  [row.sequence?.second_macd_date??row.second_bottom_macd?.cross_date,"二次MACD","macd"],
  [row.sequence?.completion_date,"二次启动","breakout"],
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
 const nearRows=useMemo(()=>data?.near_matches??data?.candidates?.filter(row=>row.match_count>=5&&row.stage!=="entry_ready"&&row.stage!=="launched")??[],[data]);
 const visibleRows=useMemo(()=>[...formalRows,...nearRows],[formalRows,nearRows]);
 const selected=useMemo(()=>visibleRows.find(row=>row.symbol===symbol)??formalRows[0]??nearRows[0],[visibleRows,formalRows,nearRows,symbol]);
 return <TrackerShell active="我最喜欢形态" title="我最喜欢形态" subtitle="每天追踪你真正愿意做的日线共振，而不是再堆一套评分。">
  <div className="favoritePage">
   <section className="favoriteIntro"><div><small>MY FAVORITE DAILY SETUP · MECHANISM REVIEW</small><h2>案例教机制，不要求复制形状</h2><p>系统先看背景、位置、结构、趋势转变、真实重置、再次启动和供给风险。ADBE只是“先转变、再重置、再确认”的教学案例，不是所有机会必须长成同一张图。匹配度不是胜率。</p><p className="favoriteReferenceLine">ADBE / BABA 机制教学 · TTD / AEVA 风险回归 · PG 仅留V1历史</p></div><mark>生产权重 0 · 独立观察</mark></section>
   <section className="favoriteFunnel" aria-label="形态七步流程">{stages.map(([index,title,note])=><article key={index}><i>{index}</i><b>{title}</b><span>{note}</span></article>)}</section>
   {data?<>
    <section className="favoriteMetrics"><article><small>数据日</small><b>{data.as_of}</b><span>{data.pattern_version}</span></article><article><small>正式就绪</small><b>{data.summary.entry_ready}</b><span>7阶段完成＋风险清除</span></article><article><small>接近机会</small><b>{data.summary.near_match??nearRows.filter(row=>row.mechanism_profile?.status!=="blocked_near_match").length}</b><span>只供人工复核</span></article><article><small>接近但被阻断</small><b>{data.summary.blocked_near_match??nearRows.filter(row=>row.mechanism_profile?.status==="blocked_near_match").length}</b><span>正面进度不能覆盖风险</span></article><article><small>等待第二次确认</small><b>{data.summary.waiting_breakout}</b><span>明确显示还缺什么</span></article><article><small>当前观察表</small><b>{data.summary.watchlist}</b><span>全市场同日扫描</span></article></section>
    <div className="favoriteWarning"><b>先说清楚：</b>{data.warning_zh}</div>
    <section className="favoriteWorkspace"><aside><header><small>FORMAL · 7/7</small><h3>正式完成</h3></header>{formalRows.length?formalRows.map(row=><button type="button" key={`formal-${row.symbol}`} onClick={()=>setSymbol(row.symbol)} className={selected?.symbol===row.symbol?"active":""}><span><b>{row.symbol}</b><small>{row.stage_zh}</small></span><strong>{row.match_count}/{row.total_conditions}<small>条件</small></strong><i className={stageTone[row.stage]??"forming"}/></button>):<div className="favoriteNone"><b>今天没有正式完成</b><p>不会用近似机会冒充。</p></div>}<header><small>NEAR MATCH · REVIEW ONLY</small><h3>接近但未完成</h3></header>{nearRows.length?nearRows.map(row=><button type="button" key={`near-${row.symbol}`} onClick={()=>setSymbol(row.symbol)} className={selected?.symbol===row.symbol?"active":""}><span><b>{row.symbol}</b><small>{row.mechanism_profile?.status==="blocked_near_match"?"风险阻断":row.stage_zh}</small></span><strong>{row.match_count}/{row.total_conditions}<small>条件</small></strong><i className={row.mechanism_profile?.status==="blocked_near_match"?"invalid":stageTone[row.stage]??"forming"}/></button>):<div className="favoriteNone"><b>今天没有5/7以上近似机会</b><p>近似机会不是买入信号。</p></div>}</aside>
     <div className="favoriteDetail">{selected?<><header><div><small>POINT-IN-TIME MECHANISM AUDIT</small><h3>{selected.symbol} · {selected.stage_zh}</h3><p>{selected.action_zh}</p></div><strong>{selected.match_count}/{selected.total_conditions}<small>系统进度</small></strong></header><PriceChart row={selected}/><Evidence row={selected}/>{selected.stage!=="entry_ready"&&<div className="favoriteWarning"><b>为什么还没升级：</b>{selected.mechanism_profile?.missing?.length?selected.mechanism_profile.missing.map(item=>item.label).join("；"):"七阶段虽完成，但风险尚未清除或已离开首次确认窗口"}。这只是近似观察，不是买入信号。</div>}<div className="favoriteFacts"><article><small>第一次确认</small><b>{selected.sequence?.first_confirmation_date??"等待"}</b><span>{selected.sequence?.first_bottom?`${selected.sequence.first_bottom.first_date} / ${selected.sequence.first_bottom.second_date} 两底`:"第一底部尚未完成"}</span></article><article><small>真实重置</small><b>{selected.sequence?.reset_drawdown_pct!=null?`-${selected.sequence.reset_drawdown_pct.toFixed(1)}%`:"等待"}</b><span>{selected.sequence?.macd_reset?"✓ MACD已经重置":"MACD尚未重置"}</span></article><article><small>第二次启动</small><b>{selected.sequence?.completion_date??"等待"}</b><span>突破 {selected.sequence?.second_breakout_date??"—"} · MACD {selected.sequence?.second_macd_date??"—"} · EMA {selected.sequence?.ema_strength_date??"—"}</span></article><article><small>EMA完整排列</small><b>{selected.sequence?.full_alignment_date??"尚未"}</b><span>{selected.ema_realign?.full_alignment?`EMA20 ${money(selected.ema_realign.ema20)} ＞ EMA50 ${money(selected.ema_realign.ema50)}`:"先记录转强，不等待完美排列"}</span></article></div>{selected.risk_gate?.blocked?<div className="favoriteWarning"><b>风险否决：</b>{selected.risk_gate.reasons_zh.join("；")}</div>:<div className="favoriteWarning"><b>风险闸门：</b>当前没有命中已登记的多轮空头压力或顶部耗竭否决。</div>}<div className="favoriteTradeMap"><span>研究入场 <b>{selected.trade_map?.earliest_entry?"二次确认后下一交易日开盘":"未触发"}</b></span><span>前高目标 <b>{money(selected.trade_map?.target_previous_high)}</b></span><span>新底失效位 <b>{money(selected.trade_map?.invalidation_second_bottom)}</b></span><span>旧V1对照 <b>{selected.legacy_v1?`${selected.legacy_v1.match_count}/${selected.legacy_v1.total_conditions}`:"—"}</b></span></div></>:<div className="favoriteNone"><b>等待当日扫描结果</b></div>}</div>
    </section>
    <section className="favoriteReferences"><header><div><small>TEACHING &amp; RISK CASES</small><h2>例子负责教机制，不负责规定唯一长相</h2><p>ADBE／BABA解释判断职责与顺序；TTD／AEVA锁住风险边界。PG只留在V1历史审计，不再作为V2参考。</p></div></header><div>{data.reference_cases.filter(row=>row.symbol!=="PG").map(row=><article key={row.symbol} data-stage={row.stage}><header><b>{row.symbol}</b><mark>{row.stage_zh}</mark></header><p>{row.reference_note_zh}</p><footer>{row.available?`当前机器匹配 ${row.match_count}/${row.total_conditions}`:row.reason}</footer></article>)}</div></section>
    <section className="favoriteForward"><div><small>HUMAN-IN-THE-LOOP REVIEW</small><h2>每轮固定看漏检赢家、误收输家和门槛边界</h2><p>人工复核负责发现系统缺口；新思路先登记为后验假设，再开新版本做对照。不会拿单一案例直接改权重。</p></div><div><strong>{data.forward_tracking.minimum_conclusion_sample}<small>至少正式案例</small></strong><strong>{data.forward_tracking.minimum_months}<small>至少月份</small></strong><strong>{data.forward_tracking.minimum_market_states}<small>至少市场状态</small></strong></div></section>
   </>:<div className="favoriteLoading"><b>正在读取今天的形态状态</b><p>首次上线后的完整交易日会开始真实前向留档。</p></div>}
  </div>
 </TrackerShell>;
}
