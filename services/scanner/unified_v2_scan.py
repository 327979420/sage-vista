"""Build the point-in-time multi-factor ranking from auditable evidence.

The ranking intentionally answers "which candidate has more technical
confirmation?" rather than claiming a calibrated win probability.  Every
objectively detected positive factor remains visible even when its historical
research weight is zero.  Industry and market context are stored separately and
can only break a complete technical tie.
"""
import argparse,json,pathlib,tempfile
from datetime import datetime,timezone

from .factor_snapshot import build_snapshot
from .factor_registry import FACTORS_BY_ID,REGISTRY_VERSION
from .industry_radar import run as industry_run
from .macd_factor_backtest import adjusted_rows
from .market_etf_watch import FUNDS,build as market_build

OUT="public/unified-v2-rankings.json"
LATEST_OUT="public/unified-v2-latest.json"
MODEL_VERSION="unified-v2-macd-trigger-1.4.0"
RULESET_ID=f"{MODEL_VERSION}+factors-{REGISTRY_VERSION}"
RARE_LIMIT=5
REMAINING_FACTOR_COUNT=len(FACTORS_BY_ID)-1
BASELINE_CORE={"qualification.long_trend":2,"macd.daily_bull_cross":3}
B_SHADOW_IDS={"volume.bottom_expansion","structure.support_bullish_engulfing","structure.trendline_three_push","structure.bottom_bullish_engulfing","macd.weekly_histogram_improving"}
GATE_FACTOR_IDS=set(BASELINE_CORE)
TIMEFRAME_PROFILE_VERSION="timeframe-profile-v1.0.0"
TIMEFRAME_KEYS={"daily":"daily","weekly_completed":"weekly","monthly_completed":"monthly"}
TIMEFRAME_LABELS={"daily":"日线主导","weekly":"周线主导","monthly":"月线主导"}


def _rankable_positive_hits(hits):
 """Return positive evidence after gates, risks and dependencies are removed."""
 positive=set()
 for factor_id in hits:
  factor=FACTORS_BY_ID.get(factor_id)
  if not factor or factor_id in GATE_FACTOR_IDS or factor.evidence_family=="risk":continue
  if factor.depends_on and not all(parent in hits for parent in factor.depends_on):continue
  positive.add(factor_id)
 return positive


def _resonance_summary(hits):
 """Count raw evidence, independent families and explicit confirmations.

 Raw hits are deliberately not deduplicated: the user wants to see every
 objective confirmation.  Family breadth and dependency/timeframe bonuses sit
 beside that raw count so correlated evidence remains auditable.
 """
 positive=_rankable_positive_hits(hits)
 families={FACTORS_BY_ID[factor_id].evidence_family for factor_id in positive}
 timeframe_counts={key:0 for key in TIMEFRAME_LABELS}
 family_timeframes={family:set() for family in families}
 for factor_id in positive:
  factor=FACTORS_BY_ID[factor_id];timeframe=TIMEFRAME_KEYS.get(factor.timeframe)
  if timeframe:
   timeframe_counts[timeframe]+=1;family_timeframes[factor.evidence_family].add(timeframe)
 confirmations=[]
 for child_id in sorted(positive):
  child=FACTORS_BY_ID[child_id]
  for parent_id in child.depends_on:
   if parent_id in positive:confirmations.append({"parent":parent_id,"child":child_id,"family":child.evidence_family,"bonus":1})
 resonance=[]
 for family,frames in sorted(family_timeframes.items()):
  if {"daily","weekly"}<=frames:resonance.append({"family":family,"timeframes":["daily","weekly"],"bonus":2})
  if {"weekly","monthly"}<=frames:resonance.append({"family":family,"timeframes":["weekly","monthly"],"bonus":2})
  if {"daily","monthly"}<=frames:resonance.append({"family":family,"timeframes":["daily","monthly"],"bonus":1})
  if {"daily","weekly","monthly"}<=frames:resonance.append({"family":family,"timeframes":["daily","weekly","monthly"],"bonus":2})
 confirmation_bonus=sum(item["bonus"] for item in confirmations)
 timeframe_bonus=sum(item["bonus"] for item in resonance)
 score=len(positive)+len(families)+confirmation_bonus+timeframe_bonus
 risks=sorted(factor_id for factor_id in hits if (factor:=FACTORS_BY_ID.get(factor_id)) and factor.evidence_family=="risk")
 return {"version":"technical-resonance-count-v1.0.0","positive_hit_count":len(positive),"positive_factor_ids":sorted(positive),"family_count":len(families),"families":sorted(families),"timeframe_counts":timeframe_counts,"parent_child_confirmation_bonus":confirmation_bonus,"parent_child_confirmations":confirmations,"timeframe_resonance_bonus":timeframe_bonus,"timeframe_resonances":resonance,"risk_hit_count":len(risks),"risk_factor_ids":risks,"technical_resonance_score":score,"formula":f"{len(positive)}颗 + {len(families)}家族 + {confirmation_bonus}重复确认 + {timeframe_bonus}周期共振 = {score}"}

