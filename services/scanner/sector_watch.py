"""Build an explainable Chinese sector-monitor snapshot from sector ETFs."""
import json,pathlib
from datetime import datetime,timezone
from .eodhd import news
from .eodhd_factor_pilot import adjusted_rows
from .technical import ema

SECTORS={"XLK":"科技","XLC":"通信服务","XLY":"可选消费","XLP":"必需消费","XLE":"能源","XLF":"金融","XLV":"医疗保健","XLI":"工业","XLB":"原材料","XLRE":"房地产","XLU":"公用事业"}
def ret(rows,n):return rows[-1]["close"]/rows[-1-n]["close"]-1
def run(out="public/sector-watch.json"):
 spy=adjusted_rows("SPY");spy_returns={n:ret(spy,n) for n in (1,5,20)};items=[]
 for code,name in SECTORS.items():
  rows=adjusted_rows(code);closes=[x["close"] for x in rows];e20=ema(closes,20)[-1];e50=ema(closes,50)[-1];vol20=sum(x["volume"] for x in rows[-21:-1])/20;articles=[]
  try:
   for x in news(code,3):articles.append({"date":x.get("date"),"title":x.get("title"),"link":x.get("link"),"source":x.get("source"),"sentiment":x.get("sentiment")})
  except Exception:pass
  r={n:ret(rows,n) for n in (1,5,20)};score=sum([r[20]>spy_returns[20],r[5]>spy_returns[5],closes[-1]>e20,closes[-1]>e50,rows[-1]["volume"]>vol20])
  state="领先" if score>=4 else "改善" if score==3 else "中性" if score==2 else "转弱"
  items.append({"ticker":code,"sector":name,"as_of":rows[-1]["date"],"price":round(closes[-1],2),"return_1d":round(r[1],4),"return_5d":round(r[5],4),"return_20d":round(r[20],4),"relative_20d":round(r[20]-spy_returns[20],4),"above_ema20":closes[-1]>e20,"above_ema50":closes[-1]>e50,"volume_ratio":round(rows[-1]["volume"]/vol20,2) if vol20 else None,"score":score,"state":state,"news":articles})
 items.sort(key=lambda x:(x["score"],x["relative_20d"]),reverse=True);breadth=sum(x["above_ema50"] for x in items)
 report={"generated_at":datetime.now(timezone.utc).isoformat(),"as_of":items[0]["as_of"],"market":{"spy_price":round(spy[-1]["close"],2),"spy_20d":round(spy_returns[20],4),"sector_breadth_above_ema50":breadth,"sector_count":len(items),"state":"扩散" if breadth>=8 else "分化" if breadth>=5 else "防守"},"sectors":items,"rules":["行业ETF仅用于观察资金风格与相对强弱，不构成买入建议","领先要求价格趋势、相对强度和成交量出现多项确认","新闻标题来自数据提供商，情绪字段只作线索，必须打开原文核实","当前为收盘后版本，不是盘中实时行情"]};pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,indent=2));return report
if __name__=="__main__":
 r=run();print(json.dumps({"as_of":r["as_of"],"market":r["market"],"leaders":r["sectors"][:3]},ensure_ascii=False,indent=2))
