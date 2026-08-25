"""Multi-timeframe MACD/RSI resonance tracker using latest completed EOD bars."""
import hashlib,json,pathlib,statistics
from datetime import date,datetime,timedelta,timezone
from .eodhd import get,latest_reference_day
from .research_pipeline import iso
from .technical import ema,macd,rsi
from .confluence_rules import RULESET,breakout_layer as cycle_breakout_layer,combine,ema_layer as cycle_ema_layer,macd_layer as cycle_macd_layer,rsi_layer as cycle_rsi_layer

def bulk_day(day,cache_dir="work/eodhd-bulk",strict=False):
 path=pathlib.Path(cache_dir)/f"{day}.json";path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():
  cached=json.loads(path.read_text())
  if cached:
   rows=cached
  else:rows=get("eod-bulk-last-day/US",date=day,_timeout=300,_attempts=3)
 else:rows=get("eod-bulk-last-day/US",date=day,_timeout=300,_attempts=3)
 valid=[row for row in rows if row.get("date")==day]
 if strict and (not valid or len(valid)!=len(rows)):raise RuntimeError(f"Bulk EOD data for {day} is not ready or has a mismatched date")
 if valid and (not path.exists() or not json.loads(path.read_text())):path.write_text(json.dumps(valid))
 return valid
def aggregate(rows,mode,completed_only=False):
 groups={}
 for row in rows:
  d=datetime.strptime(row["date"],"%m/%d/%Y").date();key=(d.isocalendar().year,d.isocalendar().week) if mode=="weekly" else (d.year,d.month)
  groups.setdefault(key,[]).append(row)
 out=[]
 for values in groups.values():
  out.append({"date":values[-1]["date"],"open":values[0]["open"],"high":max(x["high"] for x in values),"low":min(x["low"] for x in values),"close":values[-1]["close"],"volume":sum(x["volume"] for x in values)})
 return out[:-1] if completed_only and len(out)>1 else out
def bullish_divergence(rows,values,window=45):
 end=len(rows)-1;lows=[]
 for i in range(max(2,end-window),end):
  if rows[i]["low"]<rows[i-1]["low"] and rows[i]["low"]<=rows[i+1]["low"] and values[i] is not None:lows.append(i)
 if len(lows)<2:return False
 a,b=lows[-2:]
 return end-b<=8 and values[b]<50 and rows[b]["low"]<rows[a]["low"] and values[b]>values[a]+2 and rows[end]["close"]<=rows[b]["low"]*1.15
def bearish_divergence(rows,values,window=45):
 end=len(rows)-1;highs=[]
 for i in range(max(2,end-window),end):
  if rows[i]["high"]>rows[i-1]["high"] and rows[i]["high"]>=rows[i+1]["high"] and values[i] is not None:highs.append(i)
 if len(highs)<2:return False
 a,b=highs[-2:]
 return end-b<=8 and values[b]>50 and rows[b]["high"]>rows[a]["high"] and values[b]<values[a]-2 and rows[end]["close"]>=rows[b]["high"]*.85
def volume_state(rows):
 """Detect unusual daily volume and label whether it occurs near a 60-day low."""
 if len(rows)<61:return {"label":"数据不足","score":0,"ratio":None,"near_bottom":False,"direction":"—"}
 current=rows[-1];baseline=[x["volume"] for x in rows[-21:-1] if x.get("volume") is not None]
 average=sum(baseline)/len(baseline) if baseline else 0;ratio=current["volume"]/average if average else 0
 low60=min(x["low"] for x in rows[-60:]);high60=max(x["high"] for x in rows[-60:])
 near_bottom=current["close"]<=low60*1.12 or current["close"]<=high60*.82
 unusual=ratio>=1.8;up=current["close"]>=current["open"]
 label="底部放量上涨" if unusual and near_bottom and up else "底部放量" if unusual and near_bottom else "异常放量" if unusual else "正常"
 return {"label":label,"score":6 if unusual and near_bottom and up else 4 if unusual and near_bottom else 2 if unusual else 0,"ratio":round(ratio,2),"near_bottom":near_bottom,"direction":"上涨" if up else "下跌","distance_from_60d_low":round(current["close"]/low60-1,3)}
