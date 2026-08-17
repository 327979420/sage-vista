from __future__ import annotations
import json,math,sqlite3,statistics,urllib.request
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from .fetch_nasdaq import fetch
from .quick_scan import HEAD,universe
from .technical import ema

VERSION="research-v0.1.0";HORIZONS=(5,10,20,60);FACTORS=("momentum_12_1","momentum_6_1","momentum_3_1","trend_quality","low_volatility","liquidity")
def iso(s):return datetime.strptime(s,"%m/%d/%Y").date().isoformat()
def stdev_returns(rows,start,end):
 r=[rows[i]["close"]/rows[i-1]["close"]-1 for i in range(start,end+1) if i>0]
 return statistics.stdev(r)*math.sqrt(252) if len(r)>1 else None
def factor_values(rows,i):
 c=[x["close"] for x in rows[:i+1]];e50,e200=ema(c,50),ema(c,200)
 def ret(a,b):return rows[b]["close"]/rows[a]["close"]-1 if a>=0 else None
 adv=sum(x["close"]*x["volume"] for x in rows[i-19:i+1])/20
 return {"momentum_12_1":ret(i-252,i-21),"momentum_6_1":ret(i-126,i-21),"momentum_3_1":ret(i-63,i-5),"trend_quality":((rows[i]["close"]/e200[i]-1)+(e50[i]/e200[i]-1)) if i>=200 else None,"low_volatility":-stdev_returns(rows,max(1,i-59),i),"liquidity":math.log(max(adv,1))}
def rank(v):
 order=sorted(range(len(v)),key=lambda i:v[i]);out=[0.0]*len(v);i=0
 while i<len(order):
  j=i
  while j+1<len(order) and v[order[j+1]]==v[order[i]]:j+=1
  r=(i+j)/2+1
  for k in range(i,j+1):out[order[k]]=r
  i=j+1
 return out
def spearman(x,y):
 if len(x)<3:return None
 a,b=rank(x),rank(y);ma,mb=statistics.mean(a),statistics.mean(b);num=sum((u-ma)*(v-mb) for u,v in zip(a,b));den=math.sqrt(sum((u-ma)**2 for u in a)*sum((v-mb)**2 for v in b));return num/den if den else None
def monthly_indices(rows):
 out={}
 for i,r in enumerate(rows):out[iso(r["date"])[:7]]=i
 return [i for _,i in sorted(out.items()) if i>=252]
def load_symbol(meta):
 try:return meta,fetch(meta["symbol"],"2021-01-01")
 except Exception:return meta,[]
