from __future__ import annotations
import json
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean
from .technical import atr,ema,sma,rsi,macd

CONFIG_PATH=Path(__file__).parents[2]/"config"/"technical_rules.json"
def load_config(path=CONFIG_PATH):return json.loads(Path(path).read_text())

@dataclass
class Detection:
 detected:bool; timeframe:str; detection_timestamp:str; levels:dict; measurements:dict; confidence:float; explanation:str; data_used:dict; confirmation_delay:int; invalidated:bool=False; classification:str="none"
 def dict(self):return asdict(self)

def result(detected,rows,i,timeframe="daily",**kw):
 ts=rows[i]["date"] if rows and 0<=i<len(rows) else datetime.now(timezone.utc).isoformat()
 base=dict(levels={},measurements={},confidence=0.0,explanation="Not detected",data_used={"first_index":None,"last_index":i},confirmation_delay=0,invalidated=False,classification="none")
 base.update(kw);return Detection(detected,timeframe,ts,**base)

def pivots(rows,end=None,cfg=None,timeframe="daily"):
 """Return only pivots confirmed by `end`; never reads bars beyond it."""
 c=(cfg or load_config())["pivot"];end=len(rows)-1 if end is None else min(end,len(rows)-1);left,right=c["left_bars"],c["right_bars"];a=atr(rows)
 lows=[];highs=[]
 for i in range(left,end-right+1):
  if rows[i]["low"]<min(rows[j]["low"] for j in range(i-left,i)) and rows[i]["low"]<min(rows[j]["low"] for j in range(i+1,i+right+1)):lows.append({"index":i,"price":rows[i]["low"],"confirmed_index":i+right,"major":max(x["high"] for x in rows[i+1:min(end+1,i+right+11)])-rows[i]["low"]>=c["major_move_atr"]*a[i]})
  if rows[i]["high"]>max(rows[j]["high"] for j in range(i-left,i)) and rows[i]["high"]>max(rows[j]["high"] for j in range(i+1,i+right+1)):highs.append({"index":i,"price":rows[i]["high"],"confirmed_index":i+right})
 return {"lows":lows,"highs":highs,"evaluated_through":end,"confirmation_delay":right}

def detect_w_bottom(rows,end=None,cfg=None,timeframe="daily"):
 cfg=cfg or load_config();end=len(rows)-1 if end is None else end;p=pivots(rows,end,cfg,timeframe);a=atr(rows);lows=p["lows"]
 if len(lows)<2:return result(False,rows,end,timeframe,confirmation_delay=cfg["pivot"]["right_bars"],explanation="Fewer than two confirmed swing lows")
 first,second=lows[-2],lows[-1];sep=second["index"]-first["index"];wc=cfg["w_bottom"];neck=max(rows[j]["high"] for j in range(first["index"],second["index"]+1));delta=second["price"]-first["price"]
 valid=first["price"]<second["price"] and wc["min_separation_bars"]<=sep<=wc["max_separation_bars"] and delta<=wc["max_second_low_atr_above_first"]*a[second["index"]]
 classification="w_bottom" if valid else ("ordinary_higher_low" if first["price"]<second["price"] else "invalid_w")
 return result(valid,rows,end,timeframe,levels={"first_low":first["price"],"second_low":second["price"],"neckline":neck},measurements={"separation_bars":sep,"second_low_delta_atr":round(delta/a[second["index"]],3)},confidence=.8 if valid and first["major"] else .65 if valid else .2,explanation="Two confirmed swing lows form a higher-second-low W with an objective neckline" if valid else f"Pair classified as {classification}",data_used={"first_index":first["index"],"last_index":second["confirmed_index"]},confirmation_delay=cfg["pivot"]["right_bars"],classification=classification)

def relative_volume(rows,i,cfg=None,timeframe="daily"):
 cfg=cfg or load_config();n=cfg["volume"]["lookback"]
 if i<n:return result(False,rows,i,timeframe,explanation="Insufficient completed volume bars",confirmation_delay=0)
 avg=mean(x["volume"] for x in rows[i-n:i]);ratio=rows[i]["volume"]/avg if avg else 0
 tier="exceptional" if ratio>=cfg["volume"]["exceptional"] else "strong" if ratio>=cfg["volume"]["strong"] else "normal" if ratio>=1 else "weak"
 return result(ratio>=cfg["volume"]["strong"],rows,i,timeframe,measurements={"relative_volume":round(ratio,3),"prior_completed_bar_average":avg},confidence=min(1,ratio/2),explanation=f"Relative volume is {ratio:.2f}× ({tier}) versus the previous {n} completed bars",data_used={"first_index":i-n,"last_index":i},classification=tier)