def price_structure_state(rows):
 """Optional daily price-structure confirmation; never changes MACD itself."""
 if len(rows)<70:return {"confirmed":False,"score":0,"label":"历史不足","evidence":[]}
 closes=[x["close"] for x in rows];e20,e50=ema(closes,20),ema(closes,50);i=len(rows)-1;close=closes[i]
 pivots=[]
 for j in range(i-60,i):
  if rows[j]["low"]<rows[j-1]["low"] and rows[j]["low"]<=rows[j+1]["low"]:pivots.append(j)
 higher_low=len(pivots)>=2 and rows[pivots[-1]]["low"]>rows[pivots[-2]]["low"]*1.005
 trend=close>e50[i] and e50[i]>e50[i-20]
 support=(abs(close-e20[i])/close<=.03 and e20[i]>=e20[i-5]) or (abs(close-e50[i])/close<=.04 and e50[i]>=e50[i-5])
 breakout=close>max(x["high"] for x in rows[i-20:i])
 evidence=[]
 if trend:evidence.append("站上上升中的50日均线")
 if support:evidence.append("接近上升均线支撑")
 if higher_low:evidence.append("最近两个波段低点抬高")
 if breakout:evidence.append("突破近20日高点")
 score=sum((trend,support,higher_low,breakout));confirmed=score>=2
 return {"confirmed":confirmed,"score":score,"label":"结构确认" if confirmed else "结构改善" if score==1 else "结构偏弱","evidence":evidence}
def ema_state(rows):
 """Daily EMA direction is an independent evidence layer, not a score proxy."""
 closes=[x["close"] for x in rows];e20,e50=ema(closes,20),ema(closes,50);i=len(rows)-1
 bull=closes[i]>e20[i]>e50[i] and e20[i]>e20[i-5] and e50[i]>e50[i-10]
 bear=closes[i]<e20[i]<e50[i] and e20[i]<e20[i-5] and e50[i]<e50[i-10]
 recent_bull=any(e20[j]>e50[j] and e20[j-1]<=e50[j-1] for j in range(i-5,i+1))
 recent_bear=any(e20[j]<e50[j] and e20[j-1]>=e50[j-1] for j in range(i-5,i+1))
 direction="buy" if bull else "sell" if bear else "neutral"
 reclaim_buy=any(closes[j]>e20[j] and closes[j-1]<=e20[j-1] for j in range(i-3,i+1)) and e20[i]>e50[i]
 reclaim_sell=any(closes[j]<e20[j] and closes[j-1]>=e20[j-1] for j in range(i-3,i+1)) and e20[i]<e50[i]
 trigger="buy" if recent_bull or reclaim_buy else "sell" if recent_bear or reclaim_sell else "neutral"
 improving="buy" if e20[i]>e20[i-5] and closes[i]>e20[i] else "sell" if e20[i]<e20[i-5] and closes[i]<e20[i] else "neutral"
 label="多头排列" if bull else "空头排列" if bear else "均线纠缠"
 if recent_bull:label="EMA20上穿EMA50"
 if recent_bear:label="EMA20下穿EMA50"
 return {"direction":direction,"trigger":trigger,"improving":improving,"label":label,"close":round(closes[i],2),"ema20":round(e20[i],2),"ema50":round(e50[i],2),"fresh_cross":recent_bull or recent_bear}
def breakout_state(rows):
 """Confirmed close beyond the prior 20 completed bars; no intraday assumption."""
 close=rows[-1]["close"];high=max(x["high"] for x in rows[-21:-1]);low=min(x["low"] for x in rows[-21:-1])
 direction="buy" if close>high else "sell" if close<low else "neutral"
 return {"direction":direction,"label":"突破20日高点" if direction=="buy" else "跌破20日低点" if direction=="sell" else "区间内","level":round(high if direction!="sell" else low,2),"distance":round(close/(high if direction!="sell" else low)-1,4)}
