# 旧生产信号恢复审计

审计日期：2026-08-27  
来源：Git 历史中的 `public/rare-opportunity-radar.json` 生产输出

## 结论

- 共检查 10 个包含 Rare Radar 的历史提交。
- 找到 2026-08-24 至 2026-08-26 的 27 个真实 signal-day，涉及 18 只股票。
- 当前 Signal History 建立较晚，不能把这批已真实展示过的提醒当成从未发生。
- 恢复时必须读取当时提交中的原分数、组件和规则版本；不得用当前 registry 重新筛选。

## 可恢复股票

| 首次日期 | 股票 |
|---|---|
| 2026-08-24 | F、FRHC、MAR、MO、MUSA、PBR、SPGI、TSN、UDR、VICI |
| 2026-08-25 | NYT、PG |
| 2026-08-26 | AGCO、BTI、BTSG、GS、KMB、RIVN |

## PG 原始证据

- 2026-08-25：旧生产观察分 6；日线 MACD 近5日金叉、Fibonacci 支撑、EMA 支撑、三推趋势线突破、上方未补跳空缺口、Bullish FVG 支撑。
- 2026-08-26：旧生产观察分 5；日线 MACD 近5日金叉、Fibonacci 支撑、EMA 支撑、三推趋势线突破、上方未补跳空缺口。
- 后续 registry 对 Fibonacci 0.5 和三推突破的研究状态调整，只能影响新版本计分，不能抹除以上生产事实。

## 恢复纪律

1. 先把每个 symbol 的连续 signal-day 合并为当时版本的一次触发周期；
2. 冻结原始 radar payload、commit SHA、首次日期、原分数和原组件；
3. 能从同一提交取得的 Tracker、factor snapshot 和价格才可补充，缺失字段明确记为 unavailable；
4. 恢复案例单独标记 `recovered_from_git=true`，不得伪装成实时 recorder 当时已经存在；
5. Historical Backtest 与恢复后的 Production Forward 继续分组统计。
