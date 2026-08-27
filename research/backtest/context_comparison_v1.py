"""Fixed four-arm comparison for technical, industry and market context."""
from statistics import mean,median

HORIZONS=(5,20,60,100)
ARMS={
 "technical_baseline":lambda row:True,
 "technical_plus_industry":lambda row:row.get("industry_confirmed") is True,
 "technical_plus_market":lambda row:row.get("market_supportive") is True,
 "technical_plus_industry_and_market":lambda row:row.get("industry_confirmed") is True and row.get("market_supportive") is True,
}

def _drawdown(values):
 equity=peak=1.0;worst=0.0
 for value in values:
  equity*=1+value;peak=max(peak,equity);worst=min(worst,equity/peak-1)
 return worst

def _stats(rows,horizon):
 usable=[x for x in rows if x.get("forward_returns",{}).get(str(horizon)) is not None]
 returns=[x["forward_returns"][str(horizon)] for x in usable]
 excess=[x.get("excess_returns",{}).get(str(horizon)) for x in usable]
 excess=[x for x in excess if x is not None]
 return {"samples":len(usable),"win_rate":round(sum(x>0 for x in returns)/len(returns)*100,2) if returns else None,
  "mean_return":round(mean(returns),6) if returns else None,"median_return":round(median(returns),6) if returns else None,
  "mean_excess_vs_spy":round(mean(excess),6) if excess else None,"max_drawdown":round(_drawdown(returns),6) if returns else None,
  "mean_mfe":round(mean(x["mfe"] for x in usable if x.get("mfe") is not None),6) if any(x.get("mfe") is not None for x in usable) else None,
  "mean_mae":round(mean(x["mae"] for x in usable if x.get("mae") is not None),6) if any(x.get("mae") is not None for x in usable) else None}

def compare(records,horizons=HORIZONS):
 ordered=sorted(records,key=lambda x:(x["signal_date"],x.get("signal_id",x.get("symbol",""))))
 for row in ordered:
  if row.get("context_as_of")!=row["signal_date"]:raise ValueError("Context must be point-in-time at signal date")
 arms={}
 for name,eligible in ARMS.items():
  selected=[x for x in ordered if eligible(x)]
  arms[name]={"selection_count":len(selected),"horizons":{str(h):_stats(selected,h) for h in horizons},
   "periods":{year:{str(h):_stats([x for x in selected if x["signal_date"].startswith(year)],h) for h in horizons} for year in sorted({x["signal_date"][:4] for x in selected})}}
 return {"version":"context-comparison-v1","research_only":True,"production_score_changed":False,"arms":arms,
  "audit":{"same_frozen_technical_baseline":True,"point_in_time_context_required":True,"automatic_weight_search":False,"industry_weight_cap":1},
  "limitations":["Industry history is eligible only where a dated membership snapshot existed on the signal date.","Missing context is unavailable, never treated as a negative signal.","Historical backtest and production-forward observations must be reported separately."]}
