"""Point-in-time MACD event study using next-open execution.

Daily crosses are the event. Weekly and monthly states use only periods that
were completed before the event date, preventing higher-timeframe lookahead.
"""
import json,pathlib,statistics
from collections import defaultdict
from datetime import datetime
from .detectors import detect_bos,detect_w_bottom,load_config,pivots
from .resonance_tracker import bullish_divergence,macd
from .technical import atr,rsi

HORIZONS=(5,10,20,40,60,100)
SPLITS={"development":("0000-01-01","2024-12-31"),"validation":("2025-01-01","2025-12-31"),"forward":("2026-01-01","9999-12-31")}
REGIME_LABELS={"both_bull":"SPY与QQQ均在EMA200上","mixed":"SPY与QQQ方向不一致","both_bear":"SPY与QQQ均在EMA200下"}
PATTERN_FACTORS=("长期趋势合格＋日线金叉＋底部Doji","长期趋势合格＋日线金叉＋底部Bullish Engulfing","长期趋势合格＋日线金叉＋双底突破","长期趋势合格＋日线金叉＋趋势线三推突破","长期趋势合格＋日线金叉＋RSI底背离")
TECHNICAL_CONFIG=load_config()

def adjusted_rows(raw):
 out=[]
 for x in raw:
  if not x.get("close") or not x.get("adjusted_close") or not x.get("open"):continue
  ratio=x["adjusted_close"]/x["close"]
  out.append({"date":x["date"],"open":x["open"]*ratio,"high":x["high"]*ratio,"low":x["low"]*ratio,"close":x["adjusted_close"],"volume":int(x.get("volume") or 0)})
 return sorted(out,key=lambda x:x["date"])

def listing_statuses():
 """Recover listing status from the survivorship-aware panel without guessing from future price action."""
 path=pathlib.Path("work/eodhd-panel-v4.json");out={}
 if path.exists():
  for row in json.loads(path.read_text()).get("panel",[]):out[row["symbol"]]=row.get("listing_status","unknown")
 return out

def completed_groups(rows,period):
 groups=[]
 for row in rows:
  d=datetime.strptime(row["date"],"%Y-%m-%d").date();key=(d.isocalendar().year,d.isocalendar().week) if period=="weekly" else (d.year,d.month)
  if not groups or groups[-1][0]!=key:groups.append([key,{**row}])
  else:
   bar=groups[-1][1];bar["high"]=max(bar["high"],row["high"]);bar["low"]=min(bar["low"],row["low"]);bar["close"]=row["close"];bar["volume"]+=row["volume"];bar["date"]=row["date"]
 return groups

def ema(values,period=200):
 alpha=2/(period+1);out=[]
 for value in values:out.append(value if not out else alpha*value+(1-alpha)*out[-1])
 return out

def market_regimes(cache):
 states={};benchmarks={}
 for symbol in ("SPY","QQQ"):
  rows=adjusted_rows(json.loads((cache/f"{symbol}.json").read_text()));curve=ema([x["close"] for x in rows])
  benchmarks[symbol]={x["date"]:x for x in rows}
  states[symbol]={x["date"]:x["close"]>curve[i] for i,x in enumerate(rows) if i>=199}
 dates=set(states["SPY"])&set(states["QQQ"]);out={}
 for date in dates:
  pair=(states["SPY"][date],states["QQQ"][date]);out[date]="both_bull" if pair==(True,True) else "both_bear" if pair==(False,False) else "mixed"
 return out,benchmarks

def available(groups,key):
 return [bar for group_key,bar in groups if group_key<key]

def macd_state(rows):
 closes=[x["close"] for x in rows];line,signal=macd(closes);hist=[a-b for a,b in zip(line,signal)];i=len(rows)-1
 rising=hist[i]>hist[i-1] and hist[i-1]>=hist[i-2];falling=hist[i]<hist[i-1] and hist[i-1]<=hist[i-2]
 zone="零轴下" if line[i]<0 and signal[i]<0 else "零轴上" if line[i]>0 and signal[i]>0 else "穿越零轴"
 cross=line[i]>signal[i] and line[i-1]<=signal[i-1];dead=line[i]<signal[i] and line[i-1]>=signal[i-1]
 cross_zone="零轴下" if cross and line[i]<0 and signal[i]<0 else "零轴上" if cross and line[i]>0 and signal[i]>0 else "穿越零轴" if cross else None
 dead_zone="零轴下" if dead and line[i]<0 and signal[i]<0 else "零轴上" if dead and line[i]>0 and signal[i]>0 else "穿越零轴" if dead else None
 scale=statistics.pstdev(hist[-20:]) or 1;near=line[i]<=signal[i] and rising and abs(hist[i])<=scale*.35
 return {"macd_line":line[i],"signal_line":signal[i],"zero_zone":zone,"cross_zero_zone":cross_zone,"dead_cross_zero_zone":dead_zone,"histogram_rising":rising,"histogram_falling":falling,"negative_histogram_shrinking":hist[i]<0 and rising,"near_cross":near}

