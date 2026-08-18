"""Refresh derived validation views from the versioned point-in-time panel cache."""
import json,pathlib
from .eodhd_factor_validation import rolling_oos
from .research_pipeline import evaluate_report

def run(cache="work/eodhd-panel-v4.json",report_path="public/eodhd-factor-validation.json"):
 panel=json.loads(pathlib.Path(cache).read_text())["panel"];report=json.loads(pathlib.Path(report_path).read_text())
 for row in panel:row["forward"]={int(k):v for k,v in row["forward"].items()}
 report["regime_metrics"]={r:evaluate_report([x for x in panel if x["regime"]==r]) for r in ("risk_on","risk_off")}
 report["rolling_oos"]=rolling_oos([x for x in panel if x["regime"]=="risk_on"])
 pathlib.Path(report_path).write_text(json.dumps(report,indent=2));return report
if __name__=="__main__":print(json.dumps(run()["rolling_oos"]["summary"],indent=2))
