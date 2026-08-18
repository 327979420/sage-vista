import json,pathlib
from concurrent.futures import ThreadPoolExecutor
from .fetch_nasdaq import fetch
from .run_universe import SYMBOLS
from .technical import backtest,trade_efficiency,regime_map

def load(symbol):return symbol,fetch(symbol,"2016-01-01",assetclass="etf" if symbol=="SPY" else "stocks")
if __name__=="__main__":
    with ThreadPoolExecutor(max_workers=8) as pool:data=dict(pool.map(load,SYMBOLS+["SPY"]))
    market_regime=regime_map(data.pop("SPY"));by_symbol={}
    for symbol,rows in data.items():
        result=backtest(rows,market_regime=market_regime);by_symbol[symbol]={"summary":trade_efficiency(result["trades"]),"trades":result["trades"]}
    all_trades=[{"symbol":symbol,**trade} for symbol,result in by_symbol.items() for trade in result["trades"]]
    report={"status":"research_only","method":"Signals form at the daily close and enter at the next open; long trades require SPY above its 200-day EMA; fixed-horizon scenarios honor the structural stop and ignore the original target","overall":trade_efficiency(all_trades),"by_symbol":{k:v["summary"] for k,v in by_symbol.items()},"trades":all_trades}
    pathlib.Path("public/efficiency-report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report["overall"],indent=2))
