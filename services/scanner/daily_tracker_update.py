"""Build and atomically publish every daily production dataset.

Inputs: one authoritative completed US session plus cached EODHD histories.
Outputs: the synchronized JSON bundle consumed by the four website pages and
the notification job. All expensive work happens in a temporary directory;
``public/`` is replaced only after date, factor-version and lookahead checks.
"""
import argparse,copy,json,os,pathlib,tempfile
from datetime import datetime,timezone
from .eodhd import latest_reference_day
from .expand_tracker_universe import run as expand_universe
from .factor_snapshot import SNAPSHOT_MODE_VERSION,TRIGGER_FACTOR_ID,load_symbol_rows,run as run_factor_snapshot
from .factor_registry import REGISTRY_VERSION
from .factor_detectors import MONITORED_FACTOR_IDS
from .favorite_pattern_tracker import GENERALIZATION_VERSION,PATTERN_VERSION,build_gated_report
from .industry_radar import run as run_industry_radar
from .market_etf_watch import run as run_market_context
from .rare_opportunity_scanner import run as run_radar
from .signal_history import SCHEMA_VERSION as SIGNAL_HISTORY_SCHEMA_VERSION,build as build_signal_history,validate as validate_signal_history

PUBLIC=pathlib.Path("public")
PRODUCTION_HISTORY=pathlib.Path("research/production-history")
SIGNAL_HISTORY_PATH=PRODUCTION_HISTORY/"signal-history.json"
TRIGGER_SOURCES={"manual","cloudflare_cron","freshness_recovery","github_schedule"}

def read_json(path):
 path=pathlib.Path(path)
 return json.loads(path.read_text()) if path.exists() else {}

def compact_favorite_pattern(favorite):
 """Keep only the bounded lists used by the page; the ledger stays internal."""
 return {key:value for key,value in favorite.items() if key!="candidates"}

def compact_signal_history(history):
 return {"as_of":history.get("as_of"),"future_data_used":history.get("future_data_used"),"cases":[{"symbol":row.get("symbol"),"first_seen_date":row.get("first_seen_date"),"lifecycle":row.get("lifecycle"),"latest_current_status":row.get("latest_current_status"),"forward":{"elapsed_sessions":row.get("forward",{}).get("elapsed_sessions",0),"status":row.get("forward",{}).get("status","pending")}} for row in history.get("cases",[])]}

def tracker_for_forward_history(current_favorite,current_history,favorite,authoritative):
 """Keep a new pattern definition out of an already saved forward day.

 The website may show a newly deployed definition against the latest completed
 bar for calibration. True forward signals begin on the next completed session.
 """
 same_saved_day=current_favorite.get("as_of")==authoritative and current_history.get("as_of")==authoritative
 definition_changed=current_favorite.get("pattern_version")!=favorite.get("pattern_version")
 forward_tracker={"as_of":authoritative,"macd_buy_top10":[],"favorite_pattern_tracker":copy.deepcopy(favorite)}
 if not (same_saved_day and definition_changed):return forward_tracker,False
 forward_tracker["favorite_pattern_tracker"]["candidates"]=[]
 return forward_tracker,True

