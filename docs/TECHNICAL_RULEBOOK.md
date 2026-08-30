# Sage Vista Technical Rulebook

**Version:** 0.2.0  
**Status:** Authoritative  
**Configuration:** `config/technical_rules.json`

This document is the version-controlled definition of Sage Vista technical setups. Code, tests and UI explanations must agree with it. If code and prose differ, this rulebook controls until both are changed together. All analysis is deterministic from timestamped OHLCV and connector data; chart-image guessing is prohibited.

## 1. Governing principles

Sage Vista seeks quality companies in primary uptrends that are undergoing secondary pullbacks. Timeframe priority is monthly, weekly, daily, then four-hour. Monthly and weekly data determine eligibility and context; daily or four-hour data may trigger execution but cannot override weak higher-timeframe structure.

A setup and an entry are different states. Weak markets reduce recommendation strength and add a visible conflict warning; they do not rewrite the underlying setup detection. Missing data is reported, never silently scored. Detection uses only bars available at the stated detection timestamp.

## 2. Separate reference modules

These modules remain separate features until their definitions, tests and incremental value are established:

- **Weinstein Stage Analysis:** weekly Stage 1 base, Stage 2 advance, Stage 3 distribution or Stage 4 decline using the 30-week average, its slope and price location.
- **Minervini Trend Template:** price versus 50/150/200-day averages, correct alignment, rising 200-day average, 52-week range position and separately supplied relative strength.
- **Dow Theory:** confirmed higher highs/higher lows, lower highs/lower lows, and transition states. Primary-trend context remains separate from a secondary pullback.
- **Wyckoff events:** spring/liquidity sweep, sign of strength and last point of support using explicit support/resistance plus price-and-volume confirmation. Broad accumulation/distribution labels require multiple confirmed events and are not inferred from appearance.
- **O’Neil/CAN SLIM:** fundamental quality, market direction, objective base/pivot level and breakout volume. Technical breakout output does not imply that missing fundamental or market inputs passed.

No combined final score may be introduced until each module is independently tested.

## 3. Confirmed swing points

Default pivot geometry is two bars left and two bars right.

- Swing low: lower than both lows to its left and both lows to its right.
- Swing high: higher than both highs to its left and both highs to its right.
- Detection occurs only after the second right-side bar closes; confirmation delay is two bars.
- A major structural low should subsequently produce at least a 1 ATR(14) advance. Major status adds confidence but is not required for a provisional pivot.

Changing the left/right window or major-move threshold requires a configuration and version change.

## 4. W bottom and ordinary higher low

A valid preferred W bottom requires:

1. Two confirmed swing lows.
2. First low below the second low.
3. Three to ten bars between the lows.
4. The second low no more than 1 ATR(14) above the first.
5. The highest high between the lows defines the neckline/BOS level.

A higher second low beyond the ATR tolerance is an ordinary higher low, not a W. Confidence may increase when the lows align with independently detected support, a long-term trendline, 0.5/0.618 Fibonacci retracement or fair-value gap. These items must remain raw confluence evidence rather than altering the W geometry.

## 5. Resistance and trendline attempts

A level test occurs within 0.25 ATR of the objective resistance or trendline. Candles separated by no more than two bars belong to one rejection cluster and count once. Three separate tests classify a possible breakout as developing, but never confirm it. A valid closing BOS is still mandatory.

Trendlines must be fit from confirmed pivots available at the evaluation timestamp. Future pivots may not be used to redraw a historical line.

## 6. Break of structure and liquidity swipe

A bullish BOS requires a close above the confirmed swing high, neckline or resistance, with candle body at least 50% of the total range. Relative volume at or above 1.5× strengthens confidence.

If the high crosses the level but the close remains below, classification is `liquidity_swipe`, not BOS. If neither happens, classification is `unresolved_test`.

## 7. Relative volume

