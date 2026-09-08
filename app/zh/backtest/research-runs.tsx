"use client";
import {useEffect, useState} from "react";

export const RESULTS_ROOT = "https://raw.githubusercontent.com/327979420/sage-vista/main/research/backtest/output/reusable-runs/";
const CONFIG_URL = "https://raw.githubusercontent.com/327979420/sage-vista/main/research/backtest/account-scenario.json";
const WORKFLOW_URL = "https://github.com/327979420/sage-vista/actions/workflows/opportunity-ledger-refresh.yml";
type Run = {id:string; status:"completed"|"unavailable"|"failed"; request:{strategy?:string;start?:string;end?:string}; summary:Record<string,number|null>; receipt_sha256:string};
type Selection = {technical_score?:number;rank?:number;model_version?:string;factor_registry_version?:string;ruleset_id?:string;score_equation?:string;reasons?:string[];timeframe_profile?:{label?:string}};
type Trade = {event_id:string;symbol:string;signal_date:string;entry_date?:string;status:string;rank?:number;signal_snapshot?:{as_of:string;selection:Selection}};
type Receipt = Run & {reason?:string; report?:{path:string;sha256:string};code_commit?:string;source?:{ledger_sha256?:string};trades?:Trade[];audit?:{account_algorithm:string;experiment_key:string;selection_versions:string[]}};
const validId = (id:string) => /^[1-9][0-9]{0,19}-[1-9][0-9]{0,5}$/.test(id);
const fingerprint = (s:string) => /^[0-9a-f]{64}$/.test(s);
const statusLabel = {completed:"已完成",unavailable:"来源不可用",failed:"运行失败"};
const percent = (n:unknown) => typeof n!=="number" || !Number.isFinite(n) ? "不可用" : `${(n*100).toFixed(2)}%`;
const record = (v:unknown):v is Record<string,unknown> => !!v && typeof v==="object" && !Array.isArray(v);

export function checkedIndex(data:unknown):Run[]{
 const value=data as {schema_version?:string;runs?:Run[]};
 if(value?.schema_version!=="legacy-research-index-v1" || !Array.isArray(value.runs)) throw Error("结果索引格式不符");
 if(value.runs.some(r=>!record(r)||typeof r.id!=="string"||!validId(r.id)||typeof r.receipt_sha256!=="string"||!fingerprint(r.receipt_sha256)||!Object.hasOwn(statusLabel,r.status)||!record(r.request)||Object.values(r.request).some(v=>typeof v!=="string")||!record(r.summary)||Object.entries(r.summary).some(([k,v])=>k==="quantstats_version"?typeof v!=="string":v!==null&&(typeof v!=="number"||!Number.isFinite(v))))) throw Error("结果索引内容不符");
 return value.runs;
}

async function fetchText(path:string,signal:AbortSignal){
 const response=await fetch(RESULTS_ROOT+path,{cache:"no-store",signal,credentials:"omit"});
 if(!response.ok) throw Error(`读取结果失败（${response.status}），请稍后刷新。`);
 return response.text();
}
async function hash(text:string){
 return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(text)))).map(n=>n.toString(16).padStart(2,"0")).join("");
}

