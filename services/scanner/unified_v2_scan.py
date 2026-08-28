"""Point-in-time V2 research ranking: technical factors + industry + market.

This is deliberately a shadow ranking until its exact weights have a complete
out-of-sample result. Historical industry adjustments are only applied when a
membership snapshot was effective on that date.
"""
import argparse,json,pathlib,tempfile
from datetime import datetime,timezone

from .factor_snapshot import build_snapshot
from .factor_registry import FACTORS_BY_ID,REGISTRY_VERSION
from .industry_radar import run as industry_run
from .macd_factor_backtest import adjusted_rows
from .market_etf_watch import FUNDS,build as market_build

OUT="public/unified-v2-rankings.json"
MODEL_VERSION="unified-v2-macd-trigger-1.2.0"
RULESET_ID=f"{MODEL_VERSION}+factors-{REGISTRY_VERSION}"
RARE_MIN_PRIORITY=9
RARE_LIMIT=5
REMAINING_FACTOR_COUNT=len(FACTORS_BY_ID)-1
CORE={"qualification.long_trend":2,"macd.daily_bull_cross":3,"support.ema_proximity":2,"qualification.pullback_60d":1,"structure.bullish_fvg_support":1}
SUPPORT_CONFIRMATIONS={"structure.support_bullish_engulfing","volume.bottom_expansion"}
TIMEFRAME_PROFILE_VERSION="timeframe-profile-v0.1.0"
TIMEFRAME_KEYS={"daily":"daily","weekly_completed":"weekly","monthly_completed":"monthly"}
TIMEFRAME_LABELS={"daily":"日线主导","weekly":"周线主导","monthly":"月线主导"}
TIMEFRAME_ANCHORS={"trend","macd","price_structure"}

def _factor_ledger(states,hits):
 ledger=[];confirmation_awarded=False
 for factor_id,state in states.items():
  factor=FACTORS_BY_ID.get(factor_id);points=0;rule="观察，不进入V2分数"
  if factor_id in CORE:
   points=CORE[factor_id] if factor_id in hits else 0;rule=f"命中 +{CORE[factor_id]}" if points else "未命中 +0"
  elif factor_id in SUPPORT_CONFIRMATIONS:
   if factor_id in hits and not confirmation_awarded:points=1;confirmation_awarded=True;rule="支撑确认组 +1"
   elif factor_id in hits:rule="命中，但支撑确认组封顶 +0"
   else:rule="未命中 +0"
  elif factor_id=="risk.overhead_unfilled_gap":
   points=-1 if factor_id in hits else 0;rule="存在上方缺口 -1" if points else "未发现该风险 0"
  ledger.append({"factor_id":factor_id,"name":factor.name_zh if factor else factor_id,"available":bool(state.get("available")),"hit":factor_id in hits,"active_now":bool(state.get("hit")),"recent_hit":bool(state.get("recent_hit")),"bars_since_hit":state.get("bars_since_hit"),"latest_hit_date":state.get("latest_hit_date"),"points":points,"score_rule":rule,"evidence":state.get("evidence",{})})
 return ledger

def _present(state):
 return bool(state.get("recent_hit") if state.get("factor_id") in {"macd.daily_bull_cross","structure.support_bullish_engulfing","structure.engulfing_bullish_follow_through","volume.bottom_expansion"} else state.get("hit"))

def _timeframe_profile(states,hits):
 """Describe where experimental evidence lives without changing V2 rank."""
 grouped={}
 for factor_id in hits:
  factor=FACTORS_BY_ID.get(factor_id)
  if not factor or factor_id=="macd.daily_bull_cross" or factor.evidence_family=="risk" or factor.experimental_weight<=0:continue
  timeframe=TIMEFRAME_KEYS.get(factor.timeframe)
  if not timeframe:continue
  key=(timeframe,factor.redundancy_group)
  candidate={"factor_id":factor_id,"family":factor.evidence_family,"points":float(factor.experimental_weight)}
  if key not in grouped or candidate["points"]>grouped[key]["points"]:grouped[key]=candidate
 evidence={key:[] for key in TIMEFRAME_LABELS};points={key:0.0 for key in TIMEFRAME_LABELS};anchors={key:False for key in TIMEFRAME_LABELS}
 for (timeframe,_),item in sorted(grouped.items()):
  evidence[timeframe].append(item["factor_id"]);points[timeframe]+=item["points"]
  anchors[timeframe]=anchors[timeframe] or item["family"] in TIMEFRAME_ANCHORS
 total=sum(points.values());shares={key:round(value/total,4) if total else 0.0 for key,value in points.items()};groups={key:len(value) for key,value in evidence.items()}
 eligible={key:(points[key]>0 and (key=="daily" or groups[key]>=2 and anchors[key])) for key in TIMEFRAME_LABELS}
 choices=[key for key in TIMEFRAME_LABELS if eligible[key]]
 if not choices:
  dominant=None;label="周期证据不足";resonance=False
 else:
  dominant=max(choices,key=lambda key:(points[key],{"daily":0,"weekly":1,"monthly":2}[key]))
  ordered=sorted((shares[key] for key in choices),reverse=True);lead=ordered[0]-(ordered[1] if len(ordered)>1 else 0)
  resonance=len(choices)>1 and (shares[dominant]<.5 or lead<.1)
  label=f"多周期共振（{TIMEFRAME_LABELS[dominant]}）" if resonance else TIMEFRAME_LABELS[dominant]
 return {"version":TIMEFRAME_PROFILE_VERSION,"status":"experimental_descriptive_only","label":label,"dominant_timeframe":dominant,"is_resonance":resonance,"points":{key:round(value,2) for key,value in points.items()},"shares":shares,"independent_groups":groups,"anchor_present":anchors,"evidence":evidence}

