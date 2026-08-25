"""Tracker Backtest V1: research-only, point-in-time long signal replay.

This module imports the current production calculations but never writes to
public Tracker/radar files and never changes production weights or rules.
"""
from __future__ import annotations

import argparse,bisect,json,pathlib,statistics
from collections import defaultdict
from datetime import datetime,timezone

from services.scanner.confluence_rules import breakout_layer as cycle_breakout_layer,combine,ema_layer as cycle_ema_layer,macd_layer as cycle_macd_layer,rsi_layer as cycle_rsi_layer
from services.scanner.detectors import pivots
from services.scanner.macd_factor_backtest import adjusted_rows,completed_groups,daily_pattern_flags,ema,macd_state
from services.scanner.rare_opportunity_scanner import COMPONENTS,recent_bull_cross,score_observation
from services.scanner.resonance_tracker import breakout_state,early_watch_evidence,ema_state,macd,macd_buy_gate,price_structure_state,timeframe_state,volume_state

ROOT=pathlib.Path(__file__).parents[2]
CACHE=ROOT/"work/eodhd-cache"
OUT=ROOT/"research/backtest/output"
HORIZONS=(1,3,5,10,20,40)
BUFFERS=(.01,.02,.03,.05)

def strict_long_trend(rows,i,curve):
 """User-requested default: close > 200DMA and 20-session 200DMA slope > 0."""
 return i>=219 and rows[i]["close"]>curve[i] and curve[i]>curve[i-20]

def _completed(groups,keys,key,limit):
 end=bisect.bisect_left(keys,key)
 return [x[1] for x in groups[max(0,end-limit):end]]

def support_level(rows,i,curves):
 """Highest signal-time support below close; no future bar is inspected."""
 close=rows[i]["close"];levels=[]
 for period in (21,50,200):
  value=curves[period][i]
  if 0<value<close and close/value-1<=.12:levels.append((value,f"EMA{period}"))
 prior=rows[max(0,i-20):i]
 if prior:levels.append((min(x["low"] for x in prior),"prior-20D-low"))
 window=rows[max(0,i-180):i+1];confirmed=pivots(window,len(window)-1)["lows"]
 if confirmed:
  value=confirmed[-1]["price"]
  if value<close:levels.append((value,"confirmed-swing-low"))
 valid=[x for x in levels if x[0]>0]
 return max(valid,key=lambda x:x[0]) if valid else (None,"unavailable")

def _factor_hits(flags):
 return [name for name in COMPONENTS if name=="日线MACD近5日金叉" or flags.get(f"多因子组件＋{name}")]

def _candidate(symbol,listing,rows,i,line,signal,curves,weekly,wkeys,monthly,mkeys):
 if i<260 or i+40>=len(rows):return None
 current=rows[i]
 if current["close"]<5 or current["close"]*current["volume"]<10_000_000:return None
 quick_early=line[i]<signal[i] and line[i]-signal[i]<0 and (line[i]-signal[i])>(line[i-1]-signal[i-1])>=(line[i-2]-signal[i-2])
 recent_cross=recent_bull_cross(line,signal,i)
 if not (quick_early or recent_cross):return None
 day=datetime.strptime(current["date"],"%Y-%m-%d").date();wr=_completed(weekly,wkeys,(day.isocalendar().year,day.isocalendar().week),160);mr=_completed(monthly,mkeys,(day.year,day.month),120)
 if len(wr)<35 or len(mr)<35:return None
 daily=rows[max(0,i-180):i+1];frames={"日线":timeframe_state(daily),"周线":timeframe_state(wr),"月线":timeframe_state(mr)}
 if any(x is None for x in frames.values()):return None
 ema_states={"日线":ema_state(daily),"周线":ema_state(wr),"月线":ema_state(mr)};daily_breakout=breakout_state(daily)
 layers={"macd":cycle_macd_layer(frames),"rsi":cycle_rsi_layer(frames),"ema":cycle_ema_layer(ema_states),"breakout":cycle_breakout_layer(daily_breakout,ema_states)};summary=combine(layers)
 flags=daily_pattern_flags(rows,i,macd_state(wr),curves);hits=_factor_hits(flags) if recent_cross else []
 scored=score_observation(hits);volume=volume_state(daily);structure=price_structure_state(daily);macd_valid,_=macd_buy_gate(frames)
 layer_directions={k:v["direction"] for k,v in layers.items()};buy_layers=sum(x=="buy" for x in layer_directions.values())
 item={"frames":frames,"ema_layer":ema_states["日线"],"price_structure":structure,"volume":volume,"macd_rank_score":layers["macd"].get("rank_score",0),"dollar_volume":current["close"]*current["volume"]}
 early=early_watch_evidence(item);age=frames["日线"].get("bars_since_cross");confirmed=(macd_valid and age is not None and age<=5) or scored["total_score"]>=5
 status="Confirmed" if confirmed else "Early Watch" if early else None
 if not status:return None
 level,source=support_level(rows,i,curves)
 factor_states={name:(name in hits) for name in COMPONENTS};factor_states.update({f"layer.{k}":v["direction"] for k,v in layers.items()})
 return {"ticker":symbol,"listing_status":listing,"date":current["date"],"status":status,"tracker_score":summary["score"],"macd_ranking_score":layers["macd"].get("rank_score",0),"multi_factor_total_score":scored["total_score"],"aligned_long_layers":buy_layers,"factor_states":factor_states,"support_level":round(level,4) if level else None,"support_source":source,"strict_long_trend":strict_long_trend(rows,i,curves[200]),"signal_close":round(current["close"],4),"_i":i,"_rows":rows}

