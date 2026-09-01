# M04｜统一因子事实与 TechnicalEvidence 本地验收报告

- CR：`CR-2026-09-01-044`
- 分支：`m04/technical-evidence-547949b`
- 基线：`547949bad8c3447aeeb7665723ed49178f8050f2`
- 状态：`implemented`（获批影子范围已进入`main`）
- 生产状态：未部署、未启用

## 1. 结论

M04获批范围已完成本地实现：M02不可变点时行情与M03 `GateEvent 2.x`可以通过唯一`services/factors/`生产器生成不可变、无评分的`TechnicalEvidence 2.x`。每日和回放影子入口调用同一函数；当前生产入口和结果保持原样。

## 2. 已完成

- 新增唯一`TechnicalEvidence 2.x`生产器及批次身份。
- formal证据绑定GateEvent、instrument、Universe、行情快照、M02复权政策、注册表和检测政策。
- `macd.daily_bull_cross`与`qualification.long_trend`直接引用GateEvent事实。
- 其余因子复用现有唯一检测函数；固定样本逐项对照无差异。
- 每个注册表因子恰好生成一条证据，数量从注册表动态读取。
- 父子依赖分开保存`raw_hit`、`qualified_hit`和`blocked_by`，没有加入分数。
- 同一身份重放确定；内容篡改、身份篡改、重复或缺失因子均失败关闭。
- 旧快照只经一个适配器生成明确legacy 1.x视图，不补造formal身份，不改写源文件。
- 日终和回放只新增影子调用函数，没有接入默认任务。

## 3. 三个可人工检查的例子

1. `macd.daily_bull_cross`：证据的`source_kind=gate_reference`，其基线检查和`gate_event_id`直接来自M03，不在M04重新判断当前门票。
2. 普通检测因子：`available`、原始命中、最近命中日期、值和证据与旧`evaluate_all_factors`固定样本逐项相同；M04只增加身份和依赖解释。
3. 旧2026-08-28快照：所有已保存逐股因子可转换为带偏差标签的legacy视图；转换前后`public/daily-factor-snapshot.json`字节完全相同，不能进入formal 2.x入口。

## 4. 验证证据

- M04专项：14项通过。
- M01—M04定向：101项通过。
- 完整Python：474项通过。
- `PYTHONHASHSEED=0/1/42/12345`：每轮M04专项14项通过。
- Python编译：通过。
- 前端lint、TypeScript、生产构建：通过。
- 前端测试：11项通过。
- 补丁格式：通过。
- 测试前后只有本次批准范围内的文件变化，没有测试生成的意外文件。

## 5. 明确未改变

- 没有修改因子ID、定义、阈值、注册表数量或研究状态。
- 没有修改MACD门票、GateEvent、股票池或行情事实。
- 没有计算或修改评分、权重、排行榜、精选门槛或交易计划。
- 没有修改`public/`、`automation/`、工作流、网站或Discord。
- 没有访问EODHD、运行真实每日任务或真实历史回测。
- 没有实现M05以后模块或M12生产集成。

## 6. 合并与尚未完成

- 三个提交为`46c5256`、`2fabbdc`、`545a411`，审核分支保留。
- 独立审核未发现可复现阻断缺陷；审核分支以纯fast-forward进入`main`，没有产生额外合并提交。
- 尚未部署或让生产消费者读取M04证据。
- 生产切换及真实发布证据仍属于M12。

因此本报告支持M04获批影子范围为`implemented`，但不能宣称已经部署或生产启用。
