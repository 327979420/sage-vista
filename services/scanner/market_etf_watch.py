"""Cross-asset ETF dashboard for market mood, breadth, value and momentum."""
import json,pathlib
from datetime import datetime,timezone
from .eodhd_factor_pilot import adjusted_rows
from .technical import ema

FUNDS={"SPY":("标普500","大盘基准"),"QQQ":("纳斯达克100","成长/科技"),"DIA":("道琼斯","蓝筹价值"),"IWM":("罗素2000","小盘风险偏好"),"RSP":("标普500等权","市场广度"),"MDY":("标普中盘400","中盘股"),"VTI":("美国全市场","整体市场"),"IWD":("罗素1000价值","价值"),"IWF":("罗素1000成长","成长"),"MTUM":("美国动量","动量"),"QUAL":("美国质量","质量"),"USMV":("美国低波动","防守"),"HYG":("高收益债","信用风险偏好"),"LQD":("投资级债","高质量信用"),"TLT":("长期美债","利率/防守"),"GLD":("黄金","避险/通胀"),"UUP":("美元","美元强弱")}
def change(rows,n):return rows[-1]["close"]/rows[-1-n]["close"]-1
def ratio_change(a,b,n):return (a[-1]["close"]/b[-1]["close"])/(a[-1-n]["close"]/b[-1-n]["close"])-1
def run(out="public/market-etf-watch.json"):
 data={code:adjusted_rows(code) for code in FUNDS};items=[]
 for code,(name,role) in FUNDS.items():
  rows=data[code];closes=[x["close"] for x in rows];e20=ema(closes,20)[-1];e50=ema(closes,50)[-1]
  items.append({"ticker":code,"name":name,"role":role,"as_of":rows[-1]["date"],"price":round(closes[-1],2),"return_1d":round(change(rows,1),4),"return_5d":round(change(rows,5),4),"return_20d":round(change(rows,20),4),"above_ema20":closes[-1]>e20,"above_ema50":closes[-1]>e50})
 ratios={"成长相对大盘":ratio_change(data["QQQ"],data["SPY"],20),"小盘相对大盘":ratio_change(data["IWM"],data["SPY"],20),"等权相对市值权重":ratio_change(data["RSP"],data["SPY"],20),"高收益债相对投资级债":ratio_change(data["HYG"],data["LQD"],20),"价值相对成长":ratio_change(data["IWD"],data["IWF"],20),"动量相对大盘":ratio_change(data["MTUM"],data["SPY"],20)}
 spy_above=data["SPY"][-1]["close"]>ema([x["close"] for x in data["SPY"]],50)[-1];score=sum([spy_above,ratios["成长相对大盘"]>0,ratios["小盘相对大盘"]>0,ratios["等权相对市值权重"]>0,ratios["高收益债相对投资级债"]>0]);state="风险偏好" if score>=4 else "分化" if score>=2 else "防守"
 report={"generated_at":datetime.now(timezone.utc).isoformat(),"as_of":data["SPY"][-1]["date"],"market_temperature":{"score":score,"max_score":5,"state":state,"explanation":"综合SPY趋势、成长、小盘、等权广度及信用风险偏好。"},"ratios":{k:round(v,4) for k,v in ratios.items()},"funds":items,"interpretation":["SPY、QQQ、DIA和IWM不是同一类市场：它们分别代表大盘、成长、蓝筹和小盘风格","RSP强于SPY通常表示上涨更加广泛；RSP弱于SPY表示指数可能依赖少数大型公司","IWD/IWF用于观察价值与成长轮动；MTUM/SPY用于观察动量风格是否占优","HYG/LQD走强通常表示信用风险偏好改善；TLT、GLD和UUP用于补充利率、避险与美元环境","ETF价格关系是市场状态证据，不是单独的买卖信号"]};pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,indent=2));return report
if __name__=="__main__":
 r=run();print(json.dumps({"as_of":r["as_of"],"temperature":r["market_temperature"],"ratios":r["ratios"]},ensure_ascii=False,indent=2))
