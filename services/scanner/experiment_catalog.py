"""Build a lossless, machine-readable index over the append-only experiment ledger."""
import json,pathlib
from datetime import datetime,timezone

from .factor_registry import FACTORS

ROOT=pathlib.Path(__file__).parents[2]

def build(ledger=None):
 rows=ledger if ledger is not None else [json.loads(line) for line in (ROOT/"research/experiments.jsonl").read_text().splitlines() if line.strip()]
 ids=[x["experiment_id"] for x in rows]
 if len(ids)!=len(set(ids)):raise ValueError("Duplicate experiment_id")
 known=set(ids);factor_links={factor.id:[ref for ref in factor.research_refs if ref in known] for factor in FACTORS}
 missing_refs=sorted({ref for factor in FACTORS for ref in factor.research_refs if ref not in known})
 linked={ref for refs in factor_links.values() for ref in refs}
 return {"schema_version":"1.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"source":"research/experiments.jsonl","experiment_count":len(rows),"policy":{"append_only":True,"failed_results_preserved":True,"historical_backtest_separate_from_production_forward":True},"experiments":rows,"factor_experiments":factor_links,"unlinked_experiment_ids":sorted(known-linked),"missing_registry_references":missing_refs}

def write(out="public/experiment-catalog.json"):
 payload=build();pathlib.Path(out).write_text(json.dumps(payload,ensure_ascii=False,indent=2));return payload

if __name__=="__main__":print(json.dumps(write(),ensure_ascii=False,indent=2))
