"use client";
import {useEffect, useState} from "react";

export const RESULTS_ROOT = "https://raw.githubusercontent.com/327979420/sage-vista/main/research/backtest/output/reusable-runs/";
const CONFIG_URL = "https://raw.githubusercontent.com/327979420/sage-vista/main/research/backtest/account-scenario.json";
const WORKFLOW_URL = "https://github.com/327979420/sage-vista/actions/workflows/opportunity-ledger-refresh.yml";
type Run = {id:string; status:"completed"|"unavailable"|"failed"; request:{strategy?:string;start?:string;end?:string}; summary:Record<string,number|null>; receipt_sha256:string};
type Receipt = Run & {reason?:string; report?:{path:string;sha256:string}};
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
 return <section className="svPanel"><h2>历史研究运行</h2>{!runs.length?<p>还没有已保存的研究运行。下方保留早期20笔工程对账。</p>:<div className="tradeComparisonTable"><table><thead><tr><th>运行／日期</th><th>状态</th><th>账户收益</th><th>最大回撤</th><th>已平仓胜率</th></tr></thead><tbody>{runs.map(r=><tr key={r.id} data-selected={r.id===selected}><td><button onClick={()=>onSelect(r.id)}>{r.request.start} 至 {r.request.end}</button><small>#{r.id}</small></td><td>{statusLabel[r.status]}</td><td>{percent(r.summary.total_return)}</td><td>{percent(r.summary.max_drawdown)}</td><td>{percent(r.summary.win_rate)}</td></tr>)}</tbody></table></div>}</section>;
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
 const choose=(id:string)=>{setHtml("");setReceipt(null);setSelected(id)};
 return <div className="tradeComparison">
  <header className="svPanel"><small>VectorBT＋QuantStats · 旧规则研究场景</small><h2>历史研究结果</h2><p>旧策略：支撑下5%／入场亏损上限10%，2R目标，最长40个交易日。逐日回放当时保存的信号，不用今天的榜单倒填过去。</p><p>记录从2025-12-29开始。首轮建议：2025-12-29至2026-01-30、2026-02-02至2026-02-27；其他区间须每日旧策略记录与行情完整。前几年及新版策略历史重算尚未接通。</p><p>{enabled?"在 GitHub 登录后的表单选择 research 模式、旧基线策略和起止日期，然后提交。运行结束后回到这里刷新查看结果。":configLoaded?"研究配置暂不可用，提交入口暂时关闭；已有报告仍可查看。":"正在读取已批准的研究配置…"}</p><p>{enabled?<a href={WORKFLOW_URL} target="_blank" rel="noreferrer">提交回测／查看运行进度 ↗</a>:<button disabled>{configLoaded?"研究配置暂不可用":"正在读取研究配置"}</button>} · <button onClick={()=>{setLoading(true);setRefresh(v=>v+1)}}>刷新已保存结果</button></p><p>永久结果直接从仓库读取，无需每次重新部署；公开内容可能有几分钟缓存延迟。来源缺失和失败也保留，不作为零收益。研究假设不代表生产策略已获批准。</p></header>
  {loading&&<p role="status">正在读取历史运行…</p>}{error&&<p role="alert">{error}</p>}
  <ResearchRunList runs={runs} onSelect={choose} selected={selected}/>
  {receipt&&<section className="svPanel"><h3>运行 #{receipt.id} · {statusLabel[receipt.status]}</h3>{receipt.reason&&<p>{receipt.reason}</p>}<p><a href={RESULTS_ROOT+receipt.id+"/receipt.json"} target="_blank" rel="noreferrer">下载本次收据与逐笔结果</a></p>{html&&<iframe key={receipt.id} title="QuantStats账户报告与交易明细" sandbox="" referrerPolicy="no-referrer" srcDoc={'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; font-src data:; base-uri \'none\'; form-action \'none\'">'+html} style={{width:"100%",height:"1100px",border:0}}/>}</section>}
 </div>;
}
