"""Open-source industry taxonomy and ETF disclosure adapters.

FinanceDatabase data is MIT licensed and snapshotted locally. OpenBB remains an
optional external dependency: this module calls its public API without copying
AGPL source into Sage Vista.
"""
import argparse,csv,io,json,pathlib,urllib.request
from datetime import datetime,timezone

ROOT=pathlib.Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT_DIR=ROOT/"data/industry"
FINANCE_DATABASE_REPO="JerBouma/FinanceDatabase"
FINANCE_DATABASE_REF="main"
US_EXCHANGES=("ASE","BTS","NCM","NGM","NMS","NYQ","PCX")
FIELDS=("symbol","name","sector","industry_group","industry","exchange","market","market_cap","delisted")

def _download(url):
 request=urllib.request.Request(url,headers={"User-Agent":"SageVistaResearch/1.0"})
 with urllib.request.urlopen(request,timeout=120) as response:return response.read().decode("utf-8-sig")

def parse_finance_database_csv(text,wanted=None):
 wanted={x.upper() for x in wanted} if wanted else None;out=[]
 for row in csv.DictReader(io.StringIO(text)):
  symbol=(row.get("symbol") or "").strip().upper()
  if not symbol or (wanted is not None and symbol not in wanted):continue
  out.append({key:row.get(key) or None for key in FIELDS}|{"symbol":symbol})
 return out

def snapshot_finance_database(symbols,effective_from,out,ref=FINANCE_DATABASE_REF,downloader=_download):
 wanted={x.upper() for x in symbols};by_symbol={}
 urls=[]
 for exchange in US_EXCHANGES:
  url=f"https://raw.githubusercontent.com/{FINANCE_DATABASE_REPO}/{ref}/database/equities/{exchange}.csv";urls.append(url)
  for row in parse_finance_database_csv(downloader(url),wanted):by_symbol.setdefault(row["symbol"],row)
 payload={"schema_version":"1.0.0","effective_from":effective_from,"generated_at":datetime.now(timezone.utc).isoformat(),
  "source":{"project":"FinanceDatabase","repository":f"https://github.com/{FINANCE_DATABASE_REPO}","license":"MIT","ref":ref,"files":urls},
  "classification_is_current_snapshot":True,"historical_backfill_allowed":False,"requested_symbols":len(wanted),"matched_symbols":len(by_symbol),
  "unmatched_symbols":sorted(wanted-set(by_symbol)),"companies":[by_symbol[x] for x in sorted(by_symbol)]}
 path=pathlib.Path(out)
 if path.exists():raise FileExistsError(f"Refusing to overwrite versioned snapshot: {path}")
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload,indent=2)+"\n");return payload

def openbb_etf_holdings(symbol,provider=None,client=None):
 """Normalize OpenBB ETF holdings while keeping OpenBB optional and isolated."""
 if client is None:
  try:from openbb import obb as client
  except ImportError as exc:raise RuntimeError("OpenBB is not installed in this environment") from exc
 kwargs={"symbol":symbol.upper()}
 if provider:kwargs["provider"]=provider
 frame=client.etf.holdings(**kwargs).to_df().reset_index();return frame.to_dict(orient="records")

def openbb_nport_disclosure(symbol,start_date=None,end_date=None,client=None):
 """Use OpenBB's SEC N-PORT endpoint for dated fund disclosure research."""
 if client is None:
  try:from openbb import obb as client
  except ImportError as exc:raise RuntimeError("OpenBB is not installed in this environment") from exc
 kwargs={"symbol":symbol.upper(),"provider":"sec"}
 if start_date:kwargs["start_date"]=start_date
 if end_date:kwargs["end_date"]=end_date
 frame=client.etf.nport_disclosure(**kwargs).to_df().reset_index();return frame.to_dict(orient="records")

def tracked_symbols(root=ROOT):
 symbols=set();root=pathlib.Path(root)
 for path,key in ((root/"public/daily-factor-snapshot.json","symbols"),(root/"work/eodhd-panel-v4.json","panel")):
  if not path.exists():continue
  for row in json.loads(path.read_text()).get(key,[]):
   symbol=row.get("symbol")
   if symbol:symbols.add(symbol.upper())
 for path in (root/"data/themes/snapshots").glob("*.json"):
  for theme in json.loads(path.read_text()).get("themes",[]):symbols.update(x.upper() for x in theme.get("members",[]))
 return sorted(symbols)

def select_finance_database_snapshot(as_of,snapshot_dir=DEFAULT_SNAPSHOT_DIR):
 eligible=[]
 for path in pathlib.Path(snapshot_dir).glob("finance-database-*.json"):
  payload=json.loads(path.read_text());effective=payload.get("effective_from")
  if effective and effective<=as_of:eligible.append((effective,path.name,payload))
 return max(eligible,key=lambda x:(x[0],x[1]))[2] if eligible else None

def classification_by_ticker(snapshot):
 return {x["symbol"]:{key:x.get(key) for key in ("sector","industry_group","industry","market_cap")} for x in (snapshot or {}).get("companies",[])}

if __name__=="__main__":
 parser=argparse.ArgumentParser(description="Snapshot FinanceDatabase classifications for the tracked universe")
 parser.add_argument("--effective-from",required=True);parser.add_argument("--out",required=True);parser.add_argument("--ref",default=FINANCE_DATABASE_REF)
 args=parser.parse_args();result=snapshot_finance_database(tracked_symbols(),args.effective_from,args.out,args.ref)
 print(json.dumps({k:result[k] for k in ("effective_from","requested_symbols","matched_symbols","unmatched_symbols")},indent=2))
