# 历史产品与早期技术规格

本文件合并保存旧记录，按需追溯，不是当前执行流程或当前生产状态。正文中的“当前”“权威”“已批准”等表述属于原记录时点；现行业务查 [模块规则](../rules/README.md)，实际状态查 [机器来源](../CURRENT_STATUS_ZH.md)。旧文件原件及原行号可从清理前 Git 提交 `875c1d2` 恢复。

## 目录
- [technical-strategy.md](#technical-strategy)
- [TECHNICAL_RULEBOOK.md](#technical-rulebook)
- [PRODUCT_REQUIREMENTS_V2_ZH.md](#product-requirements-v2-zh)
- [PROJECT_BLUEPRINT_ZH.md](#project-blueprint-zh)
- [TRACKER_PRODUCT_REQUIREMENTS_ZH.md](#tracker-product-requirements-zh)

---

<a id="technical-strategy"></a>

## 原文件：technical-strategy.md

<a id="technical-strategy-sage-vista-technical-strategy-v01"></a>
# Sage Vista technical strategy v0.1

This is a deterministic research specification, not investment advice and not an execution system.

<a id="technical-strategy-confluence-gate"></a>
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

<a id="technical-strategy-backtest-integrity"></a>
## Backtest integrity

The test enters at the next open, evaluates stops before targets when both occur in one daily candle, prevents overlapping positions, and reports results in R multiples. It presently excludes fees, slippage, survivorship bias, dividends, corporate-action edge cases, and historical option-wall data. Those limitations must be resolved before treating results as evidence of tradability.

---

<a id="technical-rulebook"></a>

## 原文件：TECHNICAL_RULEBOOK.md

<a id="technical-rulebook-sage-vista-technical-rulebook"></a>
# Sage Vista Technical Rulebook

**Version:** 0.2.0
**Status:** Authoritative
**Configuration:** `config/technical_rules.json`

This document is the version-controlled definition of Sage Vista technical setups. Code, tests and UI explanations must agree with it. If code and prose differ, this rulebook controls until both are changed together. All analysis is deterministic from timestamped OHLCV and connector data; chart-image guessing is prohibited.

<a id="technical-rulebook-1-governing-principles"></a>
## 1. Governing principles

Sage Vista seeks quality companies in primary uptrends that are undergoing secondary pullbacks. Timeframe priority is monthly, weekly, daily, then four-hour. Monthly and weekly data determine eligibility and context; daily or four-hour data may trigger execution but cannot override weak higher-timeframe structure.

A setup and an entry are different states. Weak markets reduce recommendation strength and add a visible conflict warning; they do not rewrite the underlying setup detection. Missing data is reported, never silently scored. Detection uses only bars available at the stated detection timestamp.

<a id="technical-rulebook-2-separate-reference-modules"></a>
## 2. Separate reference modules

These modules remain separate features until their definitions, tests and incremental value are established:

- **Weinstein Stage Analysis:** weekly Stage 1 base, Stage 2 advance, Stage 3 distribution or Stage 4 decline using the 30-week average, its slope and price location.
- **Minervini Trend Template:** price versus 50/150/200-day averages, correct alignment, rising 200-day average, 52-week range position and separately supplied relative strength.
- **Dow Theory:** confirmed higher highs/higher lows, lower highs/lower lows, and transition states. Primary-trend context remains separate from a secondary pullback.
- **Wyckoff events:** spring/liquidity sweep, sign of strength and last point of support using explicit support/resistance plus price-and-volume confirmation. Broad accumulation/distribution labels require multiple confirmed events and are not inferred from appearance.
- **O’Neil/CAN SLIM:** fundamental quality, market direction, objective base/pivot level and breakout volume. Technical breakout output does not imply that missing fundamental or market inputs passed.

No combined final score may be introduced until each module is independently tested.

<a id="technical-rulebook-3-confirmed-swing-points"></a>
## 3. Confirmed swing points

Default pivot geometry is two bars left and two bars right.

- Swing low: lower than both lows to its left and both lows to its right.
- Swing high: higher than both highs to its left and both highs to its right.
- Detection occurs only after the second right-side bar closes; confirmation delay is two bars.
- A major structural low should subsequently produce at least a 1 ATR(14) advance. Major status adds confidence but is not required for a provisional pivot.

Changing the left/right window or major-move threshold requires a configuration and version change.

<a id="technical-rulebook-4-w-bottom-and-ordinary-higher-low"></a>
## 4. W bottom and ordinary higher low

A valid preferred W bottom requires:

1. Two confirmed swing lows.
2. First low below the second low.
3. Three to ten bars between the lows.
4. The second low no more than 1 ATR(14) above the first.
5. The highest high between the lows defines the neckline/BOS level.

A higher second low beyond the ATR tolerance is an ordinary higher low, not a W. Confidence may increase when the lows align with independently detected support, a long-term trendline, 0.5/0.618 Fibonacci retracement or fair-value gap. These items must remain raw confluence evidence rather than altering the W geometry.

<a id="technical-rulebook-5-resistance-and-trendline-attempts"></a>
## 5. Resistance and trendline attempts

A level test occurs within 0.25 ATR of the objective resistance or trendline. Candles separated by no more than two bars belong to one rejection cluster and count once. Three separate tests classify a possible breakout as developing, but never confirm it. A valid closing BOS is still mandatory.

Trendlines must be fit from confirmed pivots available at the evaluation timestamp. Future pivots may not be used to redraw a historical line.

<a id="technical-rulebook-6-break-of-structure-and-liquidity-swipe"></a>
## 6. Break of structure and liquidity swipe

A bullish BOS requires a close above the confirmed swing high, neckline or resistance, with candle body at least 50% of the total range. Relative volume at or above 1.5× strengthens confidence.

If the high crosses the level but the close remains below, classification is `liquidity_swipe`, not BOS. If neither happens, classification is `unresolved_test`.

<a id="technical-rulebook-7-relative-volume"></a>
## 7. Relative volume

Relative volume uses the previous 20 completed bars on the same timeframe, excluding the current bar:

- Below 1.0×: weak
- 1.0–1.49×: normal
- 1.5–1.99×: strong
- 2.0× or higher: exceptional

Volume confirms price structure and never creates a trade independently.

<a id="technical-rulebook-8-retest-and-confirmation"></a>
## 8. Retest and confirmation

A provisional retest occurs one to five completed bars after BOS, returns to the broken level or within 0.25 ATR, does not close solidly back below it, and preserves at least 1.5R.

Valid confirming patterns are:

- Bullish engulfing candle.
- Hammer/rejection candle whose lower wick is at least 1.5× its body and whose close is in the upper third.
- Bullish expansion candle with body at least 60% of range.
- Doji followed by a bullish close above both the doji high and broken level.

A doji alone is never an entry. A solid close back below the level invalidates the retest. No valid retest within five bars is `breakout_without_entry`; Sage Vista does not automatically chase.

<a id="technical-rulebook-9-entry-alternatives-and-structural-stop"></a>
## 9. Entry alternatives and structural stop

Daily and four-hour entry alternatives must be backtested separately:

1. Confirming candle close.
2. Break above confirming candle high.
3. Limit within the retest/fair-value-gap zone.

The stop belongs below structural invalidation: the retest swing low, second W low, supporting FVG or support zone, plus 0.25 ATR. The engine must not tighten a stop to manufacture reward/risk.

<a id="technical-rulebook-10-target-rewardrisk-and-size"></a>
## 10. Target, reward/risk and size

Target evidence may include prior supply/resistance, a measured move, relative-measure objective and timestamped option-wall data. Option walls must remain unavailable when a reliable connector is absent. A trade requires at least 1.5R; 2R is preferred.

Position size is:

`floor((account equity × risk percentage) / abs(entry − stop))`

Normal planned account risk is 0.5–1%; input above 2% is rejected. Liquidity, maximum-position, correlated-sector, earnings-gap and portfolio-concentration caps may only reduce size.

<a id="technical-rulebook-11-gaps-earnings-and-market-conflict"></a>
## 11. Gaps, earnings and market conflict

- Gap above intended entry below 0.5 ATR: wait for a four-hour retest.
- Gap of 0.5 ATR or more: do not chase; recalculate entry, stop, target and reward/risk.
- Reject when recalculated reward/risk is below 1.5R.
- Earnings inside the planned holding period are visibly flagged and tested separately; they may reduce size but do not automatically erase the setup.
- Weak market conditions deduct recommendation points, display a conflict warning and normally change the recommendation to watch/wait.

<a id="technical-rulebook-12-holding-period-discipline"></a>
## 12. Holding-period discipline

For the daily model, exit after ten bars when maximum favourable excursion remains below 0.5R. Maximum hold is twenty daily bars unless a separately versioned exit rule applies. Four-hour tests use ten four-hour candles for the no-expansion rule and must not silently convert that to ten trading days.

<a id="technical-rulebook-13-mandatory-detector-contract"></a>
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

<a id="technical-rulebook-14-look-ahead-and-backtest-protocol"></a>
## 14. Look-ahead and backtest protocol

Historical detection receives an `end` index and cannot read later bars. Pivots appear only after their configured right-side confirmation delay. Entry occurs no earlier than the next tradable event for the tested execution alternative. If daily stop and target both occur in one bar without intraday sequencing, the stop is assumed first. Overlapping positions, fees, slippage, delistings, splits, earnings segmentation and option-wall availability must be disclosed in each report.

Required synthetic tests cover valid/invalid W bottoms, swing highs/lows and confirmation delay, BOS versus wick-only swipe, clustered level tests, valid/failed/missing retests, volume tiers, gap rejection and mutation of unseen future bars.

<a id="technical-rulebook-15-crwd-reference-example"></a>
## 15. CRWD reference example

The CRWD example is a hypothesis checklist, not labelled training truth: 0.618 support, rising-trendline support, higher second low, bullish RSI divergence, strong-volume engulfing candle, descending-trendline breakout, MACD trendline break/cross, later EMA20/EMA50 confirmation and fair-value-gap support/targets. Each feature must be detected independently using only information available at that historical timestamp.

---

<a id="product-requirements-v2-zh"></a>

## 原文件：PRODUCT_REQUIREMENTS_V2_ZH.md

<a id="product-requirements-v2-zh-sage-vista-业务需求-v2"></a>
# Sage Vista 业务需求 V2

状态：已确认，实施中
确认日期：2026-08-27

<a id="product-requirements-v2-zh-1-当前生产规则"></a>
## 1. 当前生产规则

- 当前榜单继续使用旧生产观察评分和既有门槛；27 因子实验观察分只做 shadow observation，不提前接管榜单或 Discord。
- 当前阶段的“入池”是达到当时有效的旧生产门槛，不是要求 `official_score > 0`。目前 `official_score` 为 0 不得阻止真实生产提醒进入历史。
- 未来只有在 27 因子完成历史回测、独立验证和前向观察并形成明确结论后，才建立新的 `signal_definition_version` 替代旧规则。新版本不得重算或删除旧版本案例。
- 页面保留正式分 0、旧生产观察分和 27 因子实验观察分，综合分必须可展开解释来源。

<a id="product-requirements-v2-zh-2-因子事实与研究结论分离"></a>
## 2. 因子事实与研究结论分离

技术时效状态固定为 `ACTIVE / RECENT / EXPIRED / NEVER / UNAVAILABLE`。每个因子独立定义时效窗口；状态型因子按当日条件判断，事件型因子按注册窗口判断。

研究状态（待测试、候选、已验证、不稳定、不成立、样本不足等）与技术时效正交。技术上命中但研究未验证的因子必须继续显示，只是不进入正式权重。

“上方未补跳空缺口”在旧生产版本中暂时保留原正分语义；未来通过独立实验决定是否改为风险项，结论变更必须创建新版本。

<a id="product-requirements-v2-zh-3-current-与永久-tracking-pool"></a>
## 3. Current 与永久 Tracking Pool

- Current Opportunities 每日重建，回答今天看什么。
- 股票首次达到当时生产版本门槛后建立永久 Tracking Case。掉榜、亏损、过期、数据不可用均不得删除。
- 同一信号周期内重现属于原案例；完全离榜达到 reset 规则后再次触发，建立新案例。
- 每个案例冻结首次触发时的规则版本、价格、来源、旧生产分、27 因子实验分、正式分和完整因子证据。
- 每个交易日追加价格、各类分数、因子时效状态、是否仍在当前榜单、Industry/ETF Context、Market Context 和生命周期；历史日只保留当时可获得的数据，不用今天的分类或价格回填。
- 尽可能从 Git 可核验的历史生产输出恢复 PG 等旧提醒；恢复记录必须保留原日期、原分数和原规则，不得用今天的规则倒算。

<a id="product-requirements-v2-zh-4-industrymarket-与最终决策"></a>
## 4. Industry、Market 与最终决策

- Industry Radar 是独立行业确认层，不篡改技术原始分。
- 个股所属主题与主题 ETF 的技术位置是两类独立事实：前者来自可审计持仓快照，后者判断对应 ETF 是否处于长期趋势中的回撤支撑位。多个参考 ETF 只能为同一主题贡献最多 1 个候选权重，未完成回测前仅作 shadow context。
- 该规则对全部有可审计成员来源的主题统一执行，不为某一股票或某一行业写特例。默认使用成员来源 ETF 作为参考；如未来增加多个参考 ETF，必须有数据依据且同一主题仍只能形成一个行业加分候选。
- Market Regime 调整最终决策等级和仓位倾向，不篡改技术事实。
- 最终产品可显示综合总分，但必须同时展开技术分、行业确认、市场调整和风险项。
- Industry/Market 已接入逐日案例证据，但在完成历史回测前不进入旧生产评分；页面改版排在底层与回测框架之后。

<a id="product-requirements-v2-zh-5-实验永久账本"></a>
## 5. 实验永久账本

- 成功、失败、不稳定和样本不足的实验全部保留；新实验建立新版本，不覆盖旧结果。
- 每个因子关联全部相关 `experiment_id`，数据缺失或方法限制必须明确记录。
- 先建立旧实验清单，只重跑关键、可复现并影响当前决策的实验。
- Historical Backtest 与 Production Forward 在同一研究体系对照展示，但分别统计。综合参考必须明确标注，不能冒充真实前向胜率。

<a id="product-requirements-v2-zh-6-回测顺序"></a>
## 6. 回测顺序

1. 冻结并重建旧技术评分基准；
2. 回测 27 因子单项、冗余组和组合；
3. 比较技术基准、技术加大盘、技术加行业、三者组合；
4. 分别报告样本数、5/20/60/100 日胜率、均值/中位数收益、相对 SPY、MFE、MAE、最大回撤和时期稳定性；
5. 只有研究结论达到预先定义的晋级标准，才创建新生产评分版本。

---

<a id="project-blueprint-zh"></a>

## 原文件：PROJECT_BLUEPRINT_ZH.md

<a id="project-blueprint-zh-sage-vista-项目蓝图"></a>
# Sage Vista 项目蓝图

状态：当前产品与研究总纲
最后更新：2026-08-28

> 评分、周期、持仓、回测、实验留档和“先改规则再改代码”的当前权威要求，统一见 [`SAGE_VISTA_RULEBOOK_ZH.md`](../SAGE_VISTA_RULEBOOK_ZH.md)。本文保留产品蓝图；两者冲突时，总规则手册优先。

<a id="project-blueprint-zh-1-产品目标"></a>
## 1. 产品目标

Sage Vista 要成为一个清楚、可信、能长期积累实验结果的 MACD 技术研究助手。用户的真实交易方式是多周期、多指标、多种价格结构共同验证，因此项目要把这些判断转成可复查的因子，并通过长期历史、独立验证期和前向观察判断哪些因素真正有帮助。

项目只辅助研究和人工决策，不自动下单，不把规则匹配分数解释成收益概率。

<a id="project-blueprint-zh-2-固定产品入口"></a>
## 2. 固定产品入口

最终主导航与职责固定为四项：

1. 今日研究总览：决策摘要，不复制完整详情页；
2. 多因子：当前 37-factor technical evidence、唯一审计排行榜、精选子集和个股详情；
3. 行业雷达：Theme strength/breadth/direction 上下文；
4. 研究 / 实验：验证、失败结论与方法；
5. 市场环境可作为 secondary context。

旧“个股研究 / Technical Tracker”页面已退役；可用的个股证据与风险解释合并进多因子机会，避免保留两套排名。

双指标确认、RSI、成交量等旧独立功能页可以在依赖审计后移除。删除的是页面与重复展示，不是底层因子能力。

2026-08-27 依赖审计确认旧根路径 Signal Board 只消费 `app/data.ts` mock candidates，不被 Tracker、Multi-Factor、Industry Radar、Market Context、workflow 或 Discord 使用，因此页面与样例数据已退役。根路径改为今日研究总览。

<a id="project-blueprint-zh-3-统一因子库"></a>
## 3. 统一因子库

项目将从固定六因子评分升级为动态因子库。预计先扩展到约 20 个因子，之后允许继续增加。

每个因子必须包含：

- 稳定 ID、名称和版本；
- 人话解释与精确机器规则；
- 所属证据家族与适用周期；
- 是否只使用当时已知数据；
- 待测试、测试中、不成立、不稳定、样本不足、候选、已验证或暂停状态；
- 开发期、验证期和前向期样本；
- 20 日与 100 日胜率、收益、不利波动和相对市场结果；
- 当前是否进入正式分、观察分或只显示不计分；
- 与其他因子的重复关系，防止同类证据重复加分。

必须保留并纳入因子库规划的能力包括：

- MACD 日、周、月状态、金叉新鲜度和能量柱改善；
- 多因子雷达将最近五个完整交易日内发生、且当前仍保持多头的日线 MACD 金叉作为候选观察因子 +1；它不是已验证正式分，过期或重新死叉即失效。
- 支撑位确认新增“底部放量”和“看涨吞没”两个候选观察因子；两者必须依赖已登记支撑背景，不能脱离 Fibonacci、EMA、FVG、趋势线回踩或 Volume Profile 等位置证据单独加分。
- RSI、超卖修复、RSI 底背离和多周期背离；
- 成交量突然放大、底部放量与缩量回调；
- EMA21/50/200、Fibonacci 0.5/0.618、Golden Pocket；
- 缺口、Fair Value Gap、筹码峰和 K 线聚集区；
- Doji、Bullish Engulfing、锤头线、双底、更高低点；
- 三推趋势线突破、突破回踩及其他经明确定义的价格结构。

失败实验不删除，只是不进入正式评分。

<a id="project-blueprint-zh-4-动态多因子雷达"></a>
## 4. 动态多因子雷达

雷达将由因子注册表生成，不长期写死“六项、每项一分”。未来评分结构为：

```text
基础资格
+ 已验证因子的正式分
+ 尚待验证因子的观察分
- 冲突与风险扣分
= 多因子总分
```

页面不能只显示总分，还要按趋势、MACD、支撑、结构、RSI/量能等类别解释分数来源，并列出未命中的重要条件和冲突证据。

早期因子可以等权观察；没有跨时期验证与足够样本前，不得自动提升权重。高度相关的同类条件不能机械重复计分。

<a id="project-blueprint-zh-5-研究与晋级流程"></a>
## 5. 研究与晋级流程

每个新因子按统一流程推进：

```text
提出因子 → 写清规则 → 防前视检查 → 单因子测试
→ 核心条件加一个因子 → 跨类别组合 → 动态评分验证
→ 前向观察 → 决定是否进入正式分
```

基本分段为 2000—2024 开发、2025 独立验证、2026 前向观察。主要观察期为 20 与 100 个交易日；更大周期实验可以使用 1—6 个月，但必须和日线结论分开。

所有实验写入研究账本，包括失败、不稳定和样本不足。

<a id="project-blueprint-zh-6-每日更新与数据安全"></a>
## 6. 每日更新与数据安全

美国市场完整收盘后，统一自动任务应：

1. 获取并写回最新完整日 K；
2. 更新 MACD Tracker；
3. 生成固定 27 因子的 daily factor snapshot，并更新动态多因子雷达；
4. 在当前机会输出成功后追加/更新 canonical Signal History，只填已经到期的 forward outcome；
5. 检查 Tracker、factor snapshot、Radar、Industry、Signal History 与 provider 日期一致、历史没有缺口、没有未来数据；
6. 运行测试和生产构建；
7. 只有全部通过才发布网站；
8. 没有新交易日数据时不重复发布。

网页显示的数据日期必须是实际使用的完整收盘日，不能只显示任务运行时间。

Daily EOD workflow 之外另有独立 freshness monitor：在正常重试窗口之后重新查询 EODHD 最新完整交易日，并核对 source、Tracker、factor snapshot、Rare Radar、Industry Radar、Signal History 六项日期。漏跑时它以失败检查、artifact 和去重 issue 报警；也提供 `repository_dispatch` 给独立外部调度。部署后的 live verification 必须按整组静态文件重试跨文件日期一致性，以容忍 CDN/Workers 的短暂 mixed-date propagation；只有整组日期与防前视审计一致才进入 Discord。快速变化的 production JSON consumer 使用 `cache: no-store`，不全局关闭静态资源缓存。

<a id="project-blueprint-zh-61-currentforward-与-backtest"></a>
## 6.1 Current、Forward 与 Backtest

- Current Opportunities 回答今天看什么，不负责保存历史。
- `public/signal-history.json` 是真实生产提醒的 append-only ledger；离榜不删除，信号时 Tracker、27-factor、Industry 和版本证据不可变。
- Historical Backtest / case review 仍在 research branch，不能与 production forward 样本合并。
- 生产账本按下一交易日复权开盘进入，只随真实到来的交易 session 填充 1/5/10/20/60/100D、MFE、MAE。完整规则见 `docs/SIGNAL_HISTORY.md`。

<a id="project-blueprint-zh-7-discord-稀有机会播报"></a>
## 7. Discord 稀有机会播报

未来接入 Discord Bot。播报门槛由动态因子库决定，不永久写死为 5/6 分。

每条消息至少包含：股票、数据日期、价格、总分、正式分、观察分、分类得分、命中证据、风险、数据完整性和网站详情链接。

安全规则：

- 没有达到门槛时保持安静；
- 同一股票与同一信号去重；
- 只有分数发生实质变化才再次提醒；
- 数据不完整、日期不一致、测试失败或网站发布失败时停止发送；
- 网站成功更新后才发送 Discord；
- 永远注明“研究提醒，不是自动买入”。

<a id="project-blueprint-zh-8-ui-与文字规范"></a>
## 8. UI 与文字规范

UI 的目标是专业、克制、清楚，而不只是简单。

- 一个统一的功能介绍页负责解释项目、评分、数据和使用方法。
- 使用技巧、定义和长篇免责声明不要散落在每个功能页。
- 功能页首屏直接回答“今天有什么、数据到哪天、为什么值得看”。
- 原始技术定义和深灰色研究细节放在折叠区或专门研究页。
- 默认使用短句、图表、分类得分和可点击证据，减少重复段落。
- 四个主页面使用同一导航、状态颜色、日期格式、间距和卡片系统。

UI V2（2026-08-27）固定为五项主导航，Market Context 降为 secondary navigation。每页只有一个首要问题：Home 回答今天看什么；Technical Tracker 回答哪些股票值得注意；Multi-Factor 解释 27 项证据；Industry Radar 解释 Theme 位置；Research 回答历史或真实 forward 是否有效。桌面正文最低 16px，主要表格/卡片 15–16px，section heading 20–24px，page title 28–34px，只有审计元数据允许 13px；不再使用 10/11px 承载可读内容。

Technical Tracker 采用左侧冻结排名 screener、右侧 selected-stock research panel；Multi-Factor 和 Industry 只做 presentation join，不能回写排名。Industry 主表排除 Unavailable，后者进入 Data Quality 折叠区。Research 使用 Backtesting / Forward Testing / Experiments 三段切换；canonical Signal History 只在 Forward Testing 展示完整表，Multi-Factor 不再重复该表。共享组件限于 status badge、metric card、section header、empty state 和 audit details，不建立大型设计框架。
- 手机端优先显示股票、总分、核心证据和风险，长解释延后。
- 不为已经移除的旧页面继续维护重复说明和专属视觉组件。

<a id="project-blueprint-zh-9-实施顺序"></a>
## 9. 实施顺序

1. 审计页面、因子检测器、数据依赖和自动任务。
2. 删除旧独立页面入口，但保留 RSI、背离、量能等检测能力。
3. 建立统一因子注册表和实验状态模型。
4. 迁移现有六项及现有 RSI、量能、结构能力。
5. 把雷达改为动态读取因子库，并实现正式分、观察分和冲突扣分。
6. 验证每日 MACD 与多因子更新的一致性。
7. 接入 Discord、去重和失败保护。
8. 建立统一介绍页，移除功能页散落的重复说明。
9. 专业化改造总览、MACD、多因子雷达和 MACD 研究 UI。
10. 按统一协议持续增加与验证新因子。

<a id="project-blueprint-zh-10-变更纪律"></a>
## 10. 变更纪律

- 不重新设计已验证的 MACD 核心逻辑，除非有明确的新实验规格。
- 不覆盖用户或其他任务的未提交成果。
- 产品方向变更要同步更新本文件与决策日志。
- 实验结果变更要同步更新研究账本与页面。
- 页面删减前先确认相关检测器是否仍被因子库、回测或每日扫描使用。

<a id="project-blueprint-zh-11-已确认的研究背景"></a>
## 11. 已确认的研究背景

后续开发必须继承以下上下文，不得把项目当作空白项目重新开始：

- 数据目标覆盖 2000 年至当前，并尽量包含退市股票；退市身份只用于覆盖审计，不参与信号筛选。
- 股票进入形态研究前，应满足长期上涨或至少横盘：当前价格不能明显破坏长期均线，长期均线自身不能持续大幅向下。
- 主要日线基准是长期趋势合格后的日线 MACD 金叉；短期主要看 20 个交易日，长期主要看 100 个交易日。
- 周线与月线研究只能使用当时已经完成的周期 K 线。月线金叉在 3—6 个月观察中比周线更值得继续研究，但不能和日线 20 日结论混为一谈。
- 已测试的双底、趋势线三推、RSI 底背离、Doji、Bullish Engulfing、K 线聚集区、Volume Profile 近似筹码峰、双重筹码确认和 Fibonacci 0.5 等简单附加条件，尚未形成跨时期稳定加分；失败结果必须继续展示。
- 用户定义的筹码密集区域既包括大量 K 线聚集，也包括 Volume Profile 成交量峰。日 K 成交量只能近似真实 Volume Profile，不能冒充逐笔筹码分布。
- 用户定义的 Golden Pocket 来自已经确认的 swing low 到后续 swing high，重点关注 0.5、0.618/0.6182 回撤区域。
- 当前六项多因子评分只是第一轮实验，不是最终模型。5 分以上机会可作为稀有人工复查提醒，但样本不足，不能宣传为已验证高胜率。
- 旧 Rare Radar `historical_examples` 只属于 historical backtest/case review；真实生产提醒统一进入 Signal History，同时保留成功、失败、离榜、unavailable 与 pending，并展示触发日期、下一日开盘、当时证据和已经到期的 forward 结果。
- 所有回测按完整收盘确认、下一交易日复权开盘进入；不得用未来价格选择因子，不得只展示有利案例。

<a id="project-blueprint-zh-12-接下来三条工作主线"></a>
## 12. 接下来三条工作主线

后续工作按三个相互配合但可以独立验收的工作流推进：

<a id="project-blueprint-zh-a-ui-专业化与项目瘦身"></a>
### A. UI 专业化与项目瘦身

- 先审计依赖，再移除双指标确认、RSI、成交量等旧独立页面和只为它们服务的重复展示代码。
- 保留四个主入口，并建立统一项目介绍/使用方法页。
- 清除功能页中散落、重复的 tips 和长篇说明；研究细节归入折叠区或研究页。
- 先完成信息架构，再统一视觉系统；不得只换颜色而不解决信息杂乱。

实施进度（2026-08-25）：第一批信息架构已完成。四项主导航和统一功能介绍页已经落地，总览首屏已开始按日期、机会、理由和风险组织。三个旧指标页暂时保留 URL 作为迁移保护，待统一因子库完成字段迁移和并行验证后再删除页面与专属样式。

<a id="project-blueprint-zh-b-统一因子库与动态雷达"></a>
### B. 统一因子库与动态雷达

权威现状、27 项 inventory、Active Monitoring 定义、Tracker/Research 边界与最小迁移规格见 `docs/FACTOR_ARCHITECTURE.md`。注册表是研究目录而不是生产活跃清单；研究状态、运行状态和计分角色必须分开，Technical Tracker 在迁移共享 primitive 时保持既有排名契约。

Core migration（2026-08-26）：首批 8 个 canonical detectors、包含 hit/non-hit 与 factor version 的 deterministic daily snapshot、以及 Rare Radar snapshot consumer 已落地。它们是 shadow monitoring，不修改 Tracker ranking、official score、UI 或 Discord。Snapshot 已加入正常 daily workflow 的生成、验证、持久化、提交和 live verification contract；真实 operational activation 由持有 EODHD secret 的 GitHub Actions 运行确认。旧 multi-factor scoring 相关研究只在创建新 experiment version 后重跑，历史结果不得覆盖。

27-factor monitoring expansion（2026-08-26）：采用 **MONITOR BROADLY, SCORE CONSERVATIVELY**。Snapshot 现在固定覆盖 27 个注册 ID，其中 25 项 objective monitored、2 项 `definition_required`；event factors 保存 recent hit 日期与 session age。实验观察分分为 Core 2、谨慎 Auxiliary 1、Display-only 0，并按 redundancy group 取最大贡献；official score 仍为 0，Rare/Discord 兼容门槛与 Technical Tracker ranking 均不变。

- 设计因子注册表、证据家族、状态、版本、结果和权重接口。
- 迁移现有检测能力，先保留旧结果，再逐步增加新因子。
- 雷达动态显示约 20 个因子的分类得分、正式分、观察分和风险扣分。
- 每批新增因子先回测、记录，再决定是否进入正式评分。

实施进度（2026-08-25）：统一因子注册表 v0.1.0 已建立，首批登记25个因子。现有六因子已映射到稳定ID并继续只计观察分；雷达输出已预留正式分、观察分、风险扣分、分类得分、重要未命中和冲突/风险接口。下一步是让 Tracker 与研究管线逐步改为消费同一注册表，并为每个因子补齐结构化开发期、验证期和前向期结果。

实施进度（2026-08-25，第二批）：注册表升级至 v0.2.0，共登记26个因子。新增“三推突破后回踩确认”观察因子：只在三推下降趋势线突破后的10个交易日内、价格触及投射趋势线附近并收盘守住时命中；它与三推突破强绑定，不能脱离父因子单独加分。动态组合不要求凑满固定数量，候选因子可按命中自由叠加，但依赖关系、重复组和正式/观察状态必须继续受注册表约束。雷达 UI 已增加可复查的统一因子库板块。

<a id="project-blueprint-zh-c-discord-日终播报"></a>
### C. Discord 日终播报

- 读取与网页相同的动态雷达输出，不维护第二套评分逻辑。
- 网站成功更新后才播报；无信号保持安静；同一信号去重。
- 播报必须包含可复查证据、风险和网站链接，并明确不是自动买入。
- 接入前确认使用 Discord Webhook 还是 Bot，以及目标服务器/频道；密钥只能放在安全的运行环境中，不能写入仓库。

实施进度（2026-08-25）：已选择第一版使用 Discord Webhook，并建立可替换模板的同源通知入口。5分或以上雷达机会优先，随后为每日 MACD 看涨／看跌榜；日期、防前视、发布顺序和去重均为失败关闭。正式密钥保存在 GitHub Repository Secrets，本地 `.env.local` 只用于人工运行，二者都不得进入代码、日志或提交。

自动化升级（2026-08-27）：新增 Early Watch／Confirmed 两级状态。GitHub Actions 负责 EODHD 更新、测试、生产构建、JSON 提交、Cloudflare Worker 发布、整组 live verification 与 Discord 去重发送。Cloudflare Worker 是唯一 production；旧 ChatGPT Sites 与独立 deployment-attestation/notify 路径已退出生产。任何前置环节失败都不发送 Discord。

三个工作流的推荐顺序是：先做 UI 与依赖审计，同时设计因子注册表；再改造动态雷达；最后让 Discord 使用稳定的雷达输出。每日 MACD 与现有多因子扫描在整个改造期间不得中断。

---

<a id="tracker-product-requirements-zh"></a>

## 原文件：TRACKER_PRODUCT_REQUIREMENTS_ZH.md

<a id="tracker-product-requirements-zh-sage-vista-tracker-产品需求文档"></a>
# Sage Vista Tracker 产品需求文档

版本：v1.0（历史阶段需求，保留作参考）
目标：把现有指标雷达发展为可信、可复核、可持续回测的交易研究助手，而不是自动荐股或自动下单系统。

> 2026-08-25 更新：当前产品入口、统一因子库、动态评分、Discord 与 UI 方向以 [`PROJECT_BLUEPRINT_ZH.md`](product-history.md#project-blueprint-zh) 为准。本文件保留早期需求背景；其中 RSI、背离、成交量等能力继续作为因子保留，但不再要求拥有独立功能页。

<a id="tracker-product-requirements-zh-一当前能力"></a>
## 一、当前能力

- 每日收盘后扫描约 1,000 只以上流动性合格的美国股票。
- MACD 日线、周线、月线状态与“小周期带动大周期”识别。
- RSI 超卖、修复和新鲜底背离识别。
- 成交量异动与底部放量提示。
- MACD 与 RSI 双指标确认候选。
- 股指、指数 ETF、BTC、ETH 日线数据可用；1小时和实时数据暂无权限。

<a id="tracker-product-requirements-zh-二建议现在加入p0"></a>
## 二、建议现在加入（P0）

<a id="tracker-product-requirements-zh-1-信号生命周期"></a>
### 1. 信号生命周期

显示“正在形成、收盘确认、确认后第几根K线、已过期、已失效”。
价值：减少旧金叉、盘中假信号和追高误判。
建议：加入。

<a id="tracker-product-requirements-zh-2-市场环境过滤在etf温度计实现"></a>
### 2. 市场环境过滤（在“ETF温度计”实现）

使用 SPY、QQQ、IWM、DIA 及主要指数判断风险偏好、趋势和大小盘风格。
价值：大盘弱势时降低个股多头信号权重。
建议：加入。

产品决定：不在指标共振页面复制一套市场面板。市场判断集中在“ETF温度计”，指标共振只保留轻量入口，避免网站臃肿。

<a id="tracker-product-requirements-zh-3-价格结构确认作为macd的可选确认层"></a>
### 3. 价格结构确认（作为MACD的可选确认层）

检查支撑阻力、更高低点、趋势线、突破与回踩。
价值：避免指标向上但价格结构仍在下跌。
建议：加入。

产品决定：MACD页面增加图例和“只看价格结构确认”复选框。价格结构不修改MACD原始信号，只作为附加筛选。

<a id="tracker-product-requirements-zh-4-可复核证据"></a>
### 4. 可复核证据

每只候选展示实际触发周期、MACD线/信号线、RSI低点、成交量倍数和失效条件。
价值：用户能够人工验证，不依赖黑箱分数。
建议：加入。

<a id="tracker-product-requirements-zh-三建议下一阶段加入p1"></a>
## 三、建议下一阶段加入（P1）

<a id="tracker-product-requirements-zh-5-组合信号回测"></a>
### 5. 组合信号回测

分别测试 MACD、RSI、成交量及其组合，并加入市场环境过滤。
输出：样本数、胜率、平均收益、最大回撤、持有5/10/20日表现、交易成本敏感度。
建议：加入，是决定权重的依据。

<a id="tracker-product-requirements-zh-6-风险与交易计划"></a>
### 6. 风险与交易计划

输出候选入场条件、结构止损、目标区、收益风险比、仓位和最多持有K线数。
前提：信号先通过回测和前向观察。
建议：在回测之后加入。

<a id="tracker-product-requirements-zh-7-股指环境页"></a>
### 7. 股指环境页

独立展示 SPY、QQQ、IWM、DIA、标普500、纳斯达克和道琼斯的趋势、动能与市场宽度。
建议：加入。

<a id="tracker-product-requirements-zh-8-加密货币日线-tracker"></a>
### 8. 加密货币日线 Tracker

先支持 BTC、ETH 的日线、周线、月线；参数和股票分开校准。
建议：可加入，但优先级低于股票回测。

<a id="tracker-product-requirements-zh-四暂不建议加入p2"></a>
## 四、暂不建议加入（P2）

<a id="tracker-product-requirements-zh-9-4小时和实时提醒"></a>
### 9. 4小时和实时提醒

当前数据权限不支持1小时接口，无法可靠合成4小时K线。
建议：升级盘中数据后再做。

<a id="tracker-product-requirements-zh-10-自动下单"></a>
### 10. 自动下单

当前策略尚未完成大样本走样本外回测与长期前向验证。
建议：暂不加入。

<a id="tracker-product-requirements-zh-11-过多技术指标"></a>
### 11. 过多技术指标

暂不同时增加随机指标、CCI、Williams %R 等高度相关指标。
原因：容易重复计算同一种动能信息，造成虚假“多指标共振”。

<a id="tracker-product-requirements-zh-12-机器学习自动调参"></a>
### 12. 机器学习自动调参

在标签、交易成本、样本外验证和数据防泄漏没有稳定前，机器学习容易过拟合。
建议：基础研究管线成熟后再评估。

<a id="tracker-product-requirements-zh-五验收标准"></a>
## 五、验收标准

- 所有信号只使用当时可获得的数据。
- 收盘信号不得按当日收盘价成交，回测使用下一交易日开盘。
- 旧金叉、死叉和过期底背离不得进入当前组合榜。
- 每个组合候选必须展示可人工复核的证据。
- 每个策略组合必须报告样本量与样本外结果，不能只报告胜率。
- 放量下跌不得直接标记为买入信号。
- 没有新收盘数据时不得重复发布旧结果。

<a id="tracker-product-requirements-zh-六建议实施顺序"></a>
## 六、建议实施顺序

1. 信号生命周期和失效条件。
2. 股指/ETF市场环境过滤。
3. 价格结构确认。
4. 组合信号走样本外回测。
5. 风险与交易计划。
6. BTC、ETH独立日线Tracker。
7. 获得盘中权限后再开发4小时和实时提醒。
