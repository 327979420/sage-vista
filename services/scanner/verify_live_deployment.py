"""Fail closed unless the complete Cloudflare production bundle is consistent.

The verifier fetches every public dataset used by the four pages, checks one
expected market date, model contracts and lookahead flags, then returns a small
deployment receipt. Discord runs only after this receipt succeeds.
"""
import argparse,json,time,urllib.error,urllib.parse,urllib.request
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

def verify_once(base,expected):
 # Fetch the whole published bundle on every attempt. A deployment can briefly
 # expose a mix of old and new static assets even when every individual request
 # succeeds, so transport-only retries are insufficient.
 status=fetch(base,"update-status.json",expected,attempts=1);favorite=fetch(base,"favorite-pattern.json",expected,attempts=1);snapshot=fetch(base,"daily-factor-snapshot.json",expected,attempts=1);radar=fetch(base,"rare-opportunity-radar.json",expected,attempts=1);industry=fetch(base,"industry-radar.json",expected,attempts=1);market=fetch(base,"market-etf-watch.json",expected,attempts=1);history_summary=fetch(base,"signal-history-summary.json",expected,attempts=1);ledger_latest=fetch(base,"opportunity-ledger-latest.json",expected,attempts=1);unified_latest=fetch(base,"unified-v2-latest.json",expected,attempts=1)
 dates={status.get("source_latest_complete_date"),status.get("favorite_pattern_as_of"),status.get("factor_snapshot_as_of"),status.get("radar_as_of"),status.get("industry_radar_as_of"),status.get("market_context_as_of"),status.get("signal_history_as_of"),favorite.get("as_of"),snapshot.get("as_of"),radar.get("as_of"),industry.get("as_of"),market.get("as_of"),history_summary.get("as_of"),ledger_latest.get("as_of"),unified_latest.get("coverage",{}).get("end")}
 if dates!={expected}:raise RuntimeError(f"Live deployment date mismatch: {sorted(str(x) for x in dates)}")
 if status.get("status")!="up_to_date" or status.get("data_dates_match") is not True:raise RuntimeError("Live status integrity check failed")
 if status.get("future_data_used") is not False or favorite.get("gate",{}).get("future_data_used") is not False or snapshot.get("future_data_used") is not False or radar.get("scan",{}).get("future_data_used") is not False or industry.get("future_data_used") is not False or market.get("future_data_used") is not False or history_summary.get("future_data_used") is not False:raise RuntimeError("Live future-data audit failed")
 if snapshot.get("snapshot_mode_version")!=SNAPSHOT_MODE_VERSION or status.get("checks",{}).get("macd_trigger_first") is not True or status.get("checks",{}).get("shared_macd_candidate_pool") is not True:raise RuntimeError("Live MACD trigger-first contract failed")
 if favorite.get("as_of")!=expected or favorite.get("pattern_version")!=PATTERN_VERSION or favorite.get("generalization_version")!=GENERALIZATION_VERSION or favorite.get("production_scoring_changed") is not False or "candidates" in favorite or status.get("checks",{}).get("favorite_pattern_tracker") is not True:raise RuntimeError("Live compact favorite-pattern contract failed")
 gate=favorite.get("gate",{});snapshot_symbols=[row.get("symbol") for row in snapshot.get("symbols",[])]
 if gate.get("source")!="daily-factor-snapshot" or gate.get("full_market_deep_scan") is not False or gate.get("source_candidate_count")!=snapshot.get("triggered_count") or gate.get("deep_checked_count")!=snapshot.get("triggered_count") or gate.get("deep_checked_symbols")!=snapshot_symbols:raise RuntimeError("Live shared MACD candidate-pool contract failed")
 if ledger_latest.get("selection_future_data_used") is not False or ledger_latest.get("view",{}).get("scope")!="latest" or not isinstance(ledger_latest.get("view",{}).get("full_event_count"),int):raise RuntimeError("Live compact opportunity-ledger contract failed")
 if len(unified_latest.get("days",[]))!=1 or unified_latest["days"][0].get("date")!=expected:raise RuntimeError("Live latest V2 ranking contract failed")
 return {"result":"verified","as_of":expected,"site_url":base,"favorite_pattern_watchlist":favorite.get("summary",{}).get("watchlist"),"favorite_pattern_entry_ready":favorite.get("summary",{}).get("entry_ready"),"favorite_pattern_deep_checks":gate.get("deep_checked_count"),"factor_symbols":snapshot.get("triggered_count"),"eligible_universe":snapshot.get("eligible_count"),"forward_cases":len(history_summary.get("cases",[])),"opportunity_events":ledger_latest.get("view",{}).get("full_event_count")}

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
