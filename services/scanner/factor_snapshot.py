"""Build the deterministic, shadow-only daily canonical factor snapshot."""
import argparse,json,pathlib

from .eodhd import latest_reference_day
from .factor_detectors import MONITORED_FACTOR_IDS,evaluate_all_factors
from .factor_registry import REGISTRY_VERSION
from .factor_scoring import experimental_score
from .macd_factor_backtest import adjusted_rows
from .resonance_tracker import bulk_day
from .support_risk import EXECUTION_POLICY_VERSION,signal_support_plan
from .technical import macd

DEFAULT_OUT="public/daily-factor-snapshot.json"
SNAPSHOT_MODE_VERSION="macd-trigger-first-v1"
TRIGGER_FACTOR_ID="macd.daily_bull_cross"

def exact_daily_macd_bull_cross(rows):
 """Return true only on the completed session where MACD crosses above signal."""
 if len(rows)<2:return False
 line,signal=macd([row["close"] for row in rows])
 return line[-1]>signal[-1] and line[-2]<=signal[-2]

def build_snapshot(symbol_rows,as_of):
 symbols=[];universe_eligible_count=0
 for symbol,rows in sorted(symbol_rows.items()):
  rows=sorted((row for row in rows if row.get("date")<=as_of),key=lambda row:row["date"])
  if not rows or rows[-1]["date"]!=as_of or len(rows)<420:continue
  current=rows[-1]
  if current["close"]<5 or current["close"]*current["volume"]<10_000_000:continue
  universe_eligible_count+=1
  # Evaluate the expensive factor library only after today's exact MACD cross.
  # Recent-cross memory remains evidence and never becomes a repeated trigger.
  if not exact_daily_macd_bull_cross(rows):continue
  states=evaluate_all_factors(rows,as_of)
  serialized=[state.dict() for state in states]
  symbols.append({"symbol":symbol,"price":round(current["close"],4),"dollar_volume":round(current["close"]*current["volume"]),"trigger":{"factor_id":TRIGGER_FACTOR_ID,"date":as_of,"exact_completed_cross":True},"execution_policy_version":EXECUTION_POLICY_VERSION,"support_plan":signal_support_plan(rows),"scoring":experimental_score(serialized),"factors":serialized})
 return {"as_of":as_of,"registry_version":REGISTRY_VERSION,"mode":"macd_trigger_first","snapshot_mode_version":SNAPSHOT_MODE_VERSION,"trigger_policy":{"factor_id":TRIGGER_FACTOR_ID,"event":"exact_completed_daily_bull_cross","remaining_factors_evaluated_after_trigger":True,"remaining_factor_count":len(MONITORED_FACTOR_IDS)-1,"recent_state_does_not_retrigger":True},"execution_policy":{"version":EXECUTION_POLICY_VERSION,"entry":"next_adjusted_open","stop":"highest of signal-time support minus 5% and entry minus 10%","target":"2R","max_hold_sessions":40,"same_bar":"stop_first"},"future_data_used":False,"factor_ids":list(MONITORED_FACTOR_IDS),"universe_eligible_count":universe_eligible_count,"eligible_count":universe_eligible_count,"triggered_count":len(symbols),"symbols":symbols}

def load_symbol_rows(as_of,cache_dir="work/eodhd-cache",active_path="work/eodhd-active-common.json"):
 bulk=bulk_day(as_of,strict=True);bulk_map={row.get("code"):row for row in bulk}
 active_file=pathlib.Path(active_path);active={row["Code"] for row in json.loads(active_file.read_text())} if active_file.exists() else set(bulk_map)
 result={}
 for path in sorted(pathlib.Path(cache_dir).glob("*.json")):
  symbol=path.stem
  if symbol not in active or symbol not in bulk_map:continue
  raw=json.loads(path.read_text());today=bulk_map[symbol]
  if today.get("adjusted_close") and today.get("close") and today.get("open") and today.get("volume") is not None:
   if not any(row.get("date")==as_of for row in raw):
    raw.append(today);raw.sort(key=lambda row:row["date"]);path.write_text(json.dumps(raw))
  result[symbol]=adjusted_rows(raw)
 return result

def run(out=DEFAULT_OUT,as_of=None):
 authoritative=as_of or latest_reference_day();report=build_snapshot(load_symbol_rows(authoritative),authoritative)
 # The full-universe snapshot must remain below Cloudflare Workers' 25 MiB
 # per-asset limit. Whitespace is not part of the contract; stable key ordering
 # preserves byte determinism while compact separators avoid deployment bloat.
 if out:pathlib.Path(out).write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n")
 return report

def state_map(snapshot):
 return {row["symbol"]:{state["factor_id"]:state for state in row["factors"]} for row in snapshot.get("symbols",[])}

if __name__=="__main__":
 parser=argparse.ArgumentParser();parser.add_argument("--as-of");parser.add_argument("--out",default=DEFAULT_OUT)
 args=parser.parse_args();print(json.dumps(run(args.out,args.as_of),ensure_ascii=False,indent=2))