export function ResearchRunList({runs,onSelect,selected}:{runs:Run[];onSelect:(id:string)=>void;selected:string}){
 return <section className="svPanel"><h2>历史研究运行</h2>{!runs.length?<p>还没有已保存的研究运行。下方保留早期20笔工程对账。</p>:<div className="tradeComparisonTable"><table><thead><tr><th>运行／日期</th><th>状态</th><th>账户收益</th><th>最大回撤</th><th>已平仓胜率</th></tr></thead><tbody>{runs.map(r=><tr key={r.id} data-selected={r.id===selected}><td><span>{r.request.start} 至 {r.request.end}</span> <button aria-pressed={r.id===selected} onClick={()=>onSelect(r.id)}>{r.status==="completed"?"查看报告":"查看原因"}</button><small>#{r.id}</small></td><td>{statusLabel[r.status]}</td><td>{percent(r.summary.total_return)}</td><td>{percent(r.summary.max_drawdown)}</td><td>{percent(r.summary.win_rate)}</td></tr>)}</tbody></table></div>}</section>;
}

export function matchingSignal(trade:Trade, events:Map<string,{symbol:string;signal_date:string;selection:Selection}>):Selection{
 const event=events.get(trade.event_id);
 if(!event||event.symbol!==trade.symbol||event.signal_date!==trade.signal_date||(trade.rank!==undefined&&event.selection.rank!==trade.rank))throw Error("原交易与信号账本不一致，停止显示评分。");
 return event.selection;
}

function TradeAudit({receipt}:{receipt:Receipt}){
 const [selections,setSelections]=useState<Record<string,Selection>|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
 const trades=(receipt.trades??[]).filter(t=>t.status==="open"||t.status==="closed");
 async function load(){
  setBusy(true);setError("");
  try{
   const result:Record<string,Selection>={};
   if(trades.every(t=>t.signal_snapshot)){
    for(const t of trades){if(t.signal_snapshot!.as_of!==t.signal_date)throw Error("评分快照日期不一致");result[t.event_id]=t.signal_snapshot!.selection;}
   }else{
    if(!/^[0-9a-f]{40}$/.test(receipt.code_commit??"")||!fingerprint(receipt.source?.ledger_sha256??""))throw Error("原报告缺少评分来源身份");
    const response=await fetch(`https://raw.githubusercontent.com/327979420/sage-vista/${receipt.code_commit}/public/opportunity-ledger.json`,{credentials:"omit"});
    if(!response.ok)throw Error("原始评分账本读取失败，请重试");
    const raw=await response.text();if(await hash(raw)!==receipt.source!.ledger_sha256)throw Error("原始账本校验失败，不能用其他版本替代");
    const events=JSON.parse(raw).events;const map=new Map<string,{symbol:string;signal_date:string;selection:Selection}>();
    for(const e of events){if(map.has(e.event_id))throw Error("原账本事件重复");map.set(e.event_id,e);}
    for(const t of trades)result[t.event_id]=matchingSignal(t,map);
   }
   setSelections(result);
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
 }
 const versions=selections?[...new Set(Object.values(selections).map(s=>s.model_version??"未记录"))]:receipt.audit?.selection_versions;
 return <section className="svPanel"><h2>策略版本与买入评分</h2>
  <p>本报告为旧策略：日线金叉及旧长期趋势资格后按排名尝试入场，未使用新版月线方向否决。评分用于排序，没有额外最低买入分数。</p>
  <p>买入依据采用信号日收盘技术分，次日开盘尝试买入；旧分数不能与新版百分制直接比较。卖出时评分：未记录，不用今天的分数补填。</p>
  <p>执行版本：{receipt.request.strategy??"未记录"} · 回测代码：{receipt.code_commit??"未记录"}{receipt.audit&&<> · 账户算法：{receipt.audit.account_algorithm}</>}</p>
  {versions&&<p>实际买入使用的选股版本：{versions.join("、")}{versions.length>1&&"（混合历史版本，不视为同一策略）"}</p>}
  {receipt.audit&&<details><summary>实验身份（识别相同条件）</summary><p style={{overflowWrap:"anywhere"}}>{receipt.audit.experiment_key}</p><p>相同条件优先复用已有报告；目前尚未自动阻止重复提交。</p></details>}
  {!selections&&<button disabled={busy} onClick={load}>{busy?"正在核对原信号账本…":"查看每笔买入评分与原因"}</button>}
  {!selections&&<p>旧报告首次查看按需读取原始评分档案，约9MB；复用已保存交易，不重跑回测。</p>}
  {error&&<p role="alert">{error}</p>}
  {selections&&<div className="tradeComparisonTable"><table><thead><tr><th>股票</th><th>评分日期／买入日</th><th>技术分／原排名</th><th>评分版本</th><th>入选依据</th></tr></thead><tbody>{trades.map(t=>{const s=selections[t.event_id];return <tr key={t.event_id}><td>{t.symbol}</td><td>{t.signal_date} 收盘<br/>{t.entry_date} 买入</td><td>{typeof s.technical_score==="number"?s.technical_score:"未记录"} 分／第 {s.rank??"未记录"} 名</td><td>{s.model_version??"未记录"}<br/>因子 {s.factor_registry_version??"未记录"}</td><td>{s.reasons?.join("；")??"未记录"}<details><summary>原评分说明</summary><p>{s.score_equation??"未记录"}</p><p>{s.timeframe_profile?.label??"周期信息未记录"}</p><p>规则：{s.ruleset_id??"未记录"}</p></details></td></tr>})}</tbody></table></div>}
 </section>;
}

export default function ResearchRuns(){
 const [runs,setRuns]=useState<Run[]>([]),[selected,setSelected]=useState(""),[html,setHtml]=useState(""),[receipt,setReceipt]=useState<Receipt|null>(null),[error,setError]=useState(""),[loading,setLoading]=useState(true),[refresh,setRefresh]=useState(0);
 const [enabled,setEnabled]=useState(false),[configLoaded,setConfigLoaded]=useState(false);
 useEffect(()=>{
  const controller=new AbortController();
  fetch(CONFIG_URL,{cache:"no-store",signal:controller.signal,credentials:"omit"}).then(r=>r.ok?r.json():null).then(c=>{if(!controller.signal.aborted){setEnabled(c?.approved===true&&typeof c?.approval_ref==="string"&&c.approval_ref.length>0);setConfigLoaded(true)}}).catch(()=>{if(!controller.signal.aborted){setEnabled(false);setConfigLoaded(true)}});
  return()=>controller.abort();
 },[refresh]);
 useEffect(()=>{
  const controller=new AbortController();
  fetchText("index.json",controller.signal).then(JSON.parse).then(checkedIndex).then(values=>{setRuns(values);setSelected(old=>values.some(r=>r.id===old)?old:values[0]?.id??"");setError("");setLoading(false)}).catch(e=>{if(!controller.signal.aborted){setError(String(e.message));setLoading(false)}});
  return()=>controller.abort();
 },[refresh]);
 useEffect(()=>{
  const run=runs.find(r=>r.id===selected);if(!run)return;
  const controller=new AbortController();
  (async()=>{
   const raw=await fetchText(run.id+"/receipt.json",controller.signal);
   if(await hash(raw)!==run.receipt_sha256)throw Error("收据校验失败，请等待索引更新后刷新。");
   const value:Receipt=JSON.parse(raw);
   if(value.id!==run.id||value.status!==run.status)throw Error("运行身份不一致");
   if(value.reason!==undefined&&typeof value.reason!=="string")throw Error("运行原因格式不符");
   let report="";
   if(value.report){
    if(value.status!=="completed"||value.report.path!==run.id+"/report.html"||!fingerprint(value.report.sha256))throw Error("报告引用不符");
    report=await fetchText(value.report.path,controller.signal);
    if(await hash(report)!==value.report.sha256)throw Error("报告校验失败，请稍后刷新。");
   }
   if(!controller.signal.aborted){setReceipt(value);setHtml(report);setError("")}
  })().catch(e=>{if(!controller.signal.aborted){setReceipt(null);setHtml("");setError(String(e.message))}});
  return()=>controller.abort();
 },[selected,runs]);
 const choose=(id:string)=>{if(id===selected){document.getElementById("quantstats-report")?.scrollIntoView({behavior:"smooth"});return;}setHtml("");setReceipt(null);setError("");setSelected(id)};
 return <div className="tradeComparison">
  <header className="svPanel"><small>VectorBT＋QuantStats · 旧规则研究场景</small><h2>历史研究结果</h2><p>旧策略：支撑下5%／入场亏损上限10%，2R目标，最长40个交易日。逐日回放当时保存的信号，不用今天的榜单倒填过去。</p><p>记录从2025-12-29开始。首轮建议：2025-12-29至2026-01-30、2026-02-02至2026-02-27；其他区间须每日旧策略记录与行情完整。前几年及新版策略历史重算尚未接通。</p><p>{enabled?"在 GitHub 登录后的表单选择 research 模式、旧基线策略和起止日期，然后提交。运行结束后回到这里刷新查看结果。":configLoaded?"研究配置暂不可用，提交入口暂时关闭；已有报告仍可查看。":"正在读取已批准的研究配置…"}</p><p>{enabled?<a href={WORKFLOW_URL} target="_blank" rel="noreferrer">提交回测／查看运行进度 ↗</a>:<button disabled>{configLoaded?"研究配置暂不可用":"正在读取研究配置"}</button>} · <button onClick={()=>{setLoading(true);setRefresh(v=>v+1)}}>刷新已保存结果</button></p><p>永久结果直接从仓库读取，无需每次重新部署；公开内容可能有几分钟缓存延迟。来源缺失和失败也保留，不作为零收益。研究假设不代表生产策略已获批准。</p></header>
  {loading&&<p role="status">正在读取历史运行…</p>}{error&&<p role="alert">{error}</p>}
  <ResearchRunList runs={runs} onSelect={choose} selected={selected}/>
  {selected&&!receipt&&!error&&<p role="status">正在加载所选回测报告…</p>}
  {receipt?.status==="completed"&&<TradeAudit key={receipt.id} receipt={receipt}/>}
  {receipt&&<section id="quantstats-report" className="svPanel"><h2>QuantStats 回测报告</h2><h3>{receipt.request.start} 至 {receipt.request.end} · {statusLabel[receipt.status]}</h3>{receipt.reason&&<p>{receipt.reason}</p>}<p><a href={RESULTS_ROOT+receipt.id+"/receipt.json"} target="_blank" rel="noreferrer">下载本次收据与逐笔结果</a></p>{html&&<iframe key={receipt.id} title="QuantStats账户报告与交易明细" sandbox="" referrerPolicy="no-referrer" srcDoc={'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; font-src data:; base-uri \'none\'; form-action \'none\'">'+html} style={{width:"100%",height:"1100px",border:0}}/>}</section>}
 </div>;
}
