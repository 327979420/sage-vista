import json,urllib.parse,urllib.request
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from .detectors import detect_bos,detect_retest,detect_w_bottom,load_config
from .fetch_nasdaq import fetch
from .technical import atr,ema,position_size

HEAD={"User-Agent":"Mozilla/5.0","Accept":"application/json, text/plain, */*"}
SECTORS=("Technology","Health Care","Financials","Consumer Discretionary","Consumer Staples","Industrials","Energy","Utilities","Real Estate","Telecommunications","Basic Materials")
def universe(limit=150):
 req=urllib.request.Request(f"https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit={limit}&offset=0",headers=HEAD)
 with urllib.request.urlopen(req,timeout=30) as r:rows=json.load(r)["data"]["table"]["rows"]
 bad=(" ETF"," WARRANT"," Warrant"," Preferred"," Depositary Shares"," Units")
 rows=[x for x in rows if float(x["lastsale"].replace("$","").replace(",",""))>=5 and float((x.get("marketCap") or "0").replace(",",""))>=300_000_000 and not any(k in x["name"] for k in bad)]
 wanted={x["symbol"] for x in rows};sector_map={}
 for sector in SECTORS:
  q=urllib.parse.urlencode({"tableonly":"true","limit":10000,"offset":0,"sector":sector})
  try:
   req=urllib.request.Request(f"https://api.nasdaq.com/api/screener/stocks?{q}",headers=HEAD)
   with urllib.request.urlopen(req,timeout=30) as r:sector_rows=json.load(r)["data"]["table"]["rows"]
   for x in sector_rows:
    if x["symbol"] in wanted:sector_map[x["symbol"]]=sector
  except Exception:continue
 for x in rows:x["sector"]=sector_map.get(x["symbol"],"Unclassified")
 return rows

def inspect(meta):
 symbol=meta["symbol"]
 try:rows=fetch(symbol,"2023-01-01")
 except Exception as e:return {"symbol":symbol,"error":str(e)[:100]}
 if len(rows)<252:return {"symbol":symbol,"excluded":"less_than_one_year"}
 adv=sum(x["close"]*x["volume"] for x in rows[-20:])/20
 if adv<10_000_000:return {"symbol":symbol,"excluded":"dollar_volume","adv20":adv}
 cfg=load_config();ats=atr(rows);closes=[x["close"] for x in rows];e50,e200=ema(closes,50),ema(closes,200)
 higher_ok=closes[-1]>e200[-1] and e50[-1]>e50[-21] and closes[-1]>e50[-1]*.94
 if not higher_ok:return {"symbol":symbol,"company":meta["name"],"adv20":adv,"status":"higher_timeframe_ineligible"}
 observations=[]
 for end in range(max(220,len(rows)-50),len(rows)-2):
  w=detect_w_bottom(rows,end,cfg)
  if not w.detected:continue
  second=w.data_used["last_index"]-cfg["pivot"]["right_bars"];confirmed=w.data_used["last_index"];neck=w.levels["neckline"]
  bos=None
  for i in range(confirmed+1,min(len(rows),confirmed+16)):
   b=detect_bos(rows,i,neck,cfg)
   if b.detected:bos=b;bos_i=i;break
  if bos:
   stop=w.levels["second_low"]-.25*ats[second];target=neck+2*(neck-stop)
   ret=detect_retest(rows,bos_i,min(len(rows)-1,bos_i+5),neck,stop,target,cfg)
   entry=None;plan=None
   if ret.detected:
    ri=ret.data_used["last_index"];entry=rows[ri]["close"];target=entry+2*(entry-stop)
    plan={"entry_confirming_close":round(entry,2),"entry_break_confirming_high":round(rows[ri]["high"]+.01,2),"limit_retest_level":round(neck,2),"structural_stop":round(stop,2),"provisional_2r_target":round(target,2),"shares_at_100k_0_75pct_risk":position_size(100000,.0075,entry,stop),"expected_holding_time":"5–20 daily bars; exit at bar 10 if <0.5R progress","warning":"Target is a provisional 2R measured move; supply, earnings and option-wall checks are not complete"}
   observations.append({"w":w.dict(),"bos":bos.dict(),"retest":ret.dict(),"bos_index":bos_i,"plan":plan,"age_bars":len(rows)-1-bos_i})
  else:observations.append({"w":w.dict(),"bos":None,"retest":None,"age_bars":len(rows)-1-second})
 if not observations:return {"symbol":symbol,"company":meta["name"],"adv20":adv,"status":"no_recent_w"}
 best=sorted(observations,key=lambda x:(bool(x["retest"] and x["retest"]["detected"]),x["bos"] is not None,-x["age_bars"]),reverse=True)[0]
 fresh=best["retest"] and best["retest"]["detected"] and len(rows)-1-best["retest"]["data_used"]["last_index"]<=2
 status="qualified_retest" if fresh else "bos_waiting_retest" if best["bos"] and best["age_bars"]<=5 else "w_waiting_bos" if not best["bos"] and best["age_bars"]<=8 else "expired"
 return {"symbol":symbol,"company":meta["name"],"adv20":round(adv),"status":status,"setup":best}

if __name__=="__main__":
 names=universe();out=[]
 with ThreadPoolExecutor(max_workers=12) as pool:
  futures=[pool.submit(inspect,x) for x in names]
  for f in as_completed(futures):out.append(f.result())
 ranked=sorted([x for x in out if x.get("status") in ("qualified_retest","bos_waiting_retest","w_waiting_bos")],key=lambda x:({"qualified_retest":3,"bos_waiting_retest":2,"w_waiting_bos":1}[x["status"]],-x["setup"]["age_bars"]),reverse=True)
 report={"universe_source":"Nasdaq screener, top 150 by market capitalization","requested":len(names),"fetched":sum("error" not in x for x in out),"eligible_liquidity_history":sum("excluded" not in x and "error" not in x for x in out),"qualified_retests":sum(x["status"]=="qualified_retest" for x in ranked),"bos_waiting_retest":sum(x["status"]=="bos_waiting_retest" for x in ranked),"w_waiting_bos":sum(x["status"]=="w_waiting_bos" for x in ranked),"candidates":ranked}
 Path("work/quick-scan.json").write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!="candidates"},indent=2));print([(x["symbol"],x["status"],x["setup"]["age_bars"]) for x in ranked[:20]])
