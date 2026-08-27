"""V2 pullback-context study for market regimes and industry ETF proxies."""
from __future__ import annotations
import json,pathlib
from collections import defaultdict
from datetime import datetime,timezone

from services.scanner.macd_factor_backtest import adjusted_rows,ema
from services.scanner.resonance_tracker import macd
from research.backtest.full_line_backtest_v1 import (CACHE,OUT,assign_heat_buckets,grouped,
 relative_volume,split_metrics,stock_trades,technical_events,theme_funds)
from research.backtest.tracker_backtest_v2 import simulate

ROOT=pathlib.Path(__file__).parents[2]

def context_states(spy,qqq):
 per_benchmark=[]
 for rows in (spy,qqq):
  closes=[x["close"] for x in rows];e20=ema(closes,20);e50=ema(closes,50);e200=ema(closes,200);line,signal=macd(closes);hist=[a-b for a,b in zip(line,signal)];states={}
  for i in range(220,len(rows)):
   close=closes[i];prior_high=max(closes[i-60:i]);drawdown=1-close/prior_high
   long_trend=close>e200[i] and e200[i]>e200[i-20]
   near_support=any(abs(close/value-1)<=.03 for value in (e20[i],e50[i]) if value)
   pullback=long_trend and .03<=drawdown<=.12 and near_support
   improving=hist[i]>hist[i-1]>=hist[i-2]
   states[rows[i]["date"]]={"long_trend":long_trend,"pullback":pullback,"macd_improving":improving,"drawdown":drawdown}
  per_benchmark.append(states)
 out={}
 for date in set(per_benchmark[0])&set(per_benchmark[1]):
  a,b=per_benchmark[0][date],per_benchmark[1][date];both_long=a["long_trend"] and b["long_trend"]
  if both_long and (a["pullback"] or b["pullback"]) and (a["macd_improving"] or b["macd_improving"]):state="Pullback + MACD Repair"
  elif both_long and (a["pullback"] or b["pullback"]):state="Pullback At Support"
  elif both_long:state="Uptrend No Pullback"
  else:state="Weak Or Mixed"
  out[date]={"state":state,"spy":a,"qqq":b}
 return out

def stock_context_trades(spy,qqq):
 contexts=context_states(spy,qqq);excluded={"SPY","QQQ",*(fund for _,fund in theme_funds().values())};events=[]
 # Technical selection remains unchanged; market context is attached afterward.
 neutral_market={date:"Neutral" for date in contexts}
 for n,path in enumerate(sorted(CACHE.glob("*.json")),1):
  if path.stem not in excluded:
   try:events.extend(technical_events(path.stem,adjusted_rows(json.loads(path.read_text())),neutral_market))
   except (KeyError,ValueError,ZeroDivisionError):pass
  if n%100==0:print(json.dumps({"stock_files":n,"events":len(events)}),flush=True)
 assign_heat_buckets(events);trades=stock_trades(events)
 # Fixed before this experiment: prior V2 production-style benchmark, support -5%, 2R.
 return [{**x,"context":contexts[x["date"]]["state"]} for x in trades if x["stop_buffer"]==5 and x["target_r"]==2 and x["date"] in contexts]