def three_push_breakout(rows,end):
 """Three confirmed descending swing-high attempts followed by a solid close above their trendline."""
 start=max(0,end-120);window=rows[start:end+1];local_end=len(window)-1
 points=pivots(window,local_end,TECHNICAL_CONFIG)["highs"]
 if len(points)<3:return False
 a,b,c=points[-3:]
 if not (a["price"]>b["price"]>c["price"]):return False
 slope=(c["price"]-a["price"])/(c["index"]-a["index"]);projected=c["price"]+slope*(local_end-c["index"]);volatility=atr(window)[local_end]
 touches=all(abs(p["price"]-(a["price"]+slope*(p["index"]-a["index"])))<=TECHNICAL_CONFIG["level_test"]["proximity_atr"]*volatility for p in (a,b,c))
 separated=b["index"]-a["index"]>TECHNICAL_CONFIG["level_test"]["rejection_cluster_bars"] and c["index"]-b["index"]>TECHNICAL_CONFIG["level_test"]["rejection_cluster_bars"]
 return touches and separated and detect_bos(window,local_end,projected,TECHNICAL_CONFIG).detected

def daily_pattern_flags(rows,end):
 """Price/RSI confirmations visible at the daily MACD-cross close."""
 start=max(0,end-180);window=rows[start:end+1];w=detect_w_bottom(window,len(window)-1,TECHNICAL_CONFIG)
 double_bottom=w.detected and detect_bos(window,len(window)-1,w.levels["neckline"],TECHNICAL_CONFIG).detected
 values=rsi([x["close"] for x in window])
 closes=[x["close"] for x in rows[:end+1]];long_average=ema(closes,200);trend_ok=end>=260 and closes[end]>=long_average[end]*.90 and long_average[end]>=long_average[end-60]*.97
 recent=rows[max(1,end-4):end+1];range60=rows[max(0,end-59):end+1];low60=min(x["low"] for x in range60);high60=max(x["high"] for x in range60);bottom_limit=low60+(high60-low60)*.30
 bottom_doji=any(max(x["open"],x["close"])<=bottom_limit and abs(x["close"]-x["open"])/max(x["high"]-x["low"],1e-9)<=TECHNICAL_CONFIG["retest"]["doji_body_fraction"] for x in recent)
 bottom_engulf=False
 for j in range(max(1,end-4),end+1):
  x,prior=rows[j],rows[j-1];bullish=x["close"]>x["open"] and prior["close"]<prior["open"] and x["open"]<=prior["close"] and x["close"]>=prior["open"]
  if bullish and max(x["open"],x["close"])<=bottom_limit:bottom_engulf=True
 return {"日线金叉":True,"长期趋势合格＋日线金叉":trend_ok,"长期趋势合格＋日线金叉＋底部Doji":trend_ok and bottom_doji,"长期趋势合格＋日线金叉＋底部Bullish Engulfing":trend_ok and bottom_engulf,"长期趋势合格＋日线金叉＋双底突破":trend_ok and double_bottom,"长期趋势合格＋日线金叉＋趋势线三推突破":trend_ok and three_push_breakout(rows,end),"长期趋势合格＋日线金叉＋RSI底背离":trend_ok and bullish_divergence(window,values)}