def detect_bos(rows,i,level,cfg=None,timeframe="daily"):
 cfg=cfg or load_config();b=rows[i];rng=max(b["high"]-b["low"],1e-9);body=abs(b["close"]-b["open"])/rng;rv=relative_volume(rows,i,cfg,timeframe);close_break=b["close"]>level;wick_only=b["high"]>level and not close_break
 valid=close_break and body>=cfg["bos"]["min_body_fraction"];kind="bos" if valid else "liquidity_swipe" if wick_only else "unresolved_test"
 confidence=.7+(.2 if rv.measurements.get("relative_volume",0)>=cfg["bos"]["strong_volume_ratio"] else 0) if valid else .3 if wick_only else .1
 return result(valid,rows,i,timeframe,levels={"broken_level":level,"close":b["close"],"high":b["high"]},measurements={"body_fraction":round(body,3),"relative_volume":rv.measurements.get("relative_volume")},confidence=min(1,confidence),explanation="Solid candle close confirms break of structure" if valid else "Wick crossed but close remained below: liquidity swipe, not BOS" if wick_only else "No valid close through resistance",data_used={"first_index":max(0,i-cfg["volume"]["lookback"]),"last_index":i},confirmation_delay=0,classification=kind)

def count_level_tests(rows,end,level,cfg=None,timeframe="daily"):
 cfg=cfg or load_config();a=atr(rows);lc=cfg["level_test"];tests=[];last=-999
 for i in range(max(0,end-100),end+1):
  if abs(rows[i]["high"]-level)<=lc["proximity_atr"]*a[i] and i-last>lc["rejection_cluster_bars"]:tests.append(i);last=i
 n=len(tests);return result(n>=lc["min_attempts"],rows,end,timeframe,levels={"resistance":level},measurements={"separate_tests":n,"test_indices":tests},confidence=min(1,n/lc["min_attempts"]),explanation=f"{n} separate resistance tests; a valid close is still required for breakout",data_used={"first_index":max(0,end-100),"last_index":end},classification="breakout_developing" if n>=lc["min_attempts"] else "insufficient_tests")

def _retest_candle(rows,i,level,cfg):
 b=rows[i];rng=max(b["high"]-b["low"],1e-9);body=abs(b["close"]-b["open"]);lower=min(b["open"],b["close"])-b["low"]
 engulf=i>0 and b["close"]>b["open"] and b["open"]<rows[i-1]["close"] and b["close"]>rows[i-1]["open"]
 hammer=lower>=cfg["retest"]["hammer_wick_body_ratio"]*max(body,1e-9) and (b["close"]-b["low"])/rng>=cfg["retest"]["upper_close_fraction"]
 expansion=b["close"]>b["open"] and body/rng>=cfg["retest"]["expansion_body_fraction"]
 doji_follow=i>0 and abs(rows[i-1]["close"]-rows[i-1]["open"])/max(rows[i-1]["high"]-rows[i-1]["low"],1e-9)<=cfg["retest"]["doji_body_fraction"] and b["close"]>max(rows[i-1]["high"],level)
 return engulf or hammer or expansion or doji_follow,{"engulfing":engulf,"hammer_rejection":hammer,"expansion":expansion,"doji_follow_through":doji_follow}

def detect_retest(rows,bos_index,end,level,stop,target,cfg=None,timeframe="daily"):
 cfg=cfg or load_config();a=atr(rows);rc=cfg["retest"];start=bos_index+rc["min_bars_after_bos"];finish=min(end,bos_index+rc["max_bars_after_bos"]);risk=None if stop>=level else level-stop;rr=None if not risk else (target-level)/risk
 for i in range(start,finish+1):
  near=rows[i]["low"]<=level+rc["proximity_atr"]*a[i];failed=rows[i]["close"]<level and abs(rows[i]["close"]-level)>rc["proximity_atr"]*a[i]
  candle,raw=_retest_candle(rows,i,level,cfg)
  if near and not failed and candle and rr is not None and rr>=rc["min_reward_risk"]:return result(True,rows,i,timeframe,levels={"broken_level":level,"stop":stop,"target":target},measurements={"bars_after_bos":i-bos_index,"reward_risk":round(rr,2),**raw},confidence=.85,explanation="Retest held the broken level and printed valid bullish confirmation",data_used={"first_index":bos_index,"last_index":i},classification="valid_retest")
  if near and failed:return result(False,rows,i,timeframe,levels={"broken_level":level},measurements={"bars_after_bos":i-bos_index},confidence=.1,explanation="Retest produced a solid close back below the broken level",data_used={"first_index":bos_index,"last_index":i},invalidated=True,classification="failed_retest")
 return result(False,rows,end,timeframe,levels={"broken_level":level},measurements={"bars_observed":max(0,finish-start+1),"reward_risk":rr},confidence=0,explanation="Breakout without entry: no valid retest within the configured window",data_used={"first_index":bos_index,"last_index":finish},classification="breakout_without_entry")

def evaluate_gap(previous_close,planned_entry,next_open,atr_value,cfg=None):
 cfg=cfg or load_config();gap=next_open-planned_entry;ratio=gap/atr_value if atr_value else 999
 if gap<=0:return {"classification":"no_adverse_gap","action":"plan unchanged","gap_atr":round(ratio,3),"reject":False}
 small=ratio<cfg["gap"]["small_gap_atr"];return {"classification":"small_gap" if small else "large_gap","action":"wait for four-hour retest" if small else "do not chase; recalculate plan","gap_atr":round(ratio,3),"reject":not small}