def validate(authoritative,favorite,radar,snapshot,industry,market,history):
 if favorite.get("as_of")!=authoritative or radar.get("as_of")!=authoritative or snapshot.get("as_of")!=authoritative or industry.get("as_of")!=authoritative or market.get("as_of")!=authoritative:
  raise RuntimeError(f"Output dates do not match provider date {authoritative}")
 if radar.get("scan",{}).get("future_data_used") is not False:
  raise RuntimeError("Radar future-data audit failed")
 if snapshot.get("future_data_used") is not False:
  raise RuntimeError("Factor snapshot future-data audit failed")
 if industry.get("future_data_used") is not False:
  raise RuntimeError("Industry Radar future-data audit failed")
 if market.get("future_data_used") is not False or market.get("audit",{}).get("future_rows_used") is not False:
  raise RuntimeError("Market Context future-data audit failed")
 validate_signal_history(history,authoritative)
 if favorite.get("as_of")!=authoritative or favorite.get("pattern_version")!=PATTERN_VERSION or favorite.get("generalization_version")!=GENERALIZATION_VERSION or favorite.get("production_scoring_changed") is not False:
  raise RuntimeError("Favorite-pattern Tracker version/date boundary failed")
 if any(row.get("audit",{}).get("future_data_used") is not False for row in favorite.get("candidates",[]) if row.get("available")):
  raise RuntimeError("Favorite-pattern Tracker future-data audit failed")
 if snapshot.get("registry_version")!=REGISTRY_VERSION:
  raise RuntimeError("Factor snapshot registry version mismatch")
 if snapshot.get("snapshot_mode_version")!=SNAPSHOT_MODE_VERSION or snapshot.get("trigger_policy",{}).get("factor_id")!=TRIGGER_FACTOR_ID:
  raise RuntimeError("Factor snapshot is not using the MACD trigger-first contract")
 if snapshot.get("triggered_count")!=len(snapshot.get("symbols",[])):
  raise RuntimeError("Factor snapshot trigger count mismatch")
 if any(row.get("trigger",{}).get("exact_completed_cross") is not True or row.get("trigger",{}).get("date")!=authoritative for row in snapshot.get("symbols",[])):
  raise RuntimeError("Factor snapshot contains a non-triggered symbol")
 factor_states=[state for row in snapshot.get("symbols",[]) for state in row.get("factors",[])]
 if any([state.get("factor_id") for state in row.get("factors",[])]!=list(MONITORED_FACTOR_IDS) for row in snapshot.get("symbols",[])):
  raise RuntimeError("Factor snapshot does not contain the complete ordered registry")
 if any(state.get("as_of")!=authoritative or state.get("lookahead_audit",{}).get("future_data_used") is not False or not state.get("factor_version") for state in factor_states):
  raise RuntimeError("Factor snapshot state version/date/leakage audit failed")
 gate=favorite.get("gate",{});snapshot_symbols=[row["symbol"] for row in snapshot.get("symbols",[])]
 if gate.get("source")!="daily-factor-snapshot" or gate.get("future_data_used") is not False or gate.get("full_market_deep_scan") is not False:
  raise RuntimeError("Favorite-pattern shared-gate audit failed")
 if gate.get("source_candidate_count")!=len(snapshot_symbols) or gate.get("deep_checked_count")!=len(snapshot_symbols) or gate.get("deep_checked_symbols")!=snapshot_symbols:
  raise RuntimeError("Favorite-pattern deep-check set does not exactly match the MACD gate")
 published=[row.get("symbol") for key in ("candidates","entry_ready_candidates","near_matches") for row in favorite.get(key,[])]
 if any(symbol not in set(snapshot_symbols) for symbol in published):
  raise RuntimeError("Favorite-pattern published a symbol outside the MACD gate")

