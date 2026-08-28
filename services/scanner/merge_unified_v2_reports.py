"""Merge independently saved V2 date partitions without recalculating them."""
import argparse,json,pathlib
from datetime import datetime,timezone
from .unified_v2_scan import _compact_day


def merge(paths,out):
 reports=[json.loads(pathlib.Path(path).read_text()) for path in paths]
 if not reports:raise RuntimeError("No V2 reports supplied")
 versions={x.get("version") for x in reports}
 if len(versions)!=1:raise RuntimeError("Cannot merge different V2 model versions")
 if any(x.get("future_data_used") is not False for x in reports):raise RuntimeError("Future-data audit failed")
 by_date={}
 for report in reports:
  for day in report.get("days",[]):by_date[day["date"]]=day
 days=[_compact_day(by_date[x]) for x in sorted(by_date)]
 if not days:raise RuntimeError("No V2 sessions supplied")
 base=reports[-1]
 result={**base,"generated_at":datetime.now(timezone.utc).isoformat(),"coverage":{"start":days[0]["date"],"end":days[-1]["date"],"sessions":len(days)},"days":days}
 pathlib.Path(out).write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n")
 return result


if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("reports",nargs="+");parser.add_argument("--out",required=True);args=parser.parse_args()
 report=merge(args.reports,args.out);print(json.dumps(report["coverage"],ensure_ascii=False))
