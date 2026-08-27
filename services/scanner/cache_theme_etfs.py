"""Fetch deterministic full-history ETF proxies needed by research backtests."""
import json,pathlib
from .eodhd import prices

ROOT=pathlib.Path(__file__).parents[2]

def funds(registry=ROOT/"data/themes/theme-registry.json"):
 payload=json.loads(pathlib.Path(registry).read_text());return sorted({x.get("membership_source",{}).get("fund") for x in payload["themes"] if x.get("membership_source",{}).get("fund")})

def run(cache=ROOT/"work/eodhd-cache"):
 cache=pathlib.Path(cache);cache.mkdir(parents=True,exist_ok=True);result={"downloaded":[],"existing":[],"failed":{}}
 for symbol in funds():
  path=cache/f"{symbol}.json"
  if path.exists() and len(json.loads(path.read_text()))>=260:result["existing"].append(symbol);continue
  try:
   rows=prices(symbol,"2000-01-01")
   if len(rows)<260:raise RuntimeError(f"only {len(rows)} rows")
   path.write_text(json.dumps(rows));result["downloaded"].append(symbol)
  except Exception as exc:result["failed"][symbol]=str(exc)
 return result

if __name__=="__main__":print(json.dumps(run(),indent=2))
