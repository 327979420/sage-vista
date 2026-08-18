import json,pathlib
from concurrent.futures import ThreadPoolExecutor
from .fetch_nasdaq import fetch
from .technical import backtest,evaluate,regime_map

SYMBOLS=["TSLA","MU","LLY","CAT","UBER","CROX","PLTR"]
def load(s):return s,fetch(s,assetclass="etf" if s=="SPY" else "stocks")
if __name__=="__main__":
 pathlib.Path("public/market-data").mkdir(parents=True,exist_ok=True);report={}
 with ThreadPoolExecutor(max_workers=8) as pool:
  data=dict(pool.map(load,SYMBOLS+["SPY"]))
 market_regime=regime_map(data.pop("SPY"))
 for symbol,rows in data.items():
  pathlib.Path(f"public/market-data/{symbol}.json").write_text(json.dumps(rows[-320:],separators=(",",":")))
  split=next((i for i,r in enumerate(rows) if r["date"].endswith("/2023")),int(len(rows)*.7))
  train=backtest(rows[:split],market_regime=market_regime); test=backtest(rows[split-220:],market_regime=market_regime); latest=next((evaluate(rows,i,market_regime=market_regime) for i in range(len(rows)-2,max(220,len(rows)-32),-1) if evaluate(rows,i,market_regime=market_regime)),None)
  report[symbol]={"source":"Nasdaq historical API","through":rows[-1]["date"],"train_2016_2022":train["summary"],"test_2023_present":test["summary"],"latest_recent_plan":latest.dict() if latest else None}
 pathlib.Path("public/technical-report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
