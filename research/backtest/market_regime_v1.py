"""Point-in-time Market Regime V1 for the frozen Tracker V2 Long benchmark."""
from __future__ import annotations
import bisect,json,pathlib,statistics
from collections import defaultdict
from datetime import datetime,timezone
from services.scanner.macd_factor_backtest import adjusted_rows,completed_groups,ema
from services.scanner.resonance_tracker import macd
from research.backtest.tracker_backtest_v2 import simulate,metrics

ROOT=pathlib.Path(__file__).parents[2];CACHE=ROOT/"work/eodhd-cache";OUT=ROOT/"research/backtest/output"

def _market_arrays(rows):
 close=[x["close"] for x in rows];e50=ema(close,50);e200=ema(close,200);line,signal=macd(close);hist=[a-b for a,b in zip(line,signal)]
 weeks=completed_groups(rows,"weekly");wrows=[x[1] for x in weeks];wclose=[x["close"] for x in wrows];wl,ws=macd(wclose);wh=[a-b for a,b in zip(wl,ws)]
 return {"rows":rows,"dates":[x["date"] for x in rows],"e50":e50,"e200":e200,"line":line,"signal":signal,"hist":hist,"weeks":weeks,"wline":wl,"wsignal":ws,"whist":wh}

def benchmark_state(arr,date):
 i=bisect.bisect_right(arr["dates"],date)-1
 if i<220:return None
 row=arr["rows"][i];trend=sum((row["close"]>arr["e50"][i],row["close"]>arr["e200"][i],arr["e50"][i]>arr["e200"][i],arr["e200"][i]>arr["e200"][i-20]))*5
 bullish=arr["line"][i]>arr["signal"][i];strength=arr["hist"][i]>arr["hist"][i-1];recent_cross=any(arr["line"][j]>arr["signal"][j] and arr["line"][j-1]<=arr["signal"][j-1] for j in range(max(1,i-5),i+1));pre=(not bullish and arr["hist"][i]<0 and arr["hist"][i]>arr["hist"][i-1]>=arr["hist"][i-2])
 # Current calendar week is incomplete at a daily close, so use only the prior completed weekly bar.
 d=datetime.strptime(date,"%Y-%m-%d").date();key=(d.isocalendar().year,d.isocalendar().week);keys=[x[0] for x in arr["weeks"]];wi=bisect.bisect_left(keys,key)-1
 weekly_bull=wi>=2 and arr["wline"][wi]>arr["wsignal"][wi];weekly_strength=wi>=2 and arr["whist"][wi]>arr["whist"][wi-1]
 momentum=(4 if bullish else 0)+(2 if strength else 0)+(2 if recent_cross or pre else 0)+(4 if weekly_bull else 0)+(3 if weekly_strength else 0)
 return {"date":arr["rows"][i]["date"],"close":round(row["close"],2),"above_50dma":row["close"]>arr["e50"][i],"above_200dma":row["close"]>arr["e200"][i],"dma50_above_200":arr["e50"][i]>arr["e200"][i],"dma200_slope_positive":arr["e200"][i]>arr["e200"][i-20],"daily_macd":"confirmed_bullish" if bullish else "bullish_pre_cross" if pre else "bearish","daily_histogram":"strengthening" if strength else "weakening","weekly_macd":"bullish" if weekly_bull else "bearish","weekly_histogram":"strengthening" if weekly_strength else "weakening","trend_score":trend,"momentum_score":momentum}

def breadth_inputs(symbols):
 out=[]
 for symbol in symbols:
  path=CACHE/f"{symbol}.json"
  if not path.exists():continue
  rows=adjusted_rows(json.loads(path.read_text()))
  if len(rows)<220:continue
  close=[x["close"] for x in rows];out.append((rows,[x["date"] for x in rows],ema(close,50),ema(close,200)))
 return out

def breadth_state(inputs,date):
 counts=[0,0,0,0];eligible=0
 for rows,dates,e50,e200 in inputs:
  i=bisect.bisect_right(dates,date)-1
  if i<220 or dates[i]!=date:continue
  eligible+=1;c=rows[i]["close"];slope=e200[i]>e200[i-20]
  counts[0]+=c>e50[i];counts[1]+=c>e200[i];counts[2]+=c>e50[i]>e200[i] and slope;counts[3]+=c<e50[i]<e200[i] and not slope
 if not eligible:return None
 above50,above200,bull,bear=[x/eligible*100 for x in counts];score=.3*(above50+above200+bull+(100-bear))/4
 return {"eligible":eligible,"above_50dma_pct":round(above50,2),"above_200dma_pct":round(above200,2),"bullish_trend_pct":round(bull,2),"bearish_trend_pct":round(bear,2),"score":round(score,2)}

def classify(score):return "Risk-On" if score>=65 else "Risk-Off" if score<40 else "Neutral"