Relative volume uses the previous 20 completed bars on the same timeframe, excluding the current bar:

- Below 1.0×: weak
- 1.0–1.49×: normal
- 1.5–1.99×: strong
- 2.0× or higher: exceptional

Volume confirms price structure and never creates a trade independently.

## 8. Retest and confirmation

A provisional retest occurs one to five completed bars after BOS, returns to the broken level or within 0.25 ATR, does not close solidly back below it, and preserves at least 1.5R.

Valid confirming patterns are:

- Bullish engulfing candle.
- Hammer/rejection candle whose lower wick is at least 1.5× its body and whose close is in the upper third.
- Bullish expansion candle with body at least 60% of range.
- Doji followed by a bullish close above both the doji high and broken level.

A doji alone is never an entry. A solid close back below the level invalidates the retest. No valid retest within five bars is `breakout_without_entry`; Sage Vista does not automatically chase.

## 9. Entry alternatives and structural stop

Daily and four-hour entry alternatives must be backtested separately:

1. Confirming candle close.
2. Break above confirming candle high.
3. Limit within the retest/fair-value-gap zone.

The stop belongs below structural invalidation: the retest swing low, second W low, supporting FVG or support zone, plus 0.25 ATR. The engine must not tighten a stop to manufacture reward/risk.

## 10. Target, reward/risk and size

Target evidence may include prior supply/resistance, a measured move, relative-measure objective and timestamped option-wall data. Option walls must remain unavailable when a reliable connector is absent. A trade requires at least 1.5R; 2R is preferred.

Position size is:

`floor((account equity × risk percentage) / abs(entry − stop))`

Normal planned account risk is 0.5–1%; input above 2% is rejected. Liquidity, maximum-position, correlated-sector, earnings-gap and portfolio-concentration caps may only reduce size.

## 11. Gaps, earnings and market conflict

- Gap above intended entry below 0.5 ATR: wait for a four-hour retest.
- Gap of 0.5 ATR or more: do not chase; recalculate entry, stop, target and reward/risk.
- Reject when recalculated reward/risk is below 1.5R.
- Earnings inside the planned holding period are visibly flagged and tested separately; they may reduce size but do not automatically erase the setup.
- Weak market conditions deduct recommendation points, display a conflict warning and normally change the recommendation to watch/wait.

## 12. Holding-period discipline

For the daily model, exit after ten bars when maximum favourable excursion remains below 0.5R. Maximum hold is twenty daily bars unless a separately versioned exit rule applies. Four-hour tests use ten four-hour candles for the no-expansion rule and must not silently convert that to ten trading days.

## 13. Mandatory detector contract

Every detector returns:

- Detected/not detected
- Timeframe
- Detection timestamp
- Relevant price levels
- Raw measurements
- Confidence score
- Human-readable explanation
- Data indices used
- Confirmation delay
- Invalidated/not invalidated
- Explicit classification

## 14. Look-ahead and backtest protocol

Historical detection receives an `end` index and cannot read later bars. Pivots appear only after their configured right-side confirmation delay. Entry occurs no earlier than the next tradable event for the tested execution alternative. If daily stop and target both occur in one bar without intraday sequencing, the stop is assumed first. Overlapping positions, fees, slippage, delistings, splits, earnings segmentation and option-wall availability must be disclosed in each report.

Required synthetic tests cover valid/invalid W bottoms, swing highs/lows and confirmation delay, BOS versus wick-only swipe, clustered level tests, valid/failed/missing retests, volume tiers, gap rejection and mutation of unseen future bars.

## 15. CRWD reference example

The CRWD example is a hypothesis checklist, not labelled training truth: 0.618 support, rising-trendline support, higher second low, bullish RSI divergence, strong-volume engulfing candle, descending-trendline breakout, MACD trendline break/cross, later EMA20/EMA50 confirmation and fair-value-gap support/targets. Each feature must be detected independently using only information available at that historical timestamp.
