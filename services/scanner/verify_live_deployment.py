"""Fail-closed verification for the public Cloudflare production deployment."""
import argparse,json,urllib.parse,urllib.request

def fetch(base,path,cache_key):
 url=f"{base.rstrip('/')}/{path}?deployment={urllib.parse.quote(cache_key)}"
 request=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"SageVistaDeploymentAudit/1.0"})
 with urllib.request.urlopen(request,timeout=30) as response:
  if response.status!=200:raise RuntimeError(f"Live {path} returned HTTP {response.status}")
  return json.load(response)

def verify(base,expected):
 status=fetch(base,"update-status.json",expected);tracker=fetch(base,"resonance-tracker.json",expected);radar=fetch(base,"rare-opportunity-radar.json",expected)
 dates={status.get("source_latest_complete_date"),status.get("tracker_as_of"),status.get("radar_as_of"),tracker.get("as_of"),radar.get("as_of")}
 if dates!={expected}:raise RuntimeError(f"Live deployment date mismatch: {sorted(str(x) for x in dates)}")
 if status.get("status")!="up_to_date" or status.get("data_dates_match") is not True:raise RuntimeError("Live status integrity check failed")
 if status.get("future_data_used") is not False or radar.get("scan",{}).get("future_data_used") is not False:raise RuntimeError("Live future-data audit failed")
 details=tracker.get("details",{})
 if any(x.get("audit",{}).get("future_rows_used") or x.get("audit",{}).get("latest_bar")!=expected for x in details.values()):raise RuntimeError("Live tracker completeness audit failed")
 return {"result":"verified","as_of":expected,"site_url":base,"tracker_details":len(details)}

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--url",required=True);parser.add_argument("--expected-as-of",required=True)
 args=parser.parse_args();print(json.dumps(verify(args.url,args.expected_as_of),ensure_ascii=False,indent=2))
