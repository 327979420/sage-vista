"""Canonical, point-in-time states for every registered stock factor."""
from dataclasses import asdict,dataclass
from datetime import date

from .detectors import detect_bos,detect_triple_bottom,detect_w_bottom,load_config,pivots
from .factor_registry import FACTORS,FACTORS_BY_ID
from .macd_factor_backtest import (available,bullish_fvg_support,completed_groups,
 ema,kline_congestion_support,long_trend_ok,macd_state,overhead_unfilled_gap,
 recent_double_bottom_breakout,recent_three_push_breakout,support_bottom_volume,support_bullish_engulfing,
 three_push_breakout,three_push_retest,double_bottom_neckline_retest,volume_profile_support,fibonacci_support_levels)
from .technical import macd,rsi

MONITORED_FACTOR_IDS=tuple(factor.id for factor in FACTORS)
TECHNICAL_CONFIG=load_config()

@dataclass(frozen=True)
class FactorState:
 factor_id:str;factor_version:str;as_of:str;value:object;hit:bool;recent_hit:bool
 latest_hit_date:str|None;bars_since_hit:int|None;evidence:dict;available:bool
 runtime_status:str;factor_type:str;research_status:str;score_role:str
 experimental_weight:float;lookahead_audit:dict
 def dict(self):return asdict(self)

def trim_as_of(rows,as_of):return sorted(({**row} for row in rows if row.get("date") and row["date"]<=as_of),key=lambda row:row["date"])

def recent_bull_cross(line,signal,end,window=5):
 if end<1 or line[end]<=signal[end]:return False
 return any(line[j]>signal[j] and line[j-1]<=signal[j-1] for j in range(max(1,end-window+1),end+1))

def _base(factor_id,as_of,value,hit,evidence,available=True,latest_bar=None,runtime_status=None):
 factor=FACTORS_BY_ID[factor_id]
 return FactorState(factor_id,factor.version,as_of,value,bool(hit),False,None,None,evidence,available,runtime_status or factor.runtime_status,factor.factor_type,factor.status,factor.score_tier,factor.experimental_weight,{"as_of":as_of,"latest_bar":latest_bar,"future_data_used":False,"completed_bars_only":True,"confirmation_delay_bars":factor.confirmation_delay_bars})

def _fib_context(rows,i):
 hits=fibonacci_support_levels(rows,i);start=max(0,i-500);window=rows[start:i+1];points=pivots(window,len(window)-1,TECHNICAL_CONFIG);levels=None
 for high in reversed(points["highs"]):
  lows=[point for point in points["lows"] if point["index"]<high["index"] and point.get("major")]
  if not lows:continue
  low=lows[-1]
  if high["index"]-low["index"]<10 or high["price"]/low["price"]-1<.10:continue
  current=window[-1]["close"]
  if low["price"]<current<high["price"]:
   distance=high["price"]-low["price"];levels={"half":high["price"]-.5*distance,"618":high["price"]-.618*distance,"low":low["price"],"high":high["price"]};break
 golden=bool(levels and levels["618"]<=window[-1]["close"]<=levels["half"])
 return hits,golden,levels

def higher_timeframe_ema_support(current,bars,timeframe,tolerance):
 """Evaluate support against EMAs built only from completed higher-timeframe bars."""
 periods=(20,50,200);closes=[row["close"] for row in bars];available_periods=[period for period in periods if len(closes)>=period]
 evidence={"timeframe":timeframe,"completed_period_end":bars[-1]["date"] if bars else None,"periods":list(periods),"available_periods":available_periods,"tolerance_below":.02,"tolerance_above":tolerance,"detector_available":bool(available_periods)}
 if not available_periods:return False,evidence
 levels={str(period):ema(closes,period)[-1] for period in available_periods};distances={period:current["close"]/level-1 for period,level in levels.items()}
 hits=[period for period,distance in distances.items() if -.02<=distance<=tolerance];closest=min(distances,key=lambda period:abs(distances[period]))
 evidence.update({"levels":levels,"distance_by_period":distances,"matched_periods":hits,"closest_period":closest,"closest_level":levels[closest]})
 return bool(hits),evidence

def _bullish_engulfing_at(bars,index):
 if index<1 or index>=len(bars):return False
 prior,current=bars[index-1],bars[index]
 return prior["close"]<prior["open"] and current["close"]>current["open"] and current["open"]<=prior["close"] and current["close"]>=prior["open"]

def higher_timeframe_bullish_engulfing(bars,timeframe):
 available=len(bars)>=2;hit=available and _bullish_engulfing_at(bars,len(bars)-1)
 return hit,{"timeframe":timeframe,"completed_period_end":bars[-1]["date"] if bars else None,"prior_completed_period_end":bars[-2]["date"] if len(bars)>=2 else None,"detector_available":available,"real_body_engulfing":bool(hit)}