def replay_symbol(path,listing,start):
 rows=adjusted_rows(json.loads(path.read_text()));symbol=path.stem
 if len(rows)<340:return []
 closes=[x["close"] for x in rows];line,signal=macd(closes);curves={p:ema(closes,p) for p in (21,50,200)};weekly=completed_groups(rows,"weekly");monthly=completed_groups(rows,"monthly");wkeys=[x[0] for x in weekly];mkeys=[x[0] for x in monthly];out=[]
 for i in range(260,len(rows)-40):
  if rows[i]["date"]<start:continue
  event=_candidate(symbol,listing,rows,i,line,signal,curves,weekly,wkeys,monthly,mkeys)
  if event:out.append(event)
 return out

def trade_outcomes(event):
 rows=event.pop("_rows");i=event.pop("_i");entry=rows[i+1]["open"];event["entry_date"]=rows[i+1]["date"];event["entry_open"]=round(entry,4)
 event["forward_returns"]={str(h):round(rows[i+h]["close"]/entry-1,6) for h in HORIZONS}
 path=rows[i+1:i+41];event["mfe_40d"]=round(max(x["high"]/entry-1 for x in path),6);event["mae_40d"]=round(min(x["low"]/entry-1 for x in path),6)
 event["stop_scenarios"]={};level=event["support_level"]
 for buffer in BUFFERS:
  key=str(int(buffer*100));stop=level*(1-buffer) if level else None;risk=entry-stop if stop and stop<entry else None;stop_day=None;stop_fill=None;r_results={}
  if risk:
   targets={r:entry+r*risk for r in (1,2,3)};resolved={r:None for r in targets}
   for n,bar in enumerate(path,1):
    if stop_day is None and (bar["open"]<=stop or bar["low"]<=stop):stop_day=n;stop_fill=bar["open"] if bar["open"]<=stop else stop
    for r,target in targets.items():
     if resolved[r] is not None:continue
     if bar["open"]<=stop or (bar["low"]<=stop and bar["high"]>=target) or bar["low"]<=stop:resolved[r]=-1.0
     elif bar["open"]>=target or bar["high"]>=target:resolved[r]=float(r)
   close40=rows[i+40]["close"]
   for r in targets:r_results[str(r)]=round(resolved[r] if resolved[r] is not None else (close40-entry)/risk,4)
  ret20=(stop_fill/entry-1) if stop_day and stop_day<=20 else event["forward_returns"]["20"]
  event["stop_scenarios"][key]={"buffer_pct":int(buffer*100),"stop":round(stop,4) if stop else None,"risk_pct":round(risk/entry,6) if risk else None,"stopped":stop_day is not None,"stop_day":stop_day,"return_20d":round(ret20,6),"r_targets":r_results}
 return event

def _drawdown(values):
 equity=peak=1.;worst=0.
 for value in values:equity*=1+value;peak=max(peak,equity);worst=min(worst,equity/peak-1)
 return worst

def _non_overlapping_cohorts(rows,value,horizon=20):
 by_date=defaultdict(list)
 for row in rows:by_date[row["date"]].append(value(row))
 dates=sorted(by_date)
 return [statistics.mean(by_date[date]) for date in dates[::horizon]]

