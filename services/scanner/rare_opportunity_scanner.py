"""Daily end-of-day scanner for rare five/six-point MACD research observations."""
import json,pathlib
from datetime import datetime,timezone
from .macd_factor_backtest import adjusted_rows,ema,long_trend_ok
from .eodhd import latest_reference_day
from .resonance_tracker import bulk_day,macd
from .factor_registry import CURRENT_COMPONENT_IDS,FACTORS_BY_ID,REGISTRY_VERSION
from .factor_snapshot import run as run_factor_snapshot,state_map
from .factor_scoring import experimental_score

COMPONENTS=("日线MACD近5日金叉","Fibonacci支撑","EMA支撑","支撑位底部放量","支撑位看涨吞没","周线MACD改善","三推趋势线突破","三推突破后回踩确认","上方未补跳空缺口","Bullish FVG支撑")

def recent_bull_cross(line,signal,end,window=5):
 """Keep a completed daily bull cross fresh for five sessions including its trigger day."""
 if end<1 or line[end]<=signal[end]:return False
 return any(line[j]>signal[j] and line[j-1]<=signal[j-1] for j in range(max(1,end-window+1),end+1))

def score_observation(hits):
 raw_hits=list(dict.fromkeys(hits));raw_ids={CURRENT_COMPONENT_IDS[x] for x in raw_hits if x in CURRENT_COMPONENT_IDS};accepted=[];groups=set()
 for name in raw_hits:
  factor_id=CURRENT_COMPONENT_IDS.get(name);item=FACTORS_BY_ID.get(factor_id)
  if not item or item.score_mode not in ("official","observational") or not item.weight:continue
  if any(parent not in raw_ids for parent in item.depends_on):continue
  if item.redundancy_group in groups:continue
  groups.add(item.redundancy_group);accepted.append((name,item))
 names=[name for name,_ in accepted];official=sum(item.weight for _,item in accepted if item.score_mode=="official");observational=sum(item.weight for _,item in accepted if item.score_mode=="observational");total=official+observational
 misses=[name for name in COMPONENTS if name not in raw_hits]
 return {"score":total,"official_score":official,"observational_score":observational,"risk_deduction":0,"total_score":total,"factor_ids":[item.id for _,item in accepted],"components":names,"non_scoring_hits":[name for name in raw_hits if name not in names],"important_misses":misses,"category_scores":{"MACD":sum(x in names for x in ("日线MACD近5日金叉","周线MACD改善")),"支撑":sum(x in names for x in ("Fibonacci支撑","EMA支撑")),"价格结构":sum(x in names for x in ("三推趋势线突破","三推突破后回踩确认","支撑位看涨吞没","Bullish FVG支撑")),"量能":int("支撑位底部放量" in names),"风险／供给":int("上方未补跳空缺口" in names)},"risks":["当前动态观察因子尚未完成跨时期组合验证"]}

def latest_completed_day(as_of=None):
 expected=as_of or latest_reference_day()
 return expected,bulk_day(expected,strict=True)

def run(out="public/rare-opportunity-radar.json",as_of=None,snapshot=None):
 latest,bulk=latest_completed_day(as_of);bulk_map={x.get("code"):x for x in bulk}
 snapshot=snapshot or run_factor_snapshot(None,latest);canonical=state_map(snapshot)
 if snapshot.get("as_of")!=latest or snapshot.get("future_data_used") is not False:raise RuntimeError("Canonical factor snapshot audit failed")
 common_path=pathlib.Path("work/eodhd-active-common.json")
 active={x["Code"] for x in json.loads(common_path.read_text())} if common_path.exists() else set(bulk_map)
 signals=[];scanned=0
 for path in sorted(pathlib.Path("work/eodhd-cache").glob("*.json")):
  symbol=path.stem
  if symbol not in active or symbol not in bulk_map:continue
  raw=json.loads(path.read_text());today=bulk_map[symbol]
  if today.get("adjusted_close") and today.get("close") and today.get("open") and today.get("volume") is not None:
   if not any(x.get("date")==today.get("date") for x in raw):raw.append(today);raw.sort(key=lambda x:x["date"]);path.write_text(json.dumps(raw))
  rows=adjusted_rows(raw);scanned+=1
  if len(rows)<420 or rows[-1]["date"]!=latest:continue
  current=rows[-1]
  if current["close"]<5 or current["close"]*current["volume"]<10_000_000:continue
  states=canonical.get(symbol)
  if not states or not states["macd.daily_bull_cross"]["hit"]:continue
  i=len(rows)-1;curves={period:ema([x["close"] for x in rows],period) for period in (21,50,200)}
  pullback=rows[i]["close"]<=max(x["high"] for x in rows[max(0,i-60):i])*.95
  if not (long_trend_ok(rows,i,curves[200]) and pullback):continue
  hits=[]
  for name,factor_id in CURRENT_COMPONENT_IDS.items():
   state=states.get(factor_id)
   if state and state["available"] and state["hit"]:hits.append(name)
  retest=states.get("structure.trendline_three_push_retest",{})
  if "structure.trendline_three_push" in retest.get("evidence",{}).get("dependency_hits",[]):hits.append("三推趋势线突破")
  scored=score_observation(hits);score=scored["total_score"]
  if score>=5:
   experimental=experimental_score(list(states.values()));contributing={item["factor_id"] for item in experimental["score_contributions"]};observations=[]
   for factor_id,state in states.items():
    factor=FACTORS_BY_ID[factor_id];present=state.get("recent_hit") if factor.factor_type=="event" else state.get("hit")
    if present:observations.append({"factor_id":factor_id,"name":factor.name_zh,"presence":"active_now" if state.get("hit") else "recent","bars_since_hit":state.get("bars_since_hit"),"latest_hit_date":state.get("latest_hit_date"),"score_tier":factor.score_tier,"contributed_score":factor_id in contributing,"evidence":state.get("evidence",{})})
   signals.append({"symbol":symbol,"date":latest,"price":round(current["close"],2),"level":"极稀有" if score>=6 else "稀有","components":scored["components"],"dollar_volume":round(current["close"]*current["volume"]),"recent_observations":observations,**scored,**experimental})
 signals.sort(key=lambda x:(x["score"],x["dollar_volume"],x["symbol"]),reverse=True)
 report={"generated_at":datetime.now(timezone.utc).isoformat(),"as_of":latest,"status":"research_observation_only","registry_version":REGISTRY_VERSION,"factor_source":"canonical_daily_snapshot","score_policy":{"official":"只有已验证因子可进入正式分；当前为0","observational":"候选因子按命中自由组合；强依赖因子必须满足父因子","risk_deduction":"冲突扣分接口已保留，当前尚未启用"},"policy":"5分为稀有观察，6分或以上为极稀有观察；不是买入信号，不显示为已验证胜率。","scan":{"frequency":"每个美国交易日收盘后","universe_scanned":scanned,"minimum_price":5,"minimum_dollar_volume":10_000_000,"future_data_used":False},"signals":signals}
 pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,indent=2));return report

if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False,indent=2))
