from __future__ import annotations
from dataclasses import dataclass, asdict
from math import floor
from statistics import mean

def sma(v,n): return [None if i<n-1 else mean(v[i-n+1:i+1]) for i in range(len(v))]
def ema(v,n):
    out=[]; e=None; k=2/(n+1)
    for x in v:
        e=x if e is None else x*k+e*(1-k); out.append(e)
    return out
def rsi(v,n=14):
    out=[None]*len(v); gains=[]; losses=[]
    for i in range(1,len(v)):
        d=v[i]-v[i-1]; gains.append(max(d,0)); losses.append(max(-d,0))
        if i==n: ag,al=mean(gains[-n:]),mean(losses[-n:])
        elif i>n: ag=(ag*(n-1)+gains[-1])/n; al=(al*(n-1)+losses[-1])/n
        else: continue
        out[i]=100 if al==0 else 100-100/(1+ag/al)
    return out
def atr(rows,n=14):
    tr=[]
    for i,x in enumerate(rows): tr.append(x["high"]-x["low"] if i==0 else max(x["high"]-x["low"],abs(x["high"]-rows[i-1]["close"]),abs(x["low"]-rows[i-1]["close"])))
    return ema(tr,n)
def macd(v):
    a,b=ema(v,12),ema(v,26); line=[x-y for x,y in zip(a,b)]; sig=ema(line,9); return line,sig
def position_size(equity,risk_pct,entry,stop,max_position_pct=.20):
    if equity<=0 or not 0<risk_pct<=.02 or stop>=entry: return 0
    risk_shares=floor(equity*risk_pct/(entry-stop)); cap_shares=floor(equity*max_position_pct/entry)
    return max(0,min(risk_shares,cap_shares))

@dataclass
class Plan:
    signal_index:int; entry:float; stop:float; target:float; reward_risk:float; expected_bars:str; shares:int; reasons:list[str]; warnings:list[str]
    def dict(self): return asdict(self)

def _swing_lows(rows,end,window=45):
    pts=[]
    for i in range(max(2,end-window),end-1):
        if rows[i]["low"]<rows[i-1]["low"] and rows[i]["low"]<=rows[i+1]["low"]: pts.append(i)
    return pts

def evaluate(rows,i,equity=100000,risk_pct=.0075,min_rr=1.5):
    """Evaluate using data through bar i only; execution is next bar open."""
    if i<220 or i>=len(rows)-1:return None
    close=[x["close"] for x in rows]; vol=[x["volume"] for x in rows]
    e20,e50,e200=ema(close,20),ema(close,50),ema(close,200); rs=rsi(close); at=atr(rows); ml,ms=macd(close); av=sma(vol,20)
    # Higher-timeframe proxy: strong 200D structure plus rising 50D; never overridden by lower timeframe.
    higher=close[i]>e200[i] and e50[i]>e50[i-20] and close[i]>e50[i]*.94
    if not higher:return None
    lows=_swing_lows(rows,i); support=[]
    if abs(close[i]-e50[i])<=at[i]*1.25:support.append("price at rising EMA50 demand")
    if abs(close[i]-e200[i])<=at[i]:support.append("price at EMA200 structural support")
    hi=max(x["high"] for x in rows[i-63:i+1]); lo=min(x["low"] for x in rows[i-63:i+1]); retr=(hi-close[i])/(hi-lo) if hi>lo else 0
    if .47<=retr<=.65:support.append("pullback in 50–61.8% retracement zone")
    if not support:return None
    confirms=[]
    if ml[i]>ms[i] and ml[i-1]<=ms[i-1]:confirms.append("MACD bullish cross")
    if close[i]>rows[i-1]["open"] and rows[i]["open"]<close[i-1] and close[i]>=rows[i-1]["open"]:confirms.append("bullish engulfing candle")
    body=max(abs(close[i]-rows[i]["open"]),.01); wick=min(rows[i]["open"],close[i])-rows[i]["low"]
    if wick>body*1.5 and av[i] and vol[i]>av[i]*1.2:confirms.append("high-volume liquidity rejection")
    if len(lows)>=2:
        a,b=lows[-2],lows[-1]
        if 5<=b-a<=35 and abs(rows[a]["low"]-rows[b]["low"])/rows[a]["low"]<=.035:
            neckline=max(x["high"] for x in rows[a:b+1])
            if close[i]>neckline:confirms.append("double-bottom neckline break")
        if rows[b]["low"]<rows[a]["low"] and rs[b] and rs[a] and rs[b]>rs[a]+2:confirms.append("bullish RSI price divergence")
    if len(set(confirms))<2:return None
    entry=rows[i+1]["open"]; recent=min(x["low"] for x in rows[max(0,i-12):i+1]); stop=min(recent-at[i]*.15,min(e50[i],close[i])-at[i]*.65)
    risk=entry-stop
    if risk<=0 or risk/entry>.12:return None
    resistance=sorted({x["high"] for x in rows[max(0,i-126):i+1] if x["high"]>entry+min_rr*risk})
    measured=entry+2*risk; target=min(resistance[0],measured) if resistance else measured
    rr=(target-entry)/risk
    if rr<min_rr:return None
    return Plan(i,round(entry,2),round(stop,2),round(target,2),round(rr,2),"5–20 daily bars; exit at bar 10 if <0.5R progress",position_size(equity,risk_pct,entry,stop),support+list(dict.fromkeys(confirms)),["Options wall unavailable: target uses prior supply/resistance and 2R measured move","Daily-bar research model; 4-hour confirmation deferred"])

