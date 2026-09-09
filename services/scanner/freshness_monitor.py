"""Independent repository-freshness audit for the completed EOD provider date."""
import argparse,json,pathlib
from datetime import datetime,timezone

from .eodhd import latest_reference_day

def evaluate(provider_latest,status):
 dates={"source":status.get("source_latest_complete_date"),"tracker":status.get("tracker_as_of"),"radar":status.get("radar_as_of"),"factor_snapshot":status.get("factor_snapshot_as_of"),"industry_radar":status.get("industry_radar_as_of"),"market_context":status.get("market_context_as_of"),"signal_history":status.get("signal_history_as_of")}
 # Older production states may not have the snapshot field; that is itself stale
 # after the snapshot integration is deployed.
 synchronized=all(value==provider_latest for value in dates.values())
 safe=status.get("future_data_used") is False and status.get("data_dates_match") is True
 return {"result":"fresh" if synchronized and safe else "stale","provider_latest":provider_latest,"repository_dates":dates,"data_dates_match":synchronized,"future_data_used":status.get("future_data_used"),"checked_at":datetime.now(timezone.utc).isoformat()}

def evaluate_live(provider_latest, status, candidate, market, industry):
 result = evaluate(provider_latest, status)
 from services.contracts.cr056_policy import POLICY_VERSION, POLICY_FINGERPRINT
 checks = {
  'candidate_date': candidate.get('as_of') == provider_latest,
  'candidate_policy': candidate.get('policy_version') == POLICY_VERSION and candidate.get('policy_fingerprint') == POLICY_FINGERPRINT,
  'candidate_refresh': candidate.get('refresh_status', {}).get('status') in ('current', 'updated'),
  'market_date': market.get('as_of') == provider_latest,
  'industry_date': industry.get('as_of') == provider_latest and industry.get('display_context', {}).get('as_of') == provider_latest,
 }
 result['live_checks'] = checks
 if not all(checks.values()): result['result'] = 'stale'
 return result


def run(status_path="public/update-status.json", url=None):
 provider_latest = latest_reference_day()
 status = json.loads(pathlib.Path(status_path).read_text())
 result = evaluate(provider_latest, status)
 if url:
  from .verify_live_deployment import fetch
  key = datetime.now(timezone.utc).isoformat()
  try:
   live = evaluate_live(provider_latest, *[fetch(url, path, key, attempts=1) for path in
     ('update-status.json', 'cr056-ranking.json', 'market-etf-watch.json', 'industry-radar.json')])
   result['live'] = live
   if live['result'] != 'fresh': result['result'] = 'stale'
  except Exception as error:
   result['result'] = 'stale'
   result['live'] = {'result':'unavailable','reason':type(error).__name__}
 return result

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--status",default="public/update-status.json")
 parser.add_argument("--url")
 args=parser.parse_args();print(json.dumps(run(args.status,args.url),ensure_ascii=False,indent=2))
