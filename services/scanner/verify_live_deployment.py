"""Fail closed unless the complete Cloudflare production bundle is consistent.

The verifier fetches every public dataset used by the four pages, checks one
expected market date, model contracts and lookahead flags, then returns a small
deployment receipt. Discord runs only after this receipt succeeds.
"""
import argparse,datetime,json,os,pathlib,re,tempfile,time,urllib.error,urllib.parse,urllib.request
from .factor_snapshot import SNAPSHOT_MODE_VERSION
from .favorite_pattern_tracker import GENERALIZATION_VERSION, PATTERN_VERSION

def fetch(base,path,cache_key,attempts=12,delay_seconds=5):
 url=f"{base.rstrip('/')}/{path}?deployment={urllib.parse.quote(cache_key)}"
 request=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"SageVistaDeploymentAudit/1.0"})
 last_error=None
 for attempt in range(attempts):
  try:
   with urllib.request.urlopen(request,timeout=30) as response:
    if response.status!=200:raise RuntimeError(f"Live {path} returned HTTP {response.status}")
    return json.load(response)
  except (urllib.error.HTTPError,urllib.error.URLError,json.JSONDecodeError,RuntimeError) as error:
   last_error=error
   if attempt+1<attempts:time.sleep(delay_seconds)
 raise RuntimeError(f"Live {path} was not ready after {attempts} attempts: {last_error}") from last_error

def fetch_text(base,cache_key):
 url=f"{base.rstrip('/')}?deployment={urllib.parse.quote(cache_key)}"
 request=urllib.request.Request(url,headers={"Accept":"text/html","User-Agent":"SageVistaDeploymentAudit/1.0"})
 with urllib.request.urlopen(request,timeout=30) as response:
  if response.status!=200:raise RuntimeError(f"Live website returned HTTP {response.status}")
  return response.read().decode("utf-8")

def verify_once(base,expected,deployment_commit):
 if not deployment_commit:raise RuntimeError("Deployment commit evidence is required")
 # Fetch the whole published bundle on every attempt. A deployment can briefly
 # expose a mix of old and new static assets even when every individual request
 # succeeds, so transport-only retries are insufficient.
 status=fetch(base,"update-status.json",expected,attempts=1);tracker=fetch(base,"resonance-tracker.json",expected,attempts=1);favorite_public=fetch(base,"favorite-pattern.json",expected,attempts=1);snapshot=fetch(base,"daily-factor-snapshot.json",expected,attempts=1);radar=fetch(base,"rare-opportunity-radar.json",expected,attempts=1);industry=fetch(base,"industry-radar.json",expected,attempts=1);market=fetch(base,"market-etf-watch.json",expected,attempts=1);history=fetch(base,"signal-history.json",expected,attempts=1);history_summary=fetch(base,"signal-history-summary.json",expected,attempts=1);ledger=fetch(base,"opportunity-ledger.json",expected,attempts=1);ledger_latest=fetch(base,"opportunity-ledger-latest.json",expected,attempts=1);unified_latest=fetch(base,"unified-v2-latest.json",expected,attempts=1)
 dates={status.get("source_latest_complete_date"),status.get("tracker_as_of"),status.get("factor_snapshot_as_of"),status.get("radar_as_of"),status.get("industry_radar_as_of"),status.get("market_context_as_of"),status.get("signal_history_as_of"),tracker.get("as_of"),snapshot.get("as_of"),radar.get("as_of"),industry.get("as_of"),market.get("as_of"),history.get("as_of"),history_summary.get("as_of"),ledger_latest.get("as_of"),unified_latest.get("coverage",{}).get("end")}
 if dates!={expected}:raise RuntimeError(f"Live deployment date mismatch: {sorted(str(x) for x in dates)}")
 if status.get("status")!="up_to_date" or status.get("data_dates_match") is not True:raise RuntimeError("Live status integrity check failed")
 if status.get("future_data_used") is not False or snapshot.get("future_data_used") is not False or radar.get("scan",{}).get("future_data_used") is not False or industry.get("future_data_used") is not False or market.get("future_data_used") is not False or history.get("future_data_used") is not False:raise RuntimeError("Live future-data audit failed")
 if snapshot.get("snapshot_mode_version")!=SNAPSHOT_MODE_VERSION or status.get("checks",{}).get("macd_trigger_first") is not True:raise RuntimeError("Live MACD trigger-first contract failed")
 favorite=tracker.get("favorite_pattern_tracker",{})
 if favorite.get("as_of")!=expected or favorite.get("pattern_version")!=PATTERN_VERSION or favorite.get("generalization_version")!=GENERALIZATION_VERSION or favorite.get("production_scoring_changed") is not False or status.get("checks",{}).get("favorite_pattern_tracker") is not True:raise RuntimeError("Live favorite-pattern Tracker contract failed")
 if favorite_public.get("as_of")!=expected or favorite_public.get("pattern_version")!=PATTERN_VERSION or favorite_public.get("generalization_version")!=GENERALIZATION_VERSION or "candidates" in favorite_public:raise RuntimeError("Live compact favorite-pattern contract failed")
 if ledger.get("as_of")!=expected or ledger.get("selection_future_data_used") is not False:raise RuntimeError("Live opportunity ledger audit failed")
 if history_summary.get("future_data_used") is not False or len(history_summary.get("cases",[]))!=len(history.get("cases",[])):raise RuntimeError("Live compact signal-history contract failed")
 if ledger_latest.get("selection_future_data_used") is not False or ledger_latest.get("view",{}).get("scope")!="latest" or ledger_latest.get("view",{}).get("full_event_count")!=len(ledger.get("events",[])):raise RuntimeError("Live compact opportunity-ledger contract failed")
 if len(unified_latest.get("days",[]))!=1 or unified_latest["days"][0].get("date")!=expected:raise RuntimeError("Live latest V2 ranking contract failed")
 website_version=unified_latest.get("version")
 if not website_version:raise RuntimeError("Live website version evidence is missing")
 page=fetch_text(base,deployment_commit)
 if f"Build {deployment_commit[:7]}" not in page:raise RuntimeError("Live deployment commit marker mismatch")
 details=tracker.get("details",{})
 if any(x.get("audit",{}).get("future_rows_used") or x.get("audit",{}).get("latest_bar")!=expected for x in details.values()):raise RuntimeError("Live tracker completeness audit failed")
 return {"result":"verified","as_of":expected,"site_url":base,"website_version":website_version,"deployment_commit":deployment_commit,"tracker_details":len(details),"favorite_pattern_watchlist":favorite.get("summary",{}).get("watchlist"),"favorite_pattern_entry_ready":favorite.get("summary",{}).get("entry_ready"),"factor_symbols":snapshot.get("triggered_count"),"eligible_universe":snapshot.get("eligible_count"),"forward_cases":len(history.get("cases",[])),"opportunity_events":len(ledger.get("events",[]))}

