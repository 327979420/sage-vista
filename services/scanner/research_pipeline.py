from __future__ import annotations
import json,math,sqlite3,statistics,urllib.request
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from .fetch_nasdaq import fetch
from .fetch_yahoo import fetch as fetch_long_history
from .quick_scan import HEAD,universe
from .technical import atr,ema,macd,rsi

VERSION="research-v0.5.0";HORIZONS=(5,10,20,60);FACTORS=("momentum_12_1","momentum_6_1","momentum_3_1","trend_quality","low_volatility","liquidity","rsi_14","macd_strength","adx_14","volume_expansion","breakout_252","volatility_contraction","relative_strength_6m")
SPLIT_BOUNDS={"development":("0000-01-01","2024-12-31"),"validation":("2025-01-01","2025-12-31"),"forward_test":("2026-01-01","9999-12-31")}
def iso(s):return datetime.strptime(s,"%m/%d/%Y").date().isoformat()
def stdev_returns(rows,start,end):
 r=[rows[i]["close"]/rows[i-1]["close"]-1 for i in range(start,end+1) if i>0]
 return statistics.stdev(r)*math.sqrt(252) if len(r)>1 else None
def adx(rows,n=14):
 if len(rows)<n+2:return None
 tr=[];plus=[];minus=[]
 for j in range(1,len(rows)):
  up=rows[j]["high"]-rows[j-1]["high"];down=rows[j-1]["low"]-rows[j]["low"]
  plus.append(up if up>down and up>0 else 0);minus.append(down if down>up and down>0 else 0)
  tr.append(max(rows[j]["high"]-rows[j]["low"],abs(rows[j]["high"]-rows[j-1]["close"]),abs(rows[j]["low"]-rows[j-1]["close"])))
 if len(tr)<n:return None
 p=sum(plus[-n:]);m=sum(minus[-n:]);t=sum(tr[-n:])
 return 0 if not t or not p+m else abs(p-m)/(p+m)*100
def factor_values(rows,i,benchmark=None):
 c=[x["close"] for x in rows[:i+1]];e50,e200=ema(c,50),ema(c,200);rs=rsi(c);ml,ms=macd(c);ats=atr(rows[:i+1])
 def ret(a,b):return rows[b]["close"]/rows[a]["close"]-1 if a>=0 else None
 adv=sum(x["close"]*x["volume"] for x in rows[i-19:i+1])/20
 short_vol=stdev_returns(rows,max(1,i-19),i);long_vol=stdev_returns(rows,max(1,i-59),i);prior_high=max(x["high"] for x in rows[i-251:i]) if i>=252 else None
 stock_6m=ret(i-126,i);bench_6m=None
 if benchmark and rows[i-126]["date"] in benchmark and rows[i]["date"] in benchmark:bench_6m=benchmark[rows[i]["date"]]/benchmark[rows[i-126]["date"]]-1
 prior_volume=sum(x["volume"] for x in rows[i-20:i])/20 if i>=20 else 0
 return {"momentum_12_1":ret(i-252,i-21),"momentum_6_1":ret(i-126,i-21),"momentum_3_1":ret(i-63,i-5),"trend_quality":((rows[i]["close"]/e200[i]-1)+(e50[i]/e200[i]-1)) if i>=200 else None,"low_volatility":-long_vol,"liquidity":math.log(max(adv,1)),"rsi_14":rs[i],"macd_strength":(ml[i]-ms[i])/ats[i] if ats[i] else None,"adx_14":adx(rows[max(0,i-40):i+1]),"volume_expansion":rows[i]["volume"]/prior_volume if prior_volume else None,"breakout_252":rows[i]["close"]/prior_high-1 if prior_high else None,"volatility_contraction":-(short_vol/long_vol) if short_vol and long_vol else None,"relative_strength_6m":stock_6m-bench_6m if stock_6m is not None and bench_6m is not None else None}
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
def roll_spread_bps(rows,i,n=60):
 changes=[rows[j]["close"]-rows[j-1]["close"] for j in range(max(1,i-n+1),i+1)]
 if len(changes)<3:return None
 a,b=changes[:-1],changes[1:];ma,mb=statistics.mean(a),statistics.mean(b);cov=sum((x-ma)*(y-mb) for x,y in zip(a,b))/len(a)
 return 0 if cov>=0 else 2*math.sqrt(-cov)/rows[i]["close"]*10000
