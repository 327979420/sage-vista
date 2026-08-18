import json,pathlib
from concurrent.futures import ThreadPoolExecutor
from .fetch_nasdaq import fetch
from .run_universe import SYMBOLS
from .technical import backtest,trade_efficiency

def load(symbol):
    rows=fetch(symbol,"2016-01-01");result=backtest(rows)
    return symbol,{"summary":trade_efficiency(result["trades"]),"trades":result["trades"]}
if __name__=="__main__":
    with ThreadPoolExecutor(max_workers=7) as pool:by_symbol=dict(pool.map(load,SYMBOLS))
    all_trades=[{"symbol":symbol,**trade} for symbol,result in by_symbol.items() for trade in result["trades"]]
    report={"status":"research_only","method":"Long entries at next daily open; fixed-horizon scenarios honor the structural stop and ignore the original target","overall":trade_efficiency(all_trades),"by_symbol":{k:v["summary"] for k,v in by_symbol.items()},"trades":all_trades}
    pathlib.Path("public/efficiency-report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report["overall"],indent=2))
