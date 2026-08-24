"use client";
import {useEffect,useMemo,useState} from "react";
import {TrackerShell} from "../tracker-ui";

type Metric={side:string;regime:string;regime_label:string;factor:string;horizon:number;samples:number;win_rate:number|null;trimmed_mean_return:number|null;median_return:number|null;mean_adverse:number|null};
type Candidate={side:string;factor:string;horizon:number;status:string;development:Metric;validation:Metric;forward:Metric};
type Study={universe:{eligible:number;events:number;trigger_counts:Record<string,number>};splits:{development:Metric[];validation:Metric[];forward:Metric[]};validated_combinations:Candidate[];execution:string;lookahead:string;warning:string};
const baseFactors=["日线零轴下金叉","周线零轴下金叉","月线零轴下金叉"];

export default function Research(){
 const [data,setData]=useState<Study|null>(null);useEffect(()=>{fetch("/macd-factor-backtest.json").then(x=>x.json()).then(setData)},[]);
 const baselines=useMemo(()=>data?baseFactors.map(f=>[5,10,20].map(h=>{const find=(split:keyof Study["splits"])=>data.splits[split].find(x=>x.side==="buy"&&x.regime==="all"&&x.factor===f&&x.horizon===h)!;const development=find("development"),validation=find("validation"),forward=find("forward");return {factor:f,horizon:h,development,validation,forward,average:((development.win_rate??0)+(validation.win_rate??0)+(forward.win_rate??0))/3}}).sort((a,b)=>b.average-a.average)[0]):[],[data]);
 return <TrackerShell active="MACD研究" title="MACD 因子研究" subtitle="研究样本、周期结论和策略表现与当前个股排行榜完全分开。">
  {data&&<>
   <section className="rtSummary"><article className="rtSummaryPrimary"><small>合格股票历史</small><b>{data.universe.eligible.toLocaleString()}</b><p>至少420个交易日</p></article><article><small>全部MACD事件</small><b>{data.universe.events.toLocaleString()}</b><p>均按下一交易日开盘计算</p></article>{Object.entries(data.universe.trigger_counts).map(([k,v])=><article key={k}><small>{k}触发</small><b>{v.toLocaleString()}</b><p>完整{k}收盘后确认</p></article>)}</section>
   <section className="rtSignals"><div className="rtSectionTitle"><div><p>周期单独测试</p><h2>日线、周线、月线零轴下金叉</h2></div><span>按三阶段平均胜率选择固定持有期</span></div><div className="rtModuleGrid">{baselines.map(x=><article key={x.factor}><small>{x.factor} · 当前最稳健窗口</small><h2>{x.horizon}个交易日</h2><p>2024年前 {x.development.win_rate}% · {x.development.samples.toLocaleString()}样本<br/>2025验证 {x.validation.win_rate}% · {x.validation.samples.toLocaleString()}样本<br/>2026观察 {x.forward.win_rate}% · {x.forward.samples.toLocaleString()}样本</p><strong>验证期稳健均值 {x.validation.trimmed_mean_return}% · 中位数 {x.validation.median_return}%</strong></article>)}</div><p className="rtRankNote">当前三个周期都以20个交易日最稳定。周线金叉的5日和10日表现没有通过2025验证；月线信号较强，但样本远少于日线，不能仅凭单年高胜率提高过多权重。</p></section>
   <section className="rtSignals"><div className="rtSectionTitle"><div><p>看涨组合</p><h2>跨阶段仍为正的MACD策略</h2></div><span>2024年前发现 → 2025验证 → 2026观察</span></div><div className="rtMatrix"><div className="rtMatrixHead"><span>策略</span><span>市场环境</span><span>2025验证</span><span>2026观察</span><span>结论</span></div>{data.validated_combinations.filter(x=>x.side==="buy").slice(0,12).map((x,i)=><div className="rtMatrixRow" key={`${x.factor}-${x.horizon}-${x.validation.regime}`}><div className="rtMatrixTicker"><em>{i+1}</em><b>{x.factor}</b><small>持有{x.horizon}日</small></div><div className="rtLayerCell buy"><b>{x.validation.regime_label}</b><small>固定环境</small></div><div className="rtLayerCell buy"><b>{x.validation.win_rate}%</b><small>{x.validation.samples.toLocaleString()}样本 · 均值{x.validation.trimmed_mean_return}%</small></div><div className="rtLayerCell buy"><b>{x.forward.win_rate}%</b><small>{x.forward.samples.toLocaleString()}样本 · 均值{x.forward.trimmed_mean_return}%</small></div><div className="rtMatrixVerdict buy"><b>{x.status==="forward_supportive"?"继续保留":"继续观察"}</b><small>不是个股推荐</small></div></div>)}</div><p className="rtMethod">{data.execution}。{data.lookahead}。{data.warning}</p></section>
  </>}
 </TrackerShell>
}