def _benchmark_trades(signals):
 cache={};index={};out=[]
 for e in signals:
  if e["status"]!="Confirmed" or not e["strict_long_trend"] or not e.get("support_level"):continue
  t=e["ticker"]
  if t not in cache:
   cache[t]=adjusted_rows(json.loads((CACHE/f"{t}.json").read_text()));index[t]={x["date"]:i for i,x in enumerate(cache[t])}
  rows=cache[t];i=index[t][e["date"]];entry=e["entry_open"];stop=e["support_level"]*.95;risk=entry-stop
  if risk/entry<=.001:continue
  fill,bars,reason,mfe,mae=simulate(entry,stop,entry+2*risk,rows[i+1:i+41])
  out.append({"ticker":t,"date":e["date"],"return":fill/entry-1,"r":(fill-entry)/risk,"reason":reason,"bars":bars,"mfe":mfe,"mae":mae,"risk_pct":risk/entry})
 return out

def run(out_dir=OUT):
 out_dir=pathlib.Path(out_dir);signals=[json.loads(x) for x in (out_dir/"signals.jsonl").read_text().splitlines() if x];trades=_benchmark_trades(signals)
 panel=json.loads((ROOT/"work/eodhd-panel-v4.json").read_text());symbols=sorted({x["symbol"] for x in panel["panel"]});breadth=breadth_inputs(symbols)
 markets={s:_market_arrays(adjusted_rows(json.loads((CACHE/f"{s}.json").read_text()))) for s in ("SPY","QQQ")}
 market_dates=sorted(set(markets["SPY"]["dates"])&set(markets["QQQ"]["dates"]));needed=sorted({x["date"] for x in trades}|set(market_dates[-120:]))
 regimes={}
 for n,date in enumerate(needed,1):
  spy=benchmark_state(markets["SPY"],date);qqq=benchmark_state(markets["QQQ"],date);b=breadth_state(breadth,date)
  if not spy or not qqq or not b:continue
  trend=spy["trend_score"]+qqq["trend_score"];momentum=spy["momentum_score"]+qqq["momentum_score"];score=round(trend+momentum+b["score"],2)
  regimes[date]={"date":date,"regime":classify(score),"score":score,"trend_score":trend,"momentum_score":momentum,"breadth_score":b["score"],"spy":spy,"qqq":qqq,"breadth":b}
 tagged=[{**x,"regime":regimes[x["date"]]["regime"]} for x in trades if x["date"] in regimes]
 groups={name:metrics([x for x in tagged if x["regime"]==name]) for name in ("Risk-On","Neutral","Risk-Off")};groups["All"]=metrics(tagged)
 periods={}
 for label,lo,hi in (("development","0000","2024-12-31"),("validation_2025","2025-01-01","2025-12-31"),("forward_2026","2026-01-01","9999")):
  periods[label]={name:metrics([x for x in tagged if lo<=x["date"]<=hi and x["regime"]==name]) for name in ("Risk-On","Neutral","Risk-Off")}
 allm=groups["All"];risk=groups["Risk-On"]
 report={"version":"1.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"benchmark":{"definition":"Confirmed + strict long trend + next adjusted Open + Support −5% Stop + 2R TP","frozen":True,"expected_v2":{"profit_factor":1.159,"expectancy_pct":.694},"reconstructed":allm},"rules":{"trend":{"weight":40,"items":"SPY and QQQ: Close>50DMA, Close>200DMA, 50DMA>200DMA, positive 20D 200DMA slope; 5 points each"},"momentum":{"weight":30,"items":"Each index: daily MACD direction 4, histogram direction 2, recent/pre-cross 2, prior completed-week MACD 4, weekly histogram 3"},"breadth":{"weight":30,"items":"Equal-weight continuous average of above50, above200, bullish trend, inverse bearish trend"},"classification":{"Risk-On":">=65","Neutral":"40 to <65","Risk-Off":"<40"}},"audit":{"point_in_time":True,"weekly_bars":"prior completed week only","future_rows_used":False,"universe_symbols":len(symbols),"breadth_histories":len(breadth),"tagged_benchmark_trades":len(tagged),"production_outputs_written":False},"current":regimes[max(regimes)],"timeline":[regimes[x] for x in sorted(regimes)[-120:]],"by_regime":groups,"by_period_regime":periods,"answers":{"risk_on_vs_all":{"sample_reduction_pct":round((1-risk["samples"]/allm["samples"])*100,2),"pf_change":round(risk["profit_factor"]-allm["profit_factor"],3),"expectancy_change_pct":round(risk["expectancy_pct"]-allm["expectancy_pct"],3),"drawdown_change_pct":round(risk["max_drawdown_pct"]-allm["max_drawdown_pct"],3)},"direction_consistency":"See by_period_regime; no parameter was selected or optimized."},"limitations":["Research cache current date may lag the production daily pipeline; the page displays its own as-of date.","Breadth uses the deterministic V1 survivorship-aware universe with partial delisted coverage, not the complete historical US market.","Regime thresholds and weights are fixed ex ante and were not fitted to returns.","Signals overlap; drawdown remains the V2 non-overlapping cohort diagnostic."]}
 (out_dir/"market-regime-v1.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n");return report
if __name__=="__main__":print(json.dumps(run()["answers"],indent=2))
