"""Append-only production signal ledger and strictly elapsed forward outcomes."""
import copy,hashlib,json,pathlib
from datetime import datetime,timezone

from .eodhd_factor_pilot import adjusted_rows

SCHEMA_VERSION="1.3.0"
PRODUCT_VERSION="SV-PRODUCT-V1"
SIGNAL_DEFINITION_VERSION="signal-history-v1.1"
RESET_SESSIONS=5
HORIZONS=(1,5,10,20,60,100)

def _ranked_tracker_rows(tracker):
 """The existing primary Tracker list is consumed as-is; never re-rank it here."""
 return list(tracker.get("macd_buy_top10",[]))

def _favorite_entry_rows(tracker):
 """Only a completed-close entry-ready state becomes a forward signal."""
 return [x for x in tracker.get("favorite_pattern_tracker",{}).get("candidates",[]) if x.get("stage")=="entry_ready"]

def _factor_by_symbol(snapshot):return {x["symbol"]:{**x,"registry_version":snapshot.get("registry_version")} for x in snapshot.get("symbols",[])}

def _industry_by_symbol(industry):
 themes={x["theme_id"]:x for x in industry.get("themes",[])};out={}
 for symbol,links in industry.get("ticker_context",{}).items():
  out[symbol]=[{**{k:item.get(k) for k in ("theme_id","name","state","relative_20d","relative_60d","breadth_above_sma50","breadth_change_10d")},"etf_context":copy.deepcopy(item.get("etf_context"))} for link in links if (item:=themes.get(link["theme_id"]))]
 return out

def _industry_snapshot_for_symbol(industry,symbol):
 return {"classification":copy.deepcopy(industry.get("classification_by_ticker",{}).get(symbol)),"themes":copy.deepcopy(_industry_by_symbol(industry).get(symbol,[]))}

def _signal_id(symbol,day):return f"SVP1-{symbol}-{day}"

