"""Conservative, explicitly experimental scoring of canonical factor states."""
from .factor_registry import FACTORS_BY_ID

def _present(state,factor):
 return bool(state.get("recent_hit") if factor.factor_type=="event" else state.get("hit"))

def experimental_score(states):
 by_id={state["factor_id"]:state for state in states};eligible=[];non_scoring=[]
 for factor_id,state in by_id.items():
  factor=FACTORS_BY_ID[factor_id]
  if not state.get("available") or not _present(state,factor):continue
  reason=None
  if factor.status in {"rejected","unstable","insufficient_sample"}:reason=factor.status
  elif factor.score_tier=="display_only" or not factor.experimental_weight:reason="display_only"
  elif factor.depends_on and any(parent not in by_id or not _present(by_id[parent],FACTORS_BY_ID[parent]) for parent in factor.depends_on):reason="dependency_missing"
  elif factor.dependency_policy=="support_context" and not state.get("evidence",{}).get("support_context"):reason="support_context_missing"
  if reason:non_scoring.append({"factor_id":factor_id,"reason":reason});continue
  eligible.append({"factor_id":factor_id,"tier":factor.score_tier,"weight":factor.experimental_weight,"redundancy_group":factor.redundancy_group})
 # One contribution per redundancy group: retain the maximum weight, then stable ID.
 chosen={}
 for item in eligible:
  group=item["redundancy_group"];current=chosen.get(group)
  if current is None or (item["weight"],item["factor_id"])>(current["weight"],current["factor_id"]):chosen[group]=item
 contributions=sorted(chosen.values(),key=lambda item:item["factor_id"])
 selected={item["factor_id"] for item in contributions}
 non_scoring.extend({"factor_id":item["factor_id"],"reason":"redundancy_capped"} for item in eligible if item["factor_id"] not in selected)
 core=sum(item["weight"] for item in contributions if item["tier"]=="core");aux=sum(item["weight"] for item in contributions if item["tier"]=="auxiliary")
 official=sum(FACTORS_BY_ID[item["factor_id"]].weight for item in contributions if FACTORS_BY_ID[item["factor_id"]].score_mode=="official")
 return {"official_score":official,"experimental_observational_score":core+aux,"experimental_core_score":core,"experimental_auxiliary_score":aux,"score_contributions":contributions,"non_scoring_observations":sorted(non_scoring,key=lambda item:item["factor_id"]),"redundancy_policy":"maximum contribution per redundancy_group"}
