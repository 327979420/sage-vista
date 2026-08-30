"""One-time, auditable recovery of real Rare Radar signals preserved in Git history."""
import argparse,copy,json,pathlib,subprocess
from datetime import datetime,timezone

from .signal_history import HORIZONS,PRODUCT_VERSION,SCHEMA_VERSION,_immutable_fingerprint,_update_forward,validate

PUBLIC=pathlib.Path("public")
RECOVERY_VERSION="git-rare-radar-recovery-v1"
LEGACY_DEFINITION="legacy-rare-score-v1"

def _factor_states(signal):
 ids=signal.get("factor_ids",[]);names=signal.get("components",[])
 return [{"factor_id":factor_id,"factor_version":None,"temporal_status":"ACTIVE","hit":True,"recent_hit":True,"latest_hit_date":signal.get("date"),"bars_since_hit":0,"research_status":"historical_original","score_role":"legacy_production"} for factor_id in ids] or [{"factor_id":name,"factor_version":None,"temporal_status":"ACTIVE","hit":True,"recent_hit":True,"latest_hit_date":signal.get("date"),"bars_since_hit":0,"research_status":"historical_original","score_role":"legacy_production"} for name in names]

def _new_recovered_case(symbol,observations,as_of):
 first=observations[0];last=observations[-1];signal=first["signal"];day=first["date"]
 case={"signal_id":f"SVP1-{symbol}-{day}","signal_schema_version":SCHEMA_VERSION,"observation_mode":"production_forward","product_version":"SV-PRODUCT-LEGACY-RECOVERED-V1","signal_definition_version":LEGACY_DEFINITION,"symbol":symbol,"first_seen_date":day,"last_seen_date":last["date"],"days_active":len(observations),"absent_sessions":0,"lifecycle":"MONITORING","initial_source_systems":["multi_factor_radar"],"source_systems":["multi_factor_radar"],"latest_current_status":"historical_recovered","entry":{"convention":"next_trading_day_adjusted_open","date":None,"price":None},
 "signal_time_snapshot":{"technical":{"tracker_rank":None,"technical_score":None,"combined_score":None,"setup":None,"status":None,"rank_reason":None},"multi_factor":{"factor_registry_version":first["radar"].get("registry_version"),"legacy_production_score":signal.get("total_score",signal.get("score")),"official_score":signal.get("official_score",0),"experimental_observational_score":signal.get("experimental_observational_score"),"score_contributions":copy.deepcopy(signal.get("factor_ids",[])),"factor_states":_factor_states(signal),"non_scoring_evidence":copy.deepcopy(signal.get("non_scoring_hits",[])),"risks":copy.deepcopy(signal.get("risks",[]))},"industry":{"industry_radar_as_of":None,"membership_version":None,"rule_version":None,"themes":[]},"market":{"status":"unavailable_at_recovery"}},
 "versions":{"code_version":PRODUCT_VERSION,"factor_registry_version":first["radar"].get("registry_version"),"industry_membership_version":None},"forward":{"returns":{str(x):None for x in HORIZONS},"mfe":None,"mae":None,"elapsed_sessions":0,"status":"pending","data_status":"pending"},
 "daily_states":[{"date":x["date"],"price":x["signal"].get("price"),"source_systems":["multi_factor_radar"],"in_current_opportunities":True,"legacy_production_score":x["signal"].get("total_score",x["signal"].get("score")),"official_score":x["signal"].get("official_score",0),"experimental_observational_score":x["signal"].get("experimental_observational_score"),"factor_states":_factor_states(x["signal"])} for x in observations],
 "recovery":{"recovered_from_git":True,"recovery_version":RECOVERY_VERSION,"source_commits":sorted({x["commit"] for x in observations}),"original_signal_days":[x["date"] for x in observations],"limitations":["Recorder did not exist at original signal time","Unavailable original context is not reconstructed from current definitions"]},"audit":{"future_data_used":False,"created_as_of":as_of,"last_updated_as_of":as_of,"recovered_at":datetime.now(timezone.utc).isoformat()}}
 case["immutable_fingerprint"]=_immutable_fingerprint(case);return case

def recover(previous,radar_versions,as_of,loader=lambda _:[]):
 """Union same-day production appearances; never let a later rewrite erase an earlier alert."""
 by_day={}
 for version in radar_versions:
  radar=version["radar"];day=radar.get("as_of")
  if not day or day>as_of:continue
  for signal in radar.get("signals",[]):
   signal_day=signal.get("date",day);key=(signal["symbol"],signal_day);score=signal.get("total_score",signal.get("score",0))
   current=by_day.get(key)
   if current is None or score>current["signal"].get("total_score",current["signal"].get("score",0)):by_day[key]={"date":signal_day,"signal":copy.deepcopy(signal),"radar":copy.deepcopy(radar),"commit":version["commit"]}
 grouped={}
 for (symbol,_),item in by_day.items():grouped.setdefault(symbol,[]).append(item)
 cases=copy.deepcopy(previous.get("cases",[]));existing={(x["symbol"],x["first_seen_date"]):x for x in cases}
 for symbol,items in sorted(grouped.items()):
  items.sort(key=lambda x:x["date"]);key=(symbol,items[0]["date"])
  recovered=_new_recovered_case(symbol,items,as_of)
  if key in existing:
   case=existing[key];case["recovery"]=recovered["recovery"]
   case["signal_time_snapshot"]["multi_factor"]["legacy_production_score"]=recovered["signal_time_snapshot"]["multi_factor"]["legacy_production_score"]
   by_date={x["date"]:x for x in case.get("daily_states",[])}
   for state in recovered["daily_states"]:
    if state["date"] in by_date:by_date[state["date"]]["legacy_production_score"]=state["legacy_production_score"]
    else:case.setdefault("daily_states",[]).append(state)
   case["daily_states"].sort(key=lambda x:x["date"]);case["immutable_fingerprint"]=_immutable_fingerprint(case);case["audit"]["recovery_migrated_as_of"]=as_of
  else:
   case=recovered;_update_forward(case,as_of,loader);cases.append(case);existing[key]=case
 cases.sort(key=lambda x:(x["first_seen_date"],x["symbol"],x["signal_id"]))
 payload={**copy.deepcopy(previous),"signal_schema_version":SCHEMA_VERSION,"as_of":as_of,"generated_at":datetime.now(timezone.utc).isoformat(),"observation_mode":"production_forward","future_data_used":False,"cases":cases}
 payload.pop("content_hash",None);validate(payload,as_of);return payload

def git_versions():
 commits=subprocess.check_output(["git","log","--format=%H","--","public/rare-opportunity-radar.json"],text=True).splitlines();out=[]
 for commit in reversed(commits):
  try:radar=json.loads(subprocess.check_output(["git","show",f"{commit}:public/rare-opportunity-radar.json"],text=True,stderr=subprocess.DEVNULL))
  except (subprocess.CalledProcessError,json.JSONDecodeError):continue
  out.append({"commit":commit,"radar":radar})
 return out

def run(history_path="research/production-history/signal-history.json",out=None):
 path=pathlib.Path(history_path);previous=json.loads(path.read_text());payload=recover(previous,git_versions(),previous["as_of"])
 target=pathlib.Path(out) if out else path;target.write_text(json.dumps(payload,ensure_ascii=False,indent=2));return payload

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--history",default="research/production-history/signal-history.json");parser.add_argument("--out")
 args=parser.parse_args();result=run(args.history,args.out);print(json.dumps({"cases":len(result["cases"]),"as_of":result["as_of"]},ensure_ascii=False))
