"""Selection Research V1: Leadership vs Strong-Trend Pullback, research only."""
from __future__ import annotations
import json,pathlib,statistics
from datetime import datetime,timezone
from services.scanner.macd_factor_backtest import adjusted_rows,ema
from services.scanner.resonance_tracker import macd
from research.backtest.tracker_backtest_v2 import simulate,metrics

ROOT=pathlib.Path(__file__).parents[2];CACHE=ROOT/"work/eodhd-cache";OUT=ROOT/"research/backtest/output"
PERIODS=(("development","0000","2024-12-31"),("validation_2025","2025-01-01","2025-12-31"),("forward_2026","2026-01-01","9999"))

def _return(rows,i,n):return rows[i]["close"]/rows[i-n]["close"]-1
def _rs(rows,i,spy,si,n):return _return(rows,i,n)-_return(spy,si,n)

def features(rows,i,spy,si,event):
 close=rows[i]["close"];closes=[x["close"] for x in rows[:i+1]];e200=ema(closes,200);e50=ema(closes,50);line,signal=macd(closes);hist=[a-b for a,b in zip(line,signal)]
 year=rows[i-251:i+1];low=min(x["low"] for x in year);high=max(x["high"] for x in year);position=(close-low)/(high-low) if high>low else .5
 avg_volume=statistics.mean(x["volume"] for x in rows[i-20:i]);relative_volume=rows[i]["volume"]/avg_volume if avg_volume else 0
 ret10=_return(rows,i,10);ret20=_return(rows,i,20);ret126=_return(rows,i,126);ret252=_return(rows,i,252)
 drawdown=close/max(x["high"] for x in rows[i-59:i+1])-1;support=event.get("support_level");near_support=bool(support and abs(close/support-1)<=.05) or abs(close/e50[-1]-1)<=.03 or abs(close/e200[-1]-1)<=.03
 down_now=[x["volume"] for j,x in enumerate(rows[i-4:i+1],i-4) if x["close"]<x["open"]];down_prior=[x["volume"] for j,x in enumerate(rows[i-14:i-4],i-14) if x["close"]<x["open"]]
 selling_volume_decay=bool(down_now and down_prior and statistics.mean(down_now)<statistics.mean(down_prior));contraction=hist[-1]<0 and hist[-1]>hist[-2]>=hist[-3]
 leadership=close>e200[-1] and e200[-1]>e200[-21] and _rs(rows,i,spy,si,60)>0 and _rs(rows,i,spy,si,20)>0 and position>=.70 and relative_volume>=1.20
 pullback=e200[-1]>e200[-21] and _rs(rows,i,spy,si,126)>0 and _rs(rows,i,spy,si,252)>0 and ret20<ret126/6-.05 and ret10<0 and drawdown<=-.10 and close>e200[-1] and near_support
 return {"leadership":leadership,"pullback":pullback,"rs_20_spy":_rs(rows,i,spy,si,20),"rs_60_spy":_rs(rows,i,spy,si,60),"rs_126_spy":_rs(rows,i,spy,si,126),"rs_252_spy":_rs(rows,i,spy,si,252),"year_position":position,"relative_volume":relative_volume,"return_10d":ret10,"return_20d":ret20,"drawdown_60d":drawdown,"near_support":near_support,"histogram_contraction":contraction,"selling_volume_decay":selling_volume_decay,"industry_relative_strength":None}

def trade(event,rows,i):
 entry=event["entry_open"];stop=event["support_level"]*.95;risk=entry-stop
 if risk/entry<=.001:return None
 fill,bars,reason,mfe,mae=simulate(entry,stop,entry+2*risk,rows[i+1:i+41])
 return {"ticker":event["ticker"],"date":event["date"],"status":event["status"],"return":fill/entry-1,"r":(fill-entry)/risk,"reason":reason,"bars":bars,"mfe":mfe,"mae":mae,"risk_pct":risk/entry}

def compact(rows):
 m=metrics(rows);return {k:m.get(k) for k in ("samples","win_rate","profit_factor","expectancy_pct","average_r","stop_out_rate","max_drawdown_pct","average_holding_bars")}

def group(rows,key):
 selected=[x for x in rows if x[key]]
 return {"overall":compact(selected),"periods":{p:compact([x for x in selected if a<=x["date"]<=b]) for p,a,b in PERIODS},"diagnostics":{"histogram_contraction_pct":round(sum(x["histogram_contraction"] for x in selected)/len(selected)*100,2) if selected else None,"selling_volume_decay_pct":round(sum(x["selling_volume_decay"] for x in selected)/len(selected)*100,2) if selected else None,"average_drawdown_60d_pct":round(statistics.mean(x["drawdown_60d"] for x in selected)*100,2) if selected else None,"average_rs_126_spy_pct":round(statistics.mean(x["rs_126_spy"] for x in selected)*100,2) if selected else None}}