def _factor_ledger(states,hits,resonance):
 ledger=[];shadow_groups=set()
 positive=set(resonance["positive_factor_ids"])
 confirmation_children={item["child"] for item in resonance["parent_child_confirmations"]}
 for factor_id,state in states.items():
  factor=FACTORS_BY_ID.get(factor_id);points=0;shadow_points=0;rule="未命中或当前不可检测"
  counted=factor_id in positive
  if factor_id in BASELINE_CORE:
   rule="共同门票：显示，不参与候选间颗数排序" if factor_id in hits else "共同门票未满足"
  elif counted:
   points=1;rule=f"技术证据 +1颗；研究状态 {factor.status}"
  if factor_id in B_SHADOW_IDS:
   group=factor.redundancy_group if factor else factor_id
   if factor_id in hits and group not in shadow_groups:shadow_points=1;shadow_groups.add(group)
  if factor and factor.evidence_family=="risk" and factor_id in hits:rule="风险证据：单列，不增加技术颗数"
  ledger.append({"factor_id":factor_id,"name":factor.name_zh if factor else factor_id,"available":bool(state.get("available")),"hit":factor_id in hits,"active_now":bool(state.get("hit")),"recent_hit":bool(state.get("recent_hit")),"bars_since_hit":state.get("bars_since_hit"),"latest_hit_date":state.get("latest_hit_date"),"points":points,"counted_in_resonance":counted,"count_points":points,"confirmation_bonus":1 if factor_id in confirmation_children else 0,"factor_family":factor.evidence_family if factor else None,"timeframe":TIMEFRAME_KEYS.get(factor.timeframe,factor.timeframe) if factor else None,"research_status":factor.status if factor else None,"shadow_points":shadow_points,"score_rule":rule,"evidence":state.get("evidence",{})})
 return ledger

def _present(state):
 return bool(state.get("recent_hit") if state.get("factor_id") in {"macd.daily_bull_cross","structure.support_bullish_engulfing","structure.engulfing_bullish_follow_through","volume.bottom_expansion"} else state.get("hit"))

def _timeframe_profile(states,hits,resonance):
 """Show every counted daily/weekly/monthly hit used by the rank."""
 evidence={key:[] for key in TIMEFRAME_LABELS};points={key:0.0 for key in TIMEFRAME_LABELS};families={key:set() for key in TIMEFRAME_LABELS}
 for factor_id in resonance["positive_factor_ids"]:
  factor=FACTORS_BY_ID[factor_id];timeframe=TIMEFRAME_KEYS.get(factor.timeframe)
  if not timeframe:continue
  evidence[timeframe].append(factor_id);points[timeframe]+=1;families[timeframe].add(factor.evidence_family)
 total=sum(points.values());shares={key:round(value/total,4) if total else 0.0 for key,value in points.items()};groups={key:len(value) for key,value in evidence.items()}
 anchors={key:bool(families[key]) for key in TIMEFRAME_LABELS}
 eligible={key:points[key]>0 for key in TIMEFRAME_LABELS}
 choices=[key for key in TIMEFRAME_LABELS if eligible[key]]
 if not choices:
  dominant=None;label="周期证据不足";resonance=False
 else:
  dominant=max(choices,key=lambda key:(points[key],{"daily":0,"weekly":1,"monthly":2}[key]))
  ordered=sorted((shares[key] for key in choices),reverse=True);lead=ordered[0]-(ordered[1] if len(ordered)>1 else 0)
  is_resonance=len(choices)>1 and (shares[dominant]<.5 or lead<.1)
  label=f"多周期共振（{TIMEFRAME_LABELS[dominant]}）" if is_resonance else TIMEFRAME_LABELS[dominant]
 return {"version":TIMEFRAME_PROFILE_VERSION,"status":"count_based_research_priority","label":label,"dominant_timeframe":dominant,"is_resonance":is_resonance,"points":{key:round(value,2) for key,value in points.items()},"shares":shares,"independent_groups":{key:len(families[key]) for key in TIMEFRAME_LABELS},"anchor_present":anchors,"evidence":evidence,"resonance_bonus":resonance["timeframe_resonance_bonus"],"resonances":resonance["timeframe_resonances"]}

