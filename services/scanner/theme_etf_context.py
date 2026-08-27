"""Point-in-time technical context for ETFs representing an industry theme."""
import json,pathlib
from datetime import datetime

from .technical import ema,macd

ROOT=pathlib.Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY=ROOT/"data/themes/theme-registry.json"
MODEL_VERSION="theme-etf-position-v1"

def _day(value):
 return value if "-" in value else datetime.strptime(value,"%m/%d/%Y").date().isoformat()

def rows_as_of(rows,as_of):
 out=[]
 for row in rows or []:
  if not row.get("date") or row.get("close") is None:continue
  day=_day(row["date"])
  if day<=as_of:out.append({**row,"date":day,"close":float(row["close"])})
 return sorted(out,key=lambda x:x["date"])

def reference_funds(snapshot,registry=DEFAULT_REGISTRY):
 """Membership ETF and context ETFs are related evidence, not the same fact."""
 configured={}
 path=pathlib.Path(registry)
 if path.exists():
  configured={x["theme_id"]:x for x in json.loads(path.read_text()).get("themes",[])}
 result={}
 for theme in snapshot.get("themes",[]):
  item=configured.get(theme["theme_id"],{})
  membership=(item.get("membership_source") or {}).get("fund") or theme.get("source")
  funds=item.get("context_funds") or ([membership] if membership else [])
  result[theme["theme_id"]]=list(dict.fromkeys(x for x in funds if x))
 return result

def evaluate_fund(symbol,rows,as_of):
 rows=rows_as_of(rows,as_of)
 base={"symbol":symbol,"as_of":as_of,"model_version":MODEL_VERSION,"available":False,"favorable_setup":False,"candidate_weight":0}
 if len(rows)<220 or rows[-1]["date"]!=as_of:return {**base,"state":"Unavailable","reason":"exact_as_of_or_history_unavailable"}
 closes=[x["close"] for x in rows];e21=ema(closes,21);e50=ema(closes,50);e200=ema(closes,200);line,signal=macd(closes)
 close=closes[-1];prior_high=max(closes[-61:-1]);pullback=max(0,prior_high/close-1)
 supports=[name for name,value in (("EMA21",e21[-1]),("EMA50",e50[-1]),("EMA200",e200[-1])) if value and abs(close/value-1)<=.03]
 long_trend=close>=e200[-1]*.90 and e200[-1]>=e200[-61]*.97
 recent_cross=any(line[i]>signal[i] and line[i-1]<=signal[i-1] for i in range(len(line)-5,len(line)))
 favorable=long_trend and .05<=pullback<=.25 and bool(supports)
 if favorable:state="Rising Pullback At Support"
 elif long_trend and close>=e50[-1]:state="Uptrend"
 elif long_trend:state="Pullback Unconfirmed"
 else:state="Weak Or Unconfirmed"
 return {**base,"available":True,"state":state,"favorable_setup":favorable,"candidate_weight":1 if favorable else 0,
  "close":round(close,6),"prior_60d_high":round(prior_high,6),"pullback_from_60d_high":round(pullback,6),
  "support_levels":supports,"long_trend_qualified":long_trend,"macd_bullish":line[-1]>signal[-1],"recent_macd_bull_cross":recent_cross,
  "rule":"long trend + 5%-25% pullback from prior 60-session high + within 3% of EMA21/50/200"}

def evaluate_theme(funds,price_data,as_of):
 evidence=[evaluate_fund(symbol,price_data.get(symbol,[]),as_of) for symbol in funds]
 confirmations=[x["symbol"] for x in evidence if x["favorable_setup"]]
 return {"model_version":MODEL_VERSION,"mode":"shadow_context_factor_not_production_weight","reference_funds":evidence,
  "favorable_setup":bool(confirmations),"confirming_funds":confirmations,"candidate_weight":1 if confirmations else 0,
  "weight_cap":1,"production_score_changed":False}
