"""Independent repository-freshness audit for the completed EOD provider date."""
import argparse,json,pathlib
from datetime import datetime,timezone

from .eodhd import latest_reference_day

def evaluate(provider_latest,status):
 dates={"source":status.get("source_latest_complete_date"),"tracker":status.get("tracker_as_of"),"radar":status.get("radar_as_of"),"factor_snapshot":status.get("factor_snapshot_as_of"),"industry_radar":status.get("industry_radar_as_of")}
 # Older production states may not have the snapshot field; that is itself stale
 # after the snapshot integration is deployed.
 synchronized=all(value==provider_latest for value in dates.values())
 safe=status.get("future_data_used") is False and status.get("data_dates_match") is True
 return {"result":"fresh" if synchronized and safe else "stale","provider_latest":provider_latest,"repository_dates":dates,"data_dates_match":synchronized,"future_data_used":status.get("future_data_used"),"checked_at":datetime.now(timezone.utc).isoformat()}

def run(status_path="public/update-status.json"):
 status=json.loads(pathlib.Path(status_path).read_text());return evaluate(latest_reference_day(),status)

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--status",default="public/update-status.json")
 args=parser.parse_args();print(json.dumps(run(args.status),ensure_ascii=False,indent=2))
