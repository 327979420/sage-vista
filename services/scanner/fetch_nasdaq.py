import json,sys,urllib.parse,urllib.request

def fetch(symbol,start="2016-01-01",end="2026-08-16",assetclass="stocks"):
    q=urllib.parse.urlencode({"assetclass":assetclass,"fromdate":start,"todate":end,"limit":5000})
    req=urllib.request.Request(f"https://api.nasdaq.com/api/quote/{symbol.upper()}/historical?{q}",headers={"User-Agent":"Mozilla/5.0","Accept":"application/json, text/plain, */*"})
    with urllib.request.urlopen(req,timeout=30) as r:data=json.load(r)
    raw=data["data"]["tradesTable"]["rows"]
    def num(x):return float(x.replace("$","").replace(",",""))
    usable=[x for x in raw if all(x.get(k) not in (None,"","N/A") for k in ("open","high","low","close","volume"))]
    return list(reversed([{"date":x["date"],"open":num(x["open"]),"high":num(x["high"]),"low":num(x["low"]),"close":num(x["close"]),"volume":int(x["volume"].replace(",",""))} for x in usable]))

if __name__=="__main__":json.dump(fetch(sys.argv[1]),sys.stdout)
