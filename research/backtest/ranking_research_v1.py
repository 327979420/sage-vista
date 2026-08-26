"""Ranking Research V1: five fixed rankers on one point-in-time candidate pool."""
from __future__ import annotations
import hashlib,json,pathlib
from collections import defaultdict
from datetime import datetime,timezone
from research.backtest.tracker_backtest_v1 import replay_symbol
from research.backtest.tracker_backtest_v2 import simulate,metrics

ROOT=pathlib.Path(__file__).parents[2];CACHE=ROOT/"work/eodhd-cache";OUT=ROOT/"research/backtest/output";SEED="sage-vista-ranking-v1-seed-2026"
PERIODS=(("development","0000","2024-12-31"),("validation_2025","2025-01-01","2025-12-31"),("forward_2026","2026-01-01","9999"))
BUCKETS=(("Rank 1–3",1,3),("Rank 4–6",4,6),("Rank 7–10",7,10))

def trade(event):
 if event["status"]!="Confirmed" or not event["strict_long_trend"] or not event.get("support_level"):return None
 rows=event.pop("_rows");i=event.pop("_i");entry=rows[i+1]["open"];stop=event["support_level"]*.95;risk=entry-stop
 if risk/entry<=.001:return None
 fill,bars,reason,mfe,mae=simulate(entry,stop,entry+2*risk,rows[i+1:i+41])
 return {"ticker":event["ticker"],"date":event["date"],"macd":event["macd_ranking_score"],"factor":event["multi_factor_total_score"],"return":fill/entry-1,"r":(fill-entry)/risk,"reason":reason,"bars":bars,"mfe":mfe,"mae":mae,"risk_pct":risk/entry}

def percentile(values,value):
 unique=sorted(set(values));return .5 if len(unique)==1 else unique.index(value)/(len(unique)-1)

def order_day(rows,method):
 if method=="A":return sorted(rows,key=lambda x:(x["macd"],x["ticker"]),reverse=True)
 if method=="B":return sorted(rows,key=lambda x:(x["factor"],x["ticker"]),reverse=True)
 if method=="C":
  mv=[x["macd"] for x in rows];fv=[x["factor"] for x in rows]
  return sorted(rows,key=lambda x:(.5*percentile(mv,x["macd"])+.5*percentile(fv,x["factor"]),x["ticker"]),reverse=True)
 if method=="D":return sorted(rows,key=lambda x:hashlib.sha256(f"{SEED}|{x['date']}|{x['ticker']}".encode()).hexdigest())
 raise ValueError(method)

def compact(rows):
 m=metrics(rows);return {k:m.get(k) for k in ("samples","win_rate","profit_factor","expectancy_pct","average_r","max_drawdown_pct")}

def summarize_method(by_date,method,min_candidates=1):
 ranked=[]
 for date,rows in sorted(by_date.items()):
  if len(rows)<min_candidates:continue
  for rank,row in enumerate(order_day(rows,method)[:10],1):ranked.append({**row,"rank":rank})
 buckets=[]
 for name,lo,hi in BUCKETS:
  selected=[x for x in ranked if lo<=x["rank"]<=hi]
  buckets.append({"bucket":name,"overall":compact(selected),"periods":{p:compact([x for x in selected if a<=x["date"]<=b]) for p,a,b in PERIODS}})
 exps=[x["overall"]["expectancy_pct"] for x in buckets];pfs=[x["overall"]["profit_factor"] for x in buckets]
 return {"method":method,"minimum_daily_candidates":min_candidates,"selected_signals":len(ranked),"buckets":buckets,"monotonic_expectancy":all(a>b for a,b in zip(exps,exps[1:])),"monotonic_profit_factor":all(a>b for a,b in zip(pfs,pfs[1:]))}

def run(start="2010-01-01",out_dir=OUT):
 panel=json.loads((ROOT/"work/eodhd-panel-v4.json").read_text());listing={x["symbol"]:x.get("listing_status","unknown") for x in panel["panel"]};rows=[]
 for n,symbol in enumerate(sorted(listing),1):
  path=CACHE/f"{symbol}.json"
  if path.exists():
   for event in replay_symbol(path,listing[symbol],start):
    result=trade(event)
    if result:rows.append(result)
  if n%25==0:print(json.dumps({"progress":n,"symbols":len(listing),"benchmark_candidates":len(rows)}),flush=True)
 by_date=defaultdict(list)
 for x in rows:by_date[x["date"]].append(x)
 methods=[summarize_method(by_date,x) for x in ("A","B","C","D")];common_days=[summarize_method(by_date,x,10) for x in ("A","B","C","D")]
 no_rank={"method":"E","label":"No Ranking Control","overall":compact(rows),"periods":{p:compact([x for x in rows if a<=x["date"]<=b]) for p,a,b in PERIODS}}
 labels={"A":"MACD Ranking","B":"Multi-Factor Ranking","C":"Hybrid Ranking","D":"Random Control"}
 for collection in (methods,common_days):
  for x in collection:x["label"]=labels[x["method"]]
 counts=[len(x) for x in by_date.values()]
 report={"version":"1.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"benchmark":{"definition":"Confirmed + strict long trend + next adjusted Open + Support −5% + 2R TP","candidate_pool_signals":len(rows),"candidate_days":len(by_date),"days_with_4_plus":sum(x>=4 for x in counts),"days_with_7_plus":sum(x>=7 for x in counts),"days_with_10_plus":sum(x>=10 for x in counts),"maximum_daily_candidates":max(counts)},"rules":{"A":"Sort by existing MACD ranking score only.","B":"MACD admits candidates; sort by existing Multi-Factor total score only.","C":"Fixed 50/50 average of within-day MACD-score percentile and Multi-Factor-score percentile.","D":f"SHA-256 deterministic random order with fixed seed {SEED}.","E":"All eligible candidates; no rank or Top 10 selection."},"methods":methods,"common_10_candidate_days":common_days,"no_ranking":no_rank,"audit":{"point_in_time_candidate_replay":True,"completed_weekly_monthly_only":True,"entry_and_exit_unchanged":True,"future_data_for_ranking":False,"automatic_weight_optimization":False,"combination_search":False,"production_outputs_written":False},"limitations":["Random Control is one prespecified reproducible ordering, not a distribution over many seeds.","Daily candidate counts vary; lower rank buckets contain fewer observations on sparse days.","The >=10-candidate common-day diagnostic is the fair bucket comparison but may be too small for inference.","Rank bucket comparisons are observational and signals overlap.","Historical universe retains partial delisted coverage and survivorship limitations.","No production rank, factor weight, scanner, Discord or daily automation is changed."]}
 out_dir=pathlib.Path(out_dir);(out_dir/"ranking-research-v1.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n");(out_dir/"ranking-research-v1-candidates.jsonl").write_text("\n".join(json.dumps(x,ensure_ascii=False,separators=(",",":")) for x in rows)+"\n");return report
if __name__=="__main__":
 r=run();print(json.dumps({"benchmark":r["benchmark"],"monotonic":{x["method"]:[x["monotonic_expectancy"],x["monotonic_profit_factor"]] for x in r["methods"]}},indent=2))
