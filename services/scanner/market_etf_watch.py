"""Point-in-time ETF market context published with the canonical EOD bundle."""
import json,pathlib
from datetime import datetime,timedelta,timezone
from .eodhd import prices
from .macd_factor_backtest import adjusted_rows as normalize_rows
from .technical import ema

SCHEMA_VERSION="2.0.0"
FUNDS={"SPY":("标普500","大盘基准"),"QQQ":("纳斯达克100","成长/科技"),"DIA":("道琼斯","蓝筹价值"),"IWM":("罗素2000","小盘风险偏好"),"RSP":("标普500等权","市场广度"),"MDY":("标普中盘400","中盘股"),"VTI":("美国全市场","整体市场"),"IWD":("罗素1000价值","价值"),"IWF":("罗素1000成长","成长"),"MTUM":("美国动量","动量"),"QUAL":("美国质量","质量"),"USMV":("美国低波动","防守"),"HYG":("高收益债","信用风险偏好"),"LQD":("投资级债","高质量信用"),"TLT":("长期美债","利率/防守"),"GLD":("黄金","避险/通胀"),"UUP":("美元","美元强弱")}

def refreshed_rows(code,cache_dir="work/eodhd-cache"):
 """Refresh the recent tail before using an ETF cache for the daily regime."""
 path=pathlib.Path(cache_dir)/f"{code}.json";path.parent.mkdir(parents=True,exist_ok=True)
 cached=json.loads(path.read_text()) if path.exists() else []
 start=(datetime.now(timezone.utc).date()-timedelta(days=400)).isoformat()
 fresh=prices(code,start=start)
 merged={x["date"]:x for x in cached if x.get("date")};merged.update({x["date"]:x for x in fresh if x.get("date")})
 raw=[merged[day] for day in sorted(merged)];path.write_text(json.dumps(raw))
 return normalize_rows(raw)

def _iso(raw):return datetime.strptime(raw,"%m/%d/%Y").date().isoformat() if "/" in raw else raw
def _trim(rows,as_of):return sorted([{**x,"date":_iso(x["date"])} for x in rows if x.get("date") and _iso(x["date"])<=as_of],key=lambda x:x["date"])
def change(rows,n):return rows[-1]["close"]/rows[-1-n]["close"]-1
def ratio_change(a,b,n):return (a[-1]["close"]/b[-1]["close"])/(a[-1-n]["close"]/b[-1-n]["close"])-1

def build(raw_data,as_of):
 data={code:_trim(raw_data.get(code,[]),as_of) for code in FUNDS};invalid=[code for code,rows in data.items() if len(rows)<51 or rows[-1]["date"]!=as_of]
 if invalid:raise RuntimeError(f"Market context missing exact completed bar for: {','.join(invalid)}")
 items=[];trend_flags={}
 for code,(name,role) in FUNDS.items():
  rows=data[code];closes=[x["close"] for x in rows];e20=ema(closes,20)[-1];e50=ema(closes,50)[-1]
  trend_flags[code]={"above_ema20":closes[-1]>e20,"above_ema50":closes[-1]>e50}
  items.append({"ticker":code,"name":name,"role":role,"as_of":as_of,"price":round(closes[-1],2),"return_1d":round(change(rows,1),4),"return_5d":round(change(rows,5),4),"return_20d":round(change(rows,20),4),**trend_flags[code]})
 ratios={"成长相对大盘":ratio_change(data["QQQ"],data["SPY"],20),"小盘相对大盘":ratio_change(data["IWM"],data["SPY"],20),"等权相对市值权重":ratio_change(data["RSP"],data["SPY"],20),"高收益债相对投资级债":ratio_change(data["HYG"],data["LQD"],20),"价值相对成长":ratio_change(data["IWD"],data["IWF"],20),"动量相对大盘":ratio_change(data["MTUM"],data["SPY"],20)}
 signals={"spy_above_ema50":trend_flags["SPY"]["above_ema50"],"growth_leadership":ratios["成长相对大盘"]>0,"small_cap_participation":ratios["小盘相对大盘"]>0,"equal_weight_breadth":ratios["等权相对市值权重"]>0,"credit_risk_appetite":ratios["高收益债相对投资级债"]>0}
 score=sum(signals.values());state="风险偏好" if score>=4 else "分化" if score>=2 else "防守"
 layers={"trend":{"state":"supportive" if signals["spy_above_ema50"] else "defensive","signals":{"spy_above_ema20":trend_flags["SPY"]["above_ema20"],"spy_above_ema50":signals["spy_above_ema50"],"qqq_above_ema50":trend_flags["QQQ"]["above_ema50"]}},"breadth":{"state":"broad" if signals["equal_weight_breadth"] and signals["small_cap_participation"] else "narrow_or_mixed","signals":{"equal_weight_leading":signals["equal_weight_breadth"],"small_cap_leading":signals["small_cap_participation"]}},"risk_appetite":{"state":"risk_seeking" if signals["growth_leadership"] and signals["credit_risk_appetite"] else "mixed_or_defensive","signals":{"growth_leading":signals["growth_leadership"],"credit_leading":signals["credit_risk_appetite"]}}}
 return {"schema_version":SCHEMA_VERSION,"generated_at":datetime.now(timezone.utc).isoformat(),"as_of":as_of,"future_data_used":False,"mode":"decision_context_not_technical_score","market_temperature":{"score":score,"max_score":5,"state":state,"explanation":"沿用旧生产5项市场温度；趋势、广度和风险偏好另行分层，暂不修改股票技术分。"},"layers":layers,"legacy_score_signals":signals,"ratios":{k:round(v,4) for k,v in ratios.items()},"funds":items,"audit":{"required_funds":len(FUNDS),"funds_exact_as_of":len(items),"completed_bars_only":True,"future_rows_used":False},"interpretation":["市场环境是独立决策层，不回写股票技术分","趋势、广度和信用风险偏好分开保存，便于后续逐层回测","V1五项评分暂时保持不变，研究验证后才允许建立新版本"]}

def shadow_fund_rows(prepared):
 """Require the complete ETF set from the shared shadow bridge."""
 from services.market_data.consumer import require_shadow_rows
 rows=require_shadow_rows(prepared,consumer="market_etf")
 missing=sorted(set(FUNDS)-set(rows))
 if missing:raise RuntimeError(f"Shadow market ETF input missing: {','.join(missing)}")
 return rows

def run(out="public/market-etf-watch.json",as_of=None,loader=refreshed_rows):
 raw={code:loader(code) for code in FUNDS}
 if as_of is None:
  spy=_trim(raw["SPY"],"9999-12-31")
  if not spy:raise RuntimeError("SPY market context unavailable")
  as_of=spy[-1]["date"]
 report=build(raw,as_of);pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,indent=2));return report

if __name__=="__main__":
 r=run();print(json.dumps({"as_of":r["as_of"],"temperature":r["market_temperature"],"layers":r["layers"]},ensure_ascii=False,indent=2))
