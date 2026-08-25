"""Configurable Discord EOD digest using the exact website tracker outputs."""
import argparse,hashlib,json,os,pathlib,tempfile,urllib.request

PUBLIC=pathlib.Path("public")
STATE_PATH=pathlib.Path("work/discord-notification-state.json")
DEFAULT_SITE="https://northstar-equity-signals.rachelzhanzst.chatgpt.site"

def load_local_env():
 path=pathlib.Path(".env.local")
 if not path.exists():return
 for line in path.read_text().splitlines():
  if not line or line.lstrip().startswith("#") or "=" not in line:continue
  key,value=line.split("=",1)
  if key and key not in os.environ:os.environ[key]=value.strip().strip('"').strip("'")

def read_json(path):return json.loads(pathlib.Path(path).read_text())

def validate_inputs(status,tracker,radar):
 dates={status.get("source_latest_complete_date"),status.get("tracker_as_of"),status.get("radar_as_of"),tracker.get("as_of"),radar.get("as_of")}
 if status.get("status")!="up_to_date" or status.get("data_dates_match") is not True or len(dates)!=1 or None in dates:
  raise RuntimeError("Discord blocked: website, tracker and radar dates are not synchronized")
 if status.get("future_data_used") is not False or radar.get("scan",{}).get("future_data_used") is not False:
  raise RuntimeError("Discord blocked: future-data audit failed")
 return tracker["as_of"]

def compact_list(items,score_key="macd_rank_score"):
 return "\n".join(f"`{i+1:02}` **{x['symbol']}**  ${x['price']}  ·  {x.get(score_key,0)}分" for i,x in enumerate(items)) or "本日没有候选"

def rare_embed(signal,site):
 categories=" · ".join(f"{k} {v}" for k,v in signal.get("category_scores",{}).items()) or "暂无分类分"
 evidence="\n".join(f"✓ {x}" for x in signal.get("components",[])) or "暂无"
 risks="；".join(signal.get("risks",[])) or "无额外风险记录"
 return {"title":f"稀有机会 · {signal['symbol']} · {signal.get('total_score',signal['score'])}分","url":f"{site}/zh/watch/resonance/rare-opportunities","color":14197855,"description":f"${signal['price']} · {signal['date']}\n**正式分** {signal.get('official_score',0)}　**观察分** {signal.get('observational_score',signal['score'])}　**风险扣分** −{signal.get('risk_deduction',0)}","fields":[{"name":"分类得分","value":categories,"inline":False},{"name":"命中证据","value":evidence[:1024],"inline":False},{"name":"风险","value":risks[:1024],"inline":False}],"footer":{"text":"研究提醒，不是自动买入"}}

def build_payload(tracker,radar,site=DEFAULT_SITE,minimum_rare_score=5):
 rare=[x for x in radar.get("signals",[]) if x.get("total_score",x.get("score",0))>=minimum_rare_score]
 embeds=[rare_embed(x,site) for x in rare[:8]]
 embeds.append({"title":f"MACD 日榜 · {tracker['as_of']}","url":f"{site}/zh/watch/resonance/macd","color":5263264,"description":"每日完整收盘后的同源榜单；旧信号和失效信号不会重新包装。","fields":[{"name":"看涨榜","value":compact_list(tracker.get("macd_buy_top10",[]))[:1024],"inline":True},{"name":"看跌榜","value":compact_list(tracker.get("macd_sell_top10",[]))[:1024],"inline":True}],"footer":{"text":"研究提醒，不是自动买入"}})
 return {"content":f"**Sage Vista 日终研究播报 · {tracker['as_of']}**","embeds":embeds,"allowed_mentions":{"parse":[]}},rare

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]

def notification_keys(tracker,rare):
 keys=[f"rare:{x['date']}:{x['symbol']}:{digest([x.get('total_score',x['score']),x.get('factor_ids',[])])}" for x in rare]
 keys.append(f"macd:{tracker['as_of']}:{tracker.get('consistency_audit',{}).get('ranking_digest',digest([tracker.get('macd_buy_top10',[]),tracker.get('macd_sell_top10',[])]))}")
 return keys

def post(webhook,payload):
 request=urllib.request.Request(webhook,data=json.dumps(payload,ensure_ascii=False).encode(),headers={"Content-Type":"application/json","User-Agent":"SageVistaResearch/0.2"},method="POST")
 with urllib.request.urlopen(request,timeout=30) as response:
  if response.status not in (200,204):raise RuntimeError(f"Discord returned HTTP {response.status}")

def save_state(path,state):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile("w",dir=path.parent,delete=False) as tmp:json.dump(state,tmp,ensure_ascii=False,indent=2);name=tmp.name
 os.replace(name,path)

def run(preview=False,state_path=STATE_PATH):
 load_local_env();status=read_json(PUBLIC/"update-status.json");tracker=read_json(PUBLIC/"resonance-tracker.json");radar=read_json(PUBLIC/"rare-opportunity-radar.json")
 as_of=validate_inputs(status,tracker,radar);site=os.environ.get("NORTHSTAR_SITE_URL",DEFAULT_SITE).rstrip("/")
 payload,rare=build_payload(tracker,radar,site);keys=notification_keys(tracker,rare)
 state=read_json(state_path) if pathlib.Path(state_path).exists() else {"sent":[]};pending=[key for key in keys if key not in state.get("sent",[])]
 if not pending:return {"result":"duplicate_skipped","as_of":as_of,"keys":keys}
 payload["embeds"]=[embed for key,embed in zip(keys[:-1],payload["embeds"][:-1]) if key in pending]+([payload["embeds"][-1]] if keys[-1] in pending else [])
 if preview:return {"result":"preview","as_of":as_of,"pending":pending,"payload":payload}
 webhook=os.environ.get("DISCORD_WEBHOOK_URL")
 if not webhook:return {"result":"not_configured","as_of":as_of,"pending":pending}
 post(webhook,payload);state["sent"]=(state.get("sent",[])+pending)[-500:];state["last_successful_date"]=as_of;save_state(state_path,state)
 return {"result":"sent","as_of":as_of,"rare":len(rare),"macd_buy":len(tracker.get("macd_buy_top10",[])),"macd_sell":len(tracker.get("macd_sell_top10",[]))}

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--preview",action="store_true");args=parser.parse_args()
 print(json.dumps(run(args.preview),ensure_ascii=False,indent=2))
