import argparse,json,pathlib
from .fetch_nasdaq import fetch
from .technical import backtest

if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("symbol");p.add_argument("--out",default="work/backtest.json");p.add_argument("--start",default="2016-01-01");a=p.parse_args()
 result={"symbol":a.symbol.upper(),"source":"Nasdaq historical API (daily, split-adjustment limitations apply)","strategy":"Northstar higher-timeframe support + two-confirmation confluence gate v0.1","result":backtest(fetch(a.symbol,a.start))}
 pathlib.Path(a.out).parent.mkdir(parents=True,exist_ok=True);pathlib.Path(a.out).write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(result["result"]["summary"],indent=2))