def _load_cache(cache_dir):
 data={}
 for path in pathlib.Path(cache_dir).glob("*.json"):
  try:
   rows=adjusted_rows(json.loads(path.read_text()))
   if rows:data[path.stem]=rows
  except Exception:continue
 return data

def shadow_scan_inputs(prepared):
 """Expose the shared point-in-time input without changing the legacy run path."""
 from services.market_data.consumer import require_shadow_rows
 return {"input_audit":prepared.audit(),"symbol_rows":require_shadow_rows(prepared,consumer="unified_v2_backtest")}

def shadow_gate_batch(prepared,*,generated_at,scan_batch_id,previous_events=(),market_revision_evidence=None):
 """Run the same M03 producer in backtest shadow mode; legacy run stays unchanged."""
 from services.gates.producer import produce_gate_batch
 shadow_scan_inputs(prepared)
 return produce_gate_batch(prepared,generated_at=generated_at,scan_batch_id=scan_batch_id,previous_events=previous_events,market_revision_evidence=market_revision_evidence)

def shadow_technical_evidence(prepared,*,gate_events,generated_at):
 """Run the same M04 producer in replay shadow mode; ranking stays unchanged."""
 from services.factors import produce_technical_evidence
 shadow_scan_inputs(prepared)
 return produce_technical_evidence(prepared,gate_events=gate_events,generated_at=generated_at)

def _dates(data,start,end):
 return [x["date"] for x in data.get("SPY",[]) if start<=x["date"]<=end]

def _market(data,day):
 raw={code:data.get(code,[]) for code in FUNDS}
 try:return market_build(raw,day)
 except Exception:return None

def _industry(day):
 try:
  with tempfile.TemporaryDirectory() as folder:return industry_run(pathlib.Path(folder)/"industry.json",day)
 except Exception:return {"as_of":day,"historical_membership_safe":False,"status":"unavailable","ticker_context":{}}

