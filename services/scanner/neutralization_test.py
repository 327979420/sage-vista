"""Point-in-time proxy sector and market-beta neutralization experiment."""
import json,math,pathlib,statistics
from datetime import datetime,timezone
from .eodhd_factor_pilot import adjusted_rows
from .eodhd_factor_validation import COMBINATIONS,percentile_scores,portfolio_stats
from .research_pipeline import SPLIT_BOUNDS,iso

SECTOR_ETFS=("XLB","XLC","XLE","XLF","XLI","XLK","XLP","XLRE","XLU","XLV","XLY")
def prepare_returns(rows):
 dates=[iso(x["date"]) for x in rows]
 values=[None]+[rows[i]["close"]/rows[i-1]["close"]-1 for i in range(1,len(rows))]
 return dates,values,{d:i for i,d in enumerate(dates)}
def aligned_returns(rows,end_date,lookback=252):
 dates,values,index=rows if isinstance(rows,tuple) else prepare_returns(rows);end=index.get(end_date)
 if end is None or end<lookback:return None
 return {dates[i]:values[i] for i in range(end-lookback+1,end+1)}
def covariance(x,y):
 if len(x)<2:return None
 mx,my=statistics.mean(x),statistics.mean(y)
 return sum((a-mx)*(b-my) for a,b in zip(x,y))/(len(x)-1)
def correlation(a,b,min_obs=126):
 dates=sorted(set(a)&set(b));x=[a[d] for d in dates];y=[b[d] for d in dates]
 if len(x)<min_obs:return None
 cov=covariance(x,y);vx=covariance(x,x);vy=covariance(y,y)
 return cov/math.sqrt(vx*vy) if cov is not None and vx and vy else None
def point_in_time_exposure(stock,benchmarks,date):
 own=aligned_returns(stock,date)
 if not own:return {"sector":None,"beta":None}
 spy=aligned_returns(benchmarks["SPY"],date);common=sorted(set(own)&set(spy or {}))
 beta=None
 if len(common)>=126:
  x=[own[d] for d in common];m=[spy[d] for d in common];var=covariance(m,m)
  beta=covariance(x,m)/var if var else None
 scored=[]
 for code in SECTOR_ETFS:
  value=correlation(own,aligned_returns(benchmarks[code],date) or {})
  if value is not None:scored.append((value,code))
 return {"sector":max(scored)[1] if scored else None,"beta":beta}
def sector_scores(rows,factors):
 groups={}
 for row in rows:
  if row.get("sector_proxy"):groups.setdefault(row["sector_proxy"],[]).append(row)
 scores={}
 for members in groups.values():
  if len(members)>=5:scores.update(percentile_scores(members,factors))
 return scores
def benchmark_forward(rows,horizon=10):
 out={}
 for i,row in enumerate(rows):
  if i+1<len(rows) and i+horizon<len(rows):out[iso(row["date"])]=rows[i+horizon]["close"]/rows[i+1]["open"]-1
 return out
