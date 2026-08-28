"""Point-in-time V2 research ranking: technical factors + industry + market.

This is deliberately a shadow ranking until its exact weights have a complete
out-of-sample result. Historical industry adjustments are only applied when a
membership snapshot was effective on that date.
"""
import argparse,json,pathlib,tempfile
from datetime import datetime,timezone

from .factor_snapshot import build_snapshot
from .factor_registry import FACTORS_BY_ID
from .industry_radar import run as industry_run
from .macd_factor_backtest import adjusted_rows
from .market_etf_watch import FUNDS,build as market_build

OUT="public/unified-v2-rankings.json"
RARE_MIN_PRIORITY=9
RARE_LIMIT=5
CORE={"qualification.long_trend":2,"macd.daily_bull_cross":3,"support.ema_proximity":2,"qualification.pullback_60d":1,"structure.bullish_fvg_support":1}
SUPPORT_CONFIRMATIONS={"structure.support_bullish_engulfing","volume.bottom_expansion"}

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
 if "qualification.long_trend" not in hits or not ({"macd.daily_bull_cross","support.ema_proximity"}&hits) or technical<4:return None
 market_score=market["market_temperature"]["score"] if market else None
 market_adjustment=1 if market_score is not None and market_score>=4 else -1 if market_score is not None and market_score<=1 else 0
 contexts=industry.get("ticker_context",{}).get(row["symbol"],[]) if industry.get("historical_membership_safe") else []
 states_seen=sorted({x.get("state") for x in contexts if x.get("state")})
 industry_adjustment=1 if "Leadership" in states_seen else .5 if set(states_seen)&{"Recovery","Pullback Watch"} else 0
 final=technical+market_adjustment+industry_adjustment
 reasons=[name for key,name in (("qualification.long_trend","长期趋势"),("macd.daily_bull_cross","MACD改善"),("support.ema_proximity","均线支撑"),("qualification.pullback_60d","从高位回撤"),("structure.bullish_fvg_support","Bullish FVG")) if key in hits]
 ledger=_factor_ledger(states,hits)
 return {"symbol":row["symbol"],"price":row["price"],"technical_score":technical,"market_adjustment":market_adjustment,"industry_adjustment":industry_adjustment,"final_priority":final,"score_equation":f"{technical} 技术 {market_adjustment:+g} 大盘 {industry_adjustment:+g} 行业 = {final:g}","reasons":reasons,"industry_states":states_seen,"factor_ledger":ledger,"factor_summary":{"scored_hits":[x["name"] for x in ledger if x["points"]>0],"risk_hits":[x["name"] for x in ledger if x["points"]<0],"observed_not_scored":[x["name"] for x in ledger if x["hit"] and x["points"]==0],"misses":[x["name"] for x in ledger if x["available"] and not x["hit"]],"unavailable":[x["name"] for x in ledger if not x["available"]]},"experimental_score":row["scoring"]["experimental_observational_score"]}

def _rank_day(snapshot,market,industry):
 day=snapshot["as_of"]
 if market.get("as_of")!=day or industry.get("as_of")!=day:raise RuntimeError("Published V2 inputs are not synchronized")
 candidates=[x for row in snapshot["symbols"] if (x:=_candidate(row,market,industry))]
 candidates.sort(key=lambda x:(-x["final_priority"],-x["technical_score"],-x["experimental_score"],x["symbol"]))
 for rank,item in enumerate(candidates[:30],1):item["rank"]=rank
 rare=[x for x in candidates[:RARE_LIMIT] if x["final_priority"]>=RARE_MIN_PRIORITY]
 pool=[{"symbol":x["symbol"],"price":x["price"],"technical_score":x["technical_score"],"market_adjustment":x["market_adjustment"],"industry_adjustment":x["industry_adjustment"],"base_priority":x["final_priority"],"experimental_score":x["experimental_score"],"hit_factor_ids":[f["factor_id"] for f in x["factor_ledger"] if f["hit"]]} for x in candidates]
 return {"date":day,"market":{"state":market["market_temperature"]["state"],"score":market["market_temperature"]["score"]},"industry_status":industry.get("status"),"historical_membership_safe":bool(industry.get("historical_membership_safe")),"eligible_count":snapshot["eligible_count"],"candidate_count":len(candidates),"rare_policy":f"统一排行榜前{RARE_LIMIT}名且最终优先级至少{RARE_MIN_PRIORITY}；顺序与排行榜完全一致","rare_opportunities":rare,"candidate_pool_policy":"通过基准入场门槛的完整候选池；辅助因子只能在池内重排，不能独立触发","candidate_pool":pool,"ranking":candidates[:30]}

def _write_report(results,out,merge_existing):
 if merge_existing and pathlib.Path(out).exists():
  existing=json.loads(pathlib.Path(out).read_text())
  if existing.get("version")=="unified-v2-shadow-1.0.0":
   by_date={x["date"]:x for x in existing.get("days",[])};by_date.update({x["date"]:x for x in results});results=[by_date[x] for x in sorted(by_date)]
 report={"version":"unified-v2-shadow-1.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"coverage":{"start":results[0]["date"],"end":results[-1]["date"],"sessions":len(results)},"production_status":"shadow_not_yet_validated","future_data_used":False,"model":{"technical":"长期趋势2 + MACD改善3 + EMA支撑2 + 回撤1 + FVG1 + 支撑确认最多1 - 上方缺口1","industry":"有当日有效成员快照时：Leadership +1；Recovery/Pullback Watch +0.5","market":"市场温度4-5加1；2-3不变；0-1减1","entry_gate":"必须长期趋势，且MACD改善或EMA支撑至少一个命中；技术分至少4；K线跟随本轮只记录不计分"},"limitations":["当前股票池来自现存缓存，正式胜率研究仍需纳入退市股票以消除幸存者偏差","没有当日有效行业成员快照的日期不做行业加分，绝不使用未来分类回填","这是新模型候选榜，不等于已验证买入信号"],"days":results}
 pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,separators=(",",":"))+"\n");return report

def run_published(out=OUT,public_dir="public"):
 root=pathlib.Path(public_dir)
 snapshot=json.loads((root/"daily-factor-snapshot.json").read_text());market=json.loads((root/"market-etf-watch.json").read_text());industry=json.loads((root/"industry-radar.json").read_text())
 return _write_report([_rank_day(snapshot,market,industry)],out,True)

def run(start="2026-07-01",end=None,out=OUT,cache_dir="work/eodhd-cache",merge_existing=True):
 data=_load_cache(cache_dir);dates=_dates(data,start,end or "9999-12-31")
 if not dates:raise RuntimeError("No cached SPY sessions in requested range")
 results=[]
 for day in dates:
  snapshot=build_snapshot(data,day);market=_market(data,day);industry=_industry(day)
  if market is not None:results.append(_rank_day(snapshot,market,industry))
 return _write_report(results,out,merge_existing)

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--start",default="2026-07-01");parser.add_argument("--end");parser.add_argument("--out",default=OUT);parser.add_argument("--cache-dir",default="work/eodhd-cache");parser.add_argument("--replace",action="store_true");parser.add_argument("--published-latest",action="store_true")
 args=parser.parse_args();report=run_published(args.out) if args.published_latest else run(args.start,args.end,args.out,args.cache_dir,not args.replace);print(json.dumps({"coverage":report["coverage"],"latest_candidates":report["days"][-1]["candidate_count"]},ensure_ascii=False))