def _candidate(row,market,industry):
 states={x["factor_id"]:x for x in row["factors"]};hits={key for key,value in states.items() if value.get("available") and _present(value)}
 trigger=row.get("trigger",{})
 if trigger.get("factor_id")!="macd.daily_bull_cross" or trigger.get("exact_completed_cross") is not True:return None
 if "qualification.long_trend" not in hits or "macd.daily_bull_cross" not in hits:return None
 resonance=_resonance_summary(hits);technical=resonance["technical_resonance_score"]
 market_score=market["market_temperature"]["score"] if market else None
 market_adjustment=1 if market_score is not None and market_score>=4 else -1 if market_score is not None and market_score<=1 else 0
 contexts=industry.get("ticker_context",{}).get(row["symbol"],[]) if industry.get("historical_membership_safe") else []
 states_seen=sorted({x.get("state") for x in contexts if x.get("state")})
 industry_adjustment=1 if "Leadership" in states_seen else .5 if set(states_seen)&{"Recovery","Pullback Watch"} else 0
 final=technical+market_adjustment+industry_adjustment
 ledger=_factor_ledger(states,hits,resonance)
 b_shadow_score=sum(item["shadow_points"] for item in ledger)
 reasons=[f"{resonance['positive_hit_count']}颗技术证据",f"{resonance['family_count']}个家族"]
 if resonance["parent_child_confirmation_bonus"]:reasons.append(f"{resonance['parent_child_confirmation_bonus']}次重复确认")
 if resonance["timeframe_resonance_bonus"]:reasons.append(f"跨周期共振 +{resonance['timeframe_resonance_bonus']}")
 return {"symbol":row["symbol"],"price":row["price"],"technical_score":technical,"technical_resonance":resonance,"b_shadow_score":b_shadow_score,"market_adjustment":market_adjustment,"industry_adjustment":industry_adjustment,"context_adjustment":market_adjustment+industry_adjustment,"final_priority":final,"score_equation":f"{resonance['formula']}；行业 {industry_adjustment:+g}、大盘 {market_adjustment:+g} 只作同分上下文","reasons":reasons,"industry_states":states_seen,"factor_ledger":ledger,"timeframe_profile":_timeframe_profile(states,hits,resonance),"execution_policy_version":row.get("execution_policy_version"),"support_plan":row.get("support_plan"),"experimental_score":row["scoring"]["experimental_observational_score"]}

def _rank_day(snapshot,market,industry):
 day=snapshot["as_of"]
 if market is not None and market.get("as_of")!=day:raise RuntimeError("Published V2 market input is not synchronized")
 if industry.get("as_of")!=day:raise RuntimeError("Published V2 industry input is not synchronized")
 candidates=[x for row in snapshot["symbols"] if (x:=_candidate(row,market,industry))]
 candidates.sort(key=lambda x:(-x["technical_score"],-x["technical_resonance"]["timeframe_resonance_bonus"],-x["technical_resonance"]["family_count"],-x["technical_resonance"]["positive_hit_count"],-x["context_adjustment"],x["symbol"]))
 for rank,item in enumerate(candidates[:30],1):item["rank"]=rank
 rare=candidates[:RARE_LIMIT]
 pool=[{"symbol":x["symbol"],"price":x["price"],"technical_score":x["technical_score"],"technical_resonance":x["technical_resonance"],"b_shadow_score":x["b_shadow_score"],"market_adjustment":x["market_adjustment"],"industry_adjustment":x["industry_adjustment"],"base_priority":x["technical_score"],"context_reference":x["final_priority"],"experimental_score":x["experimental_score"],"timeframe_profile":x["timeframe_profile"],"hit_factor_ids":[f["factor_id"] for f in x["factor_ledger"] if f["hit"]]} for x in candidates]
 rare_rows=[{k:v for k,v in x.items() if k not in {"factor_ledger","factor_summary"}} for x in rare]
 market_view={"state":market["market_temperature"]["state"],"score":market["market_temperature"]["score"]} if market else {"state":"unavailable","score":None}
 return {"date":day,"model_version":MODEL_VERSION,"factor_registry_version":REGISTRY_VERSION,"ruleset_id":RULESET_ID,"market":market_view,"industry_status":industry.get("status"),"historical_membership_safe":bool(industry.get("historical_membership_safe")),"eligible_count":snapshot["eligible_count"],"triggered_count":snapshot.get("triggered_count",len(snapshot["symbols"])),"candidate_count":len(candidates),"rare_policy":f"复杂多因子排行榜前{RARE_LIMIT}名；先比技术共振分、周期奖金、家族数和颗数，行业与大盘只处理技术完全同分","rare_symbols":[x["symbol"] for x in rare],"rare_opportunities":rare_rows,"candidate_pool_policy":f"当日完整收盘MACD金叉与长期趋势作共同门票；触发后检测其余{REMAINING_FACTOR_COUNT}项，非风险真实命中均计颗数并保留原研究状态","candidate_pool":pool,"ranking":candidates[:30]}

