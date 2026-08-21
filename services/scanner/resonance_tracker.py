"""Multi-timeframe MACD/RSI resonance tracker using latest completed EOD bars."""
import json,pathlib,statistics
from datetime import date,datetime,timedelta,timezone
from .eodhd import get
from .research_pipeline import iso
from .technical import macd,rsi

def bulk_day(day,cache_dir="work/eodhd-bulk"):
 path=pathlib.Path(cache_dir)/f"{day}.json";path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():return json.loads(path.read_text())
 rows=get("eod-bulk-last-day/US",date=day);path.write_text(json.dumps(rows));return rows
def aggregate(rows,mode):
 groups={}
 for row in rows:
  d=datetime.strptime(row["date"],"%m/%d/%Y").date();key=(d.isocalendar().year,d.isocalendar().week) if mode=="weekly" else (d.year,d.month)
  groups.setdefault(key,[]).append(row)
 out=[]
 for values in groups.values():
  out.append({"date":values[-1]["date"],"open":values[0]["open"],"high":max(x["high"] for x in values),"low":min(x["low"] for x in values),"close":values[-1]["close"],"volume":sum(x["volume"] for x in values)})
 return out
def bullish_divergence(rows,values,window=45):
 end=len(rows)-1;lows=[]
 for i in range(max(2,end-window),end):
  if rows[i]["low"]<rows[i-1]["low"] and rows[i]["low"]<=rows[i+1]["low"] and values[i] is not None:lows.append(i)
 if len(lows)<2:return False
 a,b=lows[-2:];return rows[b]["low"]<rows[a]["low"] and values[b]>values[a]+2
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
def macd_state_score(state):
 """Transparent setup score: depressed/fresh signals outrank extended ones."""
 below=state["zero_zone"]=="零轴下"
 if state["bars_since_cross"] is not None:
  freshness=max(0,3-state["bars_since_cross"])
  return (8 if below else 4)+freshness
 if state["near_cross"]:return 6 if below else 3
 if state["negative_histogram_shrinking"]:return 5
 if state["histogram_rising"]:return 3 if below else 2
 return 1 if state["macd_line"]>state["signal_line"] else 0
def transmission_score(frames):
 """Reward daily trigger -> weekly confirmation -> monthly early improvement."""
 daily,weekly,monthly=(frames[x] for x in ("日线","周线","月线"))
 active=lambda x:x["bars_since_cross"] is not None or x["near_cross"] or x["negative_histogram_shrinking"]
 reasons=[];score=0
 if daily["bars_since_cross"] is not None and daily["zero_zone"]=="零轴下":score+=4;reasons.append("日线零轴下新金叉")
 if weekly["bars_since_cross"] is not None and weekly["zero_zone"]=="零轴下":score+=5;reasons.append("周线零轴下金叉确认")
 if monthly["negative_histogram_shrinking"] or (monthly["near_cross"] and monthly["zero_zone"]=="零轴下"):
  score+=5;reasons.append("月线零轴下空头柱收缩")
 if active(daily) and active(weekly) and (monthly["negative_histogram_shrinking"] or monthly["near_cross"]):
  score+=8;reasons.append("日线→周线→月线小带大")
 return score," · ".join(reasons) if reasons else "尚未形成小带大链条"
def timeframe_state(rows):
 if len(rows)<35:return None
 closes=[x["close"] for x in rows];line,signal=macd(closes);hist=[a-b for a,b in zip(line,signal)];rv=rsi(closes);i=len(rows)-1
 rising=hist[i]>hist[i-1] and hist[i-1]>=hist[i-2];cross=line[i]>signal[i] and line[i-1]<=signal[i-1]
 scale=statistics.pstdev(hist[-20:]) or 1;near=line[i]<=signal[i] and rising and abs(hist[i])<=scale*.35
 bars_since_cross=None
 for ago in range(0,min(8,i)):
  j=i-ago
  if line[j]>signal[j] and line[j-1]<=signal[j-1]:bars_since_cross=ago;break
 zone="零轴下" if line[i]<0 and signal[i]<0 else "零轴上" if line[i]>0 and signal[i]>0 else "穿越零轴"
 shrinking=hist[i]<0 and rising
 macd_label="金叉" if cross else f"金叉后{bars_since_cross}根" if bars_since_cross is not None else "准备金叉" if near else "空头柱收缩" if shrinking else "向上拐头" if rising else "多头" if line[i]>signal[i] else "未共振"
 recovering=rv[i] is not None and rv[i-1] is not None and rv[i]>30>=rv[i-1]
 divergence=bullish_divergence(rows,rv)
 rsi_label="底背离" if divergence else "超卖修复" if recovering else "超卖" if rv[i] is not None and rv[i]<=30 else "偏强" if rv[i] is not None and rv[i]>=50 else "中性"
 state={"macd":macd_label,"macd_line":round(line[i],4),"signal_line":round(signal[i],4),"macd_histogram":round(hist[i],4),"zero_zone":zone,"bars_since_cross":bars_since_cross,"near_cross":near,"histogram_rising":rising,"negative_histogram_shrinking":shrinking,"rsi":rsi_label,"rsi_score":4 if divergence else 3 if recovering else 2 if rv[i] is not None and rv[i]<=30 else 1 if rv[i] is not None and rv[i]>=50 else 0,"rsi_value":round(rv[i],1) if rv[i] is not None else None}
 state["macd_score"]=macd_state_score(state);return state
