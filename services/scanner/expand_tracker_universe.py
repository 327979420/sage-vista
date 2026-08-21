"""Expand the live tracker toward the most liquid active US common stocks."""
import argparse,json,pathlib
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from .audit_eodhd import common
from .eodhd import prices,symbols

def run(target=1000,as_of="2026-08-20",cache_dir="work/eodhd-cache",out="public/universe-expansion.json"):
 cache=pathlib.Path(cache_dir);cache.mkdir(parents=True,exist_ok=True)
 symbol_cache=pathlib.Path("work/eodhd-active-common.json")
 if symbol_cache.exists():active=json.loads(symbol_cache.read_text())
 else:
  active=common(symbols(False));symbol_cache.write_text(json.dumps(active))
 active_codes={x["Code"] for x in active}
 bulk_path=pathlib.Path("work/eodhd-bulk")/f"{as_of}.json"
 if not bulk_path.exists():raise RuntimeError(f"Missing bulk close for {as_of}")
 rows=json.loads(bulk_path.read_text());ranked=[]
 for x in rows:
  code=x.get("code");price=x.get("adjusted_close");volume=x.get("volume")
  if code in active_codes and price and volume is not None and price>=5 and price*volume>=10_000_000:ranked.append((price*volume,code))
 selected=[code for _,code in sorted(ranked,reverse=True)[:target]]
 missing=[code for code in selected if not (cache/f"{code}.json").exists()]
 results={"downloaded":[],"failed":{}}
 def fetch(code):
  rows=prices(code,"2000-01-01")
  if len(rows)<420:raise RuntimeError(f"only {len(rows)} daily rows")
  (cache/f"{code}.json").write_text(json.dumps(rows));return code,len(rows)
 with ThreadPoolExecutor(max_workers=8) as pool:
  futures={pool.submit(fetch,code):code for code in missing}
  for future in as_completed(futures):
   code=futures[future]
   try:
    _,count=future.result();results["downloaded"].append({"symbol":code,"rows":count})
   except Exception as exc:results["failed"][code]=str(exc)
 report={"generated_at":datetime.now(timezone.utc).isoformat(),"as_of":as_of,"target":target,"selection":"最新收盘日中成交额最高、股价不低于5美元且成交额不低于1000万美元的活跃美国普通股","selected":len(selected),"already_cached":len(selected)-len(missing),"downloaded":len(results["downloaded"]),"failed":len(results["failed"]),"total_cache_files":len(list(cache.glob("*.json"))),"failures":results["failed"]}
 pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,indent=2));return report

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--target",type=int,default=1000);parser.add_argument("--as-of",default="2026-08-20");args=parser.parse_args()
 print(json.dumps(run(args.target,args.as_of),ensure_ascii=False,indent=2))