def _compact_factor(item):
 """Keep every audit decision while removing repeated labels and raw evidence."""
 factor_id=item.get("factor_id");factor=FACTORS_BY_ID.get(factor_id);available=bool(item.get("available"));hit=bool(item.get("hit"));points=item.get("points",0)
 rule=item.get("score_rule") or ("规则未客观化" if not available else f"命中 {points:+g}" if points else "命中，暂不计分" if hit else "未命中 +0")
 return {"factor_id":factor_id,"name":item.get("name") or (factor.name_zh if factor else factor_id),"available":available,"hit":hit,"active_now":bool(item.get("active_now")),"bars_since_hit":item.get("bars_since_hit"),"points":points,"counted_in_resonance":bool(item.get("counted_in_resonance")),"count_points":item.get("count_points",points),"confirmation_bonus":item.get("confirmation_bonus",0),"factor_family":item.get("factor_family") or (factor.evidence_family if factor else None),"timeframe":item.get("timeframe") or (TIMEFRAME_KEYS.get(factor.timeframe,factor.timeframe) if factor else None),"research_status":item.get("research_status") or (factor.status if factor else None),"shadow_points":item.get("shadow_points",0),"score_rule":rule}

def _compact_day(day):
 day={**day}
 ranking=[]
 for row in day.get("ranking",[]):
  row={k:v for k,v in row.items() if k!="factor_summary"}
  row["factor_ledger"]=[_compact_factor(item) for item in row.get("factor_ledger",[])]
  ranking.append(row)
 day["ranking"]=ranking
 rare_rows=[{k:v for k,v in row.items() if k not in {"factor_ledger","factor_summary"}} for row in day.get("rare_opportunities",[])]
 rare_symbols=day.get("rare_symbols") or [x.get("symbol") for x in rare_rows if x.get("symbol")]
 day["rare_symbols"]=rare_symbols
 day["rare_opportunities"]=rare_rows or [{k:v for k,v in row.items() if k!="factor_ledger"} for row in ranking if row.get("symbol") in rare_symbols]
 return day

def _trim_archived_day(day):
 """Remove redundant misses from older website history without changing facts."""
 day={**day};ranking=[]
 for row in day.get("ranking",[]):
  row={**row}
  row["factor_ledger"]=[item for item in row.get("factor_ledger",[]) if item.get("hit")]
  ranking.append(row)
 day["ranking"]=ranking
 return day

def _write_report(results,out,merge_existing):
 results=[_compact_day(day) for day in results]
 if merge_existing and pathlib.Path(out).exists():
  existing=json.loads(pathlib.Path(out).read_text())
  existing_registry=existing.get("model",{}).get("factor_registry_version","legacy_unrecorded")
  previous=[]
  for day in existing.get("days",[]):previous.append({"model_version":existing.get("version","legacy_unrecorded"),"factor_registry_version":existing_registry,"ruleset_id":f"{existing.get('version','legacy_unrecorded')}+factors-{existing_registry}",**day})
  by_date={x["date"]:x for x in previous}
  for result in results:
   prior=by_date.get(result["date"])
   # A model migration may recalculate the latest screen for today's website,
   # but it must not rewrite the immutable historical ranking for that date.
   if prior and prior.get("model_version")!=result.get("model_version"):continue
   by_date[result["date"]]=result
  results=[by_date[x] for x in sorted(by_date)]
 # The website keeps complete factor ledgers for only the latest 30 sessions.
 # Older rows retain ranking, scores, reasons and every actual hit; full research
 # checkpoints stay in Git/Actions and are never replaced by this web compaction.
 recent_dates={day["date"] for day in results[-30:]}
 results=[day if day["date"] in recent_dates else _trim_archived_day(day) for day in results]
 versions=sorted({x.get("model_version","legacy_unrecorded") for x in results});registries=sorted({x.get("factor_registry_version","legacy_unrecorded") for x in results})
 report={"version":MODEL_VERSION,"generated_at":datetime.now(timezone.utc).isoformat(),"coverage":{"start":results[0]["date"],"end":results[-1]["date"],"sessions":len(results)},"production_status":"count_based_manual_review_challenger","future_data_used":False,"version_policy":"每个历史日冻结其首次回放时的模型与因子库版本；新规则只用于后续批次，除非另开重算实验","model_versions":versions,"factor_registry_versions":registries,"model":{"ruleset_id":RULESET_ID,"factor_registry_version":REGISTRY_VERSION,"trigger":"当日完整收盘日线MACD刚发生金叉；MACD是事件门票，长期趋势是共同资格","technical":f"共同门票不参加候选分差；其余{REMAINING_FACTOR_COUNT}项中每个非风险真实命中计1颗，再加家族覆盖、父子确认和跨周期共振。研究状态继续显示，颗数不代表已验证收益","timeframe_profile":"日/周/月全部计数证据及同家族共振；直接参与人工复核排序，不承诺持仓时间","industry":"有当日有效成员快照时保存Leadership/Recovery/Pullback Watch上下文；只处理技术完全同分","market":"市场温度继续独立保存；只处理技术完全同分","entry_gate":"必须当日MACD金叉触发且长期趋势有效；其余因子按点时定义检测","execution":"新批次按下一交易日复权开盘入场；止损为信号日支撑下5%，最大计划亏损10%；2R止盈、40日到期、同日触发先算止损"},"limitations":["技术共振分是用户指定的人工复核优先级，不是已验证胜率或Alpha","相关因子会提高原始颗数，因此同时公开家族覆盖和重复确认","当前股票池来自现存缓存，正式收益研究仍需处理幸存者偏差","没有当日有效行业成员快照的日期不做行业上下文，绝不使用未来分类回填"],"days":results}
 pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,separators=(",",":"))+"\n");return report

