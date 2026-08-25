"""Daily end-of-day scanner for rare five/six-point MACD research observations."""
import json,pathlib
from datetime import date,datetime,timedelta,timezone
from .macd_factor_backtest import adjusted_rows,available,completed_groups,daily_pattern_flags,ema,outcome
from .eodhd import latest_reference_day
from .resonance_tracker import bulk_day,macd
from .factor_registry import CURRENT_COMPONENT_IDS,REGISTRY_VERSION

COMPONENTS=("日线MACD近5日金叉","Fibonacci支撑","EMA支撑","支撑位底部放量","支撑位看涨吞没","周线MACD改善","三推趋势线突破","三推突破后回踩确认","上方未补跳空缺口","Bullish FVG支撑")

def recent_bull_cross(line,signal,end,window=5):
 """Keep a completed daily bull cross fresh for five sessions including its trigger day."""
 if end<1 or line[end]<=signal[end]:return False
 return any(line[j]>signal[j] and line[j-1]<=signal[j-1] for j in range(max(1,end-window+1),end+1))

def score_observation(hits):
 hits=list(hits);misses=[name for name in COMPONENTS if name not in hits]
 return {"score":len(hits),"official_score":0,"observational_score":len(hits),"risk_deduction":0,"total_score":len(hits),"factor_ids":[CURRENT_COMPONENT_IDS[x] for x in hits],"important_misses":misses,"category_scores":{"MACD":sum(x in hits for x in ("日线MACD近5日金叉","周线MACD改善")),"支撑":sum(x in hits for x in ("Fibonacci支撑","EMA支撑")),"价格结构":sum(x in hits for x in ("三推趋势线突破","三推突破后回踩确认","支撑位看涨吞没","Bullish FVG支撑")),"量能":int("支撑位底部放量" in hits),"风险／供给":int("上方未补跳空缺口" in hits)},"risks":["当前动态观察因子尚未完成跨时期组合验证"]}

def historical_examples(start="2025-01-01",limit=20):
 """Recent point-in-time cases for human chart review; outcomes never affect selection."""
 from .macd_factor_backtest import macd_state
 examples=[]
 for path in sorted(pathlib.Path("work/eodhd-cache").glob("*.json")):
  rows=adjusted_rows(json.loads(path.read_text()))
  if len(rows)<420:continue
  closes=[x["close"] for x in rows];line,signal=macd(closes);curves={period:ema(closes,period) for period in (21,50,200)};weekly=completed_groups(rows,"weekly")
  for i in range(260,len(rows)-1):
   if rows[i]["date"]<start or not recent_bull_cross(line,signal,i):continue
   if rows[i]["close"]<5 or rows[i]["close"]*rows[i]["volume"]<10_000_000:continue
   day=datetime.strptime(rows[i]["date"],"%Y-%m-%d").date();wr=available(weekly,(day.isocalendar().year,day.isocalendar().week))
   if len(wr)<35:continue
   flags=daily_pattern_flags(rows,i,macd_state(wr[-160:]),curves)
   if not flags.get("多因子核心"):continue
   hits=["日线MACD近5日金叉"]+[name for name in COMPONENTS if name!="日线MACD近5日金叉" and flags.get(f"多因子组件＋{name}")]
   if len(hits)<5:continue
   forward,_,_=outcome(rows,i,"buy",horizons=(20,100))
   examples.append({"symbol":path.stem,"date":rows[i]["date"],"entry_date":rows[i+1]["date"],"signal_close":round(rows[i]["close"],2),"entry_open":round(rows[i+1]["open"],2),"score":len(hits),"components":hits,"return_20d":round(forward[20]*100,2) if 20 in forward else None,"return_100d":round(forward[100]*100,2) if 100 in forward else None,"listing_status":"unknown"})
 examples.sort(key=lambda x:(x["date"],x["score"],x["symbol"]),reverse=True);return examples[:limit]

def latest_completed_day(as_of=None):
 expected=as_of or latest_reference_day()
 return expected,bulk_day(expected,strict=True)

def run(out="public/rare-opportunity-radar.json",as_of=None):
 previous_path=pathlib.Path(out)
 if not previous_path.exists():previous_path=pathlib.Path("public/rare-opportunity-radar.json")
 previous_examples=json.loads(previous_path.read_text()).get("historical_examples",[]) if previous_path.exists() else []
 latest,bulk=latest_completed_day(as_of);bulk_map={x.get("code"):x for x in bulk}
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
  line,signal=macd([x["close"] for x in rows]);i=len(rows)-1
  if not recent_bull_cross(line,signal,i):continue
  day=datetime.strptime(latest,"%Y-%m-%d").date();weekly=completed_groups(rows,"weekly");wr=available(weekly,(day.isocalendar().year,day.isocalendar().week))
  if len(wr)<35:continue
  from .macd_factor_backtest import macd_state
  flags=daily_pattern_flags(rows,i,macd_state(wr[-160:]),{period:ema([x["close"] for x in rows],period) for period in (21,50,200)})
  if not flags.get("多因子核心"):continue
  hits=["日线MACD近5日金叉"]+[name for name in COMPONENTS if name!="日线MACD近5日金叉" and flags.get(f"多因子组件＋{name}")];score=len(hits)
  if score>=5:
   signals.append({"symbol":symbol,"date":latest,"price":round(current["close"],2),"level":"极稀有" if score>=6 else "稀有","components":hits,"dollar_volume":round(current["close"]*current["volume"]),**score_observation(hits)})
 signals.sort(key=lambda x:(x["score"],x["dollar_volume"],x["symbol"]),reverse=True)
 history_path=pathlib.Path("public/macd-factor-backtest.json");examples=[]
 if history_path.exists():examples=json.loads(history_path.read_text()).get("multifactor_tests",{}).get("rare_examples",[])[:20]
 if not examples:examples=previous_examples[:20]
 if not examples:examples=historical_examples()
 report={"generated_at":datetime.now(timezone.utc).isoformat(),"as_of":latest,"status":"research_observation_only","registry_version":REGISTRY_VERSION,"score_policy":{"official":"只有已验证因子可进入正式分；当前为0","observational":"候选因子按命中自由组合；强依赖因子必须满足父因子","risk_deduction":"冲突扣分接口已保留，当前尚未启用"},"policy":"5分为稀有观察，6分或以上为极稀有观察；不是买入信号，不显示为已验证胜率。","scan":{"frequency":"每个美国交易日收盘后","universe_scanned":scanned,"minimum_price":5,"minimum_dollar_volume":10_000_000,"future_data_used":False},"signals":signals,"historical_examples":examples}
 pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,indent=2));return report

if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False,indent=2))