def higher_timeframe_double_engulfing(bars,timeframe,lookback,low_tolerance=.10):
 available=len(bars)>=4;latest=len(bars)-1
 evidence={"timeframe":timeframe,"completed_period_end":bars[-1]["date"] if bars else None,"lookback_periods":lookback,"low_tolerance":low_tolerance,"detector_available":available,"engulfing_dates":[],"engulfing_lows":[]}
 if not available or not _bullish_engulfing_at(bars,latest):return False,evidence
 start=max(1,len(bars)-lookback)
 for prior_index in range(latest-2,start-1,-1):
  if not _bullish_engulfing_at(bars,prior_index):continue
  first_low=bars[prior_index]["low"];second_low=bars[latest]["low"]
  if first_low and abs(second_low/first_low-1)<=low_tolerance:
   evidence.update({"engulfing_dates":[bars[prior_index]["date"],bars[latest]["date"]],"engulfing_lows":[first_low,second_low],"low_distance":second_low/first_low-1})
   return True,evidence
 return False,evidence

def _raw(rows,i):
 """Objective current-bar states using only rows through i."""
 view=rows[:i+1];current=view[-1];closes=[row["close"] for row in view];line,signal=macd(closes);curves={period:ema(closes,period) for period in (21,50,200)}
 fib,golden,fib_levels=_fib_context(view,i);ema_distances={str(period):current["close"]/curves[period][i]-1 for period in (21,50,200)};ema_hit=any(abs(value)<=.02 for value in ema_distances.values())
 fvg=bullish_fvg_support(view,i);three_push_recent=recent_three_push_breakout(view,i);retest=three_push_recent and three_push_retest(view,i);volume_peak=volume_profile_support(view,i);congestion=kline_congestion_support(view,i)
 support_context=bool(fib[.5] or fib[.618] or ema_hit or fvg or retest or volume_peak or congestion)
 prior_engulf=False
 if i>=2:
  prior_view=view[:-1];prior_i=i-1;prior_closes=[row["close"] for row in prior_view];prior_curves={period:ema(prior_closes,period) for period in (21,50,200)}
  prior_fib,_,_=_fib_context(prior_view,prior_i);prior_ema=any(abs(prior_view[-1]["close"]/prior_curves[period][prior_i]-1)<=.02 for period in (21,50,200))
  prior_fvg=bullish_fvg_support(prior_view,prior_i);prior_three=recent_three_push_breakout(prior_view,prior_i);prior_retest=prior_three and three_push_retest(prior_view,prior_i)
  prior_support=bool(prior_fib[.5] or prior_fib[.618] or prior_ema or prior_fvg or prior_retest or volume_profile_support(prior_view,prior_i) or kline_congestion_support(prior_view,prior_i))
  prior_engulf=support_bullish_engulfing(prior_view,prior_i,prior_support)
 bullish_follow=prior_engulf and current["close"]>current["open"]
 prior_volume=view[max(0,i-20):i];volume_average=sum(row["volume"] for row in prior_volume)/len(prior_volume) if prior_volume else 0;volume_ratio=current["volume"]/volume_average if volume_average else None
 range60=view[max(0,i-59):i+1];low60=min(row["low"] for row in range60);high60=max(row["high"] for row in range60);bottom30=low60+(high60-low60)*.30
 bullish_engulf=i>=1 and view[i-1]["close"]<view[i-1]["open"] and current["close"]>current["open"] and current["open"]<=view[i-1]["close"] and current["close"]>=view[i-1]["open"]
 body=abs(current["close"]-current["open"]);rng=max(current["high"]-current["low"],1e-9);lower=min(current["open"],current["close"])-current["low"]
 exact_cross=i>=1 and line[i]>signal[i] and line[i-1]<=signal[i-1];doji=False;bottom_engulf=False
 if exact_cross:
  for j in range(max(1,i-4),i+1):
   candle=view[j];candle_range=max(candle["high"]-candle["low"],1e-9)
   doji=doji or (max(candle["open"],candle["close"])<=bottom30 and abs(candle["close"]-candle["open"])/candle_range<=TECHNICAL_CONFIG["retest"]["doji_body_fraction"])
   prior=view[j-1];engulf=candle["close"]>candle["open"] and prior["close"]<prior["open"] and candle["open"]<=prior["close"] and candle["close"]>=prior["open"]
   bottom_engulf=bottom_engulf or (engulf and max(candle["open"],candle["close"])<=bottom30)
 hammer=lower>=TECHNICAL_CONFIG["retest"]["hammer_wick_body_ratio"]*max(body,1e-9) and (current["close"]-current["low"])/rng>=TECHNICAL_CONFIG["retest"]["upper_close_fraction"]
 rv=rsi(closes);repair=i>=1 and rv[i] is not None and rv[i-1] is not None and rv[i]>30>=rv[i-1]
 confirmed=pivots(view,i,TECHNICAL_CONFIG);lows=confirmed["lows"];higher_low=len(lows)>=2 and lows[-1]["price"]>lows[-2]["price"]
 divergence=False
 if len(lows)>=2:
  a,b=lows[-2:];divergence=i-b["confirmed_index"]<=8 and rv[b["index"]] is not None and rv[a["index"]] is not None and rv[b["index"]]<50 and b["price"]<a["price"] and rv[b["index"]]>rv[a["index"]]+2 and current["close"]<=b["price"]*1.15
 pullback=current["close"]<=max(row["high"] for row in view[max(0,i-60):i])*.95 if i else False
 w=detect_w_bottom(view,i,TECHNICAL_CONFIG);double_bottom=w.detected and detect_bos(view,i,w.levels["neckline"],TECHNICAL_CONFIG).detected
 triple=detect_triple_bottom(view,i,TECHNICAL_CONFIG);trend_ok=long_trend_ok(view,i,curves[200]);triple_pullback=triple.detected and trend_ok and pullback
 double_bottom_recent=recent_double_bottom_breakout(view,i);double_bottom_retest=double_bottom_recent and double_bottom_neckline_retest(view,i)
 day=date.fromisoformat(current["date"]);weekly_rows=available(completed_groups(view,"weekly"),(day.isocalendar().year,day.isocalendar().week));monthly_rows=available(completed_groups(view,"monthly"),(day.year,day.month))
 weekly_state=macd_state(weekly_rows[-160:]) if len(weekly_rows)>=3 else None
 monthly_line,monthly_signal=macd([row["close"] for row in monthly_rows]) if len(monthly_rows)>=2 else ([],[]);monthly_cross=bool(monthly_line and monthly_line[-1]>monthly_signal[-1] and monthly_line[-2]<=monthly_signal[-2])
 weekly_ema_hit,weekly_ema_evidence=higher_timeframe_ema_support(current,weekly_rows,"weekly_completed",.03)
 monthly_ema_hit,monthly_ema_evidence=higher_timeframe_ema_support(current,monthly_rows,"monthly_completed",.05)
 weekly_engulf,weekly_engulf_evidence=higher_timeframe_bullish_engulfing(weekly_rows,"weekly_completed")
 monthly_engulf,monthly_engulf_evidence=higher_timeframe_bullish_engulfing(monthly_rows,"monthly_completed")
 weekly_double,weekly_double_evidence=higher_timeframe_double_engulfing(weekly_rows,"weekly_completed",26)
 monthly_double,monthly_double_evidence=higher_timeframe_double_engulfing(monthly_rows,"monthly_completed",12)
 return {
  "qualification.long_trend":(long_trend_ok(view,i,curves[200]),{"close":current["close"],"ema200":curves[200][i]}),
  "qualification.pullback_60d":(pullback,{"prior_60d_high":max(row["high"] for row in view[max(0,i-60):i]) if i else None}),
  "macd.daily_bull_cross":(recent_bull_cross(line,signal,i),{"macd":line[i],"signal":signal[i],"freshness_sessions":5}),
  "macd.weekly_histogram_improving":(bool(weekly_state and weekly_state["histogram_rising"]),{"completed_week_end":weekly_rows[-1]["date"] if weekly_rows else None,"histogram":weekly_state["macd_line"]-weekly_state["signal_line"] if weekly_state else None}),
  "macd.monthly_bull_cross":(monthly_cross,{"completed_month_end":monthly_rows[-1]["date"] if monthly_rows else None}),
  "support.ema_proximity":(ema_hit,{"distance_by_period":ema_distances,"tolerance":.02}),
  "support.weekly_ema_proximity":(weekly_ema_hit,weekly_ema_evidence),"support.monthly_ema_proximity":(monthly_ema_hit,monthly_ema_evidence),
  "support.fibonacci_half":(fib[.5],{"levels":fib_levels,"tolerance":.02}),"support.fibonacci_618":(fib[.618],{"levels":fib_levels,"tolerance":.02}),"support.golden_pocket":(golden,{"levels":fib_levels}),
  "structure.trendline_three_push":(three_push_breakout(view,i),{"confirmation":"completed close BOS"}),"structure.double_bottom":(double_bottom,{"neckline":w.levels.get("neckline")}),
  "structure.triple_bottom_pullback":(triple_pullback,{"dependency_hits":[factor_id for factor_id,hit in (("qualification.long_trend",trend_ok),("qualification.pullback_60d",pullback)) if hit],"pattern":triple.dict()}),"structure.higher_low":(higher_low,{"confirmed_lows":lows[-2:]}),
  "structure.trendline_three_push_retest":(retest,{"dependency_hits":["structure.trendline_three_push"] if three_push_recent else [],"lookback_sessions":10}),
  "structure.double_bottom_neckline_retest":(double_bottom_retest,{"dependency_hits":["structure.double_bottom"] if double_bottom_recent else [],"lookback_sessions":10}),
  "structure.bullish_fvg_support":(fvg,{"lookback_sessions":250,"max_distance":.05}),"risk.overhead_unfilled_gap":(overhead_unfilled_gap(view,i),{"lookback_sessions":250,"max_distance":.15}),
  "rsi.oversold_repair":(repair,{"rsi":rv[i],"prior_rsi":rv[i-1] if i else None}),"rsi.bullish_divergence":(divergence,{"confirmed_lows":lows[-2:],"rsi":rv[i]}),
  "volume.relative_expansion":(bool(volume_ratio is not None and volume_ratio>=TECHNICAL_CONFIG["volume"]["strong"]),{"ratio":volume_ratio,"threshold":TECHNICAL_CONFIG["volume"]["strong"]}),
  "volume.bottom_expansion":(support_bottom_volume(view,i,support_context),{"support_context":support_context,"ratio":volume_ratio,"ratio_threshold":1.5}),
  "structure.bottom_doji":(doji,{"bottom_limit":bottom30,"macd_cross_required":True,"candle_lookback":5}),"structure.bottom_bullish_engulfing":(bottom_engulf,{"bottom_limit":bottom30,"macd_cross_required":True,"candle_lookback":5}),
  "structure.support_bullish_engulfing":(support_bullish_engulfing(view,i,support_context),{"support_context":support_context}),"structure.hammer":(hammer,{"lower_wick_body_ratio":lower/max(body,1e-9),"close_fraction":(current["close"]-current["low"])/rng}),
  "structure.weekly_bullish_engulfing":(weekly_engulf,weekly_engulf_evidence),"structure.monthly_bullish_engulfing":(monthly_engulf,monthly_engulf_evidence),
  "structure.weekly_double_bullish_engulfing":(weekly_double,weekly_double_evidence),"structure.monthly_double_bullish_engulfing":(monthly_double,monthly_double_evidence),
  "structure.engulfing_bullish_follow_through":(bullish_follow,{"dependency_hits":["structure.support_bullish_engulfing"] if prior_engulf else [],"engulfing_date":view[i-1]["date"] if prior_engulf else None,"confirmation_date":current["date"] if bullish_follow else None}),
  "support.close_congestion":(congestion,{"lookback_sessions":250}),"support.volume_profile_proxy":(volume_peak,{"lookback_sessions":250,"bins":40}),
 }