def backtest(rows,equity=100000,risk_pct=.0075):
    trades=[]; i=220
    while i<len(rows)-12:
        p=evaluate(rows,i,equity,risk_pct)
        if not p:i+=1;continue
        risk=p.entry-p.stop; exit_price=rows[min(i+10,len(rows)-1)]["close"]; reason="10-bar time stop"
        max_r=0;min_r=0
        for j in range(i+1,min(i+21,len(rows))):
            # Conservative same-bar assumption: stop is evaluated before target.
            if rows[j]["low"]<=p.stop:exit_price=p.stop;reason="structure stop";break
            if rows[j]["high"]>=p.target:exit_price=p.target;reason="target";break
            max_r=max(max_r,(rows[j]["high"]-p.entry)/risk);min_r=min(min_r,(rows[j]["low"]-p.entry)/risk)
            if j==i+10 and max_r<.5:exit_price=rows[j]["close"];reason="10-bar no-expansion exit";break
            if j==min(i+20,len(rows)-1):exit_price=rows[j]["close"];reason="20-bar maximum hold"
        r=(exit_price-p.entry)/risk;scenarios={}
        for horizon in (5,10,15,20):
            fixed=rows[min(i+horizon,len(rows)-1)]["close"]
            for k in range(i+1,min(i+horizon+1,len(rows))):
                if rows[k]["low"]<=p.stop:fixed=p.stop;break
            scenarios[str(horizon)]=round((fixed-p.entry)/risk,3)
        gap_bps=(p.entry-rows[i]["close"])/rows[i]["close"]*10000
        trades.append({"date":rows[i+1]["date"],"exit_date":rows[j]["date"],"entry":p.entry,"stop":p.stop,"target":p.target,"exit":round(exit_price,2),"r":round(r,3),"reason":reason,"bars":j-i,"entry_gap_bps":round(gap_bps,1),"mfe_r":round(max_r,3),"mae_r":round(min_r,3),"missed_profit_r":round(max(0,max_r-r),3),"fixed_horizon_r":scenarios,"reasons":p.reasons}); i=j+1
    wins=[t for t in trades if t["r"]>0]; total=sum(t["r"] for t in trades); peak=curve=dd=0
    for t in trades:curve+=t["r"];peak=max(peak,curve);dd=max(dd,peak-curve)
    return {"trades":trades,"summary":{"count":len(trades),"win_rate":round(len(wins)/len(trades)*100,1) if trades else 0,"total_r":round(total,2),"avg_r":round(total/len(trades),2) if trades else 0,"max_drawdown_r":round(dd,2)}}

def trade_efficiency(trades):
    if not trades:return {"count":0,"average_holding_bars":0,"average_entry_gap_bps":0,"average_missed_profit_r":0,"mfe_capture_pct":0,"exit_scenarios":{}}
    winners=[t for t in trades if t["r"]>0 and t["mfe_r"]>0]
    scenarios={h:round(sum(t["fixed_horizon_r"][h] for t in trades)/len(trades),3) for h in ("5","10","15","20")}
    capture=sum(min(1,t["r"]/t["mfe_r"]) for t in winners)/len(winners)*100 if winners else 0
    return {"count":len(trades),"average_realized_r":round(sum(t["r"] for t in trades)/len(trades),3),"average_holding_bars":round(sum(t["bars"] for t in trades)/len(trades),1),"average_entry_gap_bps":round(sum(t["entry_gap_bps"] for t in trades)/len(trades),1),"average_missed_profit_r":round(sum(t["missed_profit_r"] for t in trades)/len(trades),3),"mfe_capture_pct":round(capture,1),"exit_scenarios":scenarios}
