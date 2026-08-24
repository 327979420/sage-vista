"""Reusable, versioned multi-timeframe confluence rules.

Large completed candles confirm direction; the daily candle confirms timing.
The same directional contract is used by every indicator layer.
"""

RULESET={
 "version":"2.0.0",
 "timeframes":{"direction":["上个完整月线","上个完整周线"],"timing":"最新完整日线"},
 "layer_max":25,
 "weights":{"daily_trigger":10,"weekly_direction":8,"monthly_direction":7},
 "policy":"大周期确认方向，小周期确认时机；允许小周期先启动，但月线不得反向、周线必须同向改善。",
}

def _result(direction="neutral",score=0,stage="等待",evidence=None):
 return {"direction":direction,"score":score,"stage":stage,"evidence":evidence or []}

def macd_layer(frames):
 d,w,m=(frames[x] for x in ("日线","周线","月线"))
 buy_trigger=d["bars_since_cross"] is not None and d["bars_since_cross"]<=3 and d["cross_zero_zone"]=="零轴下" and d["macd_line"]>d["signal_line"]
 sell_trigger=d["bars_since_dead_cross"] is not None and d["bars_since_dead_cross"]<=3 and d["dead_cross_zero_zone"]=="零轴上" and d["zero_zone"]=="零轴上" and d["macd_line"]<d["signal_line"]
 bull=lambda x:x["macd_line"]>x["signal_line"]
 bear=lambda x:x["macd_line"]<x["signal_line"]
 improve=lambda x:x["histogram_rising"] or x["near_cross"]
 weaken=lambda x:x["histogram_falling"] and x["zero_zone"]=="零轴上"
 if buy_trigger and bull(w) and bull(m):return _result("buy",25,"大周期→小周期",["完整月线多头","完整周线多头","日线零轴下新金叉"])
 if sell_trigger and bear(w) and bear(m):return _result("sell",25,"大周期→小周期",["完整月线空头","完整周线空头","日线零轴上新死叉"])
 if buy_trigger and improve(w) and not bear(m):return _result("buy",18,"小周期→大周期",["日线零轴下新金叉","完整周线动能改善","完整月线未反向"])
 if sell_trigger and weaken(w) and not bull(m):return _result("sell",18,"小周期→大周期",["日线零轴上新死叉","完整周线动能转弱","完整月线未反向"])
 return _result(evidence=["缺少日线有效触发，或完整周/月方向未确认"])

def rsi_layer(frames):
 d,w,m=(frames[x] for x in ("日线","周线","月线"))
 buy_trigger=d["rsi"] in ("底背离","超卖修复")
 sell_trigger=d["rsi"] in ("顶背离","超买回落")
 bull=lambda x:x["rsi_value"] is not None and x["rsi_value"]>=50
 bear=lambda x:x["rsi_value"] is not None and x["rsi_value"]<50
 if buy_trigger and bull(w) and bull(m):return _result("buy",25,"大周期→小周期",["完整周/月RSI不低于50",f"日线{x_label(d)}"])
 if sell_trigger and bear(w) and bear(m):return _result("sell",25,"大周期→小周期",["完整周/月RSI低于50",f"日线{x_label(d)}"])
 if buy_trigger and (w["rsi"] in ("底背离","超卖修复") or bull(w)) and not bear(m):return _result("buy",18,"小周期→大周期",[f"日线{x_label(d)}","周线同向改善","月线未反向"])
 if sell_trigger and (w["rsi"] in ("顶背离","超买回落") or bear(w)) and not bull(m):return _result("sell",18,"小周期→大周期",[f"日线{x_label(d)}","周线同向转弱","月线未反向"])
 return _result(evidence=["超卖本身不是买点、超买本身不是卖点；等待日线反转触发与大周期确认"])

def x_label(frame):return frame["rsi"]

def ema_layer(states):
 d,w,m=(states[x] for x in ("日线","周线","月线"))
 buy_trigger=d["trigger"]=="buy";sell_trigger=d["trigger"]=="sell"
 if buy_trigger and w["direction"]==m["direction"]=="buy":return _result("buy",25,"大周期→小周期",["完整周/月EMA多头","日线EMA上穿或重新站上"])
 if sell_trigger and w["direction"]==m["direction"]=="sell":return _result("sell",25,"大周期→小周期",["完整周/月EMA空头","日线EMA下穿或跌破"])
 if buy_trigger and w["improving"]=="buy" and m["direction"]!="sell":return _result("buy",18,"小周期→大周期",["日线向上触发","周线改善","月线未反向"])
 if sell_trigger and w["improving"]=="sell" and m["direction"]!="buy":return _result("sell",18,"小周期→大周期",["日线向下触发","周线转弱","月线未反向"])
 return _result(evidence=["EMA大周期方向与日线时机尚未同时成立"])

def breakout_layer(daily_breakout,ema_states):
 direction=daily_breakout["direction"]
 if direction not in ("buy","sell"):return _result(evidence=["日线尚未收盘突破20日区间"])
 w,m=ema_states["周线"],ema_states["月线"]
 if w["direction"]==m["direction"]==direction:return _result(direction,25,"大周期→小周期",[daily_breakout["label"],"完整周/月趋势同向"])
 if w["improving"]==direction and m["direction"]!=opposite(direction):return _result(direction,18,"小周期→大周期",[daily_breakout["label"],"完整周线同向改善","月线未反向"])
 return _result(evidence=[daily_breakout["label"],"突破与完整周/月趋势未对齐"])

def opposite(direction):return "sell" if direction=="buy" else "buy"

def combine(layers):
 active=[x["direction"] for x in layers.values() if x["direction"]!="neutral"]
 buy=active.count("buy");sell=active.count("sell");conflict=bool(buy and sell)
 direction="conflict" if conflict else "buy" if buy else "sell" if sell else "neutral"
 aligned=max(buy,sell);score=sum(x["score"] for x in layers.values() if x["direction"]==direction) if direction in ("buy","sell") else 0
 strict=aligned==len(layers) and not conflict
 label=("四重看涨共振" if direction=="buy" else "四重看跌共振") if strict else "指标冲突" if conflict else f"{aligned}层同向观察" if aligned else "等待触发"
 return {"direction":direction,"aligned":aligned,"score":score,"strict":strict,"label":label}
