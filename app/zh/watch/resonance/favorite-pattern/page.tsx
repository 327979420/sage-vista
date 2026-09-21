"use client";

import {useEffect, useMemo, useState} from "react";
import {TrackerShell} from "../tracker-ui";

type Bar = {date:string; open:number; high:number; low:number; close:number; volume:number};
type Anchor = {date:string; confirmed_at:string; price:number};
type Shape = {
  symbol:string; as_of:string; activity_rank:number; price:number; state:string; state_zh:string;
  shape_zh:string; explanation_zh:string; invalidation_price:number; chart:Bar[];
  bottom:{anchors:Anchor[]; zone_lower:number; zone_upper:number; confirmed_at:string};
  three_push:{anchors:Anchor[]; level:number; breakout_date:string|null}|null;
  liquidity:{dollar_volume:number; relative_volume:number|null};
};
type Picker = {
  version:string; as_of:string; rows:Shape[]; price_version:string;
  state_counts:Record<string,number>;
  universe:{eligible_covered_count:number; selected_activity_count:number; cached_common_count:number};
};
class PickerLoadError extends Error {}

const money = (n:number)=>`$${n.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}`;
const turnover = (n:number)=>n>=1e8?`${(n/1e8).toFixed(1)} 亿美元`:`${(n/1e4).toFixed(0)} 万美元`;