def run(out_dir=OUT):
 out_dir=pathlib.Path(out_dir);events=[json.loads(x) for x in (out_dir/"signals.jsonl").read_text().splitlines() if x];spy=adjusted_rows(json.loads((CACHE/"SPY.json").read_text()));spy_index={x["date"]:i for i,x in enumerate(spy)};spy200=ema([x["close"] for x in spy],200)
 cache={};indices={};rows_out=[]
 for e in events:
  if not e["strict_long_trend"] or not e.get("support_level") or e["date"] not in spy_index:continue
  t=e["ticker"]
  if t not in cache:
   cache[t]=adjusted_rows(json.loads((CACHE/f"{t}.json").read_text()));indices[t]={x["date"]:i for i,x in enumerate(cache[t])}
  rows=cache[t];i=indices[t].get(e["date"]);si=spy_index[e["date"]]
  if i is None or i<252 or si<252:continue
  outcome=trade(e,rows,i)
  if not outcome:continue
  f=features(rows,i,spy,si,e);rows_out.append({**outcome,**f,"spy_long_trend":spy[si]["close"]>spy200[si] and spy200[si]>spy200[si-20]})
 benchmark=[x for x in rows_out if x["status"]=="Confirmed"];early=[x for x in rows_out if x["status"]=="Early Watch"];lead=group(benchmark,"leadership");pull=group(benchmark,"pullback")
 overlap=[x for x in benchmark if x["leadership"] and x["pullback"]];lead_rows=[x for x in benchmark if x["leadership"]]
 market_split={"spy_long_trend":compact([x for x in lead_rows if x["spy_long_trend"]]),"spy_not_long_trend":compact([x for x in lead_rows if not x["spy_long_trend"]])}
 report={"version":"1.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"benchmark":{"definition":"Confirmed + long-term trend + next adjusted Open + Support −5% + 2R TP","metrics":compact(benchmark)},"rules":{"leadership":["Price > existing 200-day trend curve and positive 20-session slope","60D and 20D stock return minus SPY return > 0","Position in trailing 252-session high-low range >= 70%","Current volume / prior 20-session average volume >= 1.20"],"pullback":["Positive 200-day trend slope and Price > 200-day curve","126D and 252D relative return vs SPY > 0","10D return < 0 and 20D return at least 5 percentage points below 126D return / 6","Drawdown from trailing 60D high >= 10%","Within 5% of signal-time Support or within 3% of EMA50/EMA200"],"industry_relative_strength":"unavailable: no reliable point-in-time historical industry classification in V1 inputs"},"leadership":lead,"strong_trend_pullback":pull,"early_watch":{"all":compact(early),"leadership":compact([x for x in early if x["leadership"]]),"strong_trend_pullback":compact([x for x in early if x["pullback"]])},"overlap":{"samples":len(overlap),"leadership_overlap_pct":round(len(overlap)/lead["overall"]["samples"]*100,2) if lead["overall"]["samples"] else None,"pullback_overlap_pct":round(len(overlap)/pull["overall"]["samples"]*100,2) if pull["overall"]["samples"] else None,"explanation":"Overlap requires long-term relative strength plus a still-high 252D range position, while the stock is simultaneously in a >=10% short-term pullback near support."},"leadership_market_context":market_split,"audit":{"signals_reused":True,"point_in_time_features":True,"future_rows_for_selection":False,"entry_stop_tp_unchanged":True,"threshold_optimization":False,"industry_data_fabricated":False,"production_outputs_written":False},"limitations":["The 200-day curve follows the existing V1 EMA implementation despite the UI shorthand DMA.","Industry Relative Strength is omitted rather than backfilled from current classifications.","With-group comparisons are observational and signals overlap.","Historical universe retains V1 survivorship and partial delisted coverage limitations.","No production scanner, Ranking, factor weight, Discord or automation is changed."]}
 (out_dir/"selection-research-v1.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n");return report
if __name__=="__main__":
 r=run();print(json.dumps({"benchmark":r["benchmark"]["metrics"],"leadership":r["leadership"]["overall"],"pullback":r["strong_trend_pullback"]["overall"],"overlap":r["overlap"]},indent=2))
