import json,os,urllib.parse,urllib.request
from pathlib import Path

BASE="https://eodhd.com/api";HEAD={"User-Agent":"NorthstarResearch/0.1","Accept":"application/json"}
def token():
    value=os.environ.get("EODHD_API_TOKEN","")
    if not value:
        env=Path(__file__).resolve().parents[2]/".env.local"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("EODHD_API_TOKEN="):value=line.split("=",1)[1].strip().strip('"').strip("'")
    if not value:raise RuntimeError("EODHD_API_TOKEN is not configured")
    return value
def get(path,**params):
    params={**params,"api_token":token(),"fmt":"json"};url=f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(urllib.request.Request(url,headers=HEAD),timeout=60) as response:return json.load(response)
def symbols(delisted=False):return get("exchange-symbol-list/US",delisted=int(delisted))
def prices(code,start="2000-01-01",end=None):
    params={"from":start,"period":"d"}
    if end:params["to"]=end
    return get(f"eod/{code}.US",**params)
def actions(kind,code,start="2000-01-01"):return get(f"{kind}/{code}.US",**{"from":start})
