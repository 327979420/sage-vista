"""Build the point-in-time industry and theme context for one completed day.

Inputs are dated membership snapshots and price histories cut at ``as_of``.
Output feeds the Industry & Market page and remains separate from technical
factor evidence. Missing or future membership is never backfilled by guesswork.
"""
import argparse,json,pathlib
from datetime import date,datetime,timezone

from .eodhd import latest_reference_day
from .eodhd_factor_pilot import adjusted_rows
from .theme_etf_context import DEFAULT_REGISTRY,evaluate_theme,reference_funds
from .open_source_industry import classification_by_ticker,select_finance_database_snapshot

ROOT=pathlib.Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT_DIR=ROOT/"data/themes/snapshots"
CONFIG={
 "min_valid_members":5,
 "min_valid_member_ratio":0.50,
 "leadership_percentile":70.0,
 "healthy_breadth":0.60,
 "meaningful_breadth_decline":-0.10,
 "recovery_breadth_improvement":0.05,
}
STATE_ORDER={"Pullback Watch":0,"Leadership":1,"Recovery":2,"Neutral":3,"Unavailable":4}

def iso_day(value):
 return datetime.strptime(value,"%m/%d/%Y").date().isoformat() if "/" in value else value

def rows_as_of(rows,as_of):
 """Normalize and strictly discard every future or invalid close."""
 out=[]
 for row in rows:
  day=iso_day(row["date"])
  if day<=as_of and row.get("close") is not None:out.append({**row,"date":day,"close":float(row["close"])})
 return sorted(out,key=lambda x:x["date"])

def select_snapshot(as_of,snapshot_dir=DEFAULT_SNAPSHOT_DIR):
 """Select the newest membership version effective on or before as_of."""
 eligible=[]
 for path in pathlib.Path(snapshot_dir).glob("*.json"):
  payload=json.loads(path.read_text())
  effective=payload.get("effective_from")
  if effective and effective<=as_of:eligible.append((effective,payload.get("snapshot_revision",1),path.name,payload))
 if not eligible:return None
 return max(eligible,key=lambda x:(x[0],x[1],x[2]))[3]

def member_metrics(rows,spy,as_of):
 rows=rows_as_of(rows,as_of);spy=rows_as_of(spy,as_of)
 if len(rows)<61 or len(spy)<61:return None
 if rows[-1]["date"]!=as_of or spy[-1]["date"]!=as_of:return None
 spy_by_date={x["date"]:x["close"] for x in spy};aligned=[x for x in rows if x["date"] in spy_by_date]
 if len(aligned)<61:return None
 end=aligned[-1]
 def value(n):
  if len(aligned)<=n:return None
  prior=aligned[-1-n]
  return end["close"]/prior["close"]-1,spy_by_date[end["date"]]/spy_by_date[prior["date"]]-1
 r5,s5=value(5);r20,s20=value(20);r60,s60=value(60)
 closes=[x["close"] for x in aligned]
 above=closes[-1]>sum(closes[-50:])/50
 prior_closes=closes[:-10]
 prior_above=len(prior_closes)>=50 and prior_closes[-1]>sum(prior_closes[-50:])/50
 return {"return_5d":r5,"return_20d":r20,"return_60d":r60,"relative_5d":r5-s5,
  "relative_20d":r20-s20,"relative_60d":r60-s60,"above_sma50":above,
  "above_sma50_10d_ago":prior_above,"positive_20d":r20>0,"latest_bar":end["date"]}

def percentile(values,value):
 if not values:return None
 return 100*sum(x<=value for x in values)/len(values)

def classify_state(item,config=CONFIG):
 if item["valid_member_count"]<config["min_valid_members"] or item.get("valid_member_ratio",1)<config["min_valid_member_ratio"] or item["strength_percentile"] is None:return "Unavailable"
 strong=item["strength_percentile"]>=config["leadership_percentile"] and item["breadth_above_sma50"]>=config["healthy_breadth"]
 weakening=item["relative_5d"]<0 or item["breadth_change_10d"]<=config["meaningful_breadth_decline"]
 if strong and weakening:return "Pullback Watch"
 if strong:return "Leadership"
 if item["strength_percentile"]<config["leadership_percentile"] and item["relative_5d"]>0 and item["breadth_change_10d"]>=config["recovery_breadth_improvement"]:return "Recovery"
 return "Neutral"

def context(item):
 if item["state"]=="Unavailable":return f"Only {item['valid_member_count']} constituents have sufficient data; metrics withheld."
 rs="both strong" if item["relative_20d"]>0 and item["relative_60d"]>0 else "mixed" if item["relative_20d"]*item["relative_60d"]<0 else "both weak"
 trend="improving" if item["breadth_change_10d"]>=CONFIG["recovery_breadth_improvement"] else "weakening" if item["breadth_change_10d"]<=CONFIG["meaningful_breadth_decline"] else "stable"
 return f"20D/60D relative strength {rs}; {item['breadth_above_sma50']:.0%} of constituents above SMA50; breadth {trend}."

