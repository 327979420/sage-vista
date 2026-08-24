"""Point-in-time MACD event study using next-open execution.

Daily crosses are the event. Weekly and monthly states use only periods that
were completed before the event date, preventing higher-timeframe lookahead.
"""
import json,pathlib,statistics
from collections import defaultdict
from datetime import datetime
from .resonance_tracker import macd

HORIZONS=(5,10,20)
SPLITS={"development":("0000-01-01","2024-12-31"),"validation":("2025-01-01","2025-12-31"),"forward":("2026-01-01","9999-12-31")}
REGIME_LABELS={"both_bull":"SPY与QQQ均在EMA200上","mixed":"SPY与QQQ方向不一致","both_bear":"SPY与QQQ均在EMA200下"}

def adjusted_rows(raw):
 out=[]
 for x in raw:
  if not x.get("close") or not x.get("adjusted_close") or not x.get("open"):continue
  ratio=x["adjusted_close"]/x["close"]
  out.append({"date":x["date"],"open":x["open"]*ratio,"high":x["high"]*ratio,"low":x["low"]*ratio,"close":x["adjusted_close"],"volume":int(x.get("volume") or 0)})
 return sorted(out,key=lambda x:x["date"])

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
 states={}
 for symbol in ("SPY","QQQ"):
  rows=adjusted_rows(json.loads((cache/f"{symbol}.json").read_text()));curve=ema([x["close"] for x in rows])
  states[symbol]={x["date"]:x["close"]>curve[i] for i,x in enumerate(rows) if i>=199}
 dates=set(states["SPY"])&set(states["QQQ"]);out={}
 for date in dates:
  pair=(states["SPY"][date],states["QQQ"][date]);out[date]="both_bull" if pair==(True,True) else "both_bear" if pair==(False,False) else "mixed"
 return out

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

def features(side,d,w,m):
 bullish=lambda x:x["macd_line"]>x["signal_line"]
 below=lambda x:x["zero_zone"]=="零轴下"
 above=lambda x:x["zero_zone"]=="零轴上"
 if side=="buy":
  flags={"日线零轴下金叉":d["cross_zero_zone"]=="零轴下","周线MACD多头":bullish(w),"周线零轴下多头":bullish(w) and below(w),"月线MACD多头":bullish(m),"月线零轴下改善":below(m) and (m["negative_histogram_shrinking"] or m["near_cross"]),"周月同时支持":bullish(w) and (bullish(m) or (below(m) and m["histogram_rising"]))}
 else:
  flags={"日线零轴上死叉":d["dead_cross_zero_zone"]=="零轴上","周线MACD空头":not bullish(w),"周线零轴上空头":not bullish(w) and above(w),"月线MACD空头":not bullish(m),"月线零轴上转弱":above(m) and m["histogram_falling"],"周月同时转弱":not bullish(w) and (not bullish(m) or (above(m) and m["histogram_falling"]))}
 keys=list(flags)
 flags["日线位置＋周线方向"]=flags[keys[0]] and flags[keys[1]]
 flags["日线位置＋周线同区域"]=flags[keys[0]] and flags[keys[2]]
 flags["日线位置＋月线改善"]=flags[keys[0]] and flags[keys[4]]
 flags["周月方向组合"]=flags[keys[1]] and flags[keys[5]]
 flags["日周月完整组合"]=flags[keys[0]] and flags[keys[2]] and flags[keys[4]]
 return flags

def event_rows(symbol,rows,regimes):
 if len(rows)<300:return []
 weekly=completed_groups(rows,"weekly");monthly=completed_groups(rows,"monthly");closes=[x["close"] for x in rows];line,signal=macd(closes);events=[]
 for i in range(260,len(rows)-max(HORIZONS)-1):
  buy=line[i]>signal[i] and line[i-1]<=signal[i-1];sell=line[i]<signal[i] and line[i-1]>=signal[i-1]
  if not (buy or sell) or rows[i]["date"] not in regimes:continue
  if rows[i]["close"]<5 or rows[i]["close"]*rows[i]["volume"]<10_000_000:continue
  day=datetime.strptime(rows[i]["date"],"%Y-%m-%d").date();wk=(day.isocalendar().year,day.isocalendar().week);mo=(day.year,day.month)
  wr=available(weekly,wk);mr=available(monthly,mo)
  if len(wr)<35 or len(mr)<35:continue
  d=macd_state(rows[max(0,i-180):i+1]);w=macd_state(wr[-160:]);m=macd_state(mr[-120:]);side="buy" if buy else "sell";entry=rows[i+1]["open"]
  forward={};mae={}
  for h in HORIZONS:
   ret=rows[i+h]["close"]/entry-1
   path=rows[i+1:i+h+1]
   adverse=min(x["low"]/entry-1 for x in path) if side=="buy" else min(entry/x["high"]-1 for x in path)
   forward[h]=ret if side=="buy" else -ret;mae[h]=adverse
  events.append({"symbol":symbol,"date":rows[i]["date"],"side":side,"regime":regimes[rows[i]["date"]],"features":features(side,d,w,m),"forward":forward,"mae":mae})
 return events

def stats(events,horizon):
 vals=[x["forward"][horizon] for x in events];mae=[x["mae"][horizon] for x in events]
 if not vals:return {"samples":0,"win_rate":None,"mean_return":None,"median_return":None,"mean_adverse":None}
 ordered=sorted(vals);trim=max(1,len(vals)//100);trimmed=ordered[trim:-trim] if len(vals)>2*trim else ordered
 return {"samples":len(vals),"win_rate":round(sum(x>0 for x in vals)/len(vals)*100,1),"mean_return":round(statistics.mean(vals)*100,2),"trimmed_mean_return":round(statistics.mean(trimmed)*100,2),"median_return":round(statistics.median(vals)*100,2),"mean_adverse":round(statistics.mean(mae)*100,2)}

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

def run(out="public/macd-factor-backtest.json",limit=None):
 cache=pathlib.Path("work/eodhd-cache");regimes=market_regimes(cache);paths=sorted(cache.glob("*.json"));paths=paths[:limit] if limit else paths;events=[];loaded=0
 for path in paths:
  if path.stem in ("SPY","QQQ"):continue
  rows=adjusted_rows(json.loads(path.read_text()))
  if len(rows)>=420:events.extend(event_rows(path.stem,rows,regimes));loaded+=1
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
 report={"status":"research_only","execution":"信号收盘后，下一交易日复权开盘价进入；5/10/20日收盘退出","lookahead":"周线和月线只使用信号日前已经结束的完整周期；SPY/QQQ环境只使用信号日已收盘数据","market_regime":{"definition":"分别比较SPY、QQQ收盘价与各自EMA200","labels":REGIME_LABELS},"universe":{"history_files":len(paths),"eligible":loaded,"events":len(events),"event_filter":"信号日股价≥5美元且成交额≥1000万美元"},"splits":splits,"validated_combinations":candidates[:30],"bearish_regime_comparison":bearish_comparison,"warning":"只研究MACD周期结构与SPY/QQQ市场环境；胜率未扣交易成本，也未处理同一股票重叠信号。"}
 pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,indent=2));return report

if __name__=="__main__":
 r=run();print(json.dumps({"universe":r["universe"],"top":r["validated_combinations"][:5]},ensure_ascii=False,indent=2))
