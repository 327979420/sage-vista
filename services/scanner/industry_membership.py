"""Explicit, versioned public membership ingestion for Industry Radar."""
import argparse,csv,io,json,pathlib,urllib.request

HEADERS={"User-Agent":"Mozilla/5.0 SageVistaResearch/1.0","Accept":"application/json,text/csv,*/*"}
NASDAQ_URL="https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true"
GLOBAL_X={"fintech":("Fintech","FINX"),"robotics-ai":("Robotics & AI","BOTZ"),"uranium":("Uranium","URA"),"copper-miners":("Copper Miners","COPX")}

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

def write_new(path,payload):
 path=pathlib.Path(path)
 if path.exists():raise FileExistsError(f"Refusing to overwrite versioned snapshot: {path}")
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(payload,indent=2)+"\n")

def snapshot_nasdaq(effective_from,out):
 raw=json.loads(download(NASDAQ_URL));rows=raw["data"]["rows"]
 payload={"version":f"nasdaq-{effective_from}","source_url":NASDAQ_URL,"source_date":effective_from,"effective_from":effective_from,"classification_is_current_snapshot":True,
  "companies":[{"ticker":x.get("symbol"),"company":x.get("name"),"sector":x.get("sector"),"industry":x.get("industry")} for x in rows if x.get("symbol")]}
 write_new(out,payload);return payload

def snapshot_themes(effective_from,out,revision=None):
 themes=[]
 for theme_id,(name,fund) in GLOBAL_X.items():
  url=f"https://assets.globalxetfs.com/funds/holdings/{fund.lower()}_full-holdings_{effective_from.replace('-','')}.csv"
  members=parse_global_x(download(url))
  themes.append({"theme_id":theme_id,"name":name,"source_type":"official_etf_holdings","source":fund,"source_url":url,"source_date":effective_from,"effective_from":effective_from,"members":members})
 suffix=f"-{revision}" if revision else ""
 revision_number=int(revision.removeprefix("v")) if revision else 1
 payload={"version":f"themes-{effective_from}{suffix}","snapshot_revision":revision_number,"source_date":effective_from,"effective_from":effective_from,"themes":themes}
 write_new(out,payload);return payload

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--effective-from",required=True);parser.add_argument("--kind",choices=("nasdaq","themes","all"),default="all");parser.add_argument("--revision")
 args=parser.parse_args();day=args.effective_from
 if args.kind in ("nasdaq","all"):snapshot_nasdaq(day,f"data/industry/nasdaq-industry-{day}.json")
 if args.kind in ("themes","all"):
  suffix=f"-{args.revision}" if args.revision else ""
  snapshot_themes(day,f"data/themes/snapshots/{day}{suffix}.json",args.revision)