def evaluate_all_factors(rows,as_of):
 rows=trim_as_of(rows,as_of);latest=rows[-1]["date"] if rows else None
 if not rows or latest!=as_of or len(rows)<260:
  reason="latest bar does not match as_of" if latest!=as_of else "insufficient history"
  return [_base(factor.id,as_of,None,False,{"reason":reason},False,latest,"unavailable") for factor in FACTORS]
 i=len(rows)-1;cache={i:_raw(rows,i)};states=[]
 for factor in FACTORS:
  if factor.runtime_status=="definition_required":
   states.append(_base(factor.id,as_of,None,False,{"reason":"registry definition is not precise enough for an objective detector"},False,latest,"definition_required"));continue
  hit,evidence=cache[i][factor.id];detector_available=evidence.get("detector_available",True);state=_base(factor.id,as_of,evidence.get("ratio",evidence.get("rsi",hit)),hit,evidence,detector_available,latest,"monitored" if detector_available else "insufficient_history")
  recent=bool(hit);latest_hit=as_of if hit else None;bars_since=0 if hit else None
  if factor.factor_type=="event" and factor.observation_window_sessions:
   for ago in range(0,min(factor.observation_window_sessions,i+1)):
    j=i-ago
    if j not in cache:cache[j]=_raw(rows,j)
    raw_hit=cache[j][factor.id][0]
    if factor.id=="macd.daily_bull_cross":
     past=[row["close"] for row in rows[:j+1]];line,signal=macd(past);raw_hit=j>=1 and line[j]>signal[j] and line[j-1]<=signal[j-1]
    if raw_hit:recent=True;latest_hit=rows[j]["date"];bars_since=ago;break
  states.append(FactorState(**{**state.dict(),"recent_hit":recent,"latest_hit_date":latest_hit,"bars_since_hit":bars_since}))
 return states

def evaluate_initial_factors(rows,as_of):
 initial={"macd.daily_bull_cross","macd.weekly_histogram_improving","support.ema_proximity","structure.trendline_three_push_retest","structure.bullish_fvg_support","risk.overhead_unfilled_gap","volume.bottom_expansion","structure.support_bullish_engulfing","structure.engulfing_bullish_follow_through"}
 return [state for state in evaluate_all_factors(rows,as_of) if state.factor_id in initial]