def _immutable_fingerprint(case):
 frozen={k:case.get(k) for k in ("signal_id","signal_schema_version","observation_mode","product_version","signal_definition_version","symbol","first_seen_date","initial_source_systems","signal_time_snapshot","versions")}
 if "recovery" in case:frozen["recovery"]=case["recovery"]
 return hashlib.sha256(json.dumps(frozen,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def _market_snapshot(market,day):
 raw=str(market.get("as_of",day));normalized=datetime.strptime(raw,"%m/%d/%Y").date().isoformat() if "/" in raw else raw
 return copy.deepcopy(market) if normalized==day else {"as_of":normalized,"status":"unavailable_date_mismatch"}

def _new_case(symbol,day,sources,tracker_row,factor_row,industry,market,favorite_row=None):
 rank=next((i+1 for i,x in enumerate(_ranked_tracker_rows(tracker_row[0])) if x.get("symbol")==symbol),None)
 technical=tracker_row[1]
 factor=copy.deepcopy(factor_row) if factor_row else None
 case={
  "signal_id":_signal_id(symbol,day),"signal_schema_version":SCHEMA_VERSION,"observation_mode":"production_forward",
  "product_version":PRODUCT_VERSION,"signal_definition_version":SIGNAL_DEFINITION_VERSION,"symbol":symbol,
  "first_seen_date":day,"last_seen_date":day,"days_active":1,"absent_sessions":0,"lifecycle":"NEW",
  "initial_source_systems":sorted(sources),"source_systems":sorted(sources),"latest_current_status":"current","entry":{"convention":"next_trading_day_adjusted_open","date":None,"price":None},
  "signal_time_snapshot":{"technical":{"tracker_rank":rank,"technical_score":technical.get("ranking_score") if technical else None,"combined_score":technical.get("combined_score") if technical else None,"setup":technical.get("confluence_label") if technical else None,"status":technical.get("ranking_direction") if technical else None,"rank_reason":technical.get("rank_reason") if technical else None},
   "favorite_pattern":{"pattern_version":favorite_row.get("pattern_version"),"stage":favorite_row.get("stage"),"match_count":favorite_row.get("match_count"),"conditions":copy.deepcopy(favorite_row.get("conditions",[])),"prior_advance":copy.deepcopy(favorite_row.get("prior_advance")),"pullback":copy.deepcopy(favorite_row.get("pullback")),"double_bottom":copy.deepcopy(favorite_row.get("double_bottom")),"second_bottom_macd":copy.deepcopy(favorite_row.get("second_bottom_macd")),"three_push":copy.deepcopy(favorite_row.get("three_push")),"ema_realign":copy.deepcopy(favorite_row.get("ema_realign")),"trade_map":copy.deepcopy(favorite_row.get("trade_map"))} if favorite_row else None,
   "multi_factor":{"factor_registry_version":factor.get("registry_version") if factor else None,"official_score":factor.get("scoring",{}).get("official_score") if factor else None,"experimental_observational_score":factor.get("scoring",{}).get("experimental_observational_score") if factor else None,"score_contributions":factor.get("scoring",{}).get("score_contributions",[]) if factor else [],"factor_states":factor.get("factors",[]) if factor else [],"non_scoring_evidence":[x for x in factor.get("factors",[]) if x.get("available") and (x.get("hit") or x.get("recent_hit")) and x.get("score_role") in ("display_only","disabled")] if factor else [],"risks":[x for x in factor.get("factors",[]) if x.get("factor_id","").startswith("risk.") and x.get("hit")] if factor else []},
   "industry":{"industry_radar_as_of":industry.get("as_of"),"membership_version":industry.get("membership_version"),"classification_effective_from":industry.get("classification_snapshot",{}).get("effective_from"),"rule_version":"industry-radar-v2",**_industry_snapshot_for_symbol(industry,symbol)},"market":_market_snapshot(market,day)},
  "versions":{"code_version":PRODUCT_VERSION,"factor_registry_version":factor.get("registry_version") if factor else None,"industry_membership_version":industry.get("membership_version")},
  "forward":{"returns":{str(x):None for x in HORIZONS},"mfe":None,"mae":None,"elapsed_sessions":0,"status":"pending","data_status":"pending"},
  "audit":{"future_data_used":False,"created_as_of":day,"last_updated_as_of":day}}
 case["immutable_fingerprint"]=_immutable_fingerprint(case);return case

def _load_rows(symbol,as_of,loader):
 rows=loader(symbol) or []
 out=[]
 for row in rows:
  raw=row.get("date")
  if not raw:continue
  day=datetime.strptime(raw,"%m/%d/%Y").date().isoformat() if "/" in raw else raw
  if day<=as_of:out.append({**row,"date":day})
 return sorted(out,key=lambda x:x["date"])

def _update_forward(case,as_of,loader):
 try:rows=_load_rows(case["symbol"],as_of,loader)
 except Exception:
  case["forward"]["data_status"]="unavailable";return
 case["forward"]["data_status"]="available" if rows else "unavailable";signal_index=next((i for i,x in enumerate(rows) if x["date"]==case["first_seen_date"]),None)
 if signal_index is None:return
 entry_index=signal_index+1
 if entry_index>=len(rows):return
 entry=rows[entry_index];price=float(entry["open"]);case["entry"]={"convention":"next_trading_day_adjusted_open","date":entry["date"],"price":round(price,6)}
 elapsed=rows[entry_index:];case["forward"]["elapsed_sessions"]=len(elapsed)
 for horizon in HORIZONS:
  if len(elapsed)>=horizon:case["forward"]["returns"][str(horizon)]=round(float(elapsed[horizon-1]["close"])/price-1,8)
 highs=[float(x["high"]) for x in elapsed];lows=[float(x["low"]) for x in elapsed]
 case["forward"]["mfe"]=round(max(highs)/price-1,8);case["forward"]["mae"]=round(min(lows)/price-1,8)
 case["forward"]["status"]="matured" if len(elapsed)>=max(HORIZONS) else "observing"
 if len(elapsed)>=max(HORIZONS):case["lifecycle"]="MATURED"

def _active_case(cases,symbol):
 candidates=[x for x in cases if x["symbol"]==symbol]
 return max(candidates,key=lambda x:x["first_seen_date"]) if candidates else None

def _factor_temporal_states(case,factor_row):
 previous={}
 for daily in case.get("daily_states",[]):
  for state in daily.get("factor_states",[]):previous[state["factor_id"]]=state["temporal_status"]
 out=[]
 for state in (factor_row or {}).get("factors",[]):
  if not state.get("available"):temporal="UNAVAILABLE"
  elif state.get("hit"):temporal="ACTIVE"
  elif state.get("recent_hit"):temporal="RECENT"
  elif previous.get(state["factor_id"]) in {"ACTIVE","RECENT","EXPIRED"}:temporal="EXPIRED"
  else:temporal="NEVER"
  out.append({"factor_id":state["factor_id"],"factor_version":state.get("factor_version"),"temporal_status":temporal,"hit":bool(state.get("hit")),"recent_hit":bool(state.get("recent_hit")),"latest_hit_date":state.get("latest_hit_date"),"bars_since_hit":state.get("bars_since_hit"),"research_status":state.get("research_status"),"score_role":state.get("score_role")})
 return out

def _append_daily_state(case,as_of,sources,factor_row,radar_row,industry,market,is_current,favorite_row=None):
 """Append one point-in-time state per production session without rewriting earlier days."""
 if any(x.get("date")==as_of for x in case.get("daily_states",[])):return
 scoring=(factor_row or {}).get("scoring",{})
 case.setdefault("daily_states",[]).append({
  "date":as_of,"price":(factor_row or {}).get("price"),"source_systems":sorted(sources),
  "in_current_opportunities":bool(is_current),"legacy_production_score":radar_row.get("total_score",radar_row.get("score")) if radar_row else None,
  "official_score":scoring.get("official_score"),"experimental_observational_score":scoring.get("experimental_observational_score"),
  "favorite_pattern":{"stage":favorite_row.get("stage"),"match_count":favorite_row.get("match_count"),"pattern_version":favorite_row.get("pattern_version")} if favorite_row else None,
  "factor_states":_factor_temporal_states(case,factor_row),
  "industry_context":_industry_snapshot_for_symbol(industry,case["symbol"]),
  "market_context":_market_snapshot(market,as_of)
 })

def build(previous,tracker,radar,snapshot,industry,market,as_of,loader=adjusted_rows):
 if any(x.get("as_of")!=as_of for x in (tracker,radar,snapshot,industry)):raise ValueError("Signal inputs must share as_of")
 if previous.get("cases"):validate(previous,previous.get("as_of"))
 cases=copy.deepcopy(previous.get("cases",[]));tracker_rows=_ranked_tracker_rows(tracker);tracker_map={x["symbol"]:x for x in tracker_rows};favorite={x["symbol"]:x for x in _favorite_entry_rows(tracker)};rare={x["symbol"]:x for x in radar.get("signals",[])};factors=_factor_by_symbol(snapshot)
 current=set(tracker_map)|set(rare)|set(favorite)
 for case in cases:
  if case["observation_mode"]!="production_forward":raise ValueError("Non-forward case in production ledger")
  if case["latest_current_status"]=="current" and case["symbol"] not in current:
   case["absent_sessions"]+=1;case["latest_current_status"]="dropped";case["lifecycle"]="MONITORING"
  elif case["symbol"] not in current:case["absent_sessions"]+=1
 for symbol in sorted(current):
  sources=[]
  if symbol in tracker_map:sources.append("technical_tracker")
  if symbol in rare:sources.append("multi_factor_radar")
  if symbol in favorite:sources.append("favorite_pattern_tracker")
  active=_active_case(cases,symbol)
  if active and active["absent_sessions"]<RESET_SESSIONS:
   active["last_seen_date"]=as_of;active["days_active"]+=1;active["absent_sessions"]=0;active["latest_current_status"]="current";active["lifecycle"]="MATURED" if active.get("forward",{}).get("status")=="matured" else "ACTIVE";active["source_systems"]=sorted(set(active["source_systems"])|set(sources))
  else:cases.append(_new_case(symbol,as_of,sources,(tracker,tracker_map.get(symbol)),factors.get(symbol),industry,market,favorite.get(symbol)))
 for case in cases:
  sources=[]
  if case["symbol"] in tracker_map:sources.append("technical_tracker")
  if case["symbol"] in rare:sources.append("multi_factor_radar")
  if case["symbol"] in favorite:sources.append("favorite_pattern_tracker")
  _append_daily_state(case,as_of,sources,factors.get(case["symbol"]),rare.get(case["symbol"]),industry,market,case["symbol"] in current,favorite.get(case["symbol"]))
  _update_forward(case,as_of,loader);case["audit"]["last_updated_as_of"]=as_of
  if case["entry"].get("date") and case["entry"]["date"]>as_of:raise ValueError("Future entry leakage")
 cases.sort(key=lambda x:(x["first_seen_date"],x["symbol"],x["signal_id"]))
 payload={"signal_schema_version":SCHEMA_VERSION,"as_of":as_of,"generated_at":datetime.now(timezone.utc).isoformat(),"observation_mode":"production_forward","future_data_used":False,"reset_rule":{"completed_absent_sessions":RESET_SESSIONS},"entry_convention":"next_trading_day_adjusted_open","forward_horizons_sessions":list(HORIZONS),"cases":cases}
 payload["content_hash"]=hashlib.sha256(json.dumps({k:v for k,v in payload.items() if k not in ("generated_at","content_hash")},sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
 validate(payload,as_of);return payload

def validate(payload,as_of):
 if payload.get("as_of")!=as_of or payload.get("future_data_used") is not False:raise ValueError("Signal history date/leakage audit failed")
 ids=[x["signal_id"] for x in payload.get("cases",[])]
 if len(ids)!=len(set(ids)):raise ValueError("Duplicate signal_id")
 for case in payload.get("cases",[]):
  if case.get("observation_mode")!="production_forward" or case.get("audit",{}).get("future_data_used") is not False:raise ValueError("Invalid production-forward case")
  if case.get("immutable_fingerprint")!=_immutable_fingerprint(case):raise ValueError("Immutable signal-time snapshot changed")
  if case["first_seen_date"]>as_of or case["last_seen_date"]>as_of:raise ValueError("Future case date")
  days=[x.get("date") for x in case.get("daily_states",[])]
  if len(days)!=len(set(days)) or days!=sorted(days) or any(not x or x>as_of for x in days):raise ValueError("Invalid case daily-state timeline")
 return True
