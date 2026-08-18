"""Test whether mainstream ETF context gates improve technical-factor portfolios."""
import json,pathlib
from datetime import datetime,timezone
from .eodhd_factor_pilot import adjusted_rows
from .eodhd_factor_validation import COMBINATIONS,evaluate_portfolios
from .research_pipeline import SPLIT_BOUNDS,iso

PAIRS={"growth":"QQQ/SPY","small_cap":"IWM/SPY","breadth":"RSP/SPY","credit":"HYG/LQD","value":"IWD/IWF","momentum":"MTUM/SPY"}
def price_maps(code):return {iso(x["date"]):x["close"] for x in adjusted_rows(code)}
def ratio_signal(a,b,date,lookback=20):
 dates=sorted(set(a)&set(b));index={d:i for i,d in enumerate(dates)};i=index.get(date)
 if i is None or i<lookback:return None
 return (a[dates[i]]/b[dates[i]])/(a[dates[i-lookback]]/b[dates[i-lookback]])-1
def scenario(panel,gate,start,end):
 on=[x for x in panel if start<=x["date"]<=end and gate.get(x["date"]) is True];off=[x for x in panel if start<=x["date"]<=end and gate.get(x["date"]) is False]
 def extract(rows):
  result={}
  for x in evaluate_portfolios(rows,10):result[x["combination"]]=x["cost_scenarios_bps"]["20"]["excess_vs_eligible_universe"]
  return result
 return {"enabled":extract(on),"disabled":extract(off),"enabled_dates":len({x["date"] for x in on}),"disabled_dates":len({x["date"] for x in off})}
def run(cache="work/eodhd-panel-v4.json",out="public/market-context-factor-test.json"):
 panel=json.loads(pathlib.Path(cache).read_text())["panel"]
 for row in panel:row["forward"]={int(k):v for k,v in row["forward"].items()}
 panel=[x for x in panel if x["regime"]=="risk_on"]
 codes={x for pair in PAIRS.values() for x in pair.split("/")};maps={x:price_maps(x) for x in codes};dates={x["date"] for x in panel};gates={}
 for name,pair in PAIRS.items():
  a,b=pair.split("/");gates[name]={d:(v>0 if (v:=ratio_signal(maps[a],maps[b],d)) is not None else None) for d in dates}
 tests={name:{split:scenario(panel,gate,*bounds) for split,bounds in SPLIT_BOUNDS.items()} for name,gate in gates.items()};verdicts=[]
 for gate in PAIRS:
  for combo in COMBINATIONS:
   d=tests[gate]["development"];v=tests[gate]["validation"];f=tests[gate]["forward_test"];de=d["enabled"][combo];dd=d["disabled"][combo];ve=v["enabled"][combo];fe=f["enabled"][combo];uplift=(de.get("mean_return") or 0)-(dd.get("mean_return") or 0)
   direction_ok=uplift>0 and (ve.get("mean_return") or 0)>0 and (fe.get("mean_return") or 0)>=0
   enough_evidence=v["enabled_dates"]>=6 and f["enabled_dates"]>=3
   verdict="candidate_for_more_testing" if direction_ok and enough_evidence else "insufficient_evidence" if direction_ok else "not_stable"
   verdicts.append({"gate":gate,"pair":PAIRS[gate],"combination":combo,"development_uplift":round(uplift,4),"validation_enabled_mean":ve.get("mean_return"),"forward_enabled_mean":fe.get("mean_return"),"validation_dates":v["enabled_dates"],"forward_dates":f["enabled_dates"],"verdict":verdict})
 report={"generated_at":datetime.now(timezone.utc).isoformat(),"status":"research_only_multiple_hypothesis_test","design":{"base_universe":"Risk-on, liquid US stocks from survivorship-aware active and delisted sample","signal":"ETF ratio positive over trailing 20 trading days","portfolio":"Top quintile of each predefined technical combination","outcome":"10-day next-open excess return versus eligible universe after 20 bps cost","warning":"Six gates times three combinations creates 18 hypotheses; no result is promoted without further out-of-sample evidence."},"pairs":PAIRS,"tests":tests,"verdicts":verdicts};pathlib.Path(out).write_text(json.dumps(report,indent=2));return report
if __name__=="__main__":
 r=run();print(json.dumps([x for x in r["verdicts"] if x["verdict"]=="candidate_for_more_testing"],indent=2))
