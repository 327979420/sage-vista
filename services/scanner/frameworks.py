from __future__ import annotations
from .detectors import Detection,load_config,result,pivots,relative_volume,detect_bos
from .technical import atr,ema,sma

def weinstein_stage(rows,i,cfg=None,timeframe="weekly"):
 cfg=cfg or load_config();close=[x["close"] for x in rows];ma=ema(close,30);a=atr(rows);n=cfg["trend"]["weinstein_slope_lookback"]
 if i<30+n:return result(False,rows,i,timeframe,explanation="Insufficient weekly history")
 slope=(ma[i]-ma[i-n])/max(a[i],1e-9);above=close[i]>ma[i];flat=abs(slope)<=cfg["trend"]["flat_slope_atr"]
 stage="stage_1" if flat and not above else "stage_2" if above and slope>0 else "stage_3" if flat and above else "stage_4"
 return result(True,rows,i,timeframe,levels={"ma30":round(ma[i],3)},measurements={"ma30_slope_atr":round(slope,3),"price_above_ma30":above},confidence=min(1,.6+abs(slope)/2),explanation=f"Weinstein classification: {stage.replace('_',' ').title()}",data_used={"first_index":i-30-n,"last_index":i},classification=stage)

def minervini_template(rows,i,relative_strength=None,cfg=None,timeframe="daily"):
 cfg=cfg or load_config();close=[x["close"] for x in rows];m50,m150,m200=sma(close,50),sma(close,150),sma(close,200);n=cfg["trend"]["rising_200_lookback"]
 if i<252 or m200[i-n] is None:return result(False,rows,i,timeframe,explanation="Insufficient history for trend template")
 high=max(close[i-251:i+1]);low=min(close[i-251:i+1]);checks={"price_above_150_200":close[i]>m150[i] and close[i]>m200[i],"ma150_above_200":m150[i]>m200[i],"ma200_rising":m200[i]>m200[i-n],"ma50_above_150_200":m50[i]>m150[i] and m50[i]>m200[i],"price_above_50":close[i]>m50[i],"above_52w_low":close[i]>low*(1+cfg["trend"]["minervini_low_distance"]),"near_52w_high":close[i]>=high*(1-cfg["trend"]["minervini_high_distance"]),"relative_strength_available":relative_strength is not None,"relative_strength_positive":relative_strength is not None and relative_strength>0}
 core=all(v for k,v in checks.items() if not k.startswith("relative_strength"));return result(core,rows,i,timeframe,levels={"ma50":m50[i],"ma150":m150[i],"ma200":m200[i],"high_52w":high,"low_52w":low},measurements=checks,confidence=sum(bool(x) for x in checks.values())/len(checks),explanation="Minervini trend template passed" if core else "One or more Minervini trend-quality conditions failed",data_used={"first_index":i-251,"last_index":i},classification="pass" if core else "fail")

def dow_structure(rows,i,cfg=None,timeframe="weekly"):
 p=pivots(rows,i,cfg,timeframe);hs=p["highs"][-2:];ls=p["lows"][-2:]
 if len(hs)<2 or len(ls)<2:return result(False,rows,i,timeframe,confirmation_delay=(cfg or load_config())["pivot"]["right_bars"],explanation="Insufficient confirmed structural swings")
 hh=hs[1]["price"]>hs[0]["price"];hl=ls[1]["price"]>ls[0]["price"];kind="primary_uptrend" if hh and hl else "primary_downtrend" if not hh and not hl else "transition"
 return result(hh and hl,rows,i,timeframe,levels={"prior_high":hs[0]["price"],"latest_high":hs[1]["price"],"prior_low":ls[0]["price"],"latest_low":ls[1]["price"]},measurements={"higher_high":hh,"higher_low":hl},confidence=.85 if hh==hl else .45,explanation=f"Dow structure classified as {kind.replace('_',' ')}",data_used={"first_index":min(hs[0]["index"],ls[0]["index"]),"last_index":max(hs[1]["confirmed_index"],ls[1]["confirmed_index"])},confirmation_delay=p["confirmation_delay"],classification=kind)

def wyckoff_events(rows,i,support,resistance,cfg=None,timeframe="daily"):
 cfg=cfg or load_config();a=atr(rows);b=rows[i];rv=relative_volume(rows,i,cfg,timeframe);spring=b["low"]<support and b["close"]>support;bos=detect_bos(rows,i,resistance,cfg,timeframe);sos=bos.detected and (rv.classification in ("strong","exceptional"));lps=b["low"]<=resistance+.25*a[i] and b["close"]>=resistance
 kind="sign_of_strength" if sos else "spring" if spring else "last_point_of_support" if lps else "none"
 return result(kind!="none",rows,i,timeframe,levels={"support":support,"resistance":resistance},measurements={"spring":spring,"sign_of_strength":sos,"last_point_of_support":lps,"relative_volume":rv.measurements.get("relative_volume")},confidence=.85 if sos else .7 if spring or lps else 0,explanation=f"Wyckoff event: {kind.replace('_',' ')}" if kind!="none" else "No objective Wyckoff event",data_used={"first_index":max(0,i-20),"last_index":i},classification=kind)

def oneil_breakout(rows,i,pivot_level,market_direction="unknown",fundamental_quality=None,cfg=None,timeframe="daily"):
 cfg=cfg or load_config();bos=detect_bos(rows,i,pivot_level,cfg,timeframe);rv=relative_volume(rows,i,cfg,timeframe);volume_ok=rv.measurements.get("relative_volume",0)>=cfg["bos"]["strong_volume_ratio"];detected=bos.detected and volume_ok
 return result(detected,rows,i,timeframe,levels={"pivot":pivot_level},measurements={"precise_breakout":bos.detected,"breakout_volume":rv.measurements.get("relative_volume"),"market_direction":market_direction,"fundamental_quality":fundamental_quality},confidence=(.8 if detected else .25),explanation="O'Neil-style price/volume breakout confirmed" if detected else "Breakout level or volume requirement not confirmed",data_used={"first_index":max(0,i-cfg["volume"]["lookback"]),"last_index":i},classification="breakout" if detected else "no_breakout")
