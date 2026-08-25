"""Tracker Backtest V2: isolated stop-loss / risk-reward study on frozen V1 signals."""
from __future__ import annotations
import hashlib,json,pathlib,statistics
from collections import defaultdict
from datetime import datetime,timezone
from services.scanner.macd_factor_backtest import adjusted_rows
from services.scanner.technical import atr
ROOT=pathlib.Path(__file__).parents[2];CACHE=ROOT/"work/eodhd-cache";OUT=ROOT/"research/backtest/output"
TARGETS=(1.,1.5,2.,3.)
STOPS=(("support_1pct","Support −1%","pct",.01),("support_2pct","Support −2%","pct",.02),("support_3pct","Support −3%","pct",.03),("support_5pct","Support −5%","pct",.05),("support_0_5atr","Support −0.5 ATR","atr",.5),("support_1atr","Support −1 ATR","atr",1.))
def stop_price(s,a,k,v):return s*(1-v) if k=="pct" else s-a*v
def simulate(entry,stop,target,path):
 risk=entry-stop;mfe=mae=0.
 for bars,b in enumerate(path,1):
  mfe=max(mfe,b["high"]/entry-1);mae=min(mae,b["low"]/entry-1)
  if b["open"]<=stop:return b["open"],bars,"stop",mfe,mae
  if b["open"]>=target:return target,bars,"target",mfe,mae
  if b["low"]<=stop:return stop,bars,"stop",mfe,mae
  if b["high"]>=target:return target,bars,"target",mfe,mae
 return path[-1]["close"],len(path),"time",mfe,mae
def _dd(rows):
 by=defaultdict(list)
 for x in rows:by[x["date"]].append(x["return"])
 eq=peak=1.;worst=0.
 for d in sorted(by)[::40]:eq*=1+statistics.mean(by[d]);peak=max(peak,eq);worst=min(worst,eq/peak-1)
 return worst*100
def metrics(rows):
 if not rows:return {"samples":0}
 ret=[x["return"] for x in rows];r=[x["r"] for x in rows];w=[x for x in ret if x>0];l=[x for x in ret if x<0]
 return {"samples":len(rows),"win_rate":round(len(w)/len(rows)*100,2),"profit_factor":round(sum(w)/abs(sum(l)),3) if l else None,"expectancy_pct":round(statistics.mean(ret)*100,3),"average_r":round(statistics.mean(r),3),"stop_out_rate":round(sum(x["reason"]=="stop" for x in rows)/len(rows)*100,2),"max_drawdown_pct":round(_dd(rows),3),"average_holding_bars":round(statistics.mean(x["bars"] for x in rows),2),"mfe_pct":round(statistics.mean(x["mfe"] for x in rows)*100,3),"mae_pct":round(statistics.mean(x["mae"] for x in rows)*100,3),"average_risk_pct":round(statistics.mean(x["risk_pct"] for x in rows)*100,3),"target_hit_rate":round(sum(x["reason"]=="target" for x in rows)/len(rows)*100,2)}
def run(out_dir=OUT):
 out_dir=pathlib.Path(out_dir);source=out_dir/"signals.jsonl";raw=source.read_bytes();signals=[json.loads(x) for x in raw.splitlines() if x]
 cache={};idx={};curves={};trades=[];invalid=0
 for e in signals:
  t=e["ticker"]
  if t not in cache:
   rows=adjusted_rows(json.loads((CACHE/f"{t}.json").read_text()));cache[t]=rows;idx[t]={x["date"]:i for i,x in enumerate(rows)};curves[t]=atr(rows)
  rows=cache[t];i=idx[t].get(e["date"])
  if i is None or i+1>=len(rows) or rows[i+1]["date"]!=e["entry_date"] or abs(rows[i+1]["open"]-e["entry_open"])>.001:raise RuntimeError(f"V1 entry mismatch: {t} {e['date']}")
  s=e.get("support_level");a=curves[t][i]
  if not s or not a:invalid+=1;continue
  path=rows[i+1:i+41]
  for sid,label,kind,value in STOPS:
   stop=stop_price(s,a,kind,value);entry=e["entry_open"]
   # A near-zero risk denominator is not executable and makes Average R meaningless.
   if stop<=0 or stop>=entry or (entry-stop)/entry<=.001:invalid+=1;continue
   risk=entry-stop
   for target_r in TARGETS:
    fill,bars,reason,mfe,mae=simulate(entry,stop,entry+target_r*risk,path)
    trades.append({"ticker":t,"date":e["date"],"status":e["status"],"strict_long_trend":e["strict_long_trend"],"stop_id":sid,"target_r":target_r,"return":fill/entry-1,"r":(fill-entry)/risk,"reason":reason,"bars":bars,"mfe":mfe,"mae":mae,"risk_pct":risk/entry})
 groups={"all":lambda x:True,"early_watch":lambda x:x["status"]=="Early Watch","confirmed":lambda x:x["status"]=="Confirmed","strict_long_trend":lambda x:x["strict_long_trend"]}
 combos=[]
 for sid,label,_,_ in STOPS:
  for target_r in TARGETS:
   base=[x for x in trades if x["stop_id"]==sid and x["target_r"]==target_r]
   periods={n:metrics([x for x in base if lo<=x["date"]<=hi]) for n,lo,hi in (("development","0000","2024-12-31"),("validation_2025","2025-01-01","2025-12-31"),("forward_2026","2026-01-01","9999"))}
   combos.append({"stop_id":sid,"stop_label":label,"target_r":target_r,"groups":{n:metrics([x for x in base if f(x)]) for n,f in groups.items()},"periods":periods})
 report={"version":"2.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"source":{"v1_signals":"research/backtest/output/signals.jsonl","sha256":hashlib.sha256(raw).hexdigest(),"signals":len(signals),"entry":"unchanged V1 next trading day adjusted Open"},"audit":{"replayed_signals":len(signals),"future_data_for_atr":False,"atr_through_signal_date_only":True,"horizon_bars":40,"same_bar_stop_target":"stop first","invalid_scenarios":invalid,"production_outputs_written":False},"stop_definitions":[{"id":x[0],"label":x[1]} for x in STOPS],"targets_r":list(TARGETS),"combinations":combos,"methodology":["Signals, states, support and entries are unchanged from V1.","ATR is calculated through signal date only.","Stop-first on ambiguous daily bars; stop gaps fill at Open; target gaps receive no improvement.","Unresolved trades exit at the 40th adjusted Close.","Drawdown uses non-overlapping equal-weight 40-session cohorts, not a capital portfolio."]}
 (out_dir/"v2-summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n");return report
if __name__=="__main__":print(json.dumps(run()["audit"],indent=2))
