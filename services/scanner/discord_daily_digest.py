"""Send a deduplicated Discord digest from already-verified website outputs.

This module never recalculates rankings. It reads the same published JSON as
the website and persists notification state only after a successful send.
"""
import argparse,json,os,pathlib,tempfile,urllib.request

PUBLIC=pathlib.Path("public")
STATE_PATH=pathlib.Path("automation/discord-state.json")
DEFAULT_SITE="https://sage-vista-parallel.gizmo-allied-0s.workers.dev"

def load_local_env():
 path=pathlib.Path(".env.local")
 if not path.exists():return
 for line in path.read_text().splitlines():
  if not line or line.lstrip().startswith("#") or "=" not in line:continue
  key,value=line.split("=",1)
  if key and key not in os.environ:os.environ[key]=value.strip().strip('"').strip("'")

def read_json(path):return json.loads(pathlib.Path(path).read_text())

def _v2_day(unified,day):return next((x for x in unified.get("days",[]) if x.get("date")==day),None) if unified else None

def _v2_rare(unified,day):
 current=_v2_day(unified,day)
 if not current:return []
 return current.get("rare_opportunities") or [x for x in current.get("ranking",[])[:5] if x.get("final_priority",0)>=9]

def validate_inputs(status,favorite,radar,unified):
 dates={status.get("source_latest_complete_date"),status.get("favorite_pattern_as_of"),status.get("radar_as_of"),favorite.get("as_of"),radar.get("as_of")}
 if status.get("status")!="up_to_date" or status.get("data_dates_match") is not True or len(dates)!=1 or None in dates:
  raise RuntimeError("Discord blocked: website outputs are not synchronized")
 if status.get("future_data_used") is not False or favorite.get("gate",{}).get("future_data_used") is not False or radar.get("scan",{}).get("future_data_used") is not False:
  raise RuntimeError("Discord blocked: future-data audit failed")
 if unified.get("future_data_used") is not False or _v2_day(unified,favorite["as_of"]) is None:
  raise RuntimeError("Discord blocked: Unified V2 is missing or stale")
 return favorite["as_of"]

def ranking_list(items):
 return "\n".join(f"{i+1}. {x['symbol']}" for i,x in enumerate(items[:10])) or "No candidates"

def collect_alerts(favorite,unified):
 """Notify only the current compact multi-factor product, never the retired Tracker."""
 alerts={}
 for signal in _v2_rare(unified,favorite["as_of"]):
  alerts[signal["symbol"]]={"symbol":signal["symbol"],"status":"confirmed","date":favorite["as_of"],"price":signal["price"],"score":signal["final_priority"],"evidence":signal.get("reasons",[]),"risks":["多因子研究精选；完整盈亏验证前不等于买入信号"],"url_path":"/zh/watch/resonance/rare-opportunities"}
 return sorted(alerts.values(),key=lambda x:(x["status"]=="confirmed",x["score"],x["symbol"]),reverse=True)

def alert_embed(alert,site):
 confirmed=alert["status"]=="confirmed";label="Confirmed" if confirmed else "Early Watch"
 evidence="\n".join(f"✓ {x}" for x in alert["evidence"]) or "暂无";risks="；".join(alert["risks"]) or "无额外风险记录"
 return {"title":f"{label} · {alert['symbol']}","url":f"{site}{alert.get('url_path','/zh/watch/resonance/rare-opportunities')}","color":5763719 if confirmed else 14197855,"description":f"${alert['price']} · {alert['date']} · 规则分 {alert['score']}","fields":[{"name":"为什么进入这一状态","value":evidence[:1024],"inline":False},{"name":"风险","value":risks[:1024],"inline":False}],"footer":{"text":"研究提醒，不是自动买入"}}

def build_payload(favorite,unified,site=DEFAULT_SITE):
 alerts=collect_alerts(favorite,unified)[:8]
 embeds=[alert_embed(x,site) for x in alerts]
 day=_v2_day(unified,favorite["as_of"]);multi=day.get("ranking",[])[:10] if day else []
 embeds.append({"title":f"Multi-Factor Ranking — {favorite['as_of']}","color":5263264,"description":ranking_list(multi)})
 return {"embeds":embeds,"allowed_mentions":{"parse":[]}},alerts

def notification_keys(favorite,alerts):
 keys=[f"status:{x['symbol']}:{x['status']}" for x in alerts]
 keys.append(f"ranking:multi-factor:{favorite['as_of']}")
 return keys

def pending_plan(alerts,keys,state):
 state.setdefault("sent",[]);state.setdefault("symbol_status",{});indices=[]
 for index,alert in enumerate(alerts):
  previous=state["symbol_status"].get(alert["symbol"])
  if alert["status"]=="early_watch" and previous in ("early_watch","confirmed"):continue
  if alert["status"]=="confirmed" and previous=="confirmed":continue
  indices.append(index)
 return indices,[key not in state["sent"] for key in keys[len(alerts):]]

def post(webhook,payload):
 request=urllib.request.Request(webhook,data=json.dumps(payload,ensure_ascii=False).encode(),headers={"Content-Type":"application/json","User-Agent":"SageVistaResearch/0.2"},method="POST")
 with urllib.request.urlopen(request,timeout=30) as response:
  if response.status not in (200,204):raise RuntimeError(f"Discord returned HTTP {response.status}")

def save_state(path,state):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile("w",dir=path.parent,delete=False) as tmp:json.dump(state,tmp,ensure_ascii=False,indent=2);name=tmp.name
 os.replace(name,path)

def run(preview=False,state_path=STATE_PATH):
 load_local_env();status=read_json(PUBLIC/"update-status.json");favorite=read_json(PUBLIC/"favorite-pattern.json");radar=read_json(PUBLIC/"rare-opportunity-radar.json");unified=read_json(PUBLIC/"unified-v2-latest.json")
 as_of=validate_inputs(status,favorite,radar,unified);site=os.environ.get("SAGE_VISTA_SITE_URL",DEFAULT_SITE).rstrip("/")
 payload,alerts=build_payload(favorite,unified,site);keys=notification_keys(favorite,alerts)
 state=read_json(state_path) if pathlib.Path(state_path).exists() else {"sent":[],"symbol_status":{}}
 pending_alerts,ranking_pending=pending_plan(alerts,keys,state);ranking_keys=keys[len(alerts):]
 pending=[keys[i] for i in pending_alerts]+[key for key,is_pending in zip(ranking_keys,ranking_pending) if is_pending]
 if not pending:return {"result":"duplicate_skipped","as_of":as_of,"keys":keys}
 ranking_embeds=payload["embeds"][len(alerts):]
 payload["embeds"]=[payload["embeds"][i] for i in pending_alerts]+[embed for embed,is_pending in zip(ranking_embeds,ranking_pending) if is_pending]
 if preview:return {"result":"preview","as_of":as_of,"pending":pending,"payload":payload}
 webhook=os.environ.get("DISCORD_WEBHOOK_URL")
 if not webhook:return {"result":"not_configured","as_of":as_of,"pending":pending}
 post(webhook,payload)
 for i in pending_alerts:state["symbol_status"][alerts[i]["symbol"]]=alerts[i]["status"]
 state["sent"]=(state["sent"]+pending)[-500:];state["last_successful_date"]=as_of;save_state(state_path,state)
 return {"result":"sent","as_of":as_of,"alerts":len(pending_alerts),"rankings":sum(ranking_pending)}

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--preview",action="store_true");parser.add_argument("--state-path",default=str(STATE_PATH));args=parser.parse_args()
 print(json.dumps(run(args.preview,args.state_path),ensure_ascii=False,indent=2))