def evaluate(panel,spy_forward,start,end,horizon=10,stock_cost_bps=20,hedge_cost_bps=5):
 groups={}
 for row in panel:
  if start<=row["date"]<=end:groups.setdefault(row["date"],[]).append(row)
 result={}
 for name,factors in COMBINATIONS.items():
  streams={"baseline":[],"sector_neutral":[],"sector_and_beta_neutral":[]};coverage=[]
  for date,rows in sorted(groups.items()):
   valid=[x for x in rows if x["forward"].get(horizon) is not None];market=spy_forward.get(date)
   if len(valid)<10 or market is None:continue
   universe=statistics.mean(x["forward"][horizon] for x in valid)
   raw=percentile_scores(valid,factors);sector=sector_scores(valid,factors)
   for label,scores in (("baseline",raw),("sector_neutral",sector)):
    eligible=[x for x in valid if x["symbol"] in scores]
    if len(eligible)<10:continue
    chosen=sorted(eligible,key=lambda x:scores[x["symbol"]],reverse=True)[:max(1,len(eligible)//5)]
    top=statistics.mean(x["forward"][horizon] for x in chosen)
    streams[label].append(top-universe-stock_cost_bps/10000)
    if label=="sector_neutral":
     with_beta=[x for x in chosen if x.get("beta") is not None]
     if len(with_beta)>=max(3,len(chosen)//2):
      portfolio=statistics.mean(x["forward"][horizon] for x in with_beta);beta=statistics.mean(x["beta"] for x in with_beta)
      streams["sector_and_beta_neutral"].append(portfolio-beta*market-stock_cost_bps/10000-abs(beta)*hedge_cost_bps/10000)
      coverage.append(len(with_beta)/len(chosen))
  result[name]={key:portfolio_stats(values) for key,values in streams.items()}
  result[name]["exposure_coverage_pct"]=round(statistics.mean(coverage)*100,1) if coverage else 0
 return result
def run(cache="work/eodhd-panel-v4.json",out="research/backtest/output/legacy-foundation/neutralization-test.json"):
 panel=json.loads(pathlib.Path(cache).read_text())["panel"]
 for row in panel:row["forward"]={int(k):v for k,v in row["forward"].items()}
 panel=[x for x in panel if x["regime"]=="risk_on"]
 benchmark_codes=("SPY",)+SECTOR_ETFS;benchmark_rows={code:adjusted_rows(code) for code in benchmark_codes};benchmarks={code:prepare_returns(rows) for code,rows in benchmark_rows.items()};histories={}
 for symbol in sorted({x["symbol"] for x in panel}):
  try:histories[symbol]=prepare_returns(adjusted_rows(symbol))
  except Exception:histories[symbol]=prepare_returns([])
 exposure_cache={}
 for row in panel:
  key=(row["symbol"],row["date"])
  if key not in exposure_cache:exposure_cache[key]=point_in_time_exposure(histories[row["symbol"]],benchmarks,row["date"])
  row.update({"sector_proxy":exposure_cache[key]["sector"],"beta":exposure_cache[key]["beta"]})
 spy_forward=benchmark_forward(benchmark_rows["SPY"]);results={split:evaluate(panel,spy_forward,*bounds) for split,bounds in SPLIT_BOUNDS.items()}
 coverage=sum(x.get("sector_proxy") is not None and x.get("beta") is not None for x in panel)/len(panel)*100 if panel else 0
 candidates=[]
 for combo in COMBINATIONS:
  for design in ("sector_neutral","sector_and_beta_neutral"):
   stats=[results[x][combo][design] for x in ("development","validation","forward_test")]
   if all((x.get("mean_return") or 0)>0 for x in stats) and stats[0].get("periods",0)>=120 and stats[1].get("periods",0)>=6 and stats[2].get("periods",0)>=3:candidates.append({"combination":combo,"design":design,"status":"candidate_for_significance_test","reason":"Positive mean after modeled costs in development, 2025 validation, and 2026 forward monitoring; not yet tested for statistical significance."})
 report={"generated_at":datetime.now(timezone.utc).isoformat(),"status":"research_only_proxy_neutralization","design":{"sector":"At each signal date, assign the stock to the sector ETF with the highest correlation over the trailing 252 trading days; minimum 126 aligned observations.","sector_ranking":"Rank each predefined technical combination within proxy-sector buckets with at least five eligible stocks.","beta":"Estimate trailing 252-day beta to SPY using only returns available at the signal close.","hedge":"Subtract selected portfolio beta times SPY next-open-to-10-day return; deduct 20 bps stock cost plus 5 bps times absolute hedge beta.","warning":"ETF-correlated sector is a point-in-time statistical proxy, not historical issuer classification. Daily bars and an equal-weight hedge remain approximations."},"coverage_pct":round(coverage,1),"sector_etfs":SECTOR_ETFS,"results":results,"candidates":candidates,"decision":"A candidate advances only to bootstrap significance and rolling-year stability tests; it is not promoted to paper trading from this screen."}
 path=pathlib.Path(out);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2));return report
if __name__=="__main__":
 report=run();print(json.dumps({"coverage_pct":report["coverage_pct"],"validation":report["results"]["validation"],"forward":report["results"]["forward_test"]},indent=2))
