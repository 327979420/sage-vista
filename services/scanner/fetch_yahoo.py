import json,time,urllib.parse,urllib.request
from datetime import datetime,timezone

HEAD={"User-Agent":"Mozilla/5.0","Accept":"application/json"}
def fetch(symbol,start="2000-01-01",end=None,retries=2):
    begin=int(datetime.strptime(start,"%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    finish=int(datetime.strptime(end,"%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()) if end else int(time.time())+86400
    query=urllib.parse.urlencode({"period1":begin,"period2":finish,"interval":"1d","events":"div,splits"})
    yahoo_symbol=symbol.replace(".","-")
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(yahoo_symbol)}?{query}"
    for attempt in range(retries+1):
        try:
            request=urllib.request.Request(url,headers=HEAD)
            with urllib.request.urlopen(request,timeout=30) as response:data=json.load(response)
            result=data["chart"]["result"][0];quote=result["indicators"]["quote"][0];adjusted=result["indicators"].get("adjclose",[{}])[0].get("adjclose",quote["close"]);rows=[]
            for i,stamp in enumerate(result["timestamp"]):
                values=[quote[k][i] for k in ("open","high","low","close","volume")]
                if any(v is None for v in values) or adjusted[i] is None:continue
                ratio=adjusted[i]/quote["close"][i] if quote["close"][i] else 1
                rows.append({"date":datetime.fromtimestamp(stamp,timezone.utc).strftime("%m/%d/%Y"),"open":quote["open"][i]*ratio,"high":quote["high"][i]*ratio,"low":quote["low"][i]*ratio,"close":adjusted[i],"volume":int(quote["volume"][i])})
            return rows
        except Exception:
            if attempt==retries:raise
            time.sleep(.5*(attempt+1))
