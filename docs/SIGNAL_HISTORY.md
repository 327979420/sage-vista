# Signal History / Forward Observation

状态：生产架构权威说明  
版本：1.1.0
最后更新：2026-08-27

## Purpose and system boundary

Sage Vista 永久区分三类数据：

1. **Current Opportunities**：今天值得看什么；来自 Technical Tracker 和 Multi-Factor Radar。
2. **Production Forward Observation**：系统当时真实展示过什么，以及之后实际发生什么；权威数据是 `public/signal-history.json`。
3. **Historical Backtest / Case Review**：在受控历史实验中重建的信号；只属于 research，不得进入生产 forward aggregates。

Industry Radar 不独立创建股票案例，只冻结为信号发生时的上下文。Signal History 不修改 Technical Tracker ranking、factor score/weight、Industry state 或 Discord threshold。

## Case creation and identity

- Technical source：直接消费既有 `macd_buy_top10` 顺序，不重排。
- Multi-Factor source：消费当日 `rare-opportunity-radar.json.signals`。
- 同一 ticker 同一信号周期只有一个 stock case；两套系统同日出现时写入一个 case 的多个 `source_systems`。
- 普通信号沿用 `signal_id = SVP1-{symbol}-{first_seen_date}`，数组位置不是身份。
- 若旧版“我最喜欢形态”因定义修正而被永久保留、同一标的同日又通过新版规则，新记录使用 `SVP1-{symbol}-{first_seen_date}-FP-{pattern_version}` 的版本隔离编号。旧记录不覆盖，新记录不冒充旧定义。
- 连续出现只更新 `last_seen_date`、`days_active`、current status；原始 snapshot 不变。
- 完全离榜后累计 **5 个已完成生产会话** 才视为 reset；之后重入建立新 case。此前重入属于同一周期。
- 案例离榜、亏损、持平、数据不可用或仍 pending 都永久保留。

## Immutable signal-time evidence

创建时冻结：Tracker rank/score/setup、完整 27-factor states、正式与实验观察分、贡献、non-scoring evidence、risks，以及当时可用的 context 与版本。后续更新不得用新定义回写这部分。当前生产入池继续服从旧生产评分门槛；27-factor experimental score 只 shadow observation，直到新 signal definition 经验证后正式替换。

每个案例另有 append-only `daily_states`：按交易日保存价格、是否仍在 Current、旧生产分、正式分、27-factor 实验观察分和因子 `ACTIVE / RECENT / EXPIRED / NEVER / UNAVAILABLE` 状态。第一阶段不把 Industry/Market 写入逐日状态；两个 context 模块完成优化后再以新 schema version 接入。

V2/V3 必须创建新 `product_version` / `signal_definition_version`；V1 case 永远保留 V1。未来实验可以只读取版本、Industry state、market regime 和 frozen factor states，不改变生产记录。

## Lifecycle and forward outcomes

最小生命周期为 `NEW → ACTIVE → MONITORING → MATURED`。是否仍在今日榜单由 `latest_current_status` 独立表达；case existence 与 current opportunity status 不相同。

执行约定沿用项目标准：完整收盘确认信号，**下一交易日复权开盘价**作为 forward entry。只在真实未来 session 已经存在时更新：`+1D/+5D/+10D/+20D/+60D/+100D`。MFE/MAE 从 entry 起，只使用截至当前 `as_of` 已完成的 future rows。

新 case 的 entry、returns、MFE、MAE 都为 pending。即使本地历史 cache 含更晚数据，loader 也必须先裁切到 production `as_of`；20D 必须等满 20 个 entry sessions，100D 同理。顶层和每个 case 都要求 `future_data_used=false`。

## Production safety

Daily EOD 在 Tracker、27-factor snapshot、Rare Radar、Industry Radar 成功后执行 recorder，再在临时目录完成 schema/date/leakage/unique-ID 验证。六份 production JSON 与 status 最后才原子替换。Signal History 更新失败会 fail-close 整次发布：继续展示上一份已验证站点优于发布无法追溯或跨文件日期混合的数据。

Cloudflare live verification 和独立 freshness monitor 都检查 `signal_history_as_of`。UI 使用 `cache: no-store`，在 Multi-Factor 页面展示“历史提醒 / Forward Observation”，可按 Current/Matured、来源、信号时 Industry state、版本筛选。Backtest 页面继续明确标注 research-only，不与生产样本合并。

## Reusable boundary

唯一新共享 primitive 是 `services/scanner/signal_history.py` 的生产 recorder/outcome updater。`macd_factor_backtest.py` 与 research pipeline 保留各自受控实验统计；它们可以共享数学约定，但 production history 不读取 backtest JSON，也不再由 Rare Radar 的历史样例或 previous-JSON fallback 构造。
