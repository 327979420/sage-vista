"""Factor Attribution V1: diagnostic comparisons on the frozen Long benchmark."""
from __future__ import annotations
import json,pathlib
from datetime import datetime,timezone
from services.scanner.macd_factor_backtest import adjusted_rows
from research.backtest.tracker_backtest_v2 import simulate,metrics

ROOT=pathlib.Path(__file__).parents[2];CACHE=ROOT/"work/eodhd-cache";OUT=ROOT/"research/backtest/output"
PERIODS=(("development","0000","2024-12-31"),("validation_2025","2025-01-01","2025-12-31"),("forward_2026","2026-01-01","9999"))
PAIRS=(("双支撑确认",("Fibonacci支撑","EMA支撑")),("突破回踩结构",("三推趋势线突破","三推突破后回踩确认")),("支撑位价格量能确认",("支撑位底部放量","支撑位看涨吞没")))

def benchmark_trades(signals):
 cache={};index={};out=[]
 for e in signals:
  if e["status"]!="Confirmed" or not e["strict_long_trend"] or not e.get("support_level"):continue
  t=e["ticker"]
  if t not in cache:
   cache[t]=adjusted_rows(json.loads((CACHE/f"{t}.json").read_text()));index[t]={x["date"]:i for i,x in enumerate(cache[t])}
  rows=cache[t];i=index[t][e["date"]];entry=e["entry_open"];stop=e["support_level"]*.95;risk=entry-stop
  if risk/entry<=.001:continue
  fill,bars,reason,mfe,mae=simulate(entry,stop,entry+2*risk,rows[i+1:i+41])
  out.append({"ticker":t,"date":e["date"],"return":fill/entry-1,"r":(fill-entry)/risk,"reason":reason,"bars":bars,"mfe":mfe,"mae":mae,"risk_pct":risk/entry,"rank":e["tracker_ranking"],"score":e["multi_factor_total_score"],"tracker_score":e["tracker_score"],"aligned_long_layers":e["aligned_long_layers"],"factors":{k:bool(v) for k,v in e["factor_states"].items() if not k.startswith("layer.")}})
 return out

def compact(rows):
 m=metrics(rows);out={k:m.get(k) for k in ("samples","win_rate","profit_factor","expectancy_pct","average_r")};out["average_return_pct"]=out["expectancy_pct"];return out

def compare(rows,test):
 yes=[x for x in rows if test(x)];no=[x for x in rows if not test(x)];a=compact(yes);b=compact(no)
 return {"with":a,"without":b,"delta":{"win_rate":round((a.get("win_rate") or 0)-(b.get("win_rate") or 0),2),"profit_factor":round((a.get("profit_factor") or 0)-(b.get("profit_factor") or 0),3),"expectancy_pct":round((a.get("expectancy_pct") or 0)-(b.get("expectancy_pct") or 0),3),"average_return_pct":round((a.get("expectancy_pct") or 0)-(b.get("expectancy_pct") or 0),3)}}

def run(out_dir=OUT):
 out_dir=pathlib.Path(out_dir);signals=[json.loads(x) for x in (out_dir/"signals.jsonl").read_text().splitlines() if x];trades=benchmark_trades(signals);factors=list(trades[0]["factors"])
 attribution=[]
 for factor in factors:
  test=lambda x,f=factor:x["factors"].get(f,False);overall=compare(trades,test);periods={name:compare([x for x in trades if lo<=x["date"]<=hi],test) for name,lo,hi in PERIODS}
  directions=[periods[x]["delta"] for x,_,_ in PERIODS];enough=all(periods[x]["with"]["samples"]>=20 and periods[x]["without"]["samples"]>=20 for x,_,_ in PERIODS)
  positive=all(x["expectancy_pct"]>0 and x["profit_factor"]>0 for x in directions);negative=overall["delta"]["expectancy_pct"]<0 and overall["delta"]["profit_factor"]<0 and sum(x["expectancy_pct"]<0 for x in directions)>=2
  status="基础资格（无法对照）" if overall["without"]["samples"]==0 else "稳定正贡献" if positive and enough else "候选正贡献（样本不足）" if positive else "可能拖累" if negative else "没有明显贡献"
  attribution.append({"factor":factor,"status":status,"overall":overall,"periods":periods})
 predefined=[]
 for name,items in PAIRS:
  predefined.append({"name":name,"factors":list(items),"comparison":compare(trades,lambda x,a=items:all(x["factors"].get(f,False) for f in a)),"note":"预定义关系，仅作候选诊断；未进行组合搜索"})
 ranks=[]
 for name,test in (("Rank 1–3",lambda x:x["rank"]<=3),("Rank 4–6",lambda x:4<=x["rank"]<=6),("Rank 7–10",lambda x:x["rank"]>=7)):
  rows=[x for x in trades if test(x)];ranks.append({"bucket":name,"metrics":compact(rows),"mean_multifactor_score":round(sum(x["score"] for x in rows)/len(rows),3),"mean_tracker_score":round(sum(x["tracker_score"] for x in rows)/len(rows),3),"mean_aligned_long_layers":round(sum(x["aligned_long_layers"] for x in rows)/len(rows),3),"factor_rates":{f:round(sum(x["factors"].get(f,False) for x in rows)/len(rows)*100,2) for f in factors}})
 scores=[]
 for name,test in (("Score 0–2",lambda x:x["score"]<=2),("Score 3–4",lambda x:3<=x["score"]<=4),("Score 5+",lambda x:x["score"]>=5)):
  rows=[x for x in trades if test(x)];scores.append({"bucket":name,"metrics":compact(rows),"mean_rank":round(sum(x["rank"] for x in rows)/len(rows),3)})
 stable=[x["factor"] for x in attribution if x["status"]=="稳定正贡献"];drag=[x["factor"] for x in attribution if x["status"]=="可能拖累"]
 report={"version":"1.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"benchmark":{"definition":"Confirmed + strict long trend + next adjusted Open + Support −5% + 2R TP","metrics":compact(trades)},"audit":{"signals_reused":True,"point_in_time_entries":True,"future_rows_for_factor_selection":False,"production_outputs_written":False,"factors_tested":len(factors),"automatic_combination_search":False},"factor_attribution":attribution,"rank_diagnosis":ranks,"score_diagnosis":scores,"predefined_combinations":predefined,"answers":{"stable_positive":stable,"possible_drag":drag,"rank_vs_score":"Tracker rank is driven by aligned layer and MACD ranking fields, not solely by the multi-factor evidence count. Factor prevalence and outcome differences are shown by rank bucket.","combination_policy":"Only three semantically predefined pairs were checked; no exhaustive search or best-combination selection."},"limitations":["With/without comparisons are observational attribution, not causal estimates.","Factors overlap and their deltas cannot be added together.","Small 2025/2026 with-factor samples remain labeled rather than optimized away.","Historical universe retains the V1 partial delisted and survivorship limitations.","No weights, rankings, signals, production files or Discord behavior are changed."]}
 (out_dir/"factor-attribution-v1.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n");return report
if __name__=="__main__":print(json.dumps(run()["answers"],ensure_ascii=False,indent=2))