def features(side,d,w,m):
 bullish=lambda x:x["macd_line"]>x["signal_line"]
 below=lambda x:x["zero_zone"]=="零轴下"
 above=lambda x:x["zero_zone"]=="零轴上"
 if side=="buy":
  flags={"日线零轴下金叉":d["cross_zero_zone"]=="零轴下","日线金叉＋周线MACD多头":bullish(w),"日线金叉＋周线零轴下多头":bullish(w) and below(w),"日线金叉＋月线MACD多头":bullish(m),"日线金叉＋月线零轴下改善":below(m) and (m["negative_histogram_shrinking"] or m["near_cross"]),"日线金叉＋周月同时支持":bullish(w) and (bullish(m) or (below(m) and m["histogram_rising"]))}
  base=flags["日线零轴下金叉"]
  flags.update({"基准＋周线能量改善":base and w["histogram_rising"],"基准＋周线准备金叉":base and w["near_cross"],"基准＋周线已经多头":base and bullish(w),"基准＋月线能量改善":base and m["histogram_rising"],"基准＋月线准备金叉":base and m["near_cross"],"基准＋月线已经多头":base and bullish(m)})
 else:
  flags={"日线零轴上死叉":d["dead_cross_zero_zone"]=="零轴上","日线死叉＋周线MACD空头":not bullish(w),"日线死叉＋周线零轴上空头":not bullish(w) and above(w),"日线死叉＋月线MACD空头":not bullish(m),"日线死叉＋月线零轴上转弱":above(m) and m["histogram_falling"],"日线死叉＋周月同时转弱":not bullish(w) and (not bullish(m) or (above(m) and m["histogram_falling"]))}
 keys=list(flags)
 flags["日线位置＋周线方向"]=flags[keys[0]] and flags[keys[1]]
 flags["日线位置＋周线同区域"]=flags[keys[0]] and flags[keys[2]]
 flags["日线位置＋月线改善"]=flags[keys[0]] and flags[keys[4]]
 flags["周月方向组合"]=flags[keys[1]] and flags[keys[5]]
 flags["日周月完整组合"]=flags[keys[0]] and flags[keys[2]] and flags[keys[4]]
 return flags

def outcome(rows,i,side,benchmarks=None):
 entry=rows[i+1]["open"];forward={};mae={};excess={"SPY":{},"QQQ":{}}
 for h in HORIZONS:
  ret=rows[i+h]["close"]/entry-1;path=rows[i+1:i+h+1]
  adverse=min(x["low"]/entry-1 for x in path) if side=="buy" else min(entry/x["high"]-1 for x in path)
  forward[h]=ret if side=="buy" else -ret;mae[h]=adverse
  if benchmarks:
   for symbol in excess:
    start=benchmarks[symbol].get(rows[i+1]["date"]);end=benchmarks[symbol].get(rows[i+h]["date"])
    if start and end:
     benchmark_return=end["close"]/start["open"]-1
     excess[symbol][h]=forward[h]-(benchmark_return if side=="buy" else -benchmark_return)
 return forward,mae,excess

def event_rows(symbol,rows,regimes,benchmarks,listing_status="unknown"):
 if len(rows)<300:return []
 weekly=completed_groups(rows,"weekly");monthly=completed_groups(rows,"monthly");closes=[x["close"] for x in rows];line,signal=macd(closes);events=[]
 for i in range(260,len(rows)-max(HORIZONS)-1):
  buy=line[i]>signal[i] and line[i-1]<=signal[i-1];sell=line[i]<signal[i] and line[i-1]>=signal[i-1]
  if not (buy or sell) or rows[i]["date"] not in regimes:continue
  if rows[i]["close"]<5 or rows[i]["close"]*rows[i]["volume"]<10_000_000:continue
  day=datetime.strptime(rows[i]["date"],"%Y-%m-%d").date();wk=(day.isocalendar().year,day.isocalendar().week);mo=(day.year,day.month)
  wr=available(weekly,wk);mr=available(monthly,mo)
  if len(wr)<35 or len(mr)<35:continue
  d=macd_state(rows[max(0,i-180):i+1]);w=macd_state(wr[-160:]);m=macd_state(mr[-120:]);side="buy" if buy else "sell";forward,mae,excess=outcome(rows,i,side,benchmarks);event_features=features(side,d,w,m)
  if buy:event_features.update(daily_pattern_flags(rows,i))
  events.append({"symbol":symbol,"listing_status":listing_status,"date":rows[i]["date"],"side":side,"trigger":"日线","regime":regimes[rows[i]["date"]],"features":event_features,"forward":forward,"mae":mae,"excess":excess})
 return events