def ranking_evidence(frames,layers,buy_layers,sell_layers,ema_layer,breakout_layer,conflict):
 """Deterministic 0-100 rule-match score; never presented as return probability."""
 direction="buy" if buy_layers>sell_layers else "sell" if sell_layers>buy_layers else "neutral"
 aligned=max(buy_layers,sell_layers);alignment=aligned*15
 if direction=="buy":macd_points=min(15,round(sum(x["macd_score"] for x in frames.values())/2))
 elif direction=="sell":macd_points=min(15,sum(5 for x in frames.values() if x["zero_zone"]=="零轴上" and ((x["bars_since_dead_cross"] is not None and x["dead_cross_zero_zone"]=="零轴上") or x["histogram_falling"])))
 else:macd_points=0
 rsi_points=0
 for x in frames.values():
  if direction=="buy" and x["rsi"] in ("底背离","超卖修复"):rsi_points+=4
  if direction=="sell" and x["rsi"]=="顶背离":rsi_points+=4
 rsi_points=min(10,rsi_points)
 ema_points=(8+(2 if ema_layer["fresh_cross"] else 0)) if ema_layer["direction"]==direction else 0
 breakout_points=(8+min(2,round(abs(breakout_layer["distance"])*100))) if breakout_layer["direction"]==direction else 0
 penalty=20 if conflict else 0
 total=max(0,min(100,alignment+macd_points+rsi_points+ema_points+breakout_points-penalty))
 return total,{"同向层数":alignment,"MACD证据":macd_points,"RSI证据":rsi_points,"EMA证据":ema_points,"突破证据":breakout_points,"冲突扣分":-penalty},direction
def chart_points(rows):
 closes=[x["close"] for x in rows];e20,e50=ema(closes,20),ema(closes,50);start=max(0,len(rows)-60)
 return [{"date":rows[i]["date"],"open":round(rows[i]["open"],2),"high":round(rows[i]["high"],2),"low":round(rows[i]["low"],2),"close":round(rows[i]["close"],2),"ema20":round(e20[i],2),"ema50":round(e50[i],2),"volume":rows[i]["volume"]} for i in range(start,len(rows))]
def macd_state_score(state):
 """Transparent setup score: depressed/fresh signals outrank extended ones."""
 below=state["zero_zone"]=="零轴下"
 if state["bars_since_cross"] is not None:
  freshness=max(0,3-state["bars_since_cross"])
  return (8 if below else 4)+freshness
 if state["near_cross"]:return 6 if below else 3
 if state["negative_histogram_shrinking"]:return 5 if below else 2
 if state["histogram_rising"]:return 3 if below else 2
 return 1 if state["macd_line"]>state["signal_line"] else 0
def transmission_score(frames):
 """Reward daily trigger -> weekly confirmation -> monthly early improvement."""
 daily,weekly,monthly=(frames[x] for x in ("日线","周线","月线"))
 fresh=lambda x:x["bars_since_cross"] is not None and x["bars_since_cross"]<=3 and x["macd_line"]>x["signal_line"]
 early=lambda x:x["zero_zone"]=="零轴下" and (x["near_cross"] or x["negative_histogram_shrinking"])
 reasons=[];score=0
 if fresh(daily) and daily["zero_zone"]=="零轴下":score+=4;reasons.append("日线零轴下新金叉")
 if fresh(weekly) and weekly["zero_zone"]=="零轴下":score+=5;reasons.append("周线零轴下新金叉")
 if early(monthly):
  score+=5;reasons.append("月线零轴下空头柱收缩")
 if (fresh(daily) or early(daily)) and fresh(weekly) and early(monthly):
  score+=8;reasons.append("日线→周线→月线小带大")
 return score," · ".join(reasons) if reasons else "尚未形成小带大链条"
def macd_buy_gate(frames):
 """Strict current-state gate for the combined MACD + RSI list."""
 daily,weekly,monthly=(frames[x] for x in ("日线","周线","月线"))
 fresh=lambda x:x["bars_since_cross"] is not None and x["bars_since_cross"]<=3 and x["macd_line"]>x["signal_line"]
 early=lambda x:x["zero_zone"]=="零轴下" and (x["near_cross"] or x["negative_histogram_shrinking"])
 weekly_bull=weekly["zero_zone"]=="零轴下" and weekly["macd_line"]>weekly["signal_line"] and weekly["macd_histogram"]>0
 daily_turn=daily["histogram_rising"] and (daily["macd_line"]>daily["signal_line"] or daily["zero_zone"]=="零轴下")
 valid=((fresh(daily) or early(daily)) and (fresh(weekly) or weekly_bull)) or ((fresh(weekly) or weekly_bull) and early(monthly) and daily_turn)
 reasons=[]
 if fresh(daily):reasons.append("日线新金叉仍有效")
 elif early(daily):reasons.append("日线零轴下空头柱收缩")
 elif daily_turn:reasons.append("日线动能向上")
 if fresh(weekly):reasons.append("周线新金叉仍有效")
 elif weekly_bull:reasons.append("周线零轴下保持多头")
 if early(monthly):reasons.append("月线零轴下空头柱收缩")
 return valid," · ".join(reasons) if valid else "当前MACD未通过组合榜门槛"
