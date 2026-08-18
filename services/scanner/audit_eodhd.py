import json,pathlib
from collections import Counter
from datetime import datetime,timezone
from .eodhd import actions,prices,symbols

PRIMARY={"NASDAQ","NYSE","AMEX","NYSE MKT","NYSE ARCA"}
def common(rows):return [x for x in rows if x.get("Type")=="Common Stock" and x.get("Exchange") in PRIMARY]
def history_check(code):
    rows=prices(code,"1980-01-01");dates=[x.get("date") for x in rows]
    return {"symbol":code,"rows":len(rows),"first":dates[0] if dates else None,"last":dates[-1] if dates else None,"sorted":dates==sorted(dates),"duplicate_dates":len(dates)-len(set(dates)),"missing_adjusted_close":sum(x.get("adjusted_close") is None for x in rows),"nonpositive_ohlc":sum(any((x.get(k) or 0)<=0 for k in ("open","high","low","close")) for x in rows)}
def run(out="public/data-audit.json"):
    active_raw,delisted_raw=symbols(False),symbols(True);active,delisted=common(active_raw),common(delisted_raw)
    active_codes={x["Code"] for x in active};delisted_codes={x["Code"] for x in delisted}
    preferred=["AAPL","MSFT","GE","TSLA","AABA","TWTR","AAAP_old"]
    available=active_codes|delisted_codes;samples=[x for x in preferred if x in available]
    checks=[history_check(x) for x in samples]
    report={"generated_at":datetime.now(timezone.utc).isoformat(),"provider":"EODHD All World","status":"passed_initial_audit" if checks and all(x["sorted"] and not x["duplicate_dates"] and not x["missing_adjusted_close"] for x in checks) else "review_required","universe":{"raw_active_records":len(active_raw),"raw_delisted_records":len(delisted_raw),"primary_exchange_common_active":len(active),"primary_exchange_common_delisted":len(delisted),"active_by_exchange":Counter(x["Exchange"] for x in active),"delisted_by_exchange":Counter(x["Exchange"] for x in delisted),"symbol_collisions":len(active_codes&delisted_codes)},"history_checks":checks,"corporate_actions":{"AAPL_splits":len(actions("splits","AAPL","1980-01-01")),"AAPL_dividends":len(actions("div","AAPL","1980-01-01")),"TSLA_splits":len(actions("splits","TSLA","2010-01-01"))},"decision":"Use EODHD for the next survivorship-aware price-factor experiment. Preserve listing status and never merge recycled symbols solely by ticker.","limitations":["All World provides price and corporate-action data, not the full fundamentals package","Historical bid-ask quotes are not part of this EOD audit","Historical sector membership still requires a separate dataset or reconstruction","Raw symbol lists include foreign and OTC securities; primary-exchange common-stock filtering is mandatory"]}
    pathlib.Path(out).write_text(json.dumps(report,indent=2,default=dict));return report
if __name__=="__main__":print(json.dumps(run(),indent=2,default=dict))