def _load_cache(cache_dir):
 data={}
 for path in pathlib.Path(cache_dir).glob("*.json"):
  try:
   rows=adjusted_rows(json.loads(path.read_text()))
   if rows:data[path.stem]=rows
  except Exception:continue
 return data

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
 technical=sum(weight for key,weight in CORE.items() if key in hits)
 if hits&SUPPORT_CONFIRMATIONS:technical+=1
 if "risk.overhead_unfilled_gap" in hits:technical-=1
 trigger=row.get("trigger",{})
 if trigger.get("factor_id")!="macd.daily_bull_cross" or trigger.get("exact_completed_cross") is not True:return None
 if "qualification.long_trend" not in hits or "macd.daily_bull_cross" not in hits or technical<4:return None
 market_score=market["market_temperature"]["score"] if market else None
 market_adjustment=1 if market_score is not None and market_score>=4 else -1 if market_score is not None and market_score<=1 else 0
 contexts=industry.get("ticker_context",{}).get(row["symbol"],[]) if industry.get("historical_membership_safe") else []
 states_seen=sorted({x.get("state") for x in contexts if x.get("state")})
 industry_adjustment=1 if "Leadership" in states_seen else .5 if set(states_seen)&{"Recovery","Pullback Watch"} else 0
 final=technical+market_adjustment+industry_adjustment
 reasons=[name for key,name in (("qualification.long_trend","长期趋势"),("macd.daily_bull_cross","MACD改善"),("support.ema_proximity","均线支撑"),("qualification.pullback_60d","从高位回撤"),("structure.bullish_fvg_support","Bullish FVG")) if key in hits]
 ledger=_factor_ledger(states,hits)
 return {"symbol":row["symbol"],"price":row["price"],"technical_score":technical,"market_adjustment":market_adjustment,"industry_adjustment":industry_adjustment,"final_priority":final,"score_equation":f"{technical} 技术 {market_adjustment:+g} 大盘 {industry_adjustment:+g} 行业 = {final:g}","reasons":reasons,"industry_states":states_seen,"factor_ledger":ledger,"timeframe_profile":_timeframe_profile(states,hits),"execution_policy_version":row.get("execution_policy_version"),"support_plan":row.get("support_plan"),"experimental_score":row["scoring"]["experimental_observational_score"]}

def _rank_day(snapshot,market,industry):
 day=snapshot["as_of"]
 if market is not None and market.get("as_of")!=day:raise RuntimeError("Published V2 market input is not synchronized")
 if industry.get("as_of")!=day:raise RuntimeError("Published V2 industry input is not synchronized")
 candidates=[x for row in snapshot["symbols"] if (x:=_candidate(row,market,industry))]
 candidates.sort(key=lambda x:(-x["final_priority"],-x["technical_score"],-x["experimental_score"],x["symbol"]))
 for rank,item in enumerate(candidates[:30],1):item["rank"]=rank
 rare=[x for x in candidates[:RARE_LIMIT] if x["final_priority"]>=RARE_MIN_PRIORITY]
 pool=[{"symbol":x["symbol"],"price":x["price"],"technical_score":x["technical_score"],"market_adjustment":x["market_adjustment"],"industry_adjustment":x["industry_adjustment"],"base_priority":x["final_priority"],"experimental_score":x["experimental_score"],"timeframe_profile":x["timeframe_profile"],"hit_factor_ids":[f["factor_id"] for f in x["factor_ledger"] if f["hit"]]} for x in candidates]
 rare_rows=[{k:v for k,v in x.items() if k not in {"factor_ledger","factor_summary"}} for x in rare]
 market_view={"state":market["market_temperature"]["state"],"score":market["market_temperature"]["score"]} if market else {"state":"unavailable","score":None}
 return {"date":day,"model_version":MODEL_VERSION,"factor_registry_version":REGISTRY_VERSION,"ruleset_id":RULESET_ID,"market":market_view,"industry_status":industry.get("status"),"historical_membership_safe":bool(industry.get("historical_membership_safe")),"eligible_count":snapshot["eligible_count"],"triggered_count":snapshot.get("triggered_count",len(snapshot["symbols"])),"candidate_count":len(candidates),"rare_policy":f"统一排行榜前{RARE_LIMIT}名且最终优先级至少{RARE_MIN_PRIORITY}；顺序与排行榜完全一致","rare_symbols":[x["symbol"] for x in rare],"rare_opportunities":rare_rows,"candidate_pool_policy":f"当日完整收盘MACD金叉先触发；触发后完整检测其余{REMAINING_FACTOR_COUNT}个登记因子，用于筛选、解释和重排，不能独立触发","candidate_pool":pool,"ranking":candidates[:30]}