def calculate(snapshot,price_data,spy_rows,as_of,etf_funds=None):
 themes=[]
 for theme in snapshot["themes"]:
  observations=[]
  for symbol in theme["members"]:
   metric=member_metrics(price_data.get(symbol,[]),spy_rows,as_of)
   if metric:observations.append(metric)
  valid=len(observations);item={k:theme.get(k) for k in ("theme_id","name","source_type","source_provider","source","source_url","source_date","effective_from","source_status","parse_status","error_reason")}
  audit=theme.get("membership_audit",{});member_count=len(theme["members"]);valid_ratio=valid/member_count if member_count else 0
  item.update({"member_count":member_count,"raw_holdings_count":audit.get("total_holdings",member_count),"us_resolvable_count":audit.get("us_tradeable_members",0),"foreign_or_unmapped_count":audit.get("foreign_or_unmapped_count",len(audit.get("foreign_or_unmapped_members",[]))),"valid_member_count":valid,"valid_member_ratio":valid_ratio})
  if valid>=CONFIG["min_valid_members"] and valid_ratio>=CONFIG["min_valid_member_ratio"]:
   avg=lambda key:sum(x[key] for x in observations)/valid
   item.update({"return_20d":avg("return_20d"),"return_60d":avg("return_60d"),"relative_20d":avg("relative_20d"),"relative_60d":avg("relative_60d"),"breadth_above_sma50":avg("above_sma50"),"breadth_positive_20d":avg("positive_20d"),"relative_5d":avg("relative_5d"),"breadth_change_10d":avg("above_sma50")-avg("above_sma50_10d_ago")})
  else:
   item.update({k:None for k in ("return_20d","return_60d","relative_20d","relative_60d","breadth_above_sma50","breadth_positive_20d","relative_5d","breadth_change_10d")})
  themes.append(item)
 valid_themes=[x for x in themes if x["relative_20d"] is not None]
 strengths=[(x["relative_20d"]+x["relative_60d"])/2 for x in valid_themes]
 for item in themes:
  raw=(item["relative_20d"]+item["relative_60d"])/2 if item["relative_20d"] is not None else None
  item["strength_percentile"]=percentile(strengths,raw) if raw is not None else None
  item["state"]=classify_state(item);item["context"]=context(item)
  item["etf_context"]=evaluate_theme((etf_funds or {}).get(item["theme_id"],[]),price_data,as_of)
 themes.sort(key=lambda x:(STATE_ORDER[x["state"]],-(x["strength_percentile"] or -1),x["name"]))
 ticker_context={}
 for theme in themes:
  source=next(x for x in snapshot["themes"] if x["theme_id"]==theme["theme_id"])
  for symbol in source["members"]:ticker_context.setdefault(symbol,[]).append({"theme_id":theme["theme_id"],"state":theme["state"],"etf_context":theme["etf_context"]})
 return themes,dict(sorted(ticker_context.items()))

def run(out="public/industry-radar.json",as_of=None,snapshot_dir=DEFAULT_SNAPSHOT_DIR,loader=adjusted_rows,registry=DEFAULT_REGISTRY):
 as_of=as_of or latest_reference_day();snapshot=select_snapshot(as_of,snapshot_dir)
 if snapshot is None:
  report={"as_of":as_of,"generated_at":datetime.now(timezone.utc).isoformat(),"membership_version":None,"future_data_used":False,"historical_membership_safe":False,"status":"unavailable_no_membership_snapshot","themes":[],"ticker_context":{}}
 else:
  funds=reference_funds(snapshot,registry);symbols=sorted({s for x in snapshot["themes"] for s in x["members"]}|{s for values in funds.values() for s in values});data={};fetched=[];unavailable=[]
  for symbol in symbols:
   try:
    data[symbol]=loader(symbol)
    (fetched if data[symbol] else unavailable).append(symbol)
   except Exception:
    data[symbol]=[];unavailable.append(symbol)
  try:spy=loader("SPY")
  except Exception:spy=[]
  themes,ticker_context=calculate(snapshot,data,spy,as_of,funds)
  taxonomy=select_finance_database_snapshot(as_of);classifications=classification_by_ticker(taxonomy)
  sufficient={symbol for symbol in symbols if member_metrics(data[symbol],spy,as_of)} if spy else set()
  report={"schema_version":"2.1.0","as_of":as_of,"generated_at":datetime.now(timezone.utc).isoformat(),"membership_version":snapshot["version"],"membership_effective_from":snapshot["effective_from"],"future_data_used":False,"historical_membership_safe":True,"mode":"decision_context_not_technical_score","status":"research_prototype_not_validated_alpha" if spy else "market_data_unavailable_safe","config":CONFIG,
   "price_data_audit":{"provider":"EODHD","requested_tickers":symbols,"fetched_tickers":fetched,"unavailable_tickers":unavailable,"insufficient_history_tickers":sorted(set(fetched)-sufficient),"errors_redacted":True},
   "themes":themes,"ticker_context":ticker_context,"classification_by_ticker":classifications,"classification_snapshot":{"source":"FinanceDatabase" if taxonomy else None,"effective_from":taxonomy.get("effective_from") if taxonomy else None,"matched_symbols":taxonomy.get("matched_symbols") if taxonomy else 0,"historical_backfill_allowed":False},"membership_overlap":snapshot.get("overlap_analysis",[]),"audit":{"exact_as_of_required":True,"minimum_valid_member_ratio":CONFIG["min_valid_member_ratio"],"future_rows_used":False,"state_model":"industry-state-v2","etf_position_model":"theme-etf-position-v1","industry_candidate_weight_cap":1,"production_score_changed":False}}
 pathlib.Path(out).parent.mkdir(parents=True,exist_ok=True);pathlib.Path(out).write_text(json.dumps(report,indent=2)+"\n")
 return report

if __name__=="__main__":
 parser=argparse.ArgumentParser(description="Build the standalone Industry Radar research report")
 parser.add_argument("--as-of");parser.add_argument("--out",default="public/industry-radar.json");parser.add_argument("--snapshot-dir",default=str(DEFAULT_SNAPSHOT_DIR))
 args=parser.parse_args();print(json.dumps(run(args.out,args.as_of,args.snapshot_dir),indent=2))
