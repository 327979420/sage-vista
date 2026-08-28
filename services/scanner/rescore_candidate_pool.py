"""Fast overlays on a saved base candidate pool; never rereads market bars."""
import argparse,json,pathlib


def rescore_day(day,factor_weights):
 rows=[]
 for base in day.get("candidate_pool",[]):
  additions={factor_id:weight for factor_id,weight in factor_weights.items() if factor_id in base.get("hit_factor_ids",[])}
  overlay=sum(additions.values());rows.append({**base,"overlay_points":overlay,"overlay_contributions":additions,"test_priority":base["base_priority"]+overlay})
 rows.sort(key=lambda x:(-x["test_priority"],-x["technical_score"],-x["experimental_score"],x["symbol"]))
 for rank,row in enumerate(rows,1):row["test_rank"]=rank
 return rows


def run(source,out,factor_weights):
 report=json.loads(pathlib.Path(source).read_text());days=[]
 for day in report.get("days",[]):days.append({"date":day["date"],"base_candidate_count":len(day.get("candidate_pool",[])),"ranking":rescore_day(day,factor_weights)})
 result={"source_version":report.get("version"),"coverage":report.get("coverage"),"mode":"candidate_pool_overlay_no_price_recalculation","factor_weights":factor_weights,"days":days}
 pathlib.Path(out).write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n");return result


if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--source",required=True);parser.add_argument("--out",required=True);parser.add_argument("--factor",action="append",default=[]);args=parser.parse_args()
 weights={item.rsplit(":",1)[0]:float(item.rsplit(":",1)[1]) for item in args.factor};result=run(args.source,args.out,weights);print(json.dumps({"coverage":result["coverage"],"factors":weights},ensure_ascii=False))