def macd_sell_gate(frames):
 """Mirror of the buy gate: only fresh death crosses above zero carry strong downside weight."""
 daily,weekly=(frames[x] for x in ("日线","周线"))
 fresh=lambda x:x["bars_since_dead_cross"] is not None and x["bars_since_dead_cross"]<=3 and x["dead_cross_zero_zone"]=="零轴上" and x["zero_zone"]=="零轴上" and x["macd_line"]<x["signal_line"]
 weakening=lambda x:x["histogram_falling"] and x["zero_zone"]=="零轴上" and x["macd_line"]<x["signal_line"]
 return (fresh(daily) and (fresh(weekly) or weakening(weekly))) or (weakening(daily) and fresh(weekly))
def rsi_layer_direction(frames):
 bullish=any(x["rsi"]=="底背离" for x in frames.values()) or frames["日线"]["rsi"] in ("超卖","超卖修复")
 bearish=any(x["rsi_bearish_divergence"] for x in frames.values()) or frames["日线"]["rsi_overbought_reversal"]
 return "conflict" if bullish and bearish else "buy" if bullish else "sell" if bearish else "neutral"
def timeframe_state(rows):
 if len(rows)<35:return None
 closes=[x["close"] for x in rows];line,signal=macd(closes);hist=[a-b for a,b in zip(line,signal)];rv=rsi(closes);i=len(rows)-1
 rising=hist[i]>hist[i-1] and hist[i-1]>=hist[i-2];falling=hist[i]<hist[i-1] and hist[i-1]<=hist[i-2];cross=line[i]>signal[i] and line[i-1]<=signal[i-1]
 scale=statistics.pstdev(hist[-20:]) or 1;near=line[i]<=signal[i] and rising and abs(hist[i])<=scale*.35
 bars_since_cross=None;bars_since_dead_cross=None;cross_zero_zone=None;dead_cross_zero_zone=None
 if line[i]>signal[i]:
  for ago in range(0,min(8,i)):
   j=i-ago
   if line[j]>signal[j] and line[j-1]<=signal[j-1]:
    bars_since_cross=ago;cross_zero_zone="零轴下" if line[j]<0 and signal[j]<0 else "零轴上" if line[j]>0 and signal[j]>0 else "穿越零轴";break
 if line[i]<signal[i]:
  for ago in range(0,min(8,i)):
   j=i-ago
   if line[j]<signal[j] and line[j-1]>=signal[j-1]:
    bars_since_dead_cross=ago;dead_cross_zero_zone="零轴上" if line[j]>0 and signal[j]>0 else "零轴下" if line[j]<0 and signal[j]<0 else "穿越零轴";break
 zone="零轴下" if line[i]<0 and signal[i]<0 else "零轴上" if line[i]>0 and signal[i]>0 else "穿越零轴"
 shrinking=hist[i]<0 and rising
 dead_cross=line[i]<signal[i] and line[i-1]>=signal[i-1]
 macd_label="金叉" if cross else f"金叉后{bars_since_cross}根" if bars_since_cross is not None else "死叉" if dead_cross else f"死叉后{bars_since_dead_cross}根" if bars_since_dead_cross is not None else "准备金叉" if near else "空头柱收缩" if shrinking else "向上拐头" if rising else "多头" if line[i]>signal[i] else "空头"
 recovering=rv[i] is not None and rv[i-1] is not None and rv[i]>30>=rv[i-1]
 divergence=bullish_divergence(rows,rv);bear_divergence=bearish_divergence(rows,rv);overbought_reversal=rv[i] is not None and rv[i-1] is not None and rv[i]<70<=rv[i-1]
 rsi_label="底背离" if divergence else "顶背离" if bear_divergence else "超卖修复" if recovering else "超卖" if rv[i] is not None and rv[i]<=30 else "超买回落" if overbought_reversal else "偏强" if rv[i] is not None and rv[i]>=50 else "中性"
 energy_streak=1
 for j in range(i-1,max(i-6,0),-1):
  if (rising and hist[j]>=hist[j-1]) or (falling and hist[j]<=hist[j-1]):energy_streak+=1
  else:break
 state={"macd":macd_label,"macd_line":round(line[i],4),"signal_line":round(signal[i],4),"macd_histogram":round(hist[i],4),"macd_histogram_change":round(hist[i]-hist[i-1],4),"energy":"增强" if rising else "减弱" if falling else "震荡","energy_streak":energy_streak,"zero_zone":zone,"cross_zero_zone":cross_zero_zone,"dead_cross_zero_zone":dead_cross_zero_zone,"bars_since_cross":bars_since_cross,"bars_since_dead_cross":bars_since_dead_cross,"near_cross":near,"histogram_rising":rising,"histogram_falling":falling,"negative_histogram_shrinking":shrinking,"rsi":rsi_label,"rsi_bearish_divergence":bear_divergence,"rsi_overbought_reversal":overbought_reversal,"rsi_score":4 if divergence else 3 if recovering else 2 if rv[i] is not None and rv[i]<=30 else 1 if rv[i] is not None and rv[i]>=50 else 0,"rsi_value":round(rv[i],1) if rv[i] is not None else None}
 state["macd_score"]=macd_state_score(state);return state

