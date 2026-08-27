"""Full-line V1: technical entry, realised P/L, market risk and ETF-theme heat.

Theme ETF price/volume history is tested directly. Current ETF constituents are
never backfilled into earlier dates; stock/theme linkage starts at the first
available membership snapshot and therefore remains forward-only for now.
"""
from __future__ import annotations

import bisect,json,pathlib,statistics
from collections import defaultdict
from datetime import datetime,timezone

from services.scanner.detectors import pivots
from services.scanner.macd_factor_backtest import adjusted_rows,ema,kline_congestion_support,volume_profile_support
from services.scanner.resonance_tracker import macd
from research.backtest.tracker_backtest_v1 import support_level
from research.backtest.tracker_backtest_v2 import metrics,simulate

ROOT=pathlib.Path(__file__).parents[2];CACHE=ROOT/"work/eodhd-cache";OUT=ROOT/"research/backtest/output"
PERIODS=(("development","0000-01-01","2024-12-31"),("validation_2025","2025-01-01","2025-12-31"),("forward_2026","2026-01-01","9999-12-31"))
BUFFERS=(.05,.10);TARGETS=(1.5,2.0);MAG7={"AAPL","MSFT","AMZN","GOOGL","GOOG","META","NVDA","TSLA"}

def relative_volume(rows,i,lookback=20):
 prior=[x["volume"] for x in rows[i-lookback:i] if x["volume"]>0]
 return rows[i]["volume"]/statistics.mean(prior) if len(prior)==lookback else None

def market_state(spy,qqq,date):
 states=[]
 for rows in (spy,qqq):
  dates=[x["date"] for x in rows];i=bisect.bisect_right(dates,date)-1
  if i<220 or dates[i]!=date:return "Unavailable"
  closes=[x["close"] for x in rows[:i+1]];e50=ema(closes,50);e200=ema(closes,200);line,signal=macd(closes)
  strong=closes[-1]>e50[-1]>e200[-1] and e200[-1]>e200[-21] and line[-1]>signal[-1]
  weak=closes[-1]<e200[-1] and e200[-1]<e200[-21]
  states.append("strong" if strong else "weak" if weak else "mixed")
 return "Risk-On" if states==["strong","strong"] else "Risk-Off" if "weak" in states else "Neutral"

def market_states(spy,qqq):
 arrays=[]
 for rows in (spy,qqq):
  closes=[x["close"] for x in rows];e50=ema(closes,50);e200=ema(closes,200);line,signal=macd(closes);state={}
  for i in range(220,len(rows)):
   strong=closes[i]>e50[i]>e200[i] and e200[i]>e200[i-20] and line[i]>signal[i]
   weak=closes[i]<e200[i] and e200[i]<e200[i-20]
   state[rows[i]["date"]]="strong" if strong else "weak" if weak else "mixed"
  arrays.append(state)
 dates=set(arrays[0])&set(arrays[1]);return {date:"Risk-On" if [arrays[0][date],arrays[1][date]]==["strong","strong"] else "Risk-Off" if "weak" in (arrays[0][date],arrays[1][date]) else "Neutral" for date in dates}

def technical_events(symbol,rows,market):
 if len(rows)<340:return []
 closes=[x["close"] for x in rows];line,signal=macd(closes);curves={p:ema(closes,p) for p in (21,50,200)};out=[]
 for i in range(260,len(rows)-40):
  cross=line[i]>signal[i] and line[i-1]<=signal[i-1]
  trend=closes[i]>curves[200][i] and curves[200][i]>curves[200][i-20]
  dollar=closes[i]*rows[i]["volume"]
  if not cross or not trend or closes[i]<5 or dollar<10_000_000:continue
  level,source=support_level(rows,i,curves)
  if not level or level>=rows[i+1]["open"]:continue
  vp=volume_profile_support(rows,i);congestion=kline_congestion_support(rows,i);rv=relative_volume(rows,i)
  confirmed=pivots(rows[max(0,i-180):i+1],min(180,i))["lows"]
  higher_low=len(confirmed)>=2 and confirmed[-1]["price"]>confirmed[-2]["price"]
  out.append({"ticker":symbol,"date":rows[i]["date"],"entry_date":rows[i+1]["date"],"entry":rows[i+1]["open"],"support":level,"support_source":source,"dollar_volume":dollar,"relative_volume":rv,"volume_profile_support":vp,"kline_congestion_support":congestion,"chip_support":vp or congestion,"higher_low":higher_low,"mag7":symbol in MAG7,"market_regime":market.get(rows[i]["date"],"Unavailable"),"_path":rows[i+1:i+41]})
 return out