def run(target=1000,as_of=None,trigger_source="manual"):
 if trigger_source not in TRIGGER_SOURCES:raise ValueError(f"Unsupported trigger source: {trigger_source}")
 authoritative=as_of or latest_reference_day()
 current_favorite=read_json(PUBLIC/"favorite-pattern.json");current_history_summary=read_json(PUBLIC/"signal-history-summary.json");current_radar=read_json(PUBLIC/"rare-opportunity-radar.json");current_snapshot=read_json(PUBLIC/"daily-factor-snapshot.json");current_industry=read_json(PUBLIC/"industry-radar.json");current_market=read_json(PUBLIC/"market-etf-watch.json");current_history=read_json(SIGNAL_HISTORY_PATH)
 if current_favorite.get("as_of")==authoritative and current_favorite.get("pattern_version")==PATTERN_VERSION and current_favorite.get("generalization_version")==GENERALIZATION_VERSION and current_favorite.get("gate",{}).get("source_snapshot_version")==SNAPSHOT_MODE_VERSION and current_history_summary.get("as_of")==authoritative and current_radar.get("as_of")==authoritative and current_snapshot.get("as_of")==authoritative and current_snapshot.get("registry_version")==REGISTRY_VERSION and current_snapshot.get("snapshot_mode_version")==SNAPSHOT_MODE_VERSION and current_radar.get("registry_version")==REGISTRY_VERSION and current_industry.get("as_of")==authoritative and current_market.get("as_of")==authoritative and current_history.get("as_of")==authoritative and current_history.get("signal_schema_version")==SIGNAL_HISTORY_SCHEMA_VERSION:
  return {"result":"already_current","as_of":authoritative,"trigger_source":trigger_source}
 pathlib.Path("work").mkdir(exist_ok=True);PRODUCTION_HISTORY.mkdir(parents=True,exist_ok=True)
 # Every producer writes into one temporary bundle. If any producer or audit
 # fails, the currently published website remains untouched and date-consistent.
 with tempfile.TemporaryDirectory(prefix="daily-update-",dir="work") as folder:
  folder=pathlib.Path(folder)
  # Universe expansion is an internal preparation audit, not a website asset.
  expand_universe(target,authoritative,out=folder/"universe-expansion.json")
  # Load the adjusted daily cache once. The snapshot creates the only MACD
  # candidate pool; every deeper product receives that small pool.
  symbol_rows=load_symbol_rows(authoritative)
  snapshot=run_factor_snapshot(folder/"daily-factor-snapshot.json",authoritative,symbol_rows=symbol_rows)
  favorite=build_gated_report(snapshot,symbol_rows,authoritative)
  radar=run_radar(folder/"rare-opportunity-radar.json",authoritative,snapshot);industry=run_industry_radar(folder/"industry-radar.json",authoritative);market=run_market_context(folder/"market-etf-watch.json",authoritative)
  (folder/"favorite-pattern.json").write_text(json.dumps(compact_favorite_pattern(favorite),ensure_ascii=False,separators=(",",":"))+"\n")
  history_tracker,favorite_forward_deferred=tracker_for_forward_history(current_favorite,current_history,favorite,authoritative)
  history=build_signal_history(current_history,history_tracker,radar,snapshot,industry,market,authoritative)
  (folder/"signal-history.json").write_text(json.dumps(history,ensure_ascii=False,indent=2))
  (folder/"signal-history-summary.json").write_text(json.dumps(compact_signal_history(history),ensure_ascii=False,separators=(",",":"))+"\n")
  # This is the publish gate: no file crosses into public/ until all datasets
  # agree on the same completed session and prove they used no future rows.
  validate(authoritative,favorite,radar,snapshot,industry,market,history);now=datetime.now(timezone.utc).isoformat()
  status={"status":"up_to_date","market":"US","provider":"EODHD","source_latest_complete_date":authoritative,"favorite_pattern_as_of":favorite["as_of"],"factor_snapshot_as_of":snapshot["as_of"],"radar_as_of":radar["as_of"],"industry_radar_as_of":industry["as_of"],"market_context_as_of":market["as_of"],"signal_history_as_of":history["as_of"],"data_dates_match":True,"future_data_used":False,"last_successful_update_at":now,"trigger_source":trigger_source,"checks":{"provider_date_exact":True,"all_production_json_same_date":True,"completed_bars_only":True,"production_outputs_published_atomically":True,"signal_history_append_only":True,"macd_trigger_first":True,"shared_macd_candidate_pool":True,"favorite_pattern_tracker":True,"favorite_pattern_forward_deferred_on_same_date":favorite_forward_deferred}}
  (folder/"update-status.json").write_text(json.dumps(status,ensure_ascii=False,indent=2))
  for name in ("favorite-pattern.json","daily-factor-snapshot.json","rare-opportunity-radar.json","industry-radar.json","market-etf-watch.json","signal-history-summary.json","update-status.json"):os.replace(folder/name,PUBLIC/name)
  os.replace(folder/"signal-history.json",SIGNAL_HISTORY_PATH)
 return {"result":"updated","as_of":authoritative,"eligible":snapshot["eligible_count"],"macd_candidates":snapshot["triggered_count"],"favorite_deep_checks":favorite["gate"]["deep_checked_count"],"radar_signals":len(radar["signals"]),"trigger_source":trigger_source}

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--target",type=int,default=1000);parser.add_argument("--as-of");parser.add_argument("--trigger-source",choices=sorted(TRIGGER_SOURCES),default="manual")
 args=parser.parse_args();print(json.dumps(run(args.target,args.as_of,args.trigger_source),ensure_ascii=False,indent=2))
