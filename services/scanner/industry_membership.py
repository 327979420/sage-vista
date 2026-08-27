"""Explicit, versioned public membership ingestion for Industry Radar."""
import argparse,csv,html,io,json,pathlib,re,urllib.error,urllib.parse,urllib.request,zipfile

HEADERS={"User-Agent":"Mozilla/5.0 SageVistaResearch/1.0","Accept":"application/json,text/csv,*/*"}
NASDAQ_URL="https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25&offset=0&download=true"
DEFAULT_REGISTRY=pathlib.Path(__file__).resolve().parents[2]/"data/themes/theme-registry.json"

def download_bytes(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers=HEADERS),timeout=90) as response:return response.read()

def download(url):return download_bytes(url).decode("utf-8-sig")

def clean_tickers(values):
 out=[]
 for value in values:
  ticker=str(value or "").strip().upper()
  if not ticker or ticker in {"-","--","N/A","CASH","USD","US DOLLAR"} or ticker.startswith("CASH"):continue
  if ticker not in out:out.append(ticker)
 return out

def parse_table_csv(text,headers=("ticker","holding ticker","symbol")):
 rows=list(csv.reader(io.StringIO(text)));wanted={x.lower() for x in headers}
 for index,row in enumerate(rows):
  normalized=[x.strip().lower().lstrip("\ufeff") for x in row]
  column=next((i for i,name in enumerate(normalized) if name in wanted),None)
  if column is not None:return clean_tickers(row[column] for row in rows[index+1:] if len(row)>column)
 raise ValueError("Holdings ticker column not found")

def parse_xlsx_tickers(payload,headers=("ticker","holding ticker","symbol")):
 """Read the first XLSX sheet with stdlib only; no provider SDK or paid feed."""
 from xml.etree import ElementTree as ET
 with zipfile.ZipFile(io.BytesIO(payload)) as book:
  shared=[]
  if "xl/sharedStrings.xml" in book.namelist():
   root=ET.fromstring(book.read("xl/sharedStrings.xml"));shared=["".join(node.itertext()) for node in root]
  sheet=ET.fromstring(book.read("xl/worksheets/sheet1.xml"));rows=[]
  for row in sheet.iter():
   if not row.tag.endswith("}row"):continue
   values=[]
   for cell in row:
    if not cell.tag.endswith("}c"):continue
    value=next((x for x in cell if x.tag.endswith("}v")),None);raw=value.text if value is not None else ""
    if cell.attrib.get("t")=="s" and raw:raw=shared[int(raw)]
    values.append(raw)
   rows.append(values)
 return parse_table_csv("\n".join(",".join(csv_escape(x) for x in row) for row in rows),headers)

def csv_escape(value):return '"'+str(value).replace('"','""')+'"'

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

def parse_ishares(text):return parse_table_csv(text,("ticker",))
def parse_first_trust(text):
 try:return parse_table_csv(text,("ticker","symbol"))
 except (ValueError,csv.Error):
  values=[]
  for row in re.findall(r"<tr[^>]*>.*?</tr>",text,flags=re.I|re.S):
   cells=[html.unescape(re.sub("<[^>]+>","",x)).strip() for x in re.findall(r"<td[^>]*>.*?</td>",row,flags=re.I|re.S)]
   if len(cells)==7 and re.fullmatch(r"[A-Z0-9]{9}",cells[2]):values.append(cells[1])
  return clean_tickers(values)
def parse_state_street(payload):return parse_xlsx_tickers(payload,("ticker","symbol")) if payload[:2]==b"PK" else parse_table_csv(payload.decode("utf-8-sig"),("ticker","symbol"))
def parse_invesco(text):
 try:return clean_tickers(x.get("ticker") for x in json.loads(text).get("holdings",[]))
 except json.JSONDecodeError:return parse_table_csv(text,("holding ticker","ticker","symbol"))
def parse_vaneck(text):
 try:return parse_table_csv(text,("ticker","symbol"))
 except (ValueError,csv.Error):
  values=[]
  for row in re.findall(r"<tr[^>]*>.*?</tr>",text,flags=re.I|re.S):
   cells=[html.unescape(re.sub("<[^>]+>","",x)).strip() for x in re.findall(r"<td[^>]*>.*?</td>",row,flags=re.I|re.S)]
   if cells:values.append(cells[0])
  return clean_tickers(values)

def configured_adapter(source,effective_from,parser,binary=False):
 url=source["url"].format(fund=source["fund"].lower(),FUND=source["fund"].upper(),date=effective_from.replace("-",""))
 payload=download_bytes(url) if binary else download(url)
 return {"source":source["fund"].upper(),"source_url":url,"members":parser(payload)}

def configured_source_url(source,effective_from):
 if source["provider"]=="global_x":return f"https://assets.globalxetfs.com/funds/holdings/{source['fund'].lower()}_full-holdings_{effective_from.replace('-','')}.csv"
 return source["url"].format(fund=source["fund"].lower(),FUND=source["fund"].upper(),date=effective_from.replace("-",""))

