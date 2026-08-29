"use client";
import {useMemo,useState} from "react";
import {TrackerShell,useTracker} from "../tracker-ui";

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
 ema_realign?:{hit:boolean;cross_date:string|null;ema20:number;ema50:number;ema200:number};
 trade_map?:{signal_close:number|null;earliest_entry:string|null;target_previous_high:number|null;invalidation_second_bottom:number|null;estimated_reward_risk:number|null};
};
type Favorite={as_of:string;pattern_version:string;production_scoring_changed:boolean;summary:{watchlist:number;entry_ready:number;waiting_breakout:number;breakout_incomplete:number;forming:number;launched:number};candidates:PatternRow[];reference_cases:PatternRow[];warning_zh:string;forward_tracking:{minimum_conclusion_sample:number;minimum_months:number;minimum_market_states:number}};
type Root={favorite_pattern_tracker?:Favorite};

const stages=[
 ["01","前段上涨","先有可测量的上涨段"],
 ["02","回调到位","Golden Pocket 或 EMA200"],
 ["03","宽双底","两个确认低点＋中间反弹"],
 ["04","二底 MACD","第二底附近完整日线金叉"],
 ["05","三推突破","完整收盘越过下降趋势线"],
 ["06","EMA 重排","EMA20 重新高于 EMA50"],
 ["07","前高目标","突破后先看上一段高点"],
] as const;
const stageTone:Record<string,string>={entry_ready:"ready",waiting_breakout:"waiting",breakout_incomplete:"incomplete",bottom_confirmed:"forming",pullback_forming:"forming",launched:"launched",target_reached:"reached",invalidated:"invalid"};
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
  [row.double_bottom?.first_date,"底1","bottom"],
  [row.double_bottom?.second_date,"底2","bottom"],
  [row.second_bottom_macd?.cross_date,"MACD","macd"],
  [row.three_push?.breakout_date,"突破","breakout"],
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
 const root=useTracker() as unknown as Root|null;
 const data=root?.favorite_pattern_tracker;
 const [symbol,setSymbol]=useState("");
 const selected=useMemo(()=>data?.candidates.find(row=>row.symbol===symbol)??data?.candidates[0],[data,symbol]);
 return <TrackerShell active="我最喜欢形态" title="我最喜欢形态" subtitle="每天追踪你真正愿意做的日线共振，而不是再堆一套评分。">
  <div className="favoritePage">
   <section className="favoriteIntro"><div><small>MY FAVORITE DAILY SETUP · FORWARD TRACKER</small><h2>先有一段上涨，再等深回调后的结构重新启动</h2><p>这页不要求旧的长期趋势门票，也不替代多因子排行榜。它只回答：今天有没有股票走到你喜欢的那一段。匹配度不是胜率。</p><p className="favoriteReferenceLine">BABA 定义形态 · PG 保留反例</p></div><mark>生产权重 0 · 独立观察</mark></section>
   <section className="favoriteFunnel" aria-label="形态七步流程">{stages.map(([index,title,note])=><article key={index}><i>{index}</i><b>{title}</b><span>{note}</span></article>)}</section>
   {data?<>
    <section className="favoriteMetrics"><article><small>数据日</small><b>{data.as_of}</b><span>{data.pattern_version}</span></article><article><small>7/7 入场就绪</small><b>{data.summary.entry_ready}</b><span>完整共振＋收盘突破</span></article><article><small>已突破但不完整</small><b>{data.summary.breakout_incomplete}</b><span>6/7及以下，只观察</span></article><article><small>等待突破</small><b>{data.summary.waiting_breakout}</b><span>只观察，不行动</span></article><article><small>回调／双底形成中</small><b>{data.summary.forming}</b><span>提前放进视野</span></article><article><small>当前观察表</small><b>{data.summary.watchlist}</b><span>全市场同日扫描</span></article></section>
    <div className="favoriteWarning"><b>先说清楚：</b>{data.warning_zh}</div>
    <section className="favoriteWorkspace"><aside><header><small>TODAY&apos;S SETUPS</small><h3>今天走到哪一步</h3></header>{data.candidates.length?data.candidates.map(row=><button type="button" key={row.symbol} onClick={()=>setSymbol(row.symbol)} className={selected?.symbol===row.symbol?"active":""}><span><b>{row.symbol}</b><small>{row.stage_zh}</small></span><strong>{row.match_count}/{row.total_conditions}<small>条件</small></strong><i className={stageTone[row.stage]??"forming"}/></button>):<div className="favoriteNone"><b>今天没有4项以上匹配</b><p>不会用旧候选填充。</p></div>}</aside>
     <div className="favoriteDetail">{selected?<><header><div><small>POINT-IN-TIME PATTERN AUDIT</small><h3>{selected.symbol} · {selected.stage_zh}</h3><p>{selected.action_zh}</p></div><strong>{selected.match_count}/{selected.total_conditions}<small>形态完成度</small></strong></header><PriceChart row={selected}/><Evidence row={selected}/><div className="favoriteFacts"><article><small>前段上涨</small><b>{selected.prior_advance?`+${selected.prior_advance.advance_pct.toFixed(1)}%`:"未确认"}</b><span>{selected.prior_advance?`${selected.prior_advance.low_date} → ${selected.prior_advance.high_date}`:"需要已确认低点到高点"}</span></article><article><small>回调位置</small><b>{selected.pullback?.retracement_pct!=null?`${selected.pullback.retracement_pct.toFixed(1)}%`:"—"}</b><span>{selected.pullback?.golden_pocket?"✓ Golden Pocket":"Golden Pocket未命中"} · {selected.pullback?.ema200_support?"✓ EMA200":"EMA200未命中"}</span></article><article><small>第二底 / MACD</small><b>{selected.double_bottom?.second_date??"—"}</b><span>{selected.second_bottom_macd?.cross_date?`金叉 ${selected.second_bottom_macd.cross_date}`:"附近没有金叉"}</span></article><article><small>突破 / 均线</small><b>{selected.three_push?.breakout_date??"等待"}</b><span>{selected.ema_realign?.hit?`EMA20 ${money(selected.ema_realign.ema20)} ＞ EMA50 ${money(selected.ema_realign.ema50)}`:"EMA20/50尚未重排"}</span></article></div><div className="favoriteTradeMap"><span>研究入场 <b>{selected.trade_map?.earliest_entry?"突破后下一交易日开盘":"未触发"}</b></span><span>前高目标 <b>{money(selected.trade_map?.target_previous_high)}</b></span><span>二底失效位 <b>{money(selected.trade_map?.invalidation_second_bottom)}</b></span><span>估算盈亏比 <b>{selected.trade_map?.estimated_reward_risk?`${selected.trade_map.estimated_reward_risk.toFixed(2)}R` :"—"}</b></span></div></>:<div className="favoriteNone"><b>等待当日扫描结果</b></div>}</div>
    </section>
    <section className="favoriteReferences"><header><div><small>FIXED REFERENCE CASES</small><h2>BABA 定义形态，PG 保留反例</h2><p>参考案例不会因为现在不匹配或成绩一般而消失，也不会被强行判成命中。</p></div></header><div>{data.reference_cases.map(row=><article key={row.symbol} data-stage={row.stage}><header><b>{row.symbol}</b><mark>{row.stage_zh}</mark></header><p>{row.reference_note_zh}</p><footer>{row.available?`当前机器匹配 ${row.match_count}/${row.total_conditions}`:row.reason}</footer></article>)}</div></section>
    <section className="favoriteForward"><div><small>TRUE UNSEEN FORWARD</small><h2>从现在开始积累，不拿BABA已知走势冒充验证</h2><p>只有“入场就绪”进入永久账本，按下一交易日复权开盘记录5/10/20/40/60/100日、MFE和MAE。</p></div><div><strong>{data.forward_tracking.minimum_conclusion_sample}<small>至少入场案例</small></strong><strong>{data.forward_tracking.minimum_months}<small>至少月份</small></strong><strong>{data.forward_tracking.minimum_market_states}<small>至少市场状态</small></strong></div></section>
   </>:<div className="favoriteLoading"><b>正在读取今天的形态状态</b><p>首次上线后的完整交易日会开始真实前向留档。</p></div>}
  </div>
 </TrackerShell>;
}