def evaluate_report(panel):
 records=[]
 for f in FACTORS:
  for h in HORIZONS:
   daily=[];obs=0;top=[];bottom=[]
   for date in sorted({x["date"] for x in panel}):
    xs=[x for x in panel if x["date"]==date and x["factors"].get(f) is not None and x["forward"].get(h) is not None]
    if len(xs)<10:continue
    vals=[x["factors"][f] for x in xs];ys=[x["forward"][h] for x in xs];ic=spearman(vals,ys)
    if ic is not None:daily.append(ic)
    cut=max(1,len(xs)//5);ordered=sorted(xs,key=lambda x:x["factors"][f]);bottom.extend(x["forward"][h] for x in ordered[:cut]);top.extend(x["forward"][h] for x in ordered[-cut:]);obs+=len(xs)
   records.append({"factor":f,"horizon":h,"dates":len(daily),"observations":obs,"mean_ic":round(statistics.mean(daily),4) if daily else None,"ic_positive_pct":round(sum(x>0 for x in daily)/len(daily)*100,1) if daily else None,"top_quantile_return":round(statistics.mean(top),4) if top else None,"bottom_quantile_return":round(statistics.mean(bottom),4) if bottom else None,"spread":round(statistics.mean(top)-statistics.mean(bottom),4) if top else None})
 return records
def run(db_path="work/northstar-research.sqlite",report_path="public/research-report.json",limit=150):
 metas=universe(limit);loaded=[]
 with ThreadPoolExecutor(max_workers=12) as pool:
  fs=[pool.submit(load_symbol,m) for m in metas]
  for f in as_completed(fs):loaded.append(f.result())
 now=datetime.now(timezone.utc).isoformat();db=sqlite3.connect(db_path);db.executescript(Path(__file__).with_name("research_schema.sql").read_text());panel=[];eligible_latest=0
 for meta,rows in loaded:
  if not rows:continue
  sym=meta["symbol"];db.execute("INSERT OR REPLACE INTO instruments VALUES(?,?,?,?,?,?,?)",(sym,meta["name"],None,iso(rows[0]["date"]),iso(rows[-1]["date"]),"common_or_adr_screened","Nasdaq screener"))
  db.executemany("INSERT OR REPLACE INTO bars_daily VALUES(?,?,?,?,?,?,?,?,?)",[(sym,iso(r["date"]),r["open"],r["high"],r["low"],r["close"],r["volume"],"Nasdaq historical API",now) for r in rows])
  for i in monthly_indices(rows):
   adv=sum(x["close"]*x["volume"] for x in rows[i-19:i+1])/20;eligible=rows[i]["close"]>=5 and adv>=10_000_000 and i>=252;date=iso(rows[i]["date"])
   db.execute("INSERT OR REPLACE INTO universe_membership VALUES(?,?,?,?,?,?,?)",(date,sym,int(eligible),"eligible" if eligible else "price_liquidity_or_history",rows[i]["close"],adv,i+1))
   if not eligible:continue
   fv=factor_values(rows,i);fw={h:(rows[i+h]["close"]/rows[i]["close"]-1 if i+h<len(rows) else None) for h in HORIZONS};panel.append({"date":date,"symbol":sym,"factors":fv,"forward":fw})
   db.executemany("INSERT OR REPLACE INTO factor_observations VALUES(?,?,?,?,?,?,?)",[(date,sym,k,v,int(v is not None),"Nasdaq OHLCV derived",VERSION) for k,v in fv.items()])
   db.executemany("INSERT OR REPLACE INTO forward_returns VALUES(?,?,?,?)",[(date,sym,h,v) for h,v in fw.items()])
  i=len(rows)-1;adv=sum(x["close"]*x["volume"] for x in rows[-20:])/20;eligible_latest+=int(rows[i]["close"]>=5 and adv>=10_000_000 and i>=252)
 metrics=evaluate_report(panel);dates=sorted({x["date"] for x in panel});splits={"development":{"start":dates[0] if dates else None,"end":"2024-12-31"},"validation":{"start":"2025-01-01","end":"2025-12-31"},"forward_test":{"start":"2026-01-01","end":dates[-1] if dates else None}}
 exp_id=f"{VERSION}-{now[:10]}";spec={"factors":FACTORS,"horizons":HORIZONS,"universe":"top 150 market-cap screened, price>=5, ADV20>=10m, history>=252","splits":splits};summary={"symbols_requested":len(metas),"symbols_loaded":sum(bool(r) for _,r in loaded),"eligible_latest":eligible_latest,"panel_rows":len(panel),"snapshot_dates":len(dates)}
 db.execute("INSERT OR REPLACE INTO experiments VALUES(?,?,?,?,?,?,?,?,?)",(exp_id,now,VERSION,dates[0],dates[-1],eligible_latest,"completed",json.dumps(spec),json.dumps(summary)));db.execute("PRAGMA optimize");db.commit()
 report={"generated_at":now,"version":VERSION,"status":"research_only_not_a_trading_model","coverage":summary,"walk_forward":splits,"factors":{"implemented":[{"id":"momentum_12_1","plain":"12-month momentum excluding the latest month"},{"id":"momentum_6_1","plain":"6-month momentum excluding the latest month"},{"id":"momentum_3_1","plain":"3-month momentum excluding the latest week"},{"id":"trend_quality","plain":"price and EMA50 alignment relative to EMA200"},{"id":"low_volatility","plain":"negative 60-day annualised volatility"},{"id":"liquidity","plain":"log 20-day average dollar volume"}],"missing":["Point-in-time SEC quality/profitability","Point-in-time value","Earnings surprise and revisions","Historical sector membership","Delistings and full corporate-action audit"]},"metrics":metrics,"experiment":{"id":exp_id,"specification":spec},"interpretation":"Positive IC means higher factor ranks were associated with higher subsequent returns in this limited panel. Small samples and unadjusted data prevent investment conclusions."};Path(report_path).write_text(json.dumps(report,indent=2));return report
if __name__=="__main__":
 r=run();print(json.dumps(r["coverage"],indent=2));print(sorted(r["metrics"],key=lambda x:(x["mean_ic"] is not None,x["mean_ic"] or -9),reverse=True)[:8])