def run(out="public/resonance-tracker.json",as_of=None):
 panel=json.loads(pathlib.Path("work/eodhd-panel-v4.json").read_text())["panel"];symbols={x["symbol"] for x in panel}
 target=date.fromisoformat(as_of) if as_of else date.today();days=[]
 for offset in range(10):
  day=target-timedelta(days=offset)
  if day.weekday()<5:
   try:
    rows=bulk_day(day.isoformat())
    if rows:days.append((day,rows))
   except Exception:pass
  if len(days)>=3:break
 if not days:raise RuntimeError("No recent bulk EOD data available")
 days.sort();latest=days[-1][0].isoformat();updates={}
 for _,rows in days:
  for x in rows:
   if x.get("code") in symbols and x.get("adjusted_close") and x.get("close") and x.get("volume") is not None:updates.setdefault(x["code"],[]).append(x)
 candidates=[]
 for symbol,new in updates.items():
  if new[-1]["adjusted_close"]<5 or new[-1]["adjusted_close"]*new[-1]["volume"]<10_000_000:continue
  cache=pathlib.Path("work/eodhd-cache")/f"{symbol}.json"
  if not cache.exists():continue
  raw=json.loads(cache.read_text());known={x["date"] for x in raw};raw.extend(x for x in new if x["date"] not in known);raw.sort(key=lambda x:x["date"])
  adjusted=[]
  for x in raw:
   if not x.get("close") or not x.get("adjusted_close"):continue
   ratio=x["adjusted_close"]/x["close"];adjusted.append({"date":datetime.strptime(x["date"],"%Y-%m-%d").strftime("%m/%d/%Y"),"open":x["open"]*ratio,"high":x["high"]*ratio,"low":x["low"]*ratio,"close":x["adjusted_close"],"volume":int(x["volume"])})
  frames={"日线":timeframe_state(adjusted),"周线":timeframe_state(aggregate(adjusted,"weekly")),"月线":timeframe_state(aggregate(adjusted,"monthly"))}
  if any(v is None for v in frames.values()):continue
  chain_score,chain_reason=transmission_score(frames);base_score=sum(x["macd_score"] for x in frames.values());rsi_score=sum(x["rsi_score"] for x in frames.values());volume=volume_state(adjusted)
  divergence_frames=[name for name,state in frames.items() if state["rsi"]=="底背离"]
  confluence_bonus=(8 if divergence_frames and chain_score>=8 else 0)+(4 if volume["near_bottom"] and volume["score"]>=4 and (divergence_frames or chain_score>=8) else 0)
  combined_score=base_score+chain_score+rsi_score+volume["score"]+confluence_bonus
  candidates.append({"symbol":symbol,"price":round(adjusted[-1]["close"],2),"dollar_volume":round(adjusted[-1]["close"]*adjusted[-1]["volume"]),"frames":frames,"macd_score":base_score+chain_score,"macd_base_score":base_score,"chain_score":chain_score,"chain_reason":chain_reason,"rsi_score":rsi_score,"rsi_divergence_frames":divergence_frames,"volume":volume,"confluence_bonus":confluence_bonus,"combined_score":combined_score,"signal_count":int(chain_score>=8)+int(bool(divergence_frames))+int(volume["score"]>=4),"macd_resonance":sum(x["macd_score"]>=2 for x in frames.values()),"rsi_resonance":sum(x["rsi_score"]>=2 for x in frames.values())})
 def ranked(key):return sorted(candidates,key=lambda x:(x[key],x["dollar_volume"]),reverse=True)[:10]
 report={"generated_at":datetime.now(timezone.utc).isoformat(),"as_of":latest,"data_mode":"latest_completed_eod","intraday":{"available":False,"reason":"Current EODHD token returned HTTP 403 for the 1-hour intraday endpoint.","required":"EOD + Intraday All World Extended or a real-time WebSocket feed","four_hour_rule":"When connected, aggregate regular-session 1-hour bars and evaluate completed 4-hour candles only."},"universe":{"source":"Current members of the survivorship-aware research sample present in the latest US bulk close","eligible":len(candidates),"filters":"Price >= $5 and latest dollar volume >= $10m"},"definitions":{"macd":"零轴下新金叉权重大于零轴上；额外奖励日线触发、周线确认、月线空头柱收缩的小带大链条。","weights":"零轴下新金叉8分起，零轴上4分起；3根K线内保留新鲜度；完整小带大链条另加8分。","rsi":"价格创新低、RSI低点却抬高，识别日线/周线/月线底背离。","volume":"最新成交量至少为过去20日均量1.8倍；价格距60日低点不超过12%或较60日高点回撤18%，标记为底部放量。","combined":"组合榜必须同时出现MACD小带大链条和至少一个周期的RSI底背离；底部放量作为第三项增强证据。","warning":"The current weekly and monthly bars are still forming and signals may change before period close."},"combined_top10":sorted((x for x in candidates if x["chain_score"]>=8 and x["rsi_divergence_frames"]),key=lambda x:(x["combined_score"],x["dollar_volume"]),reverse=True)[:10],"macd_top10":ranked("macd_score"),"rsi_top10":ranked("rsi_score"),"volume_top10":sorted((x for x in candidates if x["volume"]["score"]>0),key=lambda x:(x["volume"]["score"],x["volume"]["ratio"],x["dollar_volume"]),reverse=True)[:10]}
 pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,indent=2));return report
if __name__=="__main__":
 r=run();print(json.dumps({"as_of":r["as_of"],"eligible":r["universe"]["eligible"],"macd":[x["symbol"] for x in r["macd_top10"]],"rsi":[x["symbol"] for x in r["rsi_top10"]]},ensure_ascii=False,indent=2))
