"""Test whether mainstream ETF context improves technical-factor portfolios."""
import json,pathlib,random,statistics
from datetime import datetime,timezone
from .eodhd_factor_pilot import adjusted_rows
from .eodhd_factor_validation import COMBINATIONS,evaluate_portfolios,percentile_scores
from .research_pipeline import SPLIT_BOUNDS,iso,spearman

PAIRS={"growth":"QQQ/SPY","small_cap":"IWM/SPY","breadth":"RSP/SPY","credit":"HYG/LQD","value":"IWD/IWF","momentum":"MTUM/SPY"}
def price_maps(code):return {iso(x["date"]):x["close"] for x in adjusted_rows(code)}
def ratio_signal(a,b,date,lookback=20):
 dates=sorted(set(a)&set(b));index={d:i for i,d in enumerate(dates)};i=index.get(date)
 if i is None or i<lookback:return None
 return (a[dates[i]]/b[dates[i]])/(a[dates[i-lookback]]/b[dates[i-lookback]])-1
def monthly_excess(panel,combination,horizon=10,cost_bps=20):
 groups={}
 for row in panel:groups.setdefault(row["date"],[]).append(row)
 out={};factors=COMBINATIONS[combination]
 for date,rows in sorted(groups.items()):
  scores=percentile_scores(rows,factors);valid=[x for x in rows if x["symbol"] in scores and x["forward"].get(horizon) is not None]
  if len(valid)<10:continue
  chosen=sorted(valid,key=lambda x:scores[x["symbol"]],reverse=True)[:max(1,len(valid)//5)]
  out[date]=statistics.mean(x["forward"][horizon] for x in chosen)-statistics.mean(x["forward"][horizon] for x in valid)-cost_bps/10000
 return out
def bootstrap_relation(context,returns,repetitions=2000,seed=1729):
 pairs=[(context[d],returns[d]) for d in sorted(set(context)&set(returns)) if context[d] is not None]
 if len(pairs)<3:return {"dates":len(pairs),"spearman":None,"ci_95":[None,None],"p_one_sided":None}
 observed=spearman([x[0] for x in pairs],[x[1] for x in pairs]);rng=random.Random(seed);boot=[]
 for _ in range(repetitions):
  sample=[pairs[rng.randrange(len(pairs))] for _ in pairs];value=spearman([x[0] for x in sample],[x[1] for x in sample])
  if value is not None:boot.append(value)
 boot.sort();lo=boot[int(.025*(len(boot)-1))];hi=boot[int(.975*(len(boot)-1))]
 return {"dates":len(pairs),"spearman":round(observed,4),"ci_95":[round(lo,4),round(hi,4)],"p_one_sided":round((sum(x<=0 for x in boot)+1)/(len(boot)+1),4)}
def bh_adjust(items):
 ordered=sorted(items,key=lambda x:x[1]);m=len(ordered);adjusted={};running=1.0
 for rank,(key,p) in reversed(list(enumerate(ordered,1))):running=min(running,p*m/rank);adjusted[key]=round(running,4)
 return adjusted
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
 continuous=[]
 for gate,pair in PAIRS.items():
  a,b=pair.split("/");context={d:ratio_signal(maps[a],maps[b],d) for d in dates}
  for combo in COMBINATIONS:
   returns=monthly_excess(panel,combo);splits={}
   for split,(start,end) in SPLIT_BOUNDS.items():splits[split]=bootstrap_relation({d:v for d,v in context.items() if start<=d<=end},{d:v for d,v in returns.items() if start<=d<=end},seed=1729+len(continuous)*11+len(splits))
   continuous.append({"gate":gate,"pair":pair,"combination":combo,"splits":splits})
 adjusted=bh_adjust([((x["gate"],x["combination"]),x["splits"]["development"]["p_one_sided"] or 1) for x in continuous])
 for x in continuous:
  d=x["splits"]["development"];v=x["splits"]["validation"];f=x["splits"]["forward_test"];x["development_q_bh"]=adjusted[(x["gate"],x["combination"])]
  x["verdict"]="candidate_for_more_testing" if d["ci_95"][0] is not None and d["ci_95"][0]>0 and x["development_q_bh"]<=.1 and (v["spearman"] or 0)>0 and (f["spearman"] or 0)>=0 and v["dates"]>=6 and f["dates"]>=3 else "not_confirmed"
 report={"generated_at":datetime.now(timezone.utc).isoformat(),"status":"research_only_multiple_hypothesis_test","design":{"base_universe":"Risk-on, liquid US stocks from survivorship-aware active and delisted sample","binary_signal":"ETF ratio positive over trailing 20 trading days","continuous_signal":"Magnitude of ETF relative return over trailing 20 trading days","portfolio":"Top quintile of each predefined technical combination","outcome":"10-day next-open excess return versus eligible universe after 20 bps cost","inference":"2,000 deterministic paired bootstrap samples; 95% interval; development p-values controlled with Benjamini-Hochberg","warning":"Six contexts times three combinations creates 18 hypotheses; no result is promoted without corrected development evidence and later-period confirmation."},"pairs":PAIRS,"tests":tests,"verdicts":verdicts,"continuous_results":continuous};pathlib.Path(out).write_text(json.dumps(report,indent=2));return report
if __name__=="__main__":
 r=run();print(json.dumps([x for x in r["verdicts"] if x["verdict"]=="candidate_for_more_testing"],indent=2))