def write_latest(report,out=LATEST_OUT,day=None):
 """Publish only the latest ranking day for fast daily pages."""
 selected=_compact_day(day) if day is not None else (report.get("days",[]) or [None])[-1]
 latest={**report,"days":[selected] if selected else []}
 if selected:
  latest["model_versions"]=sorted(set(latest.get("model_versions",[]))|{selected.get("model_version","legacy_unrecorded")})
 pathlib.Path(out).write_text(json.dumps(latest,ensure_ascii=False,separators=(",",":"))+"\n")
 return latest

def run_published(out=OUT,public_dir="public"):
 root=pathlib.Path(public_dir)
 snapshot=json.loads((root/"daily-factor-snapshot.json").read_text());market=json.loads((root/"market-etf-watch.json").read_text());industry=json.loads((root/"industry-radar.json").read_text())
 day=_rank_day(snapshot,market,industry)
 report=_write_report([day],out,True)
 if pathlib.Path(out)==pathlib.Path(OUT):write_latest(report,day=day)
 return report

def run(start="2026-07-01",end=None,out=OUT,cache_dir="work/eodhd-cache",merge_existing=True):
 data=_load_cache(cache_dir);dates=_dates(data,start,end or "9999-12-31")
 if not dates:
  report={"version":MODEL_VERSION,"generated_at":datetime.now(timezone.utc).isoformat(),"coverage":{"start":None,"end":None,"sessions":0},"production_status":"shadow_not_yet_validated","future_data_used":False,"model":{"ruleset_id":RULESET_ID,"factor_registry_version":REGISTRY_VERSION},"limitations":["Requested calendar partition contains no SPY trading session; preserved as a valid empty weekly checkpoint."],"days":[]}
  pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,separators=(",",":"))+"\n")
  return report
 results=[]
 for day in dates:
  snapshot=build_snapshot(data,day);market=_market(data,day);industry=_industry(day)
  # Historical technical research must not disappear merely because one of
  # the separately stratified market ETFs did not yet exist.  Missing market
  # context is recorded as unavailable and contributes zero adjustment.
  results.append(_rank_day(snapshot,market,industry))
 return _write_report(results,out,merge_existing)

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--start",default="2026-07-01");parser.add_argument("--end");parser.add_argument("--out",default=OUT);parser.add_argument("--cache-dir",default="work/eodhd-cache");parser.add_argument("--replace",action="store_true");parser.add_argument("--published-latest",action="store_true")
 args=parser.parse_args();report=run_published(args.out) if args.published_latest else run(args.start,args.end,args.out,args.cache_dir,not args.replace);print(json.dumps({"coverage":report["coverage"],"latest_candidates":report["days"][-1]["candidate_count"] if report["days"] else None},ensure_ascii=False))
