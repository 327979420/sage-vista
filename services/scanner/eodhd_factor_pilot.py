"""Run the small survivorship-aware EODHD factor pilot.

This is a reproducibility tool, not the production scanner. Its two seed strings
are frozen legacy experiment identifiers: renaming them would silently select a
different historical sample.
"""
import hashlib,json,pathlib,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from .audit_eodhd import common
from .eodhd import prices,symbols
from .research_pipeline import FACTORS,HORIZONS,evaluate_report,factor_values,iso,monthly_indices,roll_spread_bps
from .technical import ema

def stable_sample(rows,n,seed):return sorted(rows,key=lambda x:hashlib.sha256(f"{seed}:{x['Code']}".encode()).hexdigest())[:n]
def adjusted_rows(code,start="2000-01-01",cache_dir="work/eodhd-cache"):
    cache=pathlib.Path(cache_dir)/f"{code}.json";cache.parent.mkdir(parents=True,exist_ok=True)
    if cache.exists():raw=json.loads(cache.read_text())
    else:
        raw=prices(code,start);cache.write_text(json.dumps(raw));time.sleep(.03)
    out=[]
    for x in raw:
        if not x.get("close") or not x.get("adjusted_close") or x.get("volume") is None:continue
        ratio=x["adjusted_close"]/x["close"]
        out.append({"date":datetime.strptime(x["date"],"%Y-%m-%d").strftime("%m/%d/%Y"),"open":x["open"]*ratio,"high":x["high"]*ratio,"low":x["low"]*ratio,"close":x["adjusted_close"],"volume":int(x["volume"])})
    return out
def load(meta):
    try:return meta,adjusted_rows(meta["Code"])
    except Exception:return meta,[]
def run(out="research/backtest/output/legacy-foundation/eodhd-factor-pilot.json",per_group=100):
    active=stable_sample(common(symbols(False)),per_group,"northstar-active-v1");dead=stable_sample(common(symbols(True)),per_group,"northstar-delisted-v1");selected=[({**x,"listing_status":"active"}) for x in active]+[({**x,"listing_status":"delisted"}) for x in dead]
    spy=adjusted_rows("SPY");benchmark={x["date"]:x["close"] for x in spy};market_ema=ema([x["close"] for x in spy],200);regime={x["date"]:x["close"]>market_ema[i] for i,x in enumerate(spy) if i>=199};loaded=[]
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures=[pool.submit(load,x) for x in selected]
        for future in as_completed(futures):loaded.append(future.result())
    panel=[];eligible_active=eligible_delisted=0
    for meta,rows in loaded:
        if len(rows)<253:continue
        included=False
        for i in monthly_indices(rows):
            adv=sum(x["close"]*x["volume"] for x in rows[i-19:i+1])/20;spread=roll_spread_bps(rows,i)
            if rows[i]["close"]<5 or adv<10_000_000 or spread is None or spread>50 or not regime.get(rows[i]["date"],False):continue
            fv=factor_values(rows,i,benchmark);fw={h:(rows[i+h]["close"]/rows[i+1]["open"]-1 if i+1<len(rows) and i+h<len(rows) else None) for h in HORIZONS};panel.append({"date":iso(rows[i]["date"]),"symbol":meta["Code"],"listing_status":meta["listing_status"],"factors":fv,"forward":fw});included=True
        if included:
            if meta["listing_status"]=="active":eligible_active+=1
            else:eligible_delisted+=1
    metrics=evaluate_report(panel);dates=sorted({x["date"] for x in panel});report={"generated_at":datetime.now(timezone.utc).isoformat(),"status":"survivorship_aware_pilot_not_promotable","provider":"EODHD All World","sample":{"requested_active":per_group,"requested_delisted":per_group,"loaded":sum(bool(x) for _,x in loaded),"eligible_active":eligible_active,"eligible_delisted":eligible_delisted,"stock_months":len(panel),"dates":len(dates),"start":dates[0] if dates else None,"end":dates[-1] if dates else None},"design":{"selection":"Deterministic hash sample of primary-exchange common stocks","tradability":"price>=5, ADV20>=10m, Roll spread proxy<=50bps","regime":"SPY above EMA200","ranking":"raw cross-sectional pilot only"},"metrics":metrics,"decision":"Use this run to verify delisted-security ingestion and factor direction only. Do not promote factors until historical sector neutralization and a larger universe are available.","limitations":["200-security pilot sample","No historical sector neutralization","Roll spread proxy instead of quote spread","No fundamentals or transaction costs"]}
    path=pathlib.Path(out);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2));return report
if __name__=="__main__":
    r=run();print(json.dumps(r["sample"],indent=2));print(sorted(r["metrics"],key=lambda x:x["mean_ic"] if x["mean_ic"] is not None else -9,reverse=True)[:8])