def _compact_factor(item):
 """Keep every audit decision while removing repeated labels and raw evidence."""
 factor_id=item.get("factor_id");factor=FACTORS_BY_ID.get(factor_id);available=bool(item.get("available"));hit=bool(item.get("hit"));points=item.get("points",0)
 rule=item.get("score_rule") or ("规则未客观化" if not available else f"命中 {points:+g}" if points else "命中，暂不计分" if hit else "未命中 +0")
 return {"factor_id":factor_id,"name":item.get("name") or (factor.name_zh if factor else factor_id),"available":available,"hit":hit,"active_now":bool(item.get("active_now")),"bars_since_hit":item.get("bars_since_hit"),"points":points,"score_rule":rule}

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

def _write_report(results,out,merge_existing):
 if merge_existing and pathlib.Path(out).exists():
  existing=json.loads(pathlib.Path(out).read_text())
  existing_registry=existing.get("model",{}).get("factor_registry_version","legacy_unrecorded")
  previous=[]
  for day in existing.get("days",[]):previous.append({"model_version":existing.get("version","legacy_unrecorded"),"factor_registry_version":existing_registry,"ruleset_id":f"{existing.get('version','legacy_unrecorded')}+factors-{existing_registry}",**day})
  by_date={x["date"]:x for x in previous};by_date.update({x["date"]:x for x in results});results=[by_date[x] for x in sorted(by_date)]
 results=[_compact_day(day) for day in results]
 versions=sorted({x.get("model_version","legacy_unrecorded") for x in results});registries=sorted({x.get("factor_registry_version","legacy_unrecorded") for x in results})
 report={"version":MODEL_VERSION,"generated_at":datetime.now(timezone.utc).isoformat(),"coverage":{"start":results[0]["date"],"end":results[-1]["date"],"sessions":len(results)},"production_status":"shadow_not_yet_validated","future_data_used":False,"version_policy":"每个历史日冻结其首次回放时的模型与因子库版本；新规则只用于后续批次，除非另开重算实验","model_versions":versions,"factor_registry_versions":registries,"model":{"ruleset_id":RULESET_ID,"factor_registry_version":REGISTRY_VERSION,"trigger":"当日完整收盘日线MACD刚发生金叉；MACD只负责触发，不是唯一测试因子","technical":f"触发后完整检测其余{REMAINING_FACTOR_COUNT}个因子；当前正式候选计分仍为长期趋势2 + MACD改善3 + 日线EMA支撑2 + 回撤1 + FVG1 + 支撑确认最多1 - 上方缺口1；新增周/月EMA与周/月吞没进入实验观察分，完成回测前不改正式权重","timeframe_profile":"日/周/月去重后的实验观察贡献；周/月标签至少两个独立证据组且含方向、MACD质量或结构锚点。只作描述，不改变V2排名或承诺持仓时间","industry":"有当日有效成员快照时：Leadership +1；Recovery/Pullback Watch +0.5","market":"市场温度4-5加1；2-3不变；0-1减1","entry_gate":"必须当日MACD金叉触发、长期趋势有效且技术分至少4；其余因子仍全部检测、解释与排序；新增高周期因子本轮只进入实验观察分","execution":"新批次按下一交易日复权开盘入场；止损为信号日支撑下5%，最大计划亏损10%；2R止盈、40日到期、同日触发先算止损"},"limitations":["当前股票池来自现存缓存，正式胜率研究仍需纳入退市股票以消除幸存者偏差","没有当日有效行业成员快照的日期不做行业加分，绝不使用未来分类回填","这是新模型候选榜，不等于已验证买入信号"],"days":results}
 pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,separators=(",",":"))+"\n");return report

def run_published(out=OUT,public_dir="public"):
 root=pathlib.Path(public_dir)
 snapshot=json.loads((root/"daily-factor-snapshot.json").read_text());market=json.loads((root/"market-etf-watch.json").read_text());industry=json.loads((root/"industry-radar.json").read_text())
 return _write_report([_rank_day(snapshot,market,industry)],out,True)

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
