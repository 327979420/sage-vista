import json,os,time,urllib.error,urllib.parse,urllib.request
from datetime import date,timedelta
from pathlib import Path

BASE="https://eodhd.com/api";HEAD={"User-Agent":"SageVistaResearch/0.1","Accept":"application/json"}
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
    timeout=params.pop("_timeout",60);attempts=params.pop("_attempts",1)
    params={**params,"api_token":token(),"fmt":"json"};url=f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=HEAD),timeout=timeout) as response:return json.load(response)
        except (TimeoutError,urllib.error.URLError) as error:
            if attempt+1>=attempts:
                status=getattr(error,"code",None)
                detail=f" (HTTP {status})" if status is not None else ""
                # Never expose the request URL: it contains EODHD_API_TOKEN.
                raise RuntimeError(f"EODHD request failed for {path}{detail}") from None
            time.sleep(2**attempt)
def symbols(delisted=False):return get("exchange-symbol-list/US",delisted=int(delisted))
def prices(code,start="2000-01-01",end=None):
    params={"from":start,"period":"d"}
    if end:params["to"]=end
    return get(f"eod/{code}.US",**params)
def latest_reference_day(code="SPY",lookback_days=14,today=None):
    """Return the provider's latest completed US daily bar using a small query."""
    end=today or date.today();start=end-timedelta(days=lookback_days)
    rows=prices(code,start.isoformat(),end.isoformat())
    days=[row.get("date") for row in rows if row.get("date") and row.get("close") is not None]
    if not days:raise RuntimeError(f"No completed {code} daily bar is available")
    return max(days)
def actions(kind,code,start="2000-01-01"):return get(f"{kind}/{code}.US",**{"from":start})
def news(code,limit=3):return get("news",s=f"{code}.US",limit=limit,offset=0)