def higher_timeframe_events(symbol,rows,regimes,benchmarks,listing_status="unknown"):
 """Weekly/monthly crosses become usable only after that period closes."""
 date_index={x["date"]:i for i,x in enumerate(rows)};weekly=completed_groups(rows,"weekly");monthly=completed_groups(rows,"monthly");events=[]
 for trigger,groups in (("周线",weekly),("月线",monthly)):
  closes=[x[1]["close"] for x in groups];line,signal=macd(closes)
  for j in range(35,len(groups)-1):
   if not (line[j]>signal[j] and line[j-1]<=signal[j-1]):continue
   bar=groups[j][1];i=date_index.get(bar["date"])
   if i is None or i+max(HORIZONS)>=len(rows) or bar["date"] not in regimes:continue
   if rows[i]["close"]<5 or rows[i]["close"]*rows[i]["volume"]<10_000_000:continue
   state=macd_state([x[1] for x in groups[max(0,j-120):j+1]]);below=state["cross_zero_zone"]=="零轴下";d=macd_state(rows[max(0,i-180):i+1])
   if trigger=="周线":
    day=datetime.strptime(bar["date"],"%Y-%m-%d").date();mr=available(monthly,(day.year,day.month))
    if len(mr)<35:continue
    m=macd_state(mr[-120:]);monthly_bull=m["macd_line"]>m["signal_line"]
    flags={"周线零轴下金叉":below,"周线金叉＋月线多头":monthly_bull,"周线零轴下金叉＋月线改善":below and m["zero_zone"]=="零轴下" and (m["negative_histogram_shrinking"] or m["near_cross"])}
   else:
    completed_weekly=[x[1] for x in weekly if x[1]["date"]<=bar["date"]];w=macd_state(completed_weekly[-160:]);weekly_bull=w["macd_line"]>w["signal_line"];daily_bull=d["macd_line"]>d["signal_line"]
    flags={"月线零轴下金叉":below,"月线金叉＋周线多头":weekly_bull,"月线金叉＋日周多头":weekly_bull and daily_bull}
   forward,mae,excess=outcome(rows,i,"buy",benchmarks);events.append({"symbol":symbol,"listing_status":listing_status,"date":bar["date"],"side":"buy","trigger":trigger,"regime":regimes[bar["date"]],"features":flags,"forward":forward,"mae":mae,"excess":excess})
 return events

