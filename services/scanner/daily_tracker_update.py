"""Fail-closed daily updater shared by the website and future Discord alerts."""
import argparse,json,os,pathlib,tempfile
from datetime import datetime,timezone
from .eodhd import latest_reference_day
from .expand_tracker_universe import run as expand_universe
from .factor_snapshot import run as run_factor_snapshot
from .factor_registry import REGISTRY_VERSION
from .factor_detectors import MONITORED_FACTOR_IDS
from .industry_radar import run as run_industry_radar
from .rare_opportunity_scanner import run as run_radar
from .resonance_tracker import run as run_tracker
from .signal_history import build as build_signal_history,validate as validate_signal_history

PUBLIC=pathlib.Path("public")

def read_json(path):
 path=pathlib.Path(path)
 return json.loads(path.read_text()) if path.exists() else {}

def validate(authoritative,tracker,radar,snapshot,industry,history):
 if tracker.get("as_of")!=authoritative or radar.get("as_of")!=authoritative or snapshot.get("as_of")!=authoritative or industry.get("as_of")!=authoritative:
  raise RuntimeError(f"Output dates do not match provider date {authoritative}")
 if radar.get("scan",{}).get("future_data_used") is not False:
  raise RuntimeError("Radar future-data audit failed")
 if snapshot.get("future_data_used") is not False:
  raise RuntimeError("Factor snapshot future-data audit failed")
 if industry.get("future_data_used") is not False:
  raise RuntimeError("Industry Radar future-data audit failed")
 validate_signal_history(history,authoritative)
 if snapshot.get("registry_version")!=REGISTRY_VERSION:
  raise RuntimeError("Factor snapshot registry version mismatch")
 factor_states=[state for row in snapshot.get("symbols",[]) for state in row.get("factors",[])]
 if any([state.get("factor_id") for state in row.get("factors",[])]!=list(MONITORED_FACTOR_IDS) for row in snapshot.get("symbols",[])):
  raise RuntimeError("Factor snapshot does not contain the complete ordered registry")
 if any(state.get("as_of")!=authoritative or state.get("lookahead_audit",{}).get("future_data_used") is not False or not state.get("factor_version") for state in factor_states):
  raise RuntimeError("Factor snapshot state version/date/leakage audit failed")
 details=tracker.get("details",{})
 if any(x.get("audit",{}).get("future_rows_used") or x.get("audit",{}).get("latest_bar")!=authoritative for x in details.values()):
  raise RuntimeError("Tracker bar-date or future-data audit failed")

def run(target=1000,as_of=None):
 authoritative=as_of or latest_reference_day()
 current_tracker=read_json(PUBLIC/"resonance-tracker.json");current_radar=read_json(PUBLIC/"rare-opportunity-radar.json");current_snapshot=read_json(PUBLIC/"daily-factor-snapshot.json");current_industry=read_json(PUBLIC/"industry-radar.json");current_history=read_json(PUBLIC/"signal-history.json")
 if current_tracker.get("as_of")==authoritative and current_radar.get("as_of")==authoritative and current_snapshot.get("as_of")==authoritative and current_industry.get("as_of")==authoritative and current_history.get("as_of")==authoritative:
  return {"result":"already_current","as_of":authoritative}
 pathlib.Path("work").mkdir(exist_ok=True)
 with tempfile.TemporaryDirectory(prefix="daily-update-",dir="work") as folder:
  folder=pathlib.Path(folder)
  # The expansion report remains temporary so an existing uncommitted public file is never overwritten.
  expand_universe(target,authoritative,out=folder/"universe-expansion.json")
  tracker=run_tracker(folder/"resonance-tracker.json",authoritative);snapshot=run_factor_snapshot(folder/"daily-factor-snapshot.json",authoritative);radar=run_radar(folder/"rare-opportunity-radar.json",authoritative,snapshot);industry=run_industry_radar(folder/"industry-radar.json",authoritative)
  market=read_json(PUBLIC/"market-etf-watch.json");history=build_signal_history(current_history,tracker,radar,snapshot,industry,market,authoritative)
  (folder/"signal-history.json").write_text(json.dumps(history,ensure_ascii=False,indent=2))
  validate(authoritative,tracker,radar,snapshot,industry,history);now=datetime.now(timezone.utc).isoformat()
  status={"status":"up_to_date","market":"US","provider":"EODHD","source_latest_complete_date":authoritative,"tracker_as_of":tracker["as_of"],"factor_snapshot_as_of":snapshot["as_of"],"radar_as_of":radar["as_of"],"industry_radar_as_of":industry["as_of"],"signal_history_as_of":history["as_of"],"data_dates_match":True,"future_data_used":False,"last_successful_update_at":now,"checks":{"provider_date_exact":True,"all_production_json_same_date":True,"completed_bars_only":True,"production_outputs_published_atomically":True,"signal_history_append_only":True}}
  (folder/"update-status.json").write_text(json.dumps(status,ensure_ascii=False,indent=2))
  for name in ("resonance-tracker.json","daily-factor-snapshot.json","rare-opportunity-radar.json","industry-radar.json","signal-history.json","update-status.json"):os.replace(folder/name,PUBLIC/name)
 return {"result":"updated","as_of":authoritative,"eligible":tracker["universe"]["eligible"],"radar_signals":len(radar["signals"])}

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--target",type=int,default=1000);parser.add_argument("--as-of")
 args=parser.parse_args();print(json.dumps(run(args.target,args.as_of),ensure_ascii=False,indent=2))
