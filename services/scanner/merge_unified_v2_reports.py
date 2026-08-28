"""Merge independently saved V2 date partitions without recalculating them."""
import argparse,json,pathlib
from datetime import datetime,timezone
from .unified_v2_scan import _compact_day


def merge(paths,out):
 reports=[json.loads(pathlib.Path(path).read_text()) for path in paths]
 if not reports:raise RuntimeError("No V2 reports supplied")
 if any(x.get("future_data_used") is not False for x in reports):raise RuntimeError("Future-data audit failed")
 by_date={}
 for report in reports:
  registry=report.get("model",{}).get("factor_registry_version","legacy_unrecorded")
  for day in report.get("days",[]):by_date[day["date"]]={"model_version":report.get("version","legacy_unrecorded"),"factor_registry_version":registry,"ruleset_id":f"{report.get('version','legacy_unrecorded')}+factors-{registry}",**day}
 days=[_compact_day(by_date[x]) for x in sorted(by_date)]
 if not days:raise RuntimeError("No V2 sessions supplied")
 # Cloudflare serves public files with a 25 MiB per-asset ceiling. Keep full
 # audit rows for the latest 30 sessions; older rows retain every hit and all
 # scoring fields while dropping repetitive non-hit ledger entries.
 detailed_start=max(0,len(days)-30)
 for index,day in enumerate(days):
  if index>=detailed_start:continue
  for row in day.get("ranking",[]):
   row["factor_ledger"]=[item for item in row.get("factor_ledger",[]) if item.get("hit") or item.get("points")]
 base=reports[-1]
 result={**base,"generated_at":datetime.now(timezone.utc).isoformat(),"coverage":{"start":days[0]["date"],"end":days[-1]["date"],"sessions":len(days)},"version_policy":"每个历史日冻结其首次回放时的模型与因子库版本；新规则只用于后续批次，除非另开重算实验","model_versions":sorted({x.get("model_version","legacy_unrecorded") for x in days}),"factor_registry_versions":sorted({x.get("factor_registry_version","legacy_unrecorded") for x in days}),"days":days}
 pathlib.Path(out).write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n")
 return result


if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("reports",nargs="+");parser.add_argument("--out",required=True);args=parser.parse_args()
 report=merge(args.reports,args.out);print(json.dumps(report["coverage"],ensure_ascii=False))