def early_watch_evidence(item):
 """Return independent support for a pre-cross daily MACD setup, or an empty list."""
 daily=item["frames"]["日线"]
 gap=daily["signal_line"]-daily["macd_line"]
 previous_gap=gap+daily["macd_histogram_change"]
 shrink_ratio=1-gap/previous_gap if previous_gap>0 else 0
 pre_cross=(daily["macd_line"]<daily["signal_line"] and daily["macd_histogram"]<0 and daily["negative_histogram_shrinking"] and daily["energy_streak"]>=2 and daily["near_cross"] and shrink_ratio>=.15)
 if not pre_cross:return []
 weekly=item["frames"]["周线"];monthly=item["frames"]["月线"];evidence=[]
 if weekly["histogram_rising"] or weekly["macd_line"]>weekly["signal_line"]:evidence.append("完整周线MACD支持")
 if monthly["negative_histogram_shrinking"] or monthly["macd_line"]>monthly["signal_line"]:evidence.append("完整月线MACD支持")
 if item["ema_layer"]["direction"]=="buy" or item["ema_layer"].get("improving")=="buy":evidence.append("日线EMA结构改善")
 if item["price_structure"]["confirmed"]:evidence.append("价格结构确认")
 if daily["rsi_score"]>=2:evidence.append(daily["rsi"])
 if item["volume"]["near_bottom"] and item["volume"]["score"]>=4:evidence.append(item["volume"]["label"])
 if len(evidence)<2:return []
 evidence.insert(0,f"日线负柱连续收缩{daily['energy_streak']}根")
 evidence.insert(1,f"MACD/Signal差距单日缩小{round(shrink_ratio*100)}%")
 return evidence
