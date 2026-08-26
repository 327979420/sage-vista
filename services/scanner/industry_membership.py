"""Explicit, versioned public membership ingestion for Industry Radar."""
import argparse,csv,io,json,pathlib,urllib.request

HEADERS={"User-Agent":"Mozilla/5.0 SageVistaResearch/1.0","Accept":"application/json,text/csv,*/*"}
NASDAQ_URL="https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true"
DEFAULT_REGISTRY=pathlib.Path(__file__).resolve().parents[2]/"data/themes/theme-registry.json"

def download(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers=HEADERS),timeout=90) as response:return response.read().decode("utf-8-sig")

def parse_global_x(text):
 rows=list(csv.reader(io.StringIO(text)))
 header=next(i for i,row in enumerate(rows) if row and row[0].strip()=="% of Net Assets")
 tickers=[]
 for row in rows[header+1:]:
  if len(row)<2:continue
  # Preserve the official identifier verbatim (for example "BMN AU"). The
  # price layer may mark it unavailable, but must never guess a US mapping.
  ticker=row[1].strip().upper()
  if ticker and ticker not in tickers:tickers.append(ticker)
 return tickers

def global_x_adapter(source,effective_from):
 fund=source["fund"].upper();url=f"https://assets.globalxetfs.com/funds/holdings/{fund.lower()}_full-holdings_{effective_from.replace('-','')}.csv"
 return {"source":fund,"source_url":url,"members":parse_global_x(download(url))}

PROVIDER_ADAPTERS={"global_x":global_x_adapter}

def configured_themes(registry=DEFAULT_REGISTRY):
 payload=json.loads(pathlib.Path(registry).read_text())
 return [theme for theme in payload["themes"] if theme.get("membership_source")]

def write_new(path,payload):
 path=pathlib.Path(path)
 if path.exists():raise FileExistsError(f"Refusing to overwrite versioned snapshot: {path}")
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload,indent=2)+"\n")

def snapshot_nasdaq(effective_from,out):
 raw=json.loads(download(NASDAQ_URL));rows=raw["data"]["rows"]
 payload={"version":f"nasdaq-{effective_from}","source_url":NASDAQ_URL,"source_date":effective_from,"effective_from":effective_from,"classification_is_current_snapshot":True,
  "companies":[{"ticker":x.get("symbol"),"company":x.get("name"),"sector":x.get("sector"),"industry":x.get("industry")} for x in rows if x.get("symbol")]}
 write_new(out,payload);return payload

def snapshot_themes(effective_from,out,revision=None,registry=DEFAULT_REGISTRY):
 themes=[]
 for config in configured_themes(registry):
  source=config["membership_source"];provider=source["provider"]
  if provider not in PROVIDER_ADAPTERS:raise ValueError(f"Unsupported holdings provider: {provider}")
  result=PROVIDER_ADAPTERS[provider](source,effective_from)
  themes.append({"theme_id":config["theme_id"],"name":config["name"],"source_type":"official_etf_holdings","source_provider":provider,"source":result["source"],"source_url":result["source_url"],"source_date":effective_from,"effective_from":effective_from,"members":result["members"]})
 suffix=f"-{revision}" if revision else ""
 revision_number=int(revision.removeprefix("v")) if revision else 1
 payload={"version":f"themes-{effective_from}{suffix}","snapshot_revision":revision_number,"source_date":effective_from,"effective_from":effective_from,"themes":themes}
 write_new(out,payload);return payload

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--effective-from",required=True);parser.add_argument("--kind",choices=("nasdaq","themes","all"),default="all");parser.add_argument("--revision");parser.add_argument("--registry",default=str(DEFAULT_REGISTRY))
 args=parser.parse_args();day=args.effective_from
 if args.kind in ("nasdaq","all"):snapshot_nasdaq(day,f"data/industry/nasdaq-industry-{day}.json")
 if args.kind in ("themes","all"):
  suffix=f"-{args.revision}" if args.revision else ""
  snapshot_themes(day,f"data/themes/snapshots/{day}{suffix}.json",args.revision,args.registry)
