"""Fail-closed verification that the live site serves the expected audited EOD data."""
import argparse,json,urllib.request

def verify(site,expected):
 url=f"{site.rstrip('/')}/update-status.json"
 request=urllib.request.Request(url,headers={"Cache-Control":"no-cache","User-Agent":"SageVistaDeploymentAudit/1.0"})
 with urllib.request.urlopen(request,timeout=30) as response:status=json.load(response)
 dates={status.get("source_latest_complete_date"),status.get("tracker_as_of"),status.get("radar_as_of")}
 if status.get("status")!="up_to_date" or status.get("data_dates_match") is not True or dates!={expected}:raise RuntimeError("Live site is not synchronized to the expected completed EOD date")
 if status.get("future_data_used") is not False:raise RuntimeError("Live site future-data audit failed")
 return {"result":"verified","as_of":expected}

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--site",required=True);parser.add_argument("--expected",required=True);args=parser.parse_args()
 print(json.dumps(verify(args.site,args.expected)))