def stats(rows,horizon=20,buffer="1",use_stop=False):
 value=lambda x:x["stop_scenarios"][buffer]["return_20d"] if use_stop else x["forward_returns"][str(horizon)]
 values=[value(x) for x in rows];wins=[x for x in values if x>0];losses=[x for x in values if x<0];gross_win=sum(wins);gross_loss=abs(sum(losses));cohorts=_non_overlapping_cohorts(rows,value,horizon)
 return {"samples":len(values),"win_rate":round(len(wins)/len(values)*100,2) if values else None,"average_return":round(statistics.mean(values)*100,3) if values else None,"median_return":round(statistics.median(values)*100,3) if values else None,"average_win":round(statistics.mean(wins)*100,3) if wins else None,"average_loss":round(statistics.mean(losses)*100,3) if losses else None,"profit_factor":round(gross_win/gross_loss,3) if gross_loss else None,"expectancy":round(statistics.mean(values)*100,3) if values else None,"stop_out_rate":round(sum(x["stop_scenarios"][buffer]["stopped"] for x in rows)/len(rows)*100,2) if rows else None,"mfe":round(statistics.mean(x["mfe_40d"] for x in rows)*100,3) if rows else None,"mae":round(statistics.mean(x["mae_40d"] for x in rows)*100,3) if rows else None,"max_drawdown":round(_drawdown(cohorts)*100,3) if cohorts else None,"drawdown_basis":f"equal-weight non-overlapping {horizon}D signal-date cohorts"}

def _group(rows,key,buckets):
 out=[]
 for label,test in buckets:
  subset=[x for x in rows if test(x[key])];out.append({"bucket":label,**stats(subset)})
 return out