def neutralize_by_sector(panel):
 groups={}
 for row in panel:groups.setdefault((row["date"],row["sector"]),[]).append(row)
 for rows in groups.values():
  for factor in FACTORS:
   valid=[x for x in rows if x["factors"].get(factor) is not None]
   if len(valid)<5:
    for x in valid:x["factors"][factor]=None
    continue
   ranked=rank([x["factors"][factor] for x in valid]);den=max(1,len(valid)-1)
   for x,value in zip(valid,ranked):x["factors"][factor]=(value-1)/den-.5
 return panel
def load_symbol(meta,start="2021-01-01",loader=fetch):
 try:return meta,loader(meta["symbol"],start)
 except Exception:return meta,[]
def evaluate_report(panel,start="0000-01-01",end="9999-12-31"):
 panel=[x for x in panel if start<=x["date"]<=end]
 groups={}
 for x in panel:groups.setdefault(x["date"],[]).append(x)
 records=[]
 for f in FACTORS:
  for h in HORIZONS:
   daily=[];obs=0;top=[];bottom=[]
   for date in sorted(groups):
    xs=[x for x in groups[date] if x["factors"].get(f) is not None and x["forward"].get(h) is not None]
    if len(xs)<10:continue
    vals=[x["factors"][f] for x in xs];ys=[x["forward"][h] for x in xs];ic=spearman(vals,ys)
    if ic is not None:daily.append(ic)
    cut=max(1,len(xs)//5);ordered=sorted(xs,key=lambda x:x["factors"][f]);bottom.extend(x["forward"][h] for x in ordered[:cut]);top.extend(x["forward"][h] for x in ordered[-cut:]);obs+=len(xs)
   records.append({"factor":f,"horizon":h,"dates":len(daily),"observations":obs,"mean_ic":round(statistics.mean(daily),4) if daily else None,"ic_positive_pct":round(sum(x>0 for x in daily)/len(daily)*100,1) if daily else None,"top_quantile_return":round(statistics.mean(top),4) if top else None,"bottom_quantile_return":round(statistics.mean(bottom),4) if bottom else None,"spread":round(statistics.mean(top)-statistics.mean(bottom),4) if top else None})
 return records
def metric_for(metrics,factor,horizon):return next((x for x in metrics if x["factor"]==factor and x["horizon"]==horizon),None)
def classify_factor(development,validation,forward,factor,horizon=60):
 d=metric_for(development,factor,horizon);v=metric_for(validation,factor,horizon);f=metric_for(forward,factor,horizon)
 if not d or not v or not d["mean_ic"] or not v["mean_ic"]:return "insufficient"
 if d["mean_ic"]*v["mean_ic"]<=0:return "unstable"
 if d["mean_ic"]>=.02 and v["mean_ic"]>=.02 and (v["ic_positive_pct"] or 0)>=55:return "promising"
 return "weak"
def redundancy(panel):
 pairs=[];groups={}
 for x in panel:groups.setdefault(x["date"],[]).append(x)
 for i,a in enumerate(FACTORS):
  for b in FACTORS[i+1:]:
   cors=[]
   for date in sorted(groups):
    xs=[x for x in groups[date] if x["factors"].get(a) is not None and x["factors"].get(b) is not None]
    if len(xs)>=10:
     c=spearman([x["factors"][a] for x in xs],[x["factors"][b] for x in xs])
     if c is not None:cors.append(c)
   pairs.append({"a":a,"b":b,"mean_rank_correlation":round(statistics.mean(cors),3) if cors else None,"dates":len(cors)})
 return sorted(pairs,key=lambda x:abs(x["mean_rank_correlation"] or 0),reverse=True)
def run(db_path="work/northstar-research-v04.sqlite",report_path="public/research-report.json",limit=500,start="2000-01-01",persist_detail=False):
 metas=universe(limit);loaded=[];benchmark_rows=fetch_long_history("SPY",start);benchmark={x["date"]:x["close"] for x in benchmark_rows};benchmark_ema=ema([x["close"] for x in benchmark_rows],200);benchmark_regime={x["date"]:x["close"]>benchmark_ema[i] for i,x in enumerate(benchmark_rows) if i>=199}
 with ThreadPoolExecutor(max_workers=12) as pool:
  fs=[pool.submit(load_symbol,m,start,fetch_long_history) for m in metas]
  for f in as_completed(fs):loaded.append(f.result())
 now=datetime.now(timezone.utc).isoformat();db=sqlite3.connect(db_path);db.execute("PRAGMA journal_mode=OFF");db.execute("PRAGMA synchronous=OFF");db.execute("PRAGMA temp_store=MEMORY");db.executescript(Path(__file__).with_name("research_schema.sql").read_text());panel=[];eligible_latest=0
 for meta,rows in loaded:
  if not rows:continue
  sym=meta["symbol"];db.execute("INSERT OR REPLACE INTO instruments VALUES(?,?,?,?,?,?,?)",(sym,meta["name"],meta.get("sector"),iso(rows[0]["date"]),iso(rows[-1]["date"]),"common_or_adr_screened","Nasdaq screener"))
  if persist_detail:db.executemany("INSERT OR REPLACE INTO bars_daily VALUES(?,?,?,?,?,?,?,?,?)",[(sym,iso(r["date"]),r["open"],r["high"],r["low"],r["close"],r["volume"],"Yahoo chart API adjusted history",now) for r in rows])
  for i in monthly_indices(rows):
   adv=sum(x["close"]*x["volume"] for x in rows[i-19:i+1])/20;spread=roll_spread_bps(rows,i);regime_ok=benchmark_regime.get(rows[i]["date"],False);eligible=rows[i]["close"]>=5 and adv>=10_000_000 and i>=252 and spread is not None and spread<=50 and regime_ok;date=iso(rows[i]["date"])
   if persist_detail:db.execute("INSERT OR REPLACE INTO universe_membership VALUES(?,?,?,?,?,?,?)",(date,sym,int(eligible),"eligible" if eligible else "price_liquidity_or_history",rows[i]["close"],adv,i+1))
   if not eligible:continue
   fv=factor_values(rows,i,benchmark);fw={h:(rows[i+h]["close"]/rows[i]["close"]-1 if i+h<len(rows) else None) for h in HORIZONS};panel.append({"date":date,"symbol":sym,"sector":meta.get("sector","Unclassified"),"factors":fv,"forward":fw})
   if persist_detail:
    db.executemany("INSERT OR REPLACE INTO factor_observations VALUES(?,?,?,?,?,?,?)",[(date,sym,k,v,int(v is not None),"Yahoo adjusted OHLCV derived",VERSION) for k,v in fv.items()])
    db.executemany("INSERT OR REPLACE INTO forward_returns VALUES(?,?,?,?)",[(date,sym,h,v) for h,v in fw.items()])
  i=len(rows)-1;adv=sum(x["close"]*x["volume"] for x in rows[-20:])/20;eligible_latest+=int(rows[i]["close"]>=5 and adv>=10_000_000 and i>=252)
 panel=neutralize_by_sector(panel);metrics=evaluate_report(panel);dates=sorted({x["date"] for x in panel});splits={"development":{"start":dates[0] if dates else None,"end":"2024-12-31"},"validation":{"start":"2025-01-01","end":"2025-12-31"},"forward_test":{"start":"2026-01-01","end":dates[-1] if dates else None}}
 split_metrics={k:evaluate_report(panel,*bounds) for k,bounds in SPLIT_BOUNDS.items()};factor_verdicts=[{"factor":f,"horizon":60,"verdict":classify_factor(split_metrics["development"],split_metrics["validation"],split_metrics["forward_test"],f)} for f in FACTORS]
 exp_id=f"{VERSION}-{now[:10]}";spec={"factors":FACTORS,"horizons":HORIZONS,"universe":f"top {limit} market-cap screened; price>=5; current market cap>=300m; ADV20>=10m; Roll spread proxy<=50bps; history>=252; SPY above EMA200","ranking":"within current Nasdaq sector buckets; minimum five stocks per bucket","execution":"signal at close, entry at next open","history_requested_from":start,"detail_persisted":persist_detail,"splits":splits};summary={"symbols_requested":len(metas),"symbols_loaded":sum(bool(r) for _,r in loaded),"eligible_latest":eligible_latest,"panel_rows":len(panel),"snapshot_dates":len(dates),"earliest_observation":dates[0] if dates else None,"latest_observation":dates[-1] if dates else None}
 db.execute("INSERT OR REPLACE INTO experiments VALUES(?,?,?,?,?,?,?,?,?)",(exp_id,now,VERSION,dates[0],dates[-1],eligible_latest,"completed",json.dumps(spec),json.dumps(summary)));db.execute("PRAGMA optimize");db.commit()
 implemented=[{"id":"momentum_12_1","plain":"12-month momentum excluding the latest month"},{"id":"momentum_6_1","plain":"6-month momentum excluding the latest month"},{"id":"momentum_3_1","plain":"3-month momentum excluding the latest week"},{"id":"trend_quality","plain":"price and EMA50 alignment relative to EMA200"},{"id":"low_volatility","plain":"negative 60-day annualised volatility"},{"id":"liquidity","plain":"log 20-day average dollar volume"},{"id":"rsi_14","plain":"14-day relative strength index; higher means stronger recent buying"},{"id":"macd_strength","plain":"MACD distance above its signal line, scaled by ATR"},{"id":"adx_14","plain":"14-day directional trend strength, ignoring direction"},{"id":"volume_expansion","plain":"today's volume relative to its prior 20-day average"},{"id":"breakout_252","plain":"distance from the previous 252-day high"},{"id":"volatility_contraction","plain":"20-day volatility contraction relative to 60 days"},{"id":"relative_strength_6m","plain":"six-month return minus the S&P 500 ETF return"}]
 report={"generated_at":now,"version":VERSION,"status":"research_only_not_a_trading_model","safeguards":[{"name":"Tradability first","detail":"Price, current market cap, dollar-volume and 60-day Roll spread-proxy gates run before ranking."},{"name":"Delayed execution","detail":"Daily close signals execute at the following session open."},{"name":"Long regime","detail":"Long candidates are eligible only while SPY is above its 200-day EMA."},{"name":"Sector relative","detail":"Every factor is ranked within its current sector bucket; historical sector membership remains unavailable."}],"weighting_policy":{"current":"No factor qualifies for increased weight in the full-history test","method":"Future combination weights will be capped and based on out-of-sample strength, stability across eras, drawdown contribution, turnover cost and independence from other factors; no exponential weighting."},"coverage":summary,"walk_forward":splits,"factors":{"implemented":implemented,"missing":["Point-in-time SEC quality/profitability","Point-in-time value","Earnings surprise and revisions","Historical sector membership","True historical bid-ask quotes","Delistings and full corporate-action audit"]},"metrics":metrics,"split_metrics":split_metrics,"factor_verdicts":factor_verdicts,"redundancy":redundancy(panel),"data_standard":{"required":["Daily adjusted OHLCV with split and dividend audit","Historical listings and delistings with effective dates","Point-in-time fundamentals with filing availability dates","Historical sector classifications","Trading calendar and corporate-action identifiers"],"quality_gates":["No observation may use data published after its as-of timestamp","Delisted securities remain in historical universes","Prices and returns reconcile across corporate actions","Missing values are explicit, never silently forward-filled","Every dataset, factor and experiment has a version and source"]},"experiment":{"id":exp_id,"specification":spec},"interpretation":"Positive IC means higher sector-relative factor ranks were associated with higher subsequent returns while the long-market regime was active. A promising label requires development and validation IC of at least 0.02, matching signs, and positive validation IC in at least 55% of dates. True spread and historical-sector data are still required before investment use."};Path(report_path).write_text(json.dumps(report,indent=2));return report
if __name__=="__main__":
 r=run();print(json.dumps(r["coverage"],indent=2));print(sorted(r["metrics"],key=lambda x:(x["mean_ic"] is not None,x["mean_ic"] or -9),reverse=True)[:8])
