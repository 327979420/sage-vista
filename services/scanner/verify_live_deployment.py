"""Fail-closed verification for the public Cloudflare production deployment."""
import argparse,json,time,urllib.error,urllib.parse,urllib.request
from .factor_snapshot import SNAPSHOT_MODE_VERSION

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

def verify_once(base,expected):
 # Fetch the whole published bundle on every attempt. A deployment can briefly
 # expose a mix of old and new static assets even when every individual request
 # succeeds, so transport-only retries are insufficient.
 status=fetch(base,"update-status.json",expected,attempts=1);tracker=fetch(base,"resonance-tracker.json",expected,attempts=1);snapshot=fetch(base,"daily-factor-snapshot.json",expected,attempts=1);radar=fetch(base,"rare-opportunity-radar.json",expected,attempts=1);industry=fetch(base,"industry-radar.json",expected,attempts=1);market=fetch(base,"market-etf-watch.json",expected,attempts=1);history=fetch(base,"signal-history.json",expected,attempts=1);ledger=fetch(base,"opportunity-ledger.json",expected,attempts=1)
 dates={status.get("source_latest_complete_date"),status.get("tracker_as_of"),status.get("factor_snapshot_as_of"),status.get("radar_as_of"),status.get("industry_radar_as_of"),status.get("market_context_as_of"),status.get("signal_history_as_of"),tracker.get("as_of"),snapshot.get("as_of"),radar.get("as_of"),industry.get("as_of"),market.get("as_of"),history.get("as_of")}
 if dates!={expected}:raise RuntimeError(f"Live deployment date mismatch: {sorted(str(x) for x in dates)}")
 if status.get("status")!="up_to_date" or status.get("data_dates_match") is not True:raise RuntimeError("Live status integrity check failed")
 if status.get("future_data_used") is not False or snapshot.get("future_data_used") is not False or radar.get("scan",{}).get("future_data_used") is not False or industry.get("future_data_used") is not False or market.get("future_data_used") is not False or history.get("future_data_used") is not False:raise RuntimeError("Live future-data audit failed")
 if snapshot.get("snapshot_mode_version")!=SNAPSHOT_MODE_VERSION or status.get("checks",{}).get("macd_trigger_first") is not True:raise RuntimeError("Live MACD trigger-first contract failed")
 if ledger.get("as_of")!=expected or ledger.get("selection_future_data_used") is not False:raise RuntimeError("Live opportunity ledger audit failed")
 details=tracker.get("details",{})
 if any(x.get("audit",{}).get("future_rows_used") or x.get("audit",{}).get("latest_bar")!=expected for x in details.values()):raise RuntimeError("Live tracker completeness audit failed")
 return {"result":"verified","as_of":expected,"site_url":base,"tracker_details":len(details),"factor_symbols":snapshot.get("triggered_count"),"eligible_universe":snapshot.get("eligible_count"),"forward_cases":len(history.get("cases",[])),"opportunity_events":len(ledger.get("events",[]))}

def verify(base,expected,attempts=12,delay_seconds=5):
 last_error=None
 for attempt in range(attempts):
  try:return verify_once(base,expected)
  except (urllib.error.HTTPError,urllib.error.URLError,json.JSONDecodeError,RuntimeError) as error:
   last_error=error
   if attempt+1<attempts:time.sleep(delay_seconds)
 raise RuntimeError(f"Live deployment bundle was not consistent after {attempts} attempts: {last_error}") from last_error

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--url",required=True);parser.add_argument("--expected-as-of",required=True)
 args=parser.parse_args();print(json.dumps(verify(args.url,args.expected_as_of),ensure_ascii=False,indent=2))