def run(out="public/resonance-tracker.json",as_of=None):
 # The live tracker is intentionally broader than the backtest panel: every
 # locally cached active symbol may be scanned when it also trades today.
 cached_symbols={x.stem for x in pathlib.Path("work/eodhd-cache").glob("*.json")}
 common_path=pathlib.Path("work/eodhd-active-common.json")
 common_symbols={x["Code"] for x in json.loads(common_path.read_text())} if common_path.exists() else cached_symbols
 symbols=cached_symbols&common_symbols
 authoritative=as_of or latest_reference_day();target=date.fromisoformat(authoritative);days=[(target,bulk_day(authoritative,strict=True))]
 for offset in range(10):
  day=target-timedelta(days=offset)
  if day==target:continue
  if day.weekday()<5:
   try:
    rows=bulk_day(day.isoformat())
    if rows:days.append((day,rows))
   except Exception:pass
  if len(days)>=3:break
 days.sort();latest=days[-1][0].isoformat();updates={}
 if latest!=authoritative:raise RuntimeError(f"Refusing stale tracker output: expected {authoritative}, got {latest}")
 for _,rows in days:
  for x in rows:
   if x.get("code") in symbols and x.get("adjusted_close") and x.get("close") and x.get("volume") is not None:updates.setdefault(x["code"],[]).append(x)
 candidates=[]
 for symbol,new in updates.items():
  if new[-1]["adjusted_close"]<5 or new[-1]["adjusted_close"]*new[-1]["volume"]<10_000_000:continue
  cache=pathlib.Path("work/eodhd-cache")/f"{symbol}.json"
  if not cache.exists():continue
  raw=json.loads(cache.read_text());known={x["date"] for x in raw};added=[x for x in new if x["date"] not in known];raw.extend(added);raw.sort(key=lambda x:x["date"]);raw=[x for x in raw if x["date"]<=latest][-2200:]
  if added:cache.write_text(json.dumps(raw))
  adjusted=[]
  for x in raw:
   if not x.get("close") or not x.get("adjusted_close"):continue
   ratio=x["adjusted_close"]/x["close"];d=x["date"];adjusted.append({"date":f"{d[5:7]}/{d[8:10]}/{d[:4]}","open":x["open"]*ratio,"high":x["high"]*ratio,"low":x["low"]*ratio,"close":x["adjusted_close"],"volume":int(x["volume"])})
  frame_rows={"日线":adjusted,"周线":aggregate(adjusted,"weekly",True),"月线":aggregate(adjusted,"monthly",True)}
  frames={name:timeframe_state(rows) for name,rows in frame_rows.items()}
  if any(v is None for v in frames.values()):continue
  chain_score,chain_reason=transmission_score(frames);macd_buy_valid,macd_gate_reason=macd_buy_gate(frames);macd_sell_valid=macd_sell_gate(frames);base_score=sum(x["macd_score"] for x in frames.values());rsi_score=sum(x["rsi_score"] for x in frames.values());volume=volume_state(adjusted);price_structure=price_structure_state(adjusted);ema_states={name:ema_state(rows) for name,rows in frame_rows.items()};ema_layer=ema_states["日线"];breakout_layer=breakout_state(adjusted)
  divergence_frames=[name for name,state in frames.items() if state["rsi"]=="底背离"]
  bearish_divergence_frames=[name for name,state in frames.items() if state["rsi_bearish_divergence"]]
  indicator_layers={"macd":cycle_macd_layer(frames),"rsi":cycle_rsi_layer(frames),"ema":cycle_ema_layer(ema_states),"breakout":cycle_breakout_layer(breakout_layer,ema_states)};summary=combine(indicator_layers)
  layer_directions={key:value["direction"] for key,value in indicator_layers.items()};buy_layers=sum(x=="buy" for x in layer_directions.values());sell_layers=sum(x=="sell" for x in layer_directions.values())
  confluence_direction=summary["direction"] if summary["direction"]!="neutral" else "watch";confluence_label=summary["label"];ranking_score=summary["score"];ranking_direction=summary["direction"] if summary["direction"] in ("buy","sell") else "neutral";ranking_breakdown={f"{key.upper()}证据":value["score"] for key,value in indicator_layers.items()}
  confluence_bonus=(8 if divergence_frames and chain_score>=8 else 0)+(4 if volume["near_bottom"] and volume["score"]>=4 and (divergence_frames or chain_score>=8) else 0)
  combined_score=base_score+chain_score+rsi_score+volume["score"]+confluence_bonus
  candidates.append({"symbol":symbol,"price":round(adjusted[-1]["close"],2),"dollar_volume":round(adjusted[-1]["close"]*adjusted[-1]["volume"]),"frames":frames,"price_structure":price_structure,"ema_layer":ema_layer,"breakout_layer":breakout_layer,"layer_directions":layer_directions,"buy_layers":buy_layers,"sell_layers":sell_layers,"confluence_direction":confluence_direction,"confluence_label":confluence_label,"ranking_score":ranking_score,"ranking_direction":ranking_direction,"ranking_breakdown":ranking_breakdown,"rank_reason":f"{max(buy_layers,sell_layers)}层同向；规则匹配度{ranking_score}/100","macd_score":base_score+chain_score,"macd_base_score":base_score,"chain_score":chain_score,"chain_reason":chain_reason,"macd_buy_valid":macd_buy_valid,"macd_sell_valid":macd_sell_valid,"macd_gate_reason":macd_gate_reason,"rsi_score":rsi_score,"rsi_divergence_frames":divergence_frames,"rsi_bearish_divergence_frames":bearish_divergence_frames,"volume":volume,"confluence_bonus":confluence_bonus,"combined_score":combined_score,"signal_count":int(macd_buy_valid)+int(bool(divergence_frames))+int(volume["score"]>=4),"macd_resonance":sum(x["macd_score"]>=2 for x in frames.values()),"rsi_resonance":sum(x["rsi_score"]>=2 for x in frames.values()),"_detail":{"chart":chart_points(adjusted),"audit":{"latest_bar":raw[-1]["date"],"history_rows":len(adjusted),"adjusted_prices":True,"future_rows_used":False,"latest_close":round(adjusted[-1]["close"],2)}}})
  candidates[-1]["indicator_layers"]=indicator_layers;candidates[-1]["ema_states"]=ema_states;candidates[-1]["strict_confluence"]=summary["strict"]
  candidates[-1]["macd_rank_score"]=indicator_layers["macd"].get("rank_score",0)
  candidates[-1]["macd_score"]=indicator_layers["macd"]["score"];candidates[-1]["rsi_score"]=indicator_layers["rsi"]["score"];candidates[-1]["combined_score"]=indicator_layers["macd"]["score"]+indicator_layers["rsi"]["score"]
  candidates[-1]["chain_score"]=15 if indicator_layers["macd"]["stage"]=="大周期→小周期" else 8 if indicator_layers["macd"]["stage"]=="小周期→大周期" else 0;candidates[-1]["chain_reason"]=" · ".join(indicator_layers["macd"]["evidence"])
 def ranked(key):return sorted(candidates,key=lambda x:(x[key],x["dollar_volume"]),reverse=True)[:10]
 multi=sorted(candidates,key=lambda x:(x["confluence_direction"] in ("buy","sell"),max(x["buy_layers"],x["sell_layers"]),x["ranking_score"],x["dollar_volume"],x["symbol"]),reverse=True)
 report={"generated_at":datetime.now(timezone.utc).isoformat(),"as_of":latest,"data_mode":"latest_completed_eod","intraday":{"available":False,"reason":"Current EODHD token returned HTTP 403 for the 1-hour intraday endpoint.","required":"EOD + Intraday All World Extended or a real-time WebSocket feed","four_hour_rule":"When connected, aggregate regular-session 1-hour bars and evaluate completed 4-hour candles only."},"universe":{"source":"所有已有完整历史缓存、且在最新美国市场收盘数据中仍活跃的股票","cached":len(symbols),"eligible":len(candidates),"filters":"股价不低于5美元，最新单日成交额不低于1000万美元，且至少具有35个月历史"},"definitions":{"macd":"零轴下新金叉权重大于零轴上；记录金叉所在区域、距今K线数和能量柱连续变化。","rsi":"新鲜底背离/超卖修复为看涨，顶背离为看跌；单纯超买不直接当作卖出。","ema":"收盘价、EMA20、EMA50同向排列且均线斜率一致，才确认趋势方向。","breakout":"只使用完整收盘价突破此前20根K线高低点，盘中刺穿不算。","multi":"四层必须全部同向才发布四重共振；方向相反时明确标记冲突，不用总分互相抵消。","warning":"周线和月线尚未收盘，信号可能在周期结束前发生变化。"},"multi_confluence_top10":multi[:10],"four_layer_bullish":[x for x in multi if x["confluence_direction"]=="buy"][:10],"four_layer_bearish":[x for x in multi if x["confluence_direction"]=="sell"][:10],"combined_top10":sorted((x for x in candidates if x["macd_buy_valid"] and x["rsi_divergence_frames"]),key=lambda x:(x["combined_score"],x["dollar_volume"]),reverse=True)[:10],"macd_top10":ranked("macd_score"),"rsi_top10":ranked("rsi_score"),"volume_top10":sorted((x for x in candidates if x["volume"]["score"]>0),key=lambda x:(x["volume"]["score"],x["volume"]["ratio"],x["dollar_volume"]),reverse=True)[:10]}
 report["definitions"]["macd"]="看涨优先零轴下新金叉；看跌只接受当前仍在零轴上、且零轴上形成的新死叉。零轴下死叉不作为强看跌证据。"
 report["definitions"]["rsi"]="底背离、超卖或超卖修复属于反弹证据；顶背离或超买回落属于看跌证据。两者并存必须标记冲突，不得发布纯看跌。"
 report["definitions"]["multi"]=RULESET["policy"]
 report["definitions"]["warning"]="方向只使用上一个完整周线和上一个完整月线；时机只使用最新完整日线，避免未完成大周期重绘。"
 report["ruleset"]=RULESET
 report["four_layer_bullish"]=[x for x in multi if x["strict_confluence"] and x["confluence_direction"]=="buy"][:10]
 report["four_layer_bearish"]=[x for x in multi if x["strict_confluence"] and x["confluence_direction"]=="sell"][:10]
 macd_order=lambda x:(x["macd_rank_score"],x["indicator_layers"]["macd"]["score"],x["dollar_volume"],x["symbol"])
 report["macd_buy_top10"]=sorted((x for x in candidates if x["indicator_layers"]["macd"]["direction"]=="buy"),key=macd_order,reverse=True)[:10]
 report["macd_sell_top10"]=sorted((x for x in candidates if x["indicator_layers"]["macd"]["direction"]=="sell"),key=macd_order,reverse=True)[:10]
 report["macd_top10"]=report["macd_buy_top10"]
 report["rsi_top10"]=sorted((x for x in candidates if x["indicator_layers"]["rsi"]["direction"]!="neutral"),key=lambda x:(x["indicator_layers"]["rsi"]["score"],x["dollar_volume"],x["symbol"]),reverse=True)[:10]
 report["combined_top10"]=sorted((x for x in candidates if x["indicator_layers"]["macd"]["direction"]==x["indicator_layers"]["rsi"]["direction"] and x["indicator_layers"]["macd"]["direction"]!="neutral"),key=lambda x:(x["indicator_layers"]["macd"]["score"]+x["indicator_layers"]["rsi"]["score"],x["dollar_volume"],x["symbol"]),reverse=True)[:10]
 report["bullish_watch_top10"]=[x for x in multi if x["ranking_direction"]=="buy" and x["confluence_direction"]!="conflict"][:10]
 report["bearish_watch_top10"]=[x for x in multi if x["ranking_direction"]=="sell" and x["confluence_direction"]!="conflict"][:10]
 early=[]
 for x in candidates:
  evidence=early_watch_evidence(x)
  if evidence:early.append({**x,"alert_status":"early_watch","early_watch_evidence":evidence})
 report["early_watch_top10"]=sorted(early,key=lambda x:(len(x["early_watch_evidence"]),x["macd_rank_score"],x["dollar_volume"],x["symbol"]),reverse=True)[:10]
 published={x["symbol"] for key in ("multi_confluence_top10","bullish_watch_top10","bearish_watch_top10","early_watch_top10","four_layer_bullish","four_layer_bearish","combined_top10","macd_buy_top10","macd_sell_top10","rsi_top10","volume_top10") for x in report[key]}
 report["details"]={x["symbol"]:x["_detail"] for x in candidates if x["symbol"] in published}
 report["ranking_method"]={"name":"多周期四层共振","version":RULESET["version"],"order":["四层严格同向优先","同向层数","固定规则分","最新成交额","股票代码"],"score":"每层固定25分：日线触发10分、完整周线方向8分、完整月线方向7分；四层合计100分。","warning":"这是规则匹配度，不是上涨或下跌概率；盈利潜力仍需样本外回测验证。"}
 digest_rows=[(x["symbol"],x["ranking_score"],x["ranking_direction"],x["layer_directions"]) for x in multi]
 report["consistency_audit"]={"ruleset_version":RULESET["version"],"ranking_digest":hashlib.sha256(json.dumps(digest_rows,sort_keys=True).encode()).hexdigest()[:16],"overview_uses_same_candidates":True,"sub_rankings_use_layer_scores":True,"details_cover_all_published":published==set(report["details"]),"duplicate_symbols":any(len(report[key])!=len({x["symbol"] for x in report[key]}) for key in ("bullish_watch_top10","bearish_watch_top10","macd_buy_top10","macd_sell_top10","rsi_top10")),"completed_higher_timeframes_only":True}
 for x in candidates:x.pop("_detail",None)
 pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,indent=2));return report
if __name__=="__main__":
 r=run();print(json.dumps({"as_of":r["as_of"],"eligible":r["universe"]["eligible"],"macd":[x["symbol"] for x in r["macd_top10"]],"rsi":[x["symbol"] for x in r["rsi_top10"]]},ensure_ascii=False,indent=2))