def verify(base,expected,deployment_commit,attempts=12,delay_seconds=5):
 if not deployment_commit:raise RuntimeError("Deployment commit evidence is required")
 last_error=None
 for attempt in range(attempts):
  try:return verify_once(base,expected,deployment_commit)
  except (urllib.error.HTTPError,urllib.error.URLError,json.JSONDecodeError,RuntimeError) as error:
   last_error=error
   if attempt+1<attempts:time.sleep(delay_seconds)
 raise RuntimeError(f"Live deployment bundle was not consistent after {attempts} attempts: {last_error}") from last_error

def _receipt_date(value,label):
 if not isinstance(value,str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}",value) is None:raise RuntimeError(f"{label} must use YYYY-MM-DD")
 try:return datetime.date.fromisoformat(value)
 except ValueError as error:raise RuntimeError(f"{label} must be a valid YYYY-MM-DD date") from error

def persist_verified_receipt(receipt_path,state_path):
 receipt=json.loads(pathlib.Path(receipt_path).read_text())
 required=("as_of","site_url","website_version","deployment_commit")
 if receipt.get("result")!="verified":raise RuntimeError("Deployment receipt is not verified")
 missing=[key for key in required if not receipt.get(key)]
 if missing:raise RuntimeError(f"Deployment receipt is missing required evidence: {', '.join(missing)}")
 target=pathlib.Path(state_path)
 state=json.loads(target.read_text()) if target.exists() else {}
 receipt_date=_receipt_date(receipt["as_of"],"Deployment receipt as_of")
 if "as_of" in state:
  state_date=_receipt_date(state["as_of"],"Production state as_of")
  if state_date>receipt_date:raise RuntimeError("Older deployment receipt cannot replace newer production state")
 state.update({key:receipt[key] for key in required})
 state["live_verified"]=True
 target.parent.mkdir(parents=True,exist_ok=True)
 temporary=None
 try:
  with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=target.parent,prefix=f".{target.name}.",delete=False) as handle:
   temporary=pathlib.Path(handle.name)
   json.dump(state,handle,indent=2)
   handle.write("\n");handle.flush();os.fsync(handle.fileno())
  os.replace(temporary,target)
 except Exception:
  if temporary is not None:temporary.unlink(missing_ok=True)
  raise
 return state

if __name__=="__main__":
 parser=argparse.ArgumentParser();commands=parser.add_subparsers(dest="command",required=True)
 verify_parser=commands.add_parser("verify");verify_parser.add_argument("--url",required=True);verify_parser.add_argument("--expected-as-of",required=True);verify_parser.add_argument("--deployment-commit",required=True)
 persist_parser=commands.add_parser("persist");persist_parser.add_argument("--receipt-path",required=True);persist_parser.add_argument("--state-path",required=True)
 args=parser.parse_args()
 if args.command=="verify":result=verify(args.url,args.expected_as_of,args.deployment_commit)
 else:result=persist_verified_receipt(args.receipt_path,args.state_path)
 print(json.dumps(result,ensure_ascii=False,indent=2))
