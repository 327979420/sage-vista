"""Reusable, versioned multi-timeframe confluence rules.

Large completed candles confirm direction; the daily candle confirms timing.
The same directional contract is used by every indicator layer.
"""

RULESET={
 "version":"2.1.0",
 "timeframes":{"direction":["上个完整月线","上个完整周线"],"timing":"最新完整日线"},
 "layer_max":25,
 "weights":{"daily_trigger":10,"weekly_direction":8,"monthly_direction":7},
 "policy":"MACD允许小周期先启动并带动大周期，也允许大周期先确认、小周期给时机；看涨偏重零轴下金叉，看跌偏重零轴上死叉。",
}

def _result(direction="neutral",score=0,stage="等待",evidence=None,**extra):
 return {"direction":direction,"score":score,"stage":stage,"evidence":evidence or [],**extra}

def macd_layer(frames):
 d,w,m=(frames[x] for x in ("日线","周线","月线"))
 fresh_buy=lambda x:x["bars_since_cross"] is not None and x["bars_since_cross"]<=3 and x["macd_line"]>x["signal_line"]
 fresh_sell=lambda x:x["bars_since_dead_cross"] is not None and x["bars_since_dead_cross"]<=3 and x["dead_cross_zero_zone"]=="零轴上" and x["zero_zone"]=="零轴上"
 d_buy=35 if fresh_buy(d) and d["cross_zero_zone"]=="零轴下" else 25 if fresh_buy(d) and d["cross_zero_zone"]=="穿越零轴" else 18 if fresh_buy(d) else 16 if d["zero_zone"]=="零轴下" and (d["near_cross"] or d["negative_histogram_shrinking"]) else 0
 w_buy=25 if fresh_buy(w) and w["cross_zero_zone"]=="零轴下" else 20 if w["macd_line"]>w["signal_line"] and w["zero_zone"]=="零轴下" else 16 if w["zero_zone"]=="零轴下" and (w["near_cross"] or w["negative_histogram_shrinking"]) else 12 if w["macd_line"]>w["signal_line"] else 0
 m_buy=20 if m["zero_zone"]=="零轴下" and (m["near_cross"] or m["negative_histogram_shrinking"]) else 18 if m["macd_line"]>m["signal_line"] and m["zero_zone"]=="零轴下" else 12 if m["macd_line"]>m["signal_line"] else 10 if m["zero_zone"]=="零轴下" and m["histogram_rising"] else 0
 buy_rank=d_buy+w_buy+m_buy+(10 if d_buy and w_buy and m_buy else 0)
 d_sell=35 if fresh_sell(d) else 18 if d["zero_zone"]=="零轴上" and d["histogram_falling"] and d["macd_line"]<d["signal_line"] else 0
 w_sell=25 if fresh_sell(w) else 18 if w["zero_zone"]=="零轴上" and w["histogram_falling"] else 12 if w["zero_zone"]=="零轴上" and w["macd_line"]<w["signal_line"] else 0
 m_sell=20 if m["zero_zone"]=="零轴上" and m["histogram_falling"] else 12 if m["zero_zone"]=="零轴上" and m["macd_line"]<m["signal_line"] else 0
 sell_rank=d_sell+w_sell+m_sell+(10 if d_sell and w_sell and m_sell else 0)
 if buy_rank>=44 and d_buy>=16:
  stage="小周期→大周期" if (w["zero_zone"]=="零轴下" and w["macd_line"]<=w["signal_line"]) or (m["zero_zone"]=="零轴下" and m["macd_line"]<=m["signal_line"]) else "大周期→小周期"
  return _result("buy",min(25,round(buy_rank/4)),stage,[f"日线触发 {d_buy}分",f"周线确认 {w_buy}分",f"月线环境 {m_buy}分"],rank_score=buy_rank)
 if sell_rank>=44 and d_sell>=18:return _result("sell",min(25,round(sell_rank/4)),"大周期→小周期",[f"日线触发 {d_sell}分",f"周线确认 {w_sell}分",f"月线环境 {m_sell}分"],rank_score=sell_rank)
 return _result(evidence=["尚未达到MACD方向＋时机最低门槛"],rank_score=max(buy_rank,sell_rank))

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