def curves(rows):
 daily=defaultdict(list)
 for x in rows:daily[x["date"]].append(x["stop_scenarios"]["1"]["return_20d"])
 equity=peak=1.;points=[];items=sorted(daily.items())[::20]
 for date,vals in items:
  equity*=1+statistics.mean(vals);peak=max(peak,equity);points.append({"date":date,"equity":round(equity,4),"drawdown":round(equity/peak-1,4)})
 stride=max(1,len(points)//300);return points[::stride]+([] if not points or points[-1] in points[::stride] else [points[-1]])

def summarize(events,universe,start):
 control=events;trend=[x for x in events if x["strict_long_trend"]];ranking=_group(control,"tracker_ranking",[("1-3",lambda x:x<=3),("4-6",lambda x:4<=x<=6),("7-10",lambda x:7<=x<=10)]);scores=_group(control,"multi_factor_total_score",[("0-2",lambda x:x<=2),("3-4",lambda x:3<=x<=4),("5+",lambda x:x>=5)])
 def monotonic(values,direction):
  means=[x["average_return"] for x in values if x["samples"] and x["average_return"] is not None]
  return len(means)>=3 and (all(a>=b for a,b in zip(means,means[1:])) if direction=="down" else all(a<=b for a,b in zip(means,means[1:])))
 comparisons=[]
 for status in ("Early Watch","Confirmed"):
  comparisons.append({"dimension":"status","group":status,**stats([x for x in control if x["status"]==status])})
 for label,rows in (("Control · no trend filter",control),("Strict long trend",trend)):comparisons.append({"dimension":"trend","group":label,**stats(rows)})
 buffers=[{"buffer_pct":int(b*100),**stats(trend,buffer=str(int(b*100)),use_stop=True)} for b in BUFFERS]
 r_targets=[]
 for r in (1,2,3):
  vals=[x["stop_scenarios"]["1"]["r_targets"].get(str(r)) for x in trend];vals=[x for x in vals if x is not None]
  r_targets.append({"target_r":r,"samples":len(vals),"positive_outcome_rate":round(sum(x>0 for x in vals)/len(vals)*100,2) if vals else None,"target_hit_rate":round(sum(x==r for x in vals)/len(vals)*100,2) if vals else None,"average_r":round(statistics.mean(vals),3) if vals else None,"median_r":round(statistics.median(vals),3) if vals else None})
 overall={str(h):stats(control,h) for h in HORIZONS};trend20=stats(trend);control20=stats(control)
 periods={}
 for label,lo,hi in (("development","0000-01-01","2024-12-31"),("validation_2025","2025-01-01","2025-12-31"),("forward_2026","2026-01-01","9999-12-31")):
  subset=[x for x in control if lo<=x["date"]<=hi];periods[label]={"control":stats(subset),"strict_long_trend":stats([x for x in subset if x["strict_long_trend"]]),"early_watch":stats([x for x in subset if x["status"]=="Early Watch"]),"confirmed":stats([x for x in subset if x["status"]=="Confirmed"])}
 return {"version":"1.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"point_in_time_audit":{"signal_uses_bars_through_signal_date":True,"entry":"next trading day adjusted open","completed_weekly_monthly_only":True,"future_bars_used_for_selection":False,"ambiguous_stop_target":"stop first","trend_rule":"Close > EMA200 and EMA200 today > EMA200 20 sessions ago"},"universe":universe,"sample":{"requested_start":start,"actual_start":min(x["date"] for x in events),"actual_end":max(x["date"] for x in events),"signals":len(events),"control_signals":len(control),"strict_trend_signals":len(trend),"symbols_with_signals":len({x["ticker"] for x in events})},"overall_by_horizon":overall,"periods":periods,"comparisons":comparisons,"ranking_buckets":ranking,"score_buckets":scores,"monotonic":{"ranking_20d":monotonic(ranking,"down"),"score_20d":monotonic(scores,"up")},"stop_buffers":buffers,"r_targets":r_targets,"curves":curves(trend),"historical_signals":sorted(events,key=lambda x:(x["date"],x["tracker_ranking"]),reverse=True)[:300],"answers":{"edge":control20["average_return"] is not None and control20["average_return"]>0 and control20["profit_factor"] is not None and control20["profit_factor"]>1,"win_rate_over_50":control20["win_rate"] is not None and control20["win_rate"]>50,"higher_is_better":monotonic(ranking,"down") and monotonic(scores,"up"),"trend_improved":trend20["average_return"] is not None and control20["average_return"] is not None and trend20["average_return"]>control20["average_return"],"early_vs_confirmed":"calculated in comparisons"},"limitations":["Deterministic survivorship-aware research sample, not a complete historical US universe","Delisted coverage is partial; bankruptcies, mergers and ticker changes may still be missing","Adjusted OHLC is used; historical corporate-action data quality depends on EODHD","Daily bars cannot resolve intraday stop/target order, so ambiguous bars are counted stop-first","Signals overlap; equity and drawdown use non-overlapping equal-weight 20-session signal-date cohorts and are not a capital-constrained portfolio simulation","V1 ranks the long Early Watch/Confirmed selection surface each day, rather than storing every neutral production candidate"]}

def run(start="2010-01-01",out_dir=OUT):
 panel=json.loads((ROOT/"work/eodhd-panel-v4.json").read_text());listing={x["symbol"]:x.get("listing_status","unknown") for x in panel["panel"]};symbols=sorted(set(listing));raw=[]
 for n,symbol in enumerate(symbols,1):
  path=CACHE/f"{symbol}.json"
  if path.exists():raw.extend(replay_symbol(path,listing[symbol],start))
  if n%25==0:print(json.dumps({"progress":n,"symbols":len(symbols),"candidates":len(raw)}),flush=True)
 by_date=defaultdict(list)
 for x in raw:by_date[x["date"]].append(x)
 selected=[]
 for date,rows in sorted(by_date.items()):
  ordered=sorted(rows,key=lambda x:(x["aligned_long_layers"],x["tracker_score"],x["macd_ranking_score"],x["multi_factor_total_score"],x["signal_close"]*x["_rows"][x["_i"]]["volume"],x["ticker"]),reverse=True)[:10]
  for rank,event in enumerate(ordered,1):event["tracker_ranking"]=rank;selected.append(trade_outcomes(event))
 out_dir=pathlib.Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
 universe={"requested_symbols":len(symbols),"loaded_symbols":len({x["ticker"] for x in selected}),"active_symbols":sum(v=="active" for v in listing.values()),"delisted_symbols":sum(v=="delisted" for v in listing.values()),"source":"EODHD deterministic survivorship-aware panel v4"}
 summary=summarize(selected,universe,start);(out_dir/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2));(out_dir/"signals.jsonl").write_text("\n".join(json.dumps(x,ensure_ascii=False,separators=(",",":")) for x in selected)+"\n")
 return summary

def resummarize(out_dir=OUT):
 out_dir=pathlib.Path(out_dir);events=[json.loads(line) for line in (out_dir/"signals.jsonl").read_text().splitlines() if line];previous=json.loads((out_dir/"summary.json").read_text())
 summary=summarize(events,previous["universe"],previous["sample"]["requested_start"]);(out_dir/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2));return summary

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--start",default="2010-01-01");parser.add_argument("--out-dir",default=str(OUT));parser.add_argument("--summary-only",action="store_true");args=parser.parse_args();report=resummarize(args.out_dir) if args.summary_only else run(args.start,args.out_dir);print(json.dumps(report["sample"],indent=2))