def etf_pullback_events(spy):
 spy_dates={x["date"] for x in spy};trades=[];coverage=[]
 for theme,(name,fund) in theme_funds().items():
  path=CACHE/f"{fund}.json"
  if not path.exists():coverage.append({"theme":theme,"fund":fund,"available":False});continue
  rows=adjusted_rows(json.loads(path.read_text()));coverage.append({"theme":theme,"fund":fund,"available":len(rows)>=260})
  if len(rows)<260:continue
  closes=[x["close"] for x in rows];e20=ema(closes,20);e50=ema(closes,50);e200=ema(closes,200);line,signal=macd(closes);hist=[a-b for a,b in zip(line,signal)];last_by_variant={}
  for i in range(220,len(rows)-40):
   if rows[i]["date"] not in spy_dates:continue
   close=closes[i];drawdown=1-close/max(closes[i-60:i]);long_trend=close>e200[i] and e200[i]>e200[i-20]
   supports=[x for x in (e20[i],e50[i],e200[i]) if x and abs(close/x-1)<=.03]
   base=long_trend and .05<=drawdown<=.20 and bool(supports)
   improving=hist[i]>hist[i-1]>=hist[i-2];rv=relative_volume(rows,i);volume_recovery=rv is not None and rv>=1.2
   variants={"Pullback At Support":base,"Pullback + MACD Repair":base and improving,"Pullback + MACD + Volume Recovery":base and improving and volume_recovery}
   for variant,hit in variants.items():
    if not hit or i-last_by_variant.get(variant,-999)<10:continue
    support=max(x for x in supports if x<close*1.03);entry=rows[i+1]["open"];stop=support*.95;risk=entry-stop
    if stop<=0 or risk<=0 or risk/entry>.30:continue
    fill,bars,reason,mfe,mae=simulate(entry,stop,entry+2*risk,rows[i+1:i+41]);last_by_variant[variant]=i
    trades.append({"theme":theme,"theme_name":name,"fund":fund,"variant":variant,"date":rows[i]["date"],"drawdown":drawdown,"relative_volume":rv,"return":fill/entry-1,"r":(fill-entry)/risk,"reason":reason,"bars":bars,"mfe":mfe,"mae":mae,"risk_pct":risk/entry})
 return trades,coverage

def run(out=OUT/"pullback-context-v2.json"):
 spy=adjusted_rows(json.loads((CACHE/"SPY.json").read_text()));qqq=adjusted_rows(json.loads((CACHE/"QQQ.json").read_text()));stock=stock_context_trades(spy,qqq);etf,coverage=etf_pullback_events(spy)
 contexts=("Pullback + MACD Repair","Pullback At Support","Uptrend No Pullback","Weak Or Mixed");variants=("Pullback At Support","Pullback + MACD Repair","Pullback + MACD + Volume Recovery")
 report={"version":"pullback-context-backtest-v2.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"hypothesis":"Adding exposure on a still-intact market or industry pullback is more useful than adding after a volume breakout.","rules":{"stock_trade":"unchanged strict trend + daily MACD cross; next Open; structural support -5%; 2R; 40 sessions; stop first","market_pullback":"SPY and QQQ long trends intact; either index 3%-12% below prior 60D high and within 3% of EMA20/50","industry_pullback":"ETF long trend intact; 5%-20% below prior 60D high and within 3% of EMA20/50/200","repair":"MACD histogram rises for two completed sessions","volume_recovery":"current ETF volume / prior 20D average >=1.2"},"audit":{"stock_trades":len(stock),"industry_trades":len(etf),"future_rows_for_selection":False,"current_membership_backfilled":False,"same_bar_stop_target":"stop first"},"stock_by_market_context":{x:{"overall":grouped(stock,lambda row,s=x:row["context"]==s),"periods":split_metrics(stock,lambda row,s=x:row["context"]==s)} for x in contexts},"industry_pullback":{"coverage":coverage,"variants":{x:{"overall":grouped(etf,lambda row,v=x:row["variant"]==v),"periods":split_metrics(etf,lambda row,v=x:row["variant"]==v)} for x in variants},"by_theme":{theme:{x:grouped(etf,lambda row,t=theme,v=x:row["theme"]==t and row["variant"]==v) for x in variants} for theme in sorted({x["theme"] for x in etf})}},"comparison_reference":{"v1_hotspot_rule":"ETF stacked uptrend + relative volume >=1.5 + 20D relative strength > SPY","v1_report":"research/backtest/output/full-line-v1.json"},"limitations":["Historical stock-theme membership remains unavailable, so industry testing trades the ETF proxy itself.","Signals overlap; results are not a capital-constrained portfolio.","Recent per-theme samples can be small.","Fees and quote-level slippage are excluded."]}
 out=pathlib.Path(out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n");return report

if __name__=="__main__":
 r=run();print(json.dumps(r["audit"],indent=2))
