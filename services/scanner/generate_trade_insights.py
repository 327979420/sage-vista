"""Generate a practical, Chinese-ready EOD watchlist from validated factors."""
import json,math,pathlib
from datetime import datetime,timezone
from .audit_eodhd import common
from .eodhd import symbols
from .eodhd_factor_pilot import adjusted_rows,stable_sample
from .eodhd_factor_validation import percentile_scores
from .research_pipeline import factor_values,roll_spread_bps
from .technical import atr,ema

FACTORS=["breakout_252","volume_expansion","volatility_contraction","adx_14"]
def run(out="public/trade-insights.json",account=100_000):
 metas=stable_sample(common(symbols(False)),500,"northstar-active-v2");spy=adjusted_rows("SPY");benchmark={x["date"]:x["close"] for x in spy};spy_ema=ema([x["close"] for x in spy],200);risk_on=spy[-1]["close"]>spy_ema[-1]
 panel=[];rows_by_symbol={};meta_by_symbol={x["Code"]:x for x in metas}
 for meta in metas:
  rows=adjusted_rows(meta["Code"])
  if len(rows)<253:continue
  i=len(rows)-1;adv=sum(x["close"]*x["volume"] for x in rows[-20:])/20;spread=roll_spread_bps(rows,i)
  if rows[i]["close"]<5 or adv<10_000_000 or spread is None or spread>50:continue
  panel.append({"symbol":meta["Code"],"factors":factor_values(rows,i,benchmark)});rows_by_symbol[meta["Code"]]=rows
 scores=percentile_scores(panel,FACTORS);ranked=[]
 for row in panel:
  symbol=row["symbol"]
  if symbol not in scores:continue
  rows=rows_by_symbol[symbol];fv=row["factors"];a=atr(rows)[-1];last=rows[-1]
  if not a or a<=0:continue
  confirmations=[fv.get("breakout_252") is not None and fv["breakout_252"]>=-.03,fv.get("volume_expansion") is not None and fv["volume_expansion"]>=1.1,fv.get("volatility_contraction") is not None and fv["volatility_contraction"]>=-.8,fv.get("adx_14") is not None and fv["adx_14"]>=20]
  entry=last["high"]+.1*a;swing=min(x["low"] for x in rows[-20:]);stop=min(max(swing,entry-2.5*a),entry-1.2*a);risk=entry-stop;target=entry+2*risk
  shares=max(0,math.floor(min(account*.005/risk,account*.10/entry)));status="等待" if sum(confirmations)<3 or scores[symbol]<.70 else "可执行观察"
  ranked.append({"ticker":symbol,"name":meta_by_symbol[symbol].get("Name",symbol),"as_of":last["date"],"status":status,"score":round(scores[symbol]*100),"confirmations":sum(confirmations),"price":round(last["close"],2),"entry_trigger":round(entry,2),"stop":round(stop,2),"target":round(target,2),"reward_risk":2.0,"max_holding_days":10,"sample_account":account,"risk_budget":account*.005,"shares":shares,"position_value":round(shares*entry),"position_pct":round(shares*entry/account*100,1),"factors":{"距52周高点":round((fv.get("breakout_252") or 0)*100,1),"相对成交量":round(fv.get("volume_expansion") or 0,2),"波动收缩":round(-(fv.get("volatility_contraction") or 0),2),"ADX趋势强度":round(fv.get("adx_14") or 0,1)},"instruction":f"只有价格突破 ${entry:.2f} 才考虑；未突破不买。"})
 ranked=sorted(ranked,key=lambda x:(x["status"]=="可执行观察",x["score"],x["confirmations"]),reverse=True)[:12]
 report={"generated_at":datetime.now(timezone.utc).isoformat(),"as_of":max((x["as_of"] for x in ranked),default=None),"market_regime":"风险偏好" if risk_on else "风险规避","universe":{"sampled":500,"eligible":len(panel)},"account_assumption":account,"candidates":ranked,"rules":["收盘后生成信号，次日只在突破触发价时考虑入场","每笔计划风险为账户的0.5%，单一仓位不超过10%","止损参考20日支撑与2.5倍ATR，并设置最小1.2倍ATR距离","目标为2R；10个交易日仍未有效运动则退出","这是研究型观察清单，不是自动下单或收益保证"]};pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,indent=2));return report
if __name__=="__main__":
 r=run();print(json.dumps({"as_of":r["as_of"],"eligible":r["universe"]["eligible"],"candidates":r["candidates"][:5]},ensure_ascii=False,indent=2))