function ShapeChart({row}:{row:Shape}) {
  const anchors = [...row.bottom.anchors,...(row.three_push?.anchors??[])];
  const first = row.chart.findIndex(bar=>anchors.some(a=>a.date===bar.date));
  const bars = row.chart.slice(Math.max(0,first-10));
  const width=1120,height=380;
  const minimum=Math.min(...bars.map(b=>b.low),row.bottom.zone_lower);
  const maximum=Math.max(...bars.map(b=>b.high),row.bottom.zone_upper);
  const spread=Math.max(maximum-minimum,.01),low=minimum-spread*.08,high=maximum+spread*.14;
  const x=(i:number)=>65+i/Math.max(1,bars.length-1)*(width-100);
  const y=(price:number)=>22+(high-price)/(high-low)*(height-65);
  const index=(day:string)=>bars.findIndex(b=>b.date===day);
  const line=row.three_push;
  return <div className="shapeChartFrame"><div className="shapeChartScroll"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${row.symbol} 日线形态：底部确认与三推标注`}>
    {[0,1,2,3,4].map(step=>{const value=low+(high-low)*step/4;return <g key={step}><line x1="60" x2="1090" y1={y(value)} y2={y(value)} stroke="#e2e8f0"/><text x="5" y={y(value)+4}>{value.toFixed(2)}</text></g>})}
    <rect x="60" y={y(row.bottom.zone_upper)} width="1030" height={y(row.bottom.zone_lower)-y(row.bottom.zone_upper)} fill="#d1fae5" opacity=".65"/>
    {bars.map((b,i)=>{const color=b.close>=b.open?"#047857":"#dc2626";return <g key={b.date}><title>{`${b.date} 开 ${money(b.open)} 高 ${money(b.high)} 低 ${money(b.low)} 收 ${money(b.close)}`}</title><line x1={x(i)} x2={x(i)} y1={y(b.high)} y2={y(b.low)} stroke={color}/><rect x={x(i)-2.5} y={Math.min(y(b.open),y(b.close))} width="5" height={Math.max(1,Math.abs(y(b.open)-y(b.close)))} fill={color}/></g>})}
    {line&&<line x1={x(index(line.anchors[0].date))} y1={y(line.anchors[0].price)} x2={x(bars.length-1)} y2={y(line.level)} stroke="#7c3aed" strokeWidth="2"/>}
    {[{name:"底",points:row.bottom.anchors},{name:"推",points:line?.anchors??[]}].map(group=>group.points.map((a,i)=><g key={`${group.name}-${a.date}`}><circle cx={x(index(a.date))} cy={y(a.price)} r="5" fill="#1d4ed8"/><text x={x(index(a.date))} y={y(a.price)+(group.name==="底"?20:-12)} textAnchor="middle">{group.name}{i+1}</text>{group.name==="底"&&<path d={`M ${x(index(a.confirmed_at))-4} ${y(a.price)-10} l 4 -6 l 4 6 Z`} fill="#b45309"/>}</g>))}
    <text x="1080" y={y(row.bottom.zone_lower)+15} textAnchor="end">支撑区下沿 {money(row.bottom.zone_lower)}</text>
    <text x="65" y="375">{bars[0].date}</text><text x="1080" y="375" textAnchor="end">{bars.at(-1)?.date}</text>
  </svg></div><p className="shapeLegend">绿色区域：支撑区 · 紫线：三推下降线 · 蓝点：已确认转折 · 棕三角：底部确认日</p></div>;
}

export default function FavoritePatternPage() {
  const [data,setData]=useState<Picker|null>(null);
  const [error,setError]=useState("");
  const [attempt,setAttempt]=useState(0);
  const [query,setQuery]=useState("");
  const [group,setGroup]=useState("waiting");
  const [symbol,setSymbol]=useState("");
  useEffect(()=>{
    const controller=new AbortController();
    Promise.all([fetch("/daily-shape-picker.json",{cache:"no-store",signal:controller.signal}),fetch("/update-status.json",{cache:"no-store",signal:controller.signal})])
      .then(async responses=>{if(responses.some(r=>!r.ok))throw new PickerLoadError("形态数据暂时没有加载成功。");return Promise.all(responses.map(r=>r.json()))})
      .then(([picker,status])=>{
        if(picker.version!=="daily-shape-picker-v1"||!Array.isArray(picker.rows))throw new PickerLoadError("形态数据格式有误，正在等待完整更新。");
        if(picker.as_of!==status.source_latest_complete_date)throw new PickerLoadError(`形态数据仍停留在 ${picker.as_of}，尚未与最新收盘日同步。`);
        if(!controller.signal.aborted)setData(picker);
      }).catch(e=>{if(!controller.signal.aborted)setError(e instanceof PickerLoadError?e.message:"形态数据暂时无法读取，请重试。")});
    return ()=>controller.abort();
  },[attempt]);
  const rows=useMemo(()=>data?.rows.filter(row=>(group==="waiting"?row.state==="waiting":row.state!=="waiting")&&row.symbol.toLowerCase().includes(query.trim().toLowerCase()))??[],[data,group,query]);
  const selected=rows.find(r=>r.symbol===symbol)??rows[0];
  const waiting=data?.state_counts.waiting??0;
  const tracking=(data?.rows.length??0)-waiting;
  return <TrackerShell active="我最喜欢形态" title="热门股 · 日线 · 形态" subtitle="先确认底部，在突破前发现值得观察的日线形态。">
    <div className="shapePicker">
      <p className="shapeIntro">从成交活跃的股票里，找三推回调、多底支撑。点一只股票，就能核对形态和底部确认日期。</p>
      {error?<div className="shapeMessage" role="alert"><p>{error}</p><button type="button" onClick={()=>{setError("");setData(null);setAttempt(n=>n+1)}}>重新加载</button></div>:!data?<div className="shapeMessage" role="status">正在读取日线形态…</div>:<>
        <div className="shapeSummary"><div><small>行情日期</small><strong>{data.as_of}</strong></div><div><small>等待突破</small><strong>{waiting} <span>只</span></strong></div><div><small>后续跟踪</small><strong>{tracking} <span>只</span></strong></div><div><small>检查范围</small><strong>成交额前 {data.universe.selected_activity_count}</strong></div></div>
        <p className="shapeScope">范围：已覆盖的 {data.universe.eligible_covered_count.toLocaleString()} 只合格普通股。按当日成交金额选出热门股，不代表全市场或社交热度。</p>
        <div className="shapeControls"><div className="shapeTabs" aria-label="形态阶段"><button type="button" aria-pressed={group==="waiting"} onClick={()=>setGroup("waiting")}>等待突破 · {waiting}</button><button type="button" aria-pressed={group==="tracking"} onClick={()=>setGroup("tracking")}>已越线／后续跟踪 · {tracking}</button></div><label>找股票 <input aria-label="搜索股票代码" placeholder="例如 MSFT" value={query} onChange={e=>setQuery(e.target.value)}/></label></div>
        <p className="shapeCount" role="status">{rows.length?`显示 ${rows.length} 只股票 · 按成交金额排序`:"这个范围没有匹配的股票。"}</p>
        {selected?<div className="shapeWorkspace"><aside aria-label="形态候选股票">{rows.map(row=><button key={row.symbol} type="button" aria-pressed={selected.symbol===row.symbol} onClick={()=>setSymbol(row.symbol)}><span><b>{row.symbol}</b><small>{row.three_push?"三推回调＋多底":"多底支撑"}</small></span><span><b>{money(row.price)}</b><small>热度 #{row.activity_rank}</small></span></button>)}</aside>
          <article className="shapeDetail" key={selected.symbol}><header><div><small>日线形态 · {selected.as_of}</small><h2>{selected.symbol} · {selected.shape_zh}</h2></div><span className="shapeBadge">{selected.state_zh}</span></header>
            <p>{selected.explanation_zh}</p><p className="shapeScope">当日成交额 {turnover(selected.liquidity.dollar_volume)}{selected.liquidity.relative_volume!=null?` · 成交量为此前20日均量的 ${selected.liquidity.relative_volume.toFixed(2)} 倍`:""}</p>
            <ShapeChart row={selected}/>
            <div className="shapeFacts"><div><small>最后一个底部确认于</small><b>{selected.bottom.confirmed_at}</b></div><div><small>支撑区下沿</small><b>{money(selected.invalidation_price)}</b></div><div><small>{selected.three_push?"当前下降趋势线":"形态"}</small><b>{selected.three_push?money(selected.three_push.level):"多底支撑"}</b></div></div>
            <details><summary>查看底部与三推的确认日期</summary><div className="shapeTableScroll"><table><thead><tr><th>转折</th><th>发生日</th><th>确认日</th><th>价格</th></tr></thead><tbody>{[{label:"底",anchors:selected.bottom.anchors},{label:"推",anchors:selected.three_push?.anchors??[]}].flatMap(g=>g.anchors.map((a,i)=><tr key={`${g.label}-${a.date}`}><td>{g.label}{i+1}</td><td>{a.date}</td><td>{a.confirmed_at}</td><td>{money(a.price)}</td></tr>))}</tbody></table></div><p>低点出现后，要等右侧两根日K收盘才确认。仅使用已经完成的日线。</p></details>
            <p className="shapeNote">这是形态观察，不是买入指令。底部已确认，之后仍可能跌破；收盘跌破支撑区下沿，当前结构会被排除。</p>
          </article></div>:<div className="shapeMessage">{query?"试试其他股票代码，或清空搜索。":"今天没有符合这一阶段的形态，等待下一次收盘更新。"}</div>}
      </>}
    </div>
  </TrackerShell>;
}