def assign_heat_buckets(events):
 by_date=defaultdict(list)
 for event in events:by_date[event["date"]].append(event)
 for rows in by_date.values():
  ordered=sorted(rows,key=lambda x:x["dollar_volume"],reverse=True);n=len(ordered)
  for rank,event in enumerate(ordered,1):
   event["daily_volume_rank"]=rank;event["daily_volume_percentile"]=1-(rank-1)/n
   event["liquidity_bucket"]="Top 10%" if rank<=max(1,n//10) else "Top 25%" if rank<=max(1,n//4) else "Other"
 return events

def stock_trades(events):
 trades=[]
 for event in events:
  for buffer in BUFFERS:
   stop=event["support"]*(1-buffer);risk=event["entry"]-stop
   if stop<=0 or risk/event["entry"]<=.001 or risk/event["entry"]>.35:continue
   for target_r in TARGETS:
    fill,bars,reason,mfe,mae=simulate(event["entry"],stop,event["entry"]+target_r*risk,event["_path"])
    trades.append({k:v for k,v in event.items() if k!="_path"}|{"stop_buffer":int(buffer*100),"target_r":target_r,"return":fill/event["entry"]-1,"r":(fill-event["entry"])/risk,"reason":reason,"bars":bars,"mfe":mfe,"mae":mae,"risk_pct":risk/event["entry"]})
 return trades

def theme_funds():
 registry=json.loads((ROOT/"data/themes/theme-registry.json").read_text());out={}
 for item in registry["themes"]:
  source=item.get("membership_source") or {};fund=source.get("fund")
  if fund:out[item["theme_id"]]=(item["name"],fund)
 return out

def etf_hotspot_trades(spy):
 spy_by={x["date"]:i for i,x in enumerate(spy)};out=[];coverage=[]
 for theme,(name,fund) in theme_funds().items():
  path=CACHE/f"{fund}.json"
  if not path.exists():coverage.append({"theme":theme,"fund":fund,"available":False});continue
  rows=adjusted_rows(json.loads(path.read_text()));coverage.append({"theme":theme,"fund":fund,"available":len(rows)>=260})
  if len(rows)<260:continue
  closes=[x["close"] for x in rows];e20=ema(closes,20);e50=ema(closes,50);e200=ema(closes,200)
  for i in range(220,len(rows)-40):
   si=spy_by.get(rows[i]["date"])
   if si is None or si<20:continue
   rv=relative_volume(rows,i);rs20=closes[i]/closes[i-20]-spy[si]["close"]/spy[si-20]["close"]
   hot=closes[i]>e20[i]>e50[i]>e200[i] and e200[i]>e200[i-20] and rv is not None and rv>=1.5 and rs20>0
   if not hot:continue
   # One event per 10 sessions per fund prevents a volume cluster becoming ten pseudo-independent signals.
   if out and any(x["fund"]==fund and 0<i-x["index"]<10 for x in out[-30:]):continue
   entry=rows[i+1]["open"];stop=e50[i]*.95;risk=entry-stop
   if stop<=0 or risk<=0 or risk/entry>.30:continue
   fill,bars,reason,mfe,mae=simulate(entry,stop,entry+2*risk,rows[i+1:i+41])
   out.append({"theme":theme,"theme_name":name,"fund":fund,"date":rows[i]["date"],"index":i,"relative_volume":rv,"relative_strength_20d":rs20,"return":fill/entry-1,"r":(fill-entry)/risk,"reason":reason,"bars":bars,"mfe":mfe,"mae":mae,"risk_pct":risk/entry})
 return out,coverage

def grouped(trades,predicate=lambda x:True):
 rows=[x for x in trades if predicate(x)];result=metrics(rows)
 if rows:
  values=sorted(x["return"] for x in rows);trim=max(1,len(values)//100);trimmed=values[trim:-trim] if len(values)>2*trim else values
  result.update({"median_return_pct":round(statistics.median(values)*100,3),"trimmed_expectancy_pct":round(statistics.mean(trimmed)*100,3),"median_mfe_pct":round(statistics.median(x["mfe"] for x in rows)*100,3),"extreme_mfe_count":sum(x["mfe"]>2 for x in rows)})
 return result

def split_metrics(trades,predicate=lambda x:True):
 return {name:grouped(trades,lambda x,p=predicate,lo=lo,hi=hi:p(x) and lo<=x["date"]<=hi) for name,lo,hi in PERIODS}

def run(out=OUT/"full-line-v1.json"):
 spy=adjusted_rows(json.loads((CACHE/"SPY.json").read_text()));qqq=adjusted_rows(json.loads((CACHE/"QQQ.json").read_text()));market=market_states(spy,qqq);excluded={"SPY","QQQ",*(fund for _,fund in theme_funds().values())}
 events=[];files=sorted(CACHE.glob("*.json"))
 for n,path in enumerate(files,1):
  if path.stem not in excluded:
   try:events.extend(technical_events(path.stem,adjusted_rows(json.loads(path.read_text())),market))
   except (KeyError,ValueError,ZeroDivisionError):pass
  if n%100==0:print(json.dumps({"files":n,"events":len(events)}),flush=True)
 assign_heat_buckets(events);trades=stock_trades(events);etf_trades,etf_coverage=etf_hotspot_trades(spy)
 combos=[]
 for buffer in (5,10):
  for target in TARGETS:
   base=lambda x,b=buffer,t=target:x["stop_buffer"]==b and x["target_r"]==t
   combos.append({"stop_buffer_pct":buffer,"target_r":target,"all":grouped(trades,base),"periods":split_metrics(trades,base),"market":{state:grouped(trades,lambda x,s=state,p=base:p(x) and x["market_regime"]==s) for state in ("Risk-On","Neutral","Risk-Off")},"liquidity":{bucket:grouped(trades,lambda x,b=bucket,p=base:p(x) and x["liquidity_bucket"]==b) for bucket in ("Top 10%","Top 25%","Other")},"relative_volume":{label:grouped(trades,lambda x,v=value,p=base:p(x) and x["relative_volume"] is not None and x["relative_volume"]>=v) for label,value in ((">=1.2x",1.2),(">=1.5x",1.5),(">=2.0x",2.0))},"mag7":grouped(trades,lambda x,p=base:p(x) and x["mag7"]),"chip_support":grouped(trades,lambda x,p=base:p(x) and x["chip_support"])})
 report={"version":"full-line-backtest-v1.0.1","generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"rules":{"stock_signal":"strict rising EMA200 trend + completed daily MACD bullish cross + price/dollar-volume eligibility","entry":"next adjusted open","stops":"signal-time structural support minus 5% or 10%","targets":"1.5R or 2R; unresolved exits at 40th close","ambiguity":"stop first","heat":"absolute dollar volume, same-day signal percentile, and current/prior-20D relative volume","market":"SPY and QQQ point-in-time trend plus MACD; Risk-On only when both are strong","industry_hotspot":"theme ETF close>EMA20>EMA50>EMA200, rising EMA200, relative volume>=1.5 and 20D return beats SPY"},"audit":{"cache_files":len(files),"stock_events":len(events),"stock_trades":len(trades),"future_rows_for_selection":False,"current_theme_membership_backfilled":False,"stock_industry_linkage":"forward-only from 2026-08-26; insufficient completed horizon in this report","same_bar_stop_target":"stop first","robust_statistics":"median and symmetric 1% trimmed expectancy reported beside raw means"},"stock_combinations":combos,"industry_etf_hotspots":{"coverage":etf_coverage,"overall":grouped(etf_trades),"periods":split_metrics(etf_trades),"by_theme":{theme:grouped(etf_trades,lambda x,t=theme:x["theme"]==t) for theme in sorted({x["theme"] for x in etf_trades})},"events":len(etf_trades)},"limitations":["Theme ETF price-volume hotspot history is valid, but current ETF constituent membership is not backfilled into older stock dates.","Daily bars use stop-first for ambiguous stop/target touches.","Signals overlap and metrics are research diagnostics, not a capital-constrained portfolio.","Historical cache has partial delisted coverage and is not the complete US market.","Raw MFE can contain corporate-action anomalies; decisions must use realised, median and 1% trimmed returns rather than raw mean MFE.","Dollar-volume priority tests attention/ranking, not causality or fund flow."]}
 out=pathlib.Path(out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n");return report

if __name__=="__main__":
 report=run();print(json.dumps({"audit":report["audit"],"industry":report["industry_etf_hotspots"]["overall"]},ensure_ascii=False,indent=2))
