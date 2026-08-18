"""Larger, survivorship-aware EODHD factor validation with honest time splits."""
import json,math,pathlib,statistics
from datetime import datetime,timezone
from .eodhd import symbols
from .audit_eodhd import common
from .eodhd_factor_pilot import adjusted_rows,stable_sample,load
from .research_pipeline import FACTORS,HORIZONS,SPLIT_BOUNDS,evaluate_report,factor_values,iso,monthly_indices,roll_spread_bps,spearman
from .technical import ema

COMBINATIONS={
 "trend_confluence":["momentum_12_1","trend_quality","breakout_252","relative_strength_6m"],
 "breakout_confirmation":["breakout_252","volume_expansion","volatility_contraction","adx_14"],
 "balanced_technical":["momentum_12_1","trend_quality","low_volatility","relative_strength_6m","volatility_contraction"],
}

def percentile_scores(rows,factors):
 out={x["symbol"]:[] for x in rows}
 for factor in factors:
  valid=[x for x in rows if x["factors"].get(factor) is not None]
  if len(valid)<10:continue
  ordered=sorted(valid,key=lambda x:x["factors"][factor]);den=max(1,len(ordered)-1)
  for i,x in enumerate(ordered):out[x["symbol"]].append(i/den)
 return {k:statistics.mean(v) for k,v in out.items() if len(v)>=max(2,len(factors)//2)}

def evaluate_combinations(panel,horizon=10,start="0000-01-01",end="9999-12-31"):
 groups={}
 for x in panel:
  if start<=x["date"]<=end:groups.setdefault(x["date"],[]).append(x)
 results=[]
 for name,factors in COMBINATIONS.items():
  ics=[];top=[];bottom=[];obs=0
  for rows in groups.values():
   scores=percentile_scores(rows,factors);xs=[x for x in rows if x["symbol"] in scores and x["forward"].get(horizon) is not None]
   if len(xs)<10:continue
   vals=[scores[x["symbol"]] for x in xs];ys=[x["forward"][horizon] for x in xs];ic=spearman(vals,ys)
   if ic is not None:ics.append(ic)
   ordered=sorted(xs,key=lambda x:scores[x["symbol"]]);cut=max(1,len(xs)//5)
   bottom += [x["forward"][horizon] for x in ordered[:cut]];top += [x["forward"][horizon] for x in ordered[-cut:]];obs+=len(xs)
  results.append({"combination":name,"factors":factors,"horizon":horizon,"dates":len(ics),"observations":obs,"mean_ic":round(statistics.mean(ics),4) if ics else None,"ic_positive_pct":round(sum(x>0 for x in ics)/len(ics)*100,1) if ics else None,"spread":round(statistics.mean(top)-statistics.mean(bottom),4) if top else None})
 return results

def portfolio_stats(returns):
 if not returns:return {"periods":0}
 mean=statistics.mean(returns);vol=statistics.stdev(returns) if len(returns)>1 else 0;equity=peak=1;max_dd=0
 for value in returns:
  equity*=1+value;peak=max(peak,equity);max_dd=min(max_dd,equity/peak-1)
 return {"periods":len(returns),"mean_return":round(mean,4),"median_return":round(statistics.median(returns),4),"win_rate_pct":round(sum(x>0 for x in returns)/len(returns)*100,1),"annualized_sharpe":round(mean/vol*math.sqrt(12),2) if vol else None,"compounded_return":round(equity-1,4),"max_drawdown":round(max_dd,4)}

def evaluate_portfolios(panel,horizon=10,start="0000-01-01",end="9999-12-31",costs_bps=(0,20,50)):
 groups={}
 for x in panel:
  if start<=x["date"]<=end:groups.setdefault(x["date"],[]).append(x)
 results=[]
 for name,factors in COMBINATIONS.items():
  gross=[];excess=[];holdings=[]
  for date,rows in sorted(groups.items()):
   scores=percentile_scores(rows,factors);xs=[x for x in rows if x["symbol"] in scores and x["forward"].get(horizon) is not None]
   if len(xs)<10:continue
   ordered=sorted(xs,key=lambda x:scores[x["symbol"]],reverse=True);chosen=ordered[:max(1,len(ordered)//5)]
   top_return=statistics.mean(x["forward"][horizon] for x in chosen);universe_return=statistics.mean(x["forward"][horizon] for x in xs)
   gross.append(top_return);excess.append(top_return-universe_return);holdings.append(len(chosen))
  scenarios={str(cost):{"absolute":portfolio_stats([x-cost/10000 for x in gross]),"excess_vs_eligible_universe":portfolio_stats([x-cost/10000 for x in excess])} for cost in costs_bps}
  results.append({"combination":name,"horizon":horizon,"selection":"equal-weight top cross-sectional quintile","benchmark":"equal-weight eligible universe on the same date","average_holdings":round(statistics.mean(holdings),1) if holdings else 0,"cost_basis":"round-trip cost deducted from every selected portfolio return","cost_scenarios_bps":scenarios})
 return results

def run(out="public/eodhd-factor-validation.json",per_group=500):
 active=stable_sample(common(symbols(False)),per_group,"northstar-active-v2");dead=stable_sample(common(symbols(True)),per_group,"northstar-delisted-v2")
 selected=[({**x,"listing_status":"active"}) for x in active]+[({**x,"listing_status":"delisted"}) for x in dead]
 spy=adjusted_rows("SPY");benchmark={x["date"]:x["close"] for x in spy};market_ema=ema([x["close"] for x in spy],200);regime={x["date"]:x["close"]>market_ema[i] for i,x in enumerate(spy) if i>=199}
 from concurrent.futures import ThreadPoolExecutor,as_completed
 loaded=[]
 with ThreadPoolExecutor(max_workers=10) as pool:
  for future in as_completed([pool.submit(load,x) for x in selected]):loaded.append(future.result())
 panel=[];eligible={"active":0,"delisted":0}
 for meta,rows in loaded:
  if len(rows)<253:continue
  included=False
  for i in monthly_indices(rows):
   adv=sum(x["close"]*x["volume"] for x in rows[i-19:i+1])/20;spread=roll_spread_bps(rows,i)
   if rows[i]["close"]<5 or adv<10_000_000 or spread is None or spread>50 or not regime.get(rows[i]["date"],False):continue
   fw={h:(rows[i+h]["close"]/rows[i+1]["open"]-1 if i+1<len(rows) and i+h<len(rows) else None) for h in HORIZONS}
   panel.append({"date":iso(rows[i]["date"]),"symbol":meta["Code"],"listing_status":meta["listing_status"],"factors":factor_values(rows,i,benchmark),"forward":fw});included=True
  if included:eligible[meta["listing_status"]]+=1
 dates=sorted({x["date"] for x in panel});split_metrics={k:evaluate_report(panel,*v) for k,v in SPLIT_BOUNDS.items()};combinations={k:evaluate_combinations(panel,10,*v) for k,v in SPLIT_BOUNDS.items()};portfolios={k:evaluate_portfolios(panel,10,*v) for k,v in SPLIT_BOUNDS.items()}
 report={"generated_at":datetime.now(timezone.utc).isoformat(),"status":"expanded_validation_research_only","provider":"EODHD All World","sample":{"requested_active":per_group,"requested_delisted":per_group,"loaded":sum(bool(x) for _,x in loaded),"eligible_active":eligible["active"],"eligible_delisted":eligible["delisted"],"stock_months":len(panel),"dates":len(dates),"start":dates[0] if dates else None,"end":dates[-1] if dates else None},"execution":{"signal":"month-end close","entry":"next trading day's adjusted open","exits":"5, 10, 20, and 60 trading-day closes","time_stop":"10 trading days is the primary strategy evaluation horizon","cost_scenarios":"0, 20, and 50 basis points round trip"},"split_metrics":split_metrics,"combinations":combinations,"portfolios":portfolios,"limitations":["Deterministic sample, not yet a complete point-in-time US universe","No historical sector classifications, so results are not sector-neutralized","Roll spread proxy rather than historical quotes","Cost scenarios are fixed haircuts, not security-specific slippage","No fundamentals, options walls, borrow costs, or portfolio beta hedging"],"decision":"Use development to form hypotheses, validation to accept or reject them, and forward test only as an untouched monitor. No live capital authorization."}
 pathlib.Path(out).write_text(json.dumps(report,indent=2));return report

if __name__=="__main__":
 r=run();print(json.dumps(r["sample"],indent=2));print(json.dumps(r["combinations"],indent=2))