def stats(events,horizon):
 vals=[x["forward"][horizon] for x in events];mae=[x["mae"][horizon] for x in events]
 if not vals:return {"samples":0,"win_rate":None,"mean_return":None,"trimmed_mean_return":None,"median_return":None,"mean_adverse":None,"spy_excess_return":None,"qqq_excess_return":None,"beat_spy_rate":None,"beat_qqq_rate":None}
 ordered=sorted(vals);trim=max(1,len(vals)//100);trimmed=ordered[trim:-trim] if len(vals)>2*trim else ordered
 benchmark_stats={}
 for symbol in ("SPY","QQQ"):
  xs=[x["excess"][symbol][horizon] for x in events if horizon in x.get("excess",{}).get(symbol,{})]
  benchmark_stats[f"{symbol.lower()}_excess_return"]=round(statistics.mean(xs)*100,2) if xs else None
  benchmark_stats[f"beat_{symbol.lower()}_rate"]=round(sum(x>0 for x in xs)/len(xs)*100,1) if xs else None
 return {"samples":len(vals),"win_rate":round(sum(x>0 for x in vals)/len(vals)*100,1),"mean_return":round(statistics.mean(vals)*100,2),"trimmed_mean_return":round(statistics.mean(trimmed)*100,2),"median_return":round(statistics.median(vals)*100,2),"mean_adverse":round(statistics.mean(mae)*100,2),**benchmark_stats}

def summarize(events):
 names=sorted({k for x in events for k,v in x["features"].items() if v});rows=[]
 for side in ("buy","sell"):
  side_events=[x for x in events if x["side"]==side]
  for regime in ("all",*REGIME_LABELS):
   base=side_events if regime=="all" else [x for x in side_events if x["regime"]==regime]
   for name in ["全部交叉",*names]:
    selected=base if name=="全部交叉" else [x for x in base if x["features"].get(name)]
    for h in HORIZONS:rows.append({"side":side,"regime":regime,"regime_label":"全部市场" if regime=="all" else REGIME_LABELS[regime],"factor":name,"horizon":h,**stats(selected,h)})
 return rows

def incremental_report(splits):
 factors=("基准＋周线能量改善","基准＋周线准备金叉","基准＋周线已经多头","基准＋月线能量改善","基准＋月线准备金叉","基准＋月线已经多头")
 def find(split,factor):return next(x for x in splits[split] if x["side"]=="buy" and x["regime"]=="both_bear" and x["factor"]==factor and x["horizon"]==20)
 baseline={split:find(split,"日线零轴下金叉") for split in SPLITS};out=[]
 for factor in factors:
  stages={split:find(split,factor) for split in SPLITS};deltas={split:{"win_rate":round(stages[split]["win_rate"]-baseline[split]["win_rate"],1) if stages[split]["win_rate"] is not None else None,"trimmed_mean_return":round(stages[split]["trimmed_mean_return"]-baseline[split]["trimmed_mean_return"],2) if stages[split]["trimmed_mean_return"] is not None else None,"sample_retention":round(stages[split]["samples"]/baseline[split]["samples"]*100,1)} for split in SPLITS}
  positive=sum((deltas[x]["win_rate"] or 0)>0 and (deltas[x]["trimmed_mean_return"] or 0)>0 for x in SPLITS)
  enough=stages["validation"]["samples"]>=100 and stages["forward"]["samples"]>=30
  verdict="样本不足" if not enough else "有效加分" if positive==3 else "可能有效，继续观察" if positive>=2 and (deltas["development"]["win_rate"] or 0)>=0 else "没有提升" if positive>=1 else "反而削弱"
  out.append({"factor":factor,"baseline":baseline,"stages":stages,"deltas":deltas,"verdict":verdict})
 out.sort(key=lambda x:(x["verdict"]=="有效加分",min((x["deltas"][s]["win_rate"] or -999) for s in SPLITS),x["stages"]["validation"]["samples"]),reverse=True);return out

def monthly_horizon_report(splits):
 specs=(("基准＋月线准备金叉","both_bear","弱市日线零轴下金叉＋月线准备金叉"),("基准＋月线已经多头","both_bear","弱市日线零轴下金叉＋月线已经多头"),("月线零轴下金叉","all","月线零轴下刚金叉"))
 out=[]
 for factor,regime,label in specs:
  horizons=[]
  for horizon in (20,40,60,100):
   stages={split:next(x for x in splits[split] if x["side"]=="buy" and x["regime"]==regime and x["factor"]==factor and x["horizon"]==horizon) for split in SPLITS}
   horizons.append({"horizon":horizon,"stages":stages})
  out.append({"factor":factor,"label":label,"regime":regime,"horizons":horizons})
 return out

def pattern_incremental_report(splits):
 def find(split,factor):return next(x for x in splits[split] if x["side"]=="buy" and x["regime"]=="all" and x["factor"]==factor and x["horizon"]==20)
 baseline={split:find(split,"长期趋势合格＋日线金叉") for split in SPLITS};out=[]
 for factor in PATTERN_FACTORS:
  stages={split:find(split,factor) for split in SPLITS};deltas={}
  for split in SPLITS:
   stage,base=stages[split],baseline[split]
   deltas[split]={"win_rate":round(stage["win_rate"]-base["win_rate"],1) if stage["win_rate"] is not None else None,"trimmed_mean_return":round(stage["trimmed_mean_return"]-base["trimmed_mean_return"],2) if stage["trimmed_mean_return"] is not None else None,"sample_retention":round(stage["samples"]/base["samples"]*100,1)}
  enough=stages["validation"]["samples"]>=100 and stages["forward"]["samples"]>=30
  positive=sum((deltas[s]["win_rate"] or 0)>0 and (deltas[s]["trimmed_mean_return"] or 0)>0 for s in SPLITS)
  meaningful=all((deltas[s]["win_rate"] or 0)>=1 and (deltas[s]["trimmed_mean_return"] or 0)>=.25 for s in SPLITS)
  verdict="样本不足" if not enough else "成立" if meaningful else "有小幅帮助" if positive==3 else "不成立" if positive<=1 else "不稳定"
  out.append({"factor":factor,"label":factor.replace("长期趋势合格＋日线金叉＋",""),"holding_days":20,"verdict":verdict,"baseline":baseline,"stages":stages,"deltas":deltas})
 return out

def run(out="public/macd-factor-backtest.json",limit=None):
 cache=pathlib.Path("work/eodhd-cache");regimes,benchmarks=market_regimes(cache);statuses=listing_statuses();paths=sorted(cache.glob("*.json"));paths=paths[:limit] if limit else paths;events=[];loaded=0;starts=[];ends=[];row_counts=[];history_status={}
 for path in paths:
  if path.stem in ("SPY","QQQ"):continue
  rows=adjusted_rows(json.loads(path.read_text()))
  status=statuses.get(path.stem,"delisted" if path.stem.endswith("_old") else "unknown")
  if len(rows)>=420:events.extend(event_rows(path.stem,rows,regimes,benchmarks,status));events.extend(higher_timeframe_events(path.stem,rows,regimes,benchmarks,status));loaded+=1;history_status[status]=history_status.get(status,0)+1;starts.append(rows[0]["date"]);ends.append(rows[-1]["date"]);row_counts.append(len(rows))
 splits={name:summarize([x for x in events if start<=x["date"]<=end]) for name,(start,end) in SPLITS.items()}
 candidates=[]
 for row in splits["development"]:
  if row["samples"]<200 or row["factor"]=="全部交叉":continue
  val=next((x for x in splits["validation"] if (x["side"],x["regime"],x["factor"],x["horizon"])==(row["side"],row["regime"],row["factor"],row["horizon"])),None)
  if val and val["samples"]>=30 and row["trimmed_mean_return"]>0 and row["median_return"]>0 and val["trimmed_mean_return"]>0 and val["median_return"]>0:
   forward=next((x for x in splits["forward"] if (x["side"],x["regime"],x["factor"],x["horizon"])==(row["side"],row["regime"],row["factor"],row["horizon"])),None)
   status="forward_supportive" if forward and forward["samples"]>=30 and forward["trimmed_mean_return"]>0 and forward["median_return"]>0 else "forward_failed" if forward and forward["samples"]>=30 else "forward_insufficient"
   candidates.append({"side":row["side"],"factor":row["factor"],"horizon":row["horizon"],"development":row,"validation":val,"forward":forward,"status":status})
 candidates.sort(key=lambda x:(x["status"]=="forward_supportive",x["validation"]["win_rate"],x["validation"]["trimmed_mean_return"],x["validation"]["samples"]),reverse=True)
 bearish_comparison=[x for x in splits["validation"] if x["side"]=="sell" and x["factor"]=="日线零轴上死叉" and x["horizon"]==5]
 trigger_counts={name:sum(x["trigger"]==name for x in events) for name in ("日线","周线","月线")}
 event_status={status:sum(x["listing_status"]==status for x in events) for status in ("active","delisted","unknown")};report={"status":"research_only","execution":"日/周/月信号均在对应K线完整收盘后确认，下一交易日复权开盘价进入；5/10/20/40/60/100日均指交易日（日K），用于统一比较","lookahead":"周线和月线只在周期完整结束后使用；SPY/QQQ环境只使用信号日已收盘数据","market_regime":{"definition":"分别比较SPY、QQQ收盘价与各自EMA200","labels":REGIME_LABELS},"universe":{"history_files":len(paths),"eligible":loaded,"events":len(events),"trigger_counts":trigger_counts,"listing_status_histories":history_status,"listing_status_events":event_status,"event_filter":"信号日股价≥5美元且成交额≥1000万美元","history_earliest":min(starts),"history_latest":max(ends),"median_daily_bars":round(statistics.median(row_counts))},"pattern_trend_gate":{"plain":"只保留信号日当时长期上涨或横盘的股票","rule":"收盘价不低于EMA200的90%，且EMA200过去60个交易日跌幅不超过3%","future_listing_status_used":False},"splits":splits,"validated_combinations":candidates[:30],"incremental_tests":incremental_report(splits),"monthly_horizon_tests":monthly_horizon_report(splits),"pattern_incremental_tests":pattern_incremental_report(splits),"bearish_regime_comparison":bearish_comparison,"warning":"长持有期事件会重叠，胜率也会受到美股长期上涨漂移影响，不能直接视为独立交易胜率。形态组合只使用信号日当时已经确认的数据，不改变MACD本身。退市身份只用于覆盖审计，不参与信号筛选。"}
 pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,indent=2));return report

if __name__=="__main__":
 r=run();print(json.dumps({"universe":r["universe"],"top":r["validated_combinations"][:5]},ensure_ascii=False,indent=2))