def global_x_adapter(source,effective_from):
 fund=source["fund"].upper();url=f"https://assets.globalxetfs.com/funds/holdings/{fund.lower()}_full-holdings_{effective_from.replace('-','')}.csv"
 return {"source":fund,"source_url":url,"members":parse_global_x(download(url))}

def ishares_adapter(source,effective_from):
 page=download(source["url"]);match=re.search(r'href="([^"]+/latest-holdings\.csv)"',page,re.I)
 if not match:raise ValueError("official_download_link_missing")
 url=urllib.parse.urljoin(source["url"],html.unescape(match.group(1)))
 return {"source":source["fund"].upper(),"source_url":url,"members":parse_ishares(download(url))}
def first_trust_adapter(source,effective_from):return configured_adapter(source,effective_from,parse_first_trust)
def state_street_adapter(source,effective_from):return configured_adapter(source,effective_from,parse_state_street,True)
def invesco_adapter(source,effective_from):
 page=download(source["url"]);cusip=re.search(r'<meta name="cusip" content="([^"]+)"',page)
 if not cusip:raise ValueError("official_fund_identifier_missing")
 url=f"https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/{cusip.group(1)}/holdings/fund?idType=cusip&productType=ETF"
 return {"source":source["fund"].upper(),"source_url":url,"members":parse_invesco(download(url))}
def vaneck_adapter(source,effective_from):
 base=re.sub(r"/holdings/?$","",source["url"]);url=base.rstrip("/")+"/downloads/holdings/";payload=download_bytes(url)
 return {"source":source["fund"].upper(),"source_url":url,"members":parse_xlsx_tickers(payload,("ticker","symbol"))}

PROVIDER_ADAPTERS={"global_x":global_x_adapter,"ishares":ishares_adapter,"first_trust":first_trust_adapter,"state_street":state_street_adapter,"invesco":invesco_adapter,"vaneck":vaneck_adapter}

def is_us_tradeable_identifier(ticker):return bool(re.fullmatch(r"[A-Z][A-Z0-9\-]{0,9}|[A-Z]{1,6}\.[AB]",ticker))

def analyze_overlap(themes):
 pairs=[]
 for i,left in enumerate(themes):
  a=set(left["members"])
  for right in themes[i+1:]:
   b=set(right["members"]);shared=sorted(a&b);den=min(len(a),len(b));union=len(a|b)
   overlap=len(shared)/den if den else 0;jaccard=len(shared)/union if union else 0
   pairs.append({"theme_a":left["theme_id"],"theme_b":right["theme_id"],"shared_count":len(shared),"shared_members":shared,"overlap_pct":round(overlap,4),"jaccard":round(jaccard,4),"review":"near_duplicate" if overlap>=.75 else "differentiate" if overlap>=.5 else "normal"})
 return sorted(pairs,key=lambda x:(-x["overlap_pct"],x["theme_a"],x["theme_b"]))

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
  try:
   result=PROVIDER_ADAPTERS[provider](source,effective_from)
   if not result.get("members"):raise ValueError("no_normalized_holdings")
   source_status="available";parse_status="parsed";error_reason=None
  except Exception:
   # One provider format change must not erase other defensible themes. Keep a
   # zero-member unavailable record and redact transport/parser details.
   result={"source":source["fund"].upper(),"source_url":configured_source_url(source,effective_from),"members":[]};source_status="unavailable";parse_status="source_error";error_reason="provider_transport_or_format_error"
  members=result["members"];us=[x for x in members if is_us_tradeable_identifier(x)];foreign=sorted(set(members)-set(us))
  themes.append({"theme_id":config["theme_id"],"name":config["name"],"source_type":"official_etf_holdings","source_provider":provider,"source":result["source"],"source_url":result["source_url"],"source_date":effective_from,"effective_from":effective_from,"source_status":source_status,"parse_status":parse_status,"holdings_count":len(members),"error_reason":error_reason,"members":members,"membership_audit":{"total_holdings":len(members),"us_tradeable_members":len(us),"foreign_or_unmapped_members":foreign,"foreign_or_unmapped_count":len(foreign),"errors_redacted":True}})
 suffix=f"-{revision}" if revision else ""
 revision_number=int(revision.removeprefix("v")) if revision else 1
 payload={"version":f"themes-{effective_from}{suffix}","snapshot_revision":revision_number,"source_date":effective_from,"effective_from":effective_from,"themes":themes,"overlap_analysis":analyze_overlap(themes)}
 write_new(out,payload);return payload

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--effective-from",required=True);parser.add_argument("--kind",choices=("nasdaq","themes","all"),default="all");parser.add_argument("--revision");parser.add_argument("--registry",default=str(DEFAULT_REGISTRY))
 args=parser.parse_args();day=args.effective_from
 if args.kind in ("nasdaq","all"):snapshot_nasdaq(day,f"data/industry/nasdaq-industry-{day}.json")
 if args.kind in ("themes","all"):
  suffix=f"-{args.revision}" if args.revision else ""
  snapshot_themes(day,f"data/themes/snapshots/{day}{suffix}.json",args.revision,args.registry)
