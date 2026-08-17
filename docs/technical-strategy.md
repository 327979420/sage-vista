# Northstar technical strategy v0.1

This is a deterministic research specification, not investment advice and not an execution system.

## Confluence gate

Signals are gated rather than simply added. A long setup is ineligible unless the higher-timeframe proxy is constructive, price is at objective support, and at least two independent lower-timeframe confirmations agree.

1. **Structure gate:** close above EMA200, EMA50 rising versus 20 sessions ago, and price no more than 6% below EMA50.
2. **Location gate:** price within 1.25 ATR of EMA50, within 1 ATR of EMA200, or in the 47–65% retracement band of the trailing 63-session range.
3. **Confirmation gate:** at least two of MACD bullish cross, bullish engulfing candle, high-volume rejection wick, confirmed double-bottom neckline break, and bullish RSI/price divergence.
4. **Entry:** next session open, preventing same-bar look-ahead.
5. **Stop:** beyond the lower of recent 12-bar demand and the relevant EMA support, with an ATR buffer. Reject setups risking more than 12% per share.
6. **Target:** nearest prior 126-bar supply above 1.5R, capped at the 2R measured move. Option walls are not used unless a timestamped, replaceable connector supplies them.
7. **Time exit:** exit after 10 bars if maximum favourable excursion is below 0.5R. Absolute maximum hold is 20 daily bars.
8. **Size:** `floor((equity × risk%) / (entry − stop))`, capped at 20% gross position value. Risk input above 2% is rejected.

## Backtest integrity

The test enters at the next open, evaluates stops before targets when both occur in one daily candle, prevents overlapping positions, and reports results in R multiples. It presently excludes fees, slippage, survivorship bias, dividends, corporate-action edge cases, and historical option-wall data. Those limitations must be resolved before treating results as evidence of tradability.
